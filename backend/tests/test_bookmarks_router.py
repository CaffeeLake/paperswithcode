from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.models.database import Paper as DBPaper
from backend.models.database import UserBookmark
from backend.routers import bookmarks
from backend.services import bookmark_service
from backend.services.bookmark_service import BookmarkReadService, BookmarkRefListing
from backend.services.paper_bucket_service import PaperBucketError
from backend.services.saved_papers_bucket_service import SavedPaperRef


class LegacyBookmarkQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.rows


class LegacyBookmarkDb:
    def __init__(self, rows):
        self.rows = rows
        self.query_calls = 0

    def query(self, *_args):
        self.query_calls += 1
        return LegacyBookmarkQuery(self.rows)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/me/bookmarks/ids",
            "headers": [],
            "query_string": b"",
            "scheme": "https",
            "server": ("paperswithcode.co", 443),
            "client": ("127.0.0.1", 1234),
        }
    )


def test_bookmark_reads_keep_legacy_data_visible_without_bucket_authorization():
    saved_at = datetime.now(UTC)
    db = LegacyBookmarkDb([(42, saved_at, "Existing saved paper", "2601.00042", None)])

    listing = BookmarkReadService(db).list_refs(
        encrypted_credential=None,
        hf_user_id="hf-alice",
        username="alice",
    )

    assert listing.bucket_connected is False
    assert [item.paper_id for item in listing.refs] == [42]
    assert listing.refs[0].title == "Existing saved paper"
    assert db.query_calls == 1


def test_connected_bucket_read_keeps_eager_legacy_query(monkeypatch):
    saved_at = datetime.now(UTC)
    db = LegacyBookmarkDb([(42, saved_at, "Legacy paper", None, None)])
    initialized = []

    class ConnectedBucket:
        def __init__(self, *, token, username):
            assert token == "bucket-token"
            assert username == "alice"

        def initialize(self, load_legacy):
            initialized.append(load_legacy)

        def list(self):
            return [SavedPaperRef(paper_id=84, saved_at=saved_at)]

    monkeypatch.setattr(
        bookmark_service,
        "decrypt_oauth_credential",
        lambda *_args: SimpleNamespace(token="bucket-token"),
    )
    monkeypatch.setattr(bookmark_service, "SavedPapersBucket", ConnectedBucket)

    listing = BookmarkReadService(db).list_refs(
        encrypted_credential="encrypted",
        hf_user_id="hf-alice",
        username="alice",
    )

    assert [item.paper_id for item in listing.refs] == [84]
    assert listing.bucket_connected is True
    assert len(initialized) == 1
    assert db.query_calls == 1


def test_first_bucket_migration_loads_legacy_refs_again(monkeypatch):
    saved_at = datetime.now(UTC)
    db = LegacyBookmarkDb([(42, saved_at, "Legacy paper", None, None)])

    class MigratingBucket:
        def __init__(self, **_kwargs):
            self.migrated = []

        def initialize(self, load_legacy):
            self.migrated = load_legacy()

        def list(self):
            return self.migrated

    monkeypatch.setattr(
        bookmark_service,
        "decrypt_oauth_credential",
        lambda *_args: SimpleNamespace(token="bucket-token"),
    )
    monkeypatch.setattr(bookmark_service, "SavedPapersBucket", MigratingBucket)

    listing = BookmarkReadService(db).list_refs(
        encrypted_credential="encrypted",
        hf_user_id="hf-alice",
        username="alice",
    )

    assert [item.paper_id for item in listing.refs] == [42]
    assert listing.bucket_connected is True
    assert db.query_calls == 2


def test_bucket_read_failure_falls_back_to_eager_legacy_refs(monkeypatch):
    saved_at = datetime.now(UTC)
    db = LegacyBookmarkDb([(42, saved_at, "Legacy paper", None, None)])

    class FailingBucket:
        def __init__(self, **_kwargs):
            pass

        def initialize(self, _load_legacy):
            pass

        def list(self):
            raise PaperBucketError("Bucket unavailable")

    monkeypatch.setattr(
        bookmark_service,
        "decrypt_oauth_credential",
        lambda *_args: SimpleNamespace(token="bucket-token"),
    )
    monkeypatch.setattr(bookmark_service, "SavedPapersBucket", FailingBucket)

    listing = BookmarkReadService(db).list_refs(
        encrypted_credential="encrypted",
        hf_user_id="hf-alice",
        username="alice",
    )

    assert [item.paper_id for item in listing.refs] == [42]
    assert listing.bucket_connected is False
    assert db.query_calls == 1


class BookmarkListingQuery:
    def __init__(self, papers):
        self.papers = papers

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.papers


class BookmarkListingRows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class BookmarkListingDb:
    def __init__(self, papers, primary_rows):
        self.papers = papers
        self.primary_rows = primary_rows
        self.primary_params = None
        self.paper_query_calls = 0
        self.primary_query_calls = 0

    def query(self, entity):
        assert entity is DBPaper
        self.paper_query_calls += 1
        return BookmarkListingQuery(self.papers)

    def execute(self, _statement, params):
        self.primary_query_calls += 1
        self.primary_params = params
        return BookmarkListingRows(self.primary_rows)


