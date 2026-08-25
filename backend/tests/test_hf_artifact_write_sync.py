from types import SimpleNamespace
from unittest.mock import Mock

from backend.services import external_resource_service, paper_association_service
from backend.services.external_resource_service import ExternalResourceService
from backend.services.hf_artifact_service import (
    collect_explicit_hf_artifacts,
    sync_explicit_hf_artifact_links,
)
from backend.services.paper_association_service import PaperAssociationService


class _Query:
    def __init__(self, paper):
        self.paper = paper

    def filter(self, *args):
        return self

    def first(self):
        return self.paper


def test_collect_explicit_hf_artifacts_normalizes_and_deduplicates():
    artifacts = collect_explicit_hf_artifacts(
        [
            "https://huggingface.co/moonshotai/Kimi-K3",
            "https://huggingface.co/moonshotai/Kimi-K3",
        ],
        ["https://huggingface.co/datasets/org/data"],
        ["https://huggingface.co/spaces/org/demo"],
    )

    assert [(a.kind, a.repo_id) for a in artifacts] == [
        ("model", "moonshotai/Kimi-K3"),
        ("dataset", "org/data"),
        ("space", "org/demo"),
    ]


def test_sync_explicit_hf_artifact_links_upserts_and_links():
    session = Mock()
    artifact_result = Mock()
    artifact_result.scalar_one.return_value = 9
    link_result = Mock(rowcount=1)
    session.execute.side_effect = [artifact_result, link_result]

    result = sync_explicit_hf_artifact_links(
        session,
        104054,
        ["https://huggingface.co/moonshotai/Kimi-K3"],
        [],
        [],
    )

    assert result == {"artifacts": 1, "links_added": 1}
    artifact_sql = str(session.execute.call_args_list[0].args[0])
    link_sql = str(session.execute.call_args_list[1].args[0])
    assert "INSERT INTO hf_artifacts" in artifact_sql
    assert "INSERT INTO paper_hf_artifacts" in link_sql
    assert session.execute.call_args_list[1].args[1] == {
        "paper_id": 104054,
        "artifact_id": 9,
    }


def test_paper_association_service_syncs_links_and_invalidates_checkpoint(monkeypatch):
    paper = SimpleNamespace(
        id=104054,
        hf_models=None,
        hf_datasets=None,
        hf_spaces=None,
        hf_artifacts_scanned_at="stale",
    )
    db = Mock()
    db.query.return_value = _Query(paper)
    sync = Mock()
    monkeypatch.setattr(
        paper_association_service, "sync_explicit_hf_artifact_links", sync
    )
    service = PaperAssociationService(db, Mock(return_value="paper"))

    result = service.update_hf_artifacts(
        104054,
        ["https://huggingface.co/moonshotai/Kimi-K3"],
        [],
        [],
    )

    assert result == "paper"
    assert paper.hf_artifacts_scanned_at is None
    sync.assert_called_once_with(
        db,
        104054,
        ["https://huggingface.co/moonshotai/Kimi-K3"],
        None,
        None,
    )
    db.commit.assert_called_once_with()


def test_external_ingestion_syncs_links_and_invalidates_checkpoint(monkeypatch):
    paper = SimpleNamespace(
        id=104054,
        hf_models=None,
        hf_datasets=None,
        hf_spaces=None,
        hf_artifacts_scanned_at="stale",
    )
    db = Mock()
    db.query.return_value = _Query(paper)
    sync = Mock()
    monkeypatch.setattr(
        external_resource_service,
        "sync_explicit_hf_artifact_links",
        sync,
    )

    result = ExternalResourceService(db)._set_hf_artifacts(
        104054,
        ["https://huggingface.co/moonshotai/Kimi-K3"],
    )

    assert result["models_added"] == 1
    assert paper.hf_artifacts_scanned_at is None
    sync.assert_called_once_with(
        db,
        104054,
        ["https://huggingface.co/moonshotai/Kimi-K3"],
        None,
        None,
    )