def test_bookmark_groups_preserve_first_seen_order_and_use_card_hydration(monkeypatch):
    papers = [
        SimpleNamespace(id=paper_id, title=f"Paper {paper_id}")
        for paper_id in (10, 20, 30, 40, 50)
    ]
    db = BookmarkListingDb(
        papers,
        primary_rows=[
            (40, 11, "classification", "Classification", 1, "Vision"),
            (20, 21, "unscoped", "Unscoped", None, None),
            (30, 12, "segmentation", "Segmentation", 1, "Vision"),
            (50, 12, "segmentation", "Segmentation", 1, "Vision"),
        ],
    )
    bookmark_ids = [60, 50, 40, 30, 20, 10]
    monkeypatch.setattr(
        BookmarkReadService,
        "list_refs",
        lambda *_args, **_kwargs: BookmarkRefListing(
            refs=tuple(
                SavedPaperRef(paper_id=paper_id, saved_at=datetime.now(UTC))
                for paper_id in bookmark_ids
            ),
            bucket_connected=True,
        ),
    )
    hydrate_calls = []

    class HydratingPaperService:
        def __init__(self, service_db):
            assert service_db is db

        def hydrate_cards(self, db_papers, *, include_resources):
            hydrate_calls.append(([paper.id for paper in db_papers], include_resources))
            return [
                bookmark_service.ApiPaper(
                    id=str(paper.id),
                    title=paper.title,
                    authors=[],
                )
                for paper in db_papers
            ]

    monkeypatch.setattr(bookmark_service, "PaperService", HydratingPaperService)

    response = bookmarks.get_my_bookmarks(
        _request(),
        {"username": "alice", "hf_user_id": "hf-alice"},
        db,
    )

    assert hydrate_calls == [([50, 40, 30, 20, 10], False)]
    assert db.primary_params == {"paper_ids": bookmark_ids}
    assert db.paper_query_calls == 1
    assert db.primary_query_calls == 1
    assert response.count == 5
    assert response.bucket_connected is True
    assert [
        (
            area.id,
            area.name,
            [
                (
                    task.id,
                    task.slug,
                    task.name,
                    [paper.id for paper in task.papers],
                )
                for task in area.tasks
            ],
        )
        for area in response.areas
    ] == [
        (
            1,
            "Vision",
            [
                (12, "segmentation", "Segmentation", ["50", "30"]),
                (11, "classification", "Classification", ["40"]),
            ],
        ),
        (
            None,
            "Other",
            [
                (21, "unscoped", "Unscoped", ["20"]),
                (None, None, "Untagged", ["10"]),
            ],
        ),
    ]


def test_empty_bookmark_listing_skips_paper_projection(monkeypatch):
    class NoProjectionDb:
        def query(self, *_args):
            raise AssertionError("empty bookmark reads must not query papers")

        def execute(self, *_args):
            raise AssertionError("empty bookmark reads must not query tasks")

    monkeypatch.setattr(
        BookmarkReadService,
        "list_refs",
        lambda *_args, **_kwargs: BookmarkRefListing((), True),
    )

    result = BookmarkReadService(NoProjectionDb()).list_grouped(
        encrypted_credential=None,
        hf_user_id="hf-alice",
        username="alice",
    )

    assert result.count == 0
    assert result.areas == ()
    assert result.bucket_connected is True


def test_bookmark_mutations_request_bucket_authorization_dynamically():
    db = LegacyBookmarkDb([])
    user = {"username": "alice", "hf_user_id": "hf-alice"}

    with pytest.raises(HTTPException) as exc_info:
        bookmarks._require_bucket_store(_request(), user, db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == (
        "saved_papers_bucket_authorization_required"
    )


class MutationQuery:
    def __init__(self, *, first_result=None):
        self.first_result = first_result
        self.deleted = False

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.first_result

    def delete(self, *, synchronize_session):
        assert synchronize_session is False
        self.deleted = True


class MutationDb:
    def __init__(self):
        self.paper_query = MutationQuery(
            first_result=SimpleNamespace(
                title="New paper", arxiv_id="2601.00042", source_url=None
            )
        )
        self.bookmark_query = MutationQuery()
        self.added = []
        self.commits = 0

    def query(self, entity):
        return self.paper_query if entity is DBPaper else self.bookmark_query

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commits += 1


class FakeBucketStore:
    def __init__(self):
        self.added = []
        self.removed = []

    def add(self, paper_id, **metadata):
        self.added.append((paper_id, metadata))

    def remove(self, paper_id):
        self.removed.append(paper_id)


def test_bucket_mutations_keep_database_fallback_in_sync(monkeypatch):
    db = MutationDb()
    store = FakeBucketStore()
    user = {"username": "alice", "hf_user_id": "hf-alice"}
    monkeypatch.setattr(bookmarks, "_require_bucket_store", lambda *_args: store)

    bookmarks.add_bookmark(_request(), 42, user, db)

    assert store.added[0][0] == 42
    assert len(db.added) == 1
    assert isinstance(db.added[0], UserBookmark)
    assert db.added[0].paper_id == 42
    assert db.commits == 1

    bookmarks.remove_bookmark(_request(), 42, user, db)

    assert store.removed == [42]
    assert db.bookmark_query.deleted is True
    assert db.commits == 2
