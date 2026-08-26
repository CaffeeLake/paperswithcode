import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.api import ApplyMutationRequest, ResolveModelPaperMutation
from backend.models.database import (
    Base,
    Evaluation,
    HfArtifact,
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseArtifact,
    Paper,
    PaperAuthor,
    PaperConference,
    PaperCurationJob,
    PaperCurationWorkflow,
    PaperDataset,
    PaperHfArtifact,
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
    PaperOrganization,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    ProjectPage,
    TrendingModelCandidate,
    TrendingModelCurationState,
)
from backend.services.codex_add_evals_service import (
    CodexPaperJob,
    CodexPaperJobService,
    _curator_skill_digest,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)
from backend.services.hf_trending_model_curation_service import (
    HFTrendingModelCurationService,
)
from backend.services.hf_trending_model_discovery_service import (
    HFModelCardClient,
    HFModelCardSnapshot,
    HFTrendingDiscoveryClient,
    HFTrendingModel,
    is_obvious_conversion,
    should_requeue_card,
)
from backend.services.trending_model_resolution_service import (
    TrendingModelResolutionService,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def test_discovery_uses_hf_cli_global_top_fifty():
    calls = []

    def run(command):
        calls.append(command)
        return json.dumps(
            [
                {
                    "id": "Qwen/Qwen3.8-Flash-Next",
                    "author": "Qwen",
                    "tags": ["transformers", "safetensors", "eval-results"],
                    "created_at": "2026-08-25T00:00:00+00:00",
                    "last_modified": "2026-08-26T00:00:00+00:00",
                    "trending_score": 999,
                }
            ]
        )

    models = HFTrendingDiscoveryClient(run=run, hf_cli="hf").list_top_models()

    assert calls == [
        [
            "hf",
            "models",
            "list",
            "--sort",
            "trending_score",
            "--limit",
            "50",
            "--expand",
            "author,tags,createdAt,lastModified,trendingScore",
            "--format",
            "json",
        ]
    ]
    assert models[0].repo_id == "Qwen/Qwen3.8-Flash-Next"
    assert models[0].featured_publisher is True


def test_discovery_prefers_hf_cli_from_running_virtualenv(tmp_path, monkeypatch):
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    hf = python.with_name("hf")
    hf.touch(mode=0o755)
    monkeypatch.setattr("sys.executable", str(python))
    calls = []

    def run(command):
        calls.append(command)
        return "[]"

    HFTrendingDiscoveryClient(run=run).list_top_models(limit=1)

    assert calls[0][0] == str(hf)


def test_non_featured_original_release_is_not_deterministically_rejected():
    model = HFTrendingModel.from_payload(
        {
            "id": "ornith-ai/Ornith-1.5-35B-A3B",
            "author": "ornith-ai",
            "tags": ["transformers", "safetensors", "eval-results"],
            "trending_score": 425,
        }
    )

    assert model.featured_publisher is False
    assert is_obvious_conversion(model) is False


def test_novel_finetune_is_left_for_model_judgment():
    model = HFTrendingModel.from_payload(
        {
            "id": "z-lab/Qwen3.8-27B-DFlash2",
            "author": "z-lab",
            "tags": [
                "transformers",
                "dflash2",
                "speculative-decoding",
                "base_model:Qwen/Qwen3.8-27B",
                "base_model:finetune:Qwen/Qwen3.8-27B",
            ],
            "trending_score": 145,
        }
    )

    assert is_obvious_conversion(model) is False


def test_quantized_or_format_only_derivative_is_rejected_before_llm():
    model = HFTrendingModel.from_payload(
        {
            "id": "community/Qwen3.8-27B-GGUF",
            "author": "community",
            "tags": [
                "gguf",
                "quantized",
                "base_model:Qwen/Qwen3.8-27B",
                "base_model:quantized:Qwen/Qwen3.8-27B",
            ],
            "trending_score": 500,
        }
    )

    assert is_obvious_conversion(model) is True


def test_card_is_requeued_only_when_its_content_hash_changes():
    assert should_requeue_card(previous_sha=None, current_sha="a") is True
    assert should_requeue_card(previous_sha="a", current_sha="a") is False
    assert should_requeue_card(previous_sha="a", current_sha="b") is True


def test_model_identity_schema_has_stable_unique_keys():
    release_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in ModelRelease.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    alias_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in ModelProviderAlias.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    artifact_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in ModelReleaseArtifact.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("paper_id", "canonical_name") in release_uniques
    assert ("provider", "alias") in alias_uniques
    assert ("model_release_id", "hf_artifact_id") in artifact_uniques
    assert TrendingModelCandidate.__table__.c.repo_id.unique is True


def test_model_card_snapshot_hashes_readme_not_noisy_repo_metadata(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Release\n\n| Benchmark | Score |\n| X | 42 |\n")
    calls = []

    def run(command):
        calls.append(command)
        if command[:3] == ["hf", "models", "info"]:
            return json.dumps({"sha": "repo-revision-1"})
        return str(readme)

    snapshot = HFModelCardClient(run=run, hf_cli="hf").snapshot("org/model")

    assert snapshot.repo_revision == "repo-revision-1"
    assert len(snapshot.readme_sha) == 64
    assert calls[1] == [
        "hf",
        "download",
        "org/model",
        "README.md",
        "--revision",
        "repo-revision-1",
        "--quiet",
    ]


def test_resolution_accepts_exactly_one_canonical_paper_identity():
    common = {
        "decision": "accept",
        "reason": "Official technical report for a newly trained model.",
        "novelty_kind": "new_weights",
        "evidence_urls": ["https://huggingface.co/org/model"],
        "model_release": {
            "canonical_name": "Model",
            "publisher": "org",
            "is_open": True,
            "aliases": ["org/model"],
        },
    }

    external = ResolveModelPaperMutation.model_validate(
        {
            **common,
            "external_paper": {
                "source_url": "https://github.com/org/model/blob/main/report.pdf",
                "title": "Model Technical Report",
                "abstract": "We introduce Model.",
                "date_published": "2026-08-26",
            },
        }
    )
    assert external.external_paper is not None

    with pytest.raises(ValidationError, match="exactly one paper identity"):
        ResolveModelPaperMutation.model_validate(
            {**common, "existing_paper_id": 1, "arxiv_id": "2608.12345"}
        )


def test_resolution_rejection_cannot_smuggle_a_paper_mutation():
    with pytest.raises(ValidationError, match="rejection cannot include"):
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "reject",
                "reason": "Pure GGUF conversion.",
                "novelty_kind": "repackaging",
                "evidence_urls": ["https://huggingface.co/community/model-GGUF"],
                "existing_paper_id": 1,
            }
        )


def _resolution_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            ModelProviderAlias.__table__,
            TrendingModelCandidate.__table__,
            ProjectPage.__table__,
            PaperAuthor.__table__,
            PaperTask.__table__,
            PaperMethod.__table__,
            PaperMethodEvidence.__table__,
            PaperMethodExclusion.__table__,
            PaperDataset.__table__,
            PaperRepository.__table__,
            PaperProjectPage.__table__,
            PaperConference.__table__,
            PaperOrganization.__table__,
            Evaluation.__table__,
        ],
    )
    return Session(engine)


def test_resolution_links_existing_paper_release_and_hf_artifact():
    db = _resolution_session()
    paper = Paper(
        title="Existing Report",
        source="external",
        source_url="https://example.com/report",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="a" * 64,
        status="resolving",
    )
    db.add_all([paper, candidate])
    db.commit()

    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "accept",
                "reason": "New weights with first-party benchmark results.",
                "novelty_kind": "new_weights",
                "evidence_urls": [
                    "https://huggingface.co/org/model",
                    "https://example.com/report",
                ],
                "existing_paper_id": paper.id,
                "model_release": {
                    "canonical_name": "Model",
                    "publisher": "org",
                    "is_open": True,
                    "aliases": ["org/model"],
                },
            }
        ),
    )

    assert result["paper_id"] == paper.id
    assert db.query(ModelRelease).one().canonical_name == "Model"
    assert db.query(HfArtifact).one().repo_id == "org/model"
    assert db.query(PaperHfArtifact).one().paper_id == paper.id
    assert db.get(TrendingModelCandidate, candidate.id).status == "resolved"


def test_resolution_rejects_existing_paper_without_canonical_source_evidence():
    db = _resolution_session()
    paper = Paper(
        title="Unrelated Paper",
        source="external",
        source_url="https://example.com/unrelated",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="f" * 64,
        status="resolving",
    )
    db.add_all([paper, candidate])
    db.commit()

    with pytest.raises(ValueError, match="canonical source evidence"):
        TrendingModelResolutionService(db).apply(
            candidate.id,
            ResolveModelPaperMutation.model_validate(
                {
                    "decision": "accept",
                    "reason": "Attempted unrelated link.",
                    "novelty_kind": "new_release",
                    "evidence_urls": ["https://huggingface.co/org/model"],
                    "existing_paper_id": paper.id,
                    "model_release": {
                        "canonical_name": "Model",
                        "publisher": "org",
                        "is_open": True,
                        "aliases": [],
                    },
                }
            ),
        )


def test_resolution_accepts_pinned_model_card_for_existing_hf_model_paper():
    db = _resolution_session()
    paper = Paper(
        title="Qwen3.8-27B",
        source="external",
        source_url="https://huggingface.co/Qwen/Qwen3.8-27B",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="Qwen/Qwen3.8-27B",
        author="Qwen",
        readme_sha="a" * 64,
        status="resolving",
    )
    db.add_all([paper, candidate])
    db.commit()

    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "accept",
                "reason": "First-party pinned model card documents new weights.",
                "novelty_kind": "new_weights",
                "evidence_urls": [
                    "https://huggingface.co/Qwen/Qwen3.8-27B/raw/abc123/README.md"
                ],
                "existing_paper_id": paper.id,
                "model_release": {
                    "canonical_name": "Qwen3.8-27B",
                    "publisher": "Qwen",
                    "is_open": True,
                    "aliases": ["Qwen/Qwen3.8-27B"],
                },
            }
        ),
    )

    assert result["paper_id"] == paper.id
    assert db.get(TrendingModelCandidate, candidate.id).status == "resolved"


def test_resolution_rejection_is_durable_and_creates_no_catalog_rows():
    db = _resolution_session()
    candidate = TrendingModelCandidate(
        repo_id="community/model-GGUF",
        author="community",
        readme_sha="b" * 64,
        status="resolving",
    )
    db.add(candidate)
    db.commit()

    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "reject",
                "reason": "Pure quantized conversion.",
                "novelty_kind": "repackaging",
                "evidence_urls": ["https://huggingface.co/community/model-GGUF"],
            }
        ),
    )

    assert result["status"] == "rejected"
    assert db.query(ModelRelease).count() == 0
    assert db.query(Paper).count() == 0


def test_arxiv_upgrade_preserves_release_and_retires_external_paper(monkeypatch):
    db = _resolution_session()
    external = Paper(
        title="Model Release",
        source="external",
        source_url="https://org.example/model",
        version="v1",
        is_latest_version=True,
        hf_models=["https://huggingface.co/org/model"],
    )
    artifact = HfArtifact(
        kind="model",
        repo_id="org/model",
        url="https://huggingface.co/org/model",
    )
    db.add_all([external, artifact])
    db.flush()
    release = ModelRelease(
        paper_id=external.id,
        canonical_name="Model",
        publisher="org",
        canonical_source_url=external.source_url,
        aliases=["org/model"],
    )
    db.add(release)
    db.flush()
    db.add_all(
        [
            PaperHfArtifact(paper_id=external.id, hf_artifact_id=artifact.id),
            ModelReleaseArtifact(
                model_release_id=release.id, hf_artifact_id=artifact.id
            ),
        ]
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="9" * 64,
        status="resolving",
        model_release_id=release.id,
    )
    db.add(candidate)
    db.commit()

    async def import_arxiv(_service, arxiv_id, *, commit=True):
        assert commit is False
        paper = Paper(
            title="Model Technical Report",
            source="arxiv",
            arxiv_id=arxiv_id,
            version="v1",
            is_latest_version=True,
        )
        db.add(paper)
        db.flush()
        return paper, True

    monkeypatch.setattr(
        "backend.services.paper_ingestion_service.PaperIngestionService.get_or_import_arxiv_paper",
        import_arxiv,
    )
    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "accept",
                "reason": "The official release now links its arXiv report.",
                "novelty_kind": "new_weights",
                "evidence_urls": ["https://arxiv.org/abs/2608.12345"],
                "arxiv_id": "2608.12345",
                "model_release": {
                    "canonical_name": "Model",
                    "publisher": "org",
                    "is_open": True,
                    "aliases": ["org/model"],
                },
            }
        ),
    )

    upgraded = db.get(Paper, result["paper_id"])
    assert upgraded.arxiv_id == "2608.12345"
    assert db.get(Paper, external.id).is_latest_version is False
    assert db.get(ModelRelease, release.id).paper_id == upgraded.id
    assert db.get(PaperHfArtifact, (upgraded.id, artifact.id)) is not None
    assert upgraded.hf_models == ["https://huggingface.co/org/model"]
    assert db.query(ProjectPage).filter_by(url=external.source_url).one()


def test_arxiv_import_remains_rollbackable_after_downstream_failure(monkeypatch):
    db = _resolution_session()
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="8" * 64,
        status="resolving",
    )
    db.add(candidate)
    db.commit()

    async def import_arxiv(_service, arxiv_id, *, commit=True):
        assert commit is False
        paper = Paper(
            title="Uncommitted Report",
            source="arxiv",
            arxiv_id=arxiv_id,
            version="v1",
            is_latest_version=True,
        )
        db.add(paper)
        db.flush()
        return paper, True

    monkeypatch.setattr(
        "backend.services.paper_ingestion_service.PaperIngestionService.get_or_import_arxiv_paper",
        import_arxiv,
    )
    monkeypatch.setattr(
        TrendingModelResolutionService,
        "_find_release",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("downstream failure")),
    )
    mutation = ResolveModelPaperMutation.model_validate(
        {
            "decision": "accept",
            "reason": "Official report.",
            "novelty_kind": "new_weights",
            "evidence_urls": ["https://arxiv.org/abs/2608.54321"],
            "arxiv_id": "2608.54321",
            "model_release": {
                "canonical_name": "Model",
                "publisher": "org",
                "is_open": True,
                "aliases": [],
            },
        }
    )
    with pytest.raises(RuntimeError, match="downstream failure"):
        TrendingModelResolutionService(db).apply(candidate.id, mutation)
    db.rollback()

    assert db.query(Paper).count() == 0


def test_release_dedup_uses_normalized_names_and_aliases():
    db = _resolution_session()
    paper = Paper(
        title="Family Report",
        source="external",
        source_url="https://example.com/family",
        version="v1",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    release = ModelRelease(
        paper_id=paper.id,
        canonical_name="Qwen 3.8 Flash Next",
        publisher="Qwen",
        aliases=["qwen/qwen3.8-flash-next"],
    )
    candidate = TrendingModelCandidate(
        repo_id="Qwen/Qwen3.8-Flash-Next",
        author="Qwen",
        readme_sha="7" * 64,
        status="resolving",
    )
    db.add_all([release, candidate])
    db.commit()

    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "accept",
                "reason": "Same canonical release spelling.",
                "novelty_kind": "new_release",
                "evidence_urls": ["https://example.com/family"],
                "existing_paper_id": paper.id,
                "model_release": {
                    "canonical_name": "Qwen3.8-Flash-Next",
                    "publisher": "Qwen",
                    "is_open": True,
                    "aliases": ["Qwen/Qwen3.8-Flash-Next"],
                },
            }
        ),
    )

    assert result["model_release_id"] == release.id
    assert db.query(ModelRelease).count() == 1


def test_resolution_job_is_candidate_scoped_without_a_paper():
    candidate_id = uuid.uuid4()
    job = CodexPaperJob(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        paper_id=None,
        paper_route=None,
        paper_title=None,
        requested_by="hf-trending-cron",
        kind="resolve-model-paper",
        status="queued",
        created_at=datetime.now(UTC),
        attempt_count=0,
        trigger="hf-trending-cron",
    )

    assert job.candidate_id == candidate_id
    assert job.paper_id is None
    assert len(_curator_skill_digest("resolve-model-paper")) == 64


def test_enqueue_resolution_creates_scoped_high_priority_job(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="c" * 64,
        status="discovered",
    )
    db.add(candidate)
    db.commit()
    monkeypatch.setattr(
        "backend.services.codex_add_evals_service._git_revision", lambda: "HEAD"
    )

    job = CodexPaperJobService().enqueue_resolution(
        db,
        candidate=candidate,
        requested_by="hf-trending-cron",
        settings=get_settings(),
        dispatch=False,
    )

    assert job.kind == "resolve-model-paper"
    assert job.candidate_id == candidate.id
    assert job.paper_id is None
    assert job.trigger == "hf-trending-cron"
    assert job.priority < 100
    assert db.get(TrendingModelCandidate, candidate.id).status == "queued"


def test_resolution_context_exposes_only_scoped_candidate_and_exact_linked_papers():
    db = _resolution_session()
    paper = Paper(
        title="Existing Model Report",
        source="external",
        source_url="https://example.com/report",
        version="v1",
        is_latest_version=True,
    )
    artifact = HfArtifact(
        kind="model",
        repo_id="org/model",
        url="https://huggingface.co/org/model",
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="d" * 64,
        readme_revision="e" * 40,
        featured_publisher=True,
        status="resolving",
    )
    db.add_all([paper, artifact, candidate])
    db.flush()
    db.add(PaperHfArtifact(paper_id=paper.id, hf_artifact_id=artifact.id))
    db.commit()

    class Jobs:
        @staticmethod
        def serialize(_row, _settings):
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {"kind": "resolve-model-paper"}
            )

    context = CodexCurationCallbackService(db, job_service=Jobs()).context(
        SimpleNamespace(kind="resolve-model-paper", candidate_id=candidate.id),
        get_settings(),
    )

    assert context["candidate"]["repo_id"] == "org/model"
    assert context["candidate"]["readme_sha"] == "d" * 64
    assert context["paper_candidates"] == [
        {
            "id": paper.id,
            "title": "Existing Model Report",
            "arxiv_id": None,
            "source_url": "https://example.com/report",
        }
    ]
    assert "paper" not in context


def test_remote_proposal_schema_accepts_typed_model_resolution():
    schema = json.loads(Path("jobs/schemas/curation_proposal.schema.json").read_text())
    proposal = {
        "evaluations": [],
        "evaluation_removals": [],
        "benchmark_gaps": [],
        "validation_evidence": [],
        "resolve_model_paper": {
            "decision": "reject",
            "reason": "Pure conversion",
            "novelty_kind": "repackaging",
            "evidence_urls": ["https://huggingface.co/org/model-GGUF"],
        },
    }

    assert list(Draft202012Validator(schema).iter_errors(proposal)) == []


def test_callback_policy_allows_only_resolution_payload_for_resolution_job():
    mutation = ResolveModelPaperMutation.model_validate(
        {
            "decision": "reject",
            "reason": "Pure conversion",
            "novelty_kind": "repackaging",
            "evidence_urls": ["https://huggingface.co/org/model-GGUF"],
        }
    )
    body = ApplyMutationRequest(resolve_model_paper=mutation)
    row = SimpleNamespace(
        kind="resolve-model-paper",
        status="running",
        submitted_at=None,
        applied_at=None,
    )

    service = CodexCurationCallbackService(SimpleNamespace())
    service._validate_mutation(row, body)

    with pytest.raises(ValueError, match="only model resolution"):
        service._validate_mutation(
            row,
            ApplyMutationRequest(
                resolve_model_paper=mutation,
                enrich={"urls_extracted": True},
            ),
        )


def test_callback_applies_resolution_and_records_job_result():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    candidate = TrendingModelCandidate(
        repo_id="community/model-GGUF",
        author="community",
        readme_sha="1" * 64,
        status="resolving",
    )
    db.add(candidate)
    db.flush()
    row = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        candidate_id=candidate.id,
        requested_by="hf-trending-cron",
        trigger="hf-trending-cron",
        policy_version="hf-trending-v1",
        priority=25,
        status="running",
    )
    db.add(row)
    db.commit()

    result = CodexCurationCallbackService(db).apply(
        row,
        ApplyMutationRequest(
            resolve_model_paper={
                "decision": "reject",
                "reason": "Pure conversion",
                "novelty_kind": "repackaging",
                "evidence_urls": ["https://huggingface.co/community/model-GGUF"],
            }
        ),
    )

    assert result["status"] == "rejected"
    assert db.get(TrendingModelCandidate, candidate.id).status == "rejected"
    refreshed = db.get(PaperCurationJob, row.id)
    assert refreshed.applied_at is not None
    assert refreshed.mutation_result["status"] == "rejected"


def test_hourly_reconcile_queues_new_release_rejects_conversion_and_skips_unchanged(
    monkeypatch,
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    models = [
        HFTrendingModel.from_payload(
            {
                "id": "ornith-ai/Ornith-1.5-35B-A3B",
                "author": "ornith-ai",
                "tags": ["transformers", "eval-results"],
                "trending_score": 425,
            }
        ),
        HFTrendingModel.from_payload(
            {
                "id": "community/Ornith-1.5-35B-A3B-GGUF",
                "author": "community",
                "tags": [
                    "gguf",
                    "base_model:quantized:ornith-ai/Ornith-1.5-35B-A3B",
                ],
                "trending_score": 400,
            }
        ),
    ]

    class Discovery:
        @staticmethod
        def list_top_models():
            return models

    class Cards:
        calls = 0

        @classmethod
        def snapshot(cls, repo_id):
            cls.calls += 1
            assert repo_id == "ornith-ai/Ornith-1.5-35B-A3B"
            return HFModelCardSnapshot(
                repo_revision="a" * 40,
                readme_sha="b" * 64,
                markdown="# Ornith",
            )

    monkeypatch.setattr(
        "backend.services.codex_add_evals_service._git_revision", lambda: "HEAD"
    )
    service = HFTrendingModelCurationService(
        db,
        get_settings(),
        discovery=Discovery(),
        cards=Cards(),
    )

    first = service.reconcile(dispatch=False)
    second = service.reconcile(dispatch=False)

    assert first == {
        "discovered": 2,
        "queued": 1,
        "rejected_conversions": 1,
        "unchanged": 0,
        "errors": [],
        "queued_candidate_ids": [str(db.query(PaperCurationJob).one().candidate_id)],
    }
    assert second["queued"] == 0
    assert second["unchanged"] == 1
    assert db.query(PaperCurationJob).count() == 1
    assert (
        db.query(TrendingModelCandidate)
        .filter_by(repo_id="community/Ornith-1.5-35B-A3B-GGUF")
        .one()
        .status
        == "rejected"
    )


def test_rollout_freezes_canary_until_full_workflow_succeeds(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            TrendingModelCandidate.__table__,
            TrendingModelCurationState.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    models = [
        HFTrendingModel.from_payload(
            {
                "id": f"org/model-{index}",
                "author": "org",
                "tags": ["transformers"],
                "trending_score": 100 - index,
            }
        )
        for index in range(2)
    ]

    class Discovery:
        @staticmethod
        def list_top_models():
            return models

    class Cards:
        @staticmethod
        def snapshot(repo_id):
            return HFModelCardSnapshot(
                repo_revision=("a" if repo_id.endswith("0") else "b") * 40,
                readme_sha=("c" if repo_id.endswith("0") else "d") * 64,
                markdown="# Model",
            )

    monkeypatch.setattr(
        "backend.services.codex_add_evals_service._git_revision", lambda: "HEAD"
    )
    service = HFTrendingModelCurationService(
        db,
        get_settings(),
        discovery=Discovery(),
        cards=Cards(),
        rollout=True,
    )

    dry = service.reconcile(dispatch=False, max_queued=1)
    canary = service.reconcile(dispatch=False, max_queued=1)
    paused = service.reconcile(dispatch=False, max_queued=1)

    assert dry["rollout_phase"] == "discovery_dry_run_completed"
    assert db.get(TrendingModelCurationState, 1).discovery_dry_run_completed is True
    assert canary["rollout_phase"] == "canary_started"
    assert len(canary["queued_candidate_ids"]) == 1
    assert paused["rollout_phase"] == "canary_in_progress"
    assert paused["queued"] == 0
    assert db.query(PaperCurationJob).count() == 1

    canary_candidate = db.get(
        TrendingModelCandidate,
        uuid.UUID(canary["queued_candidate_ids"][0]),
    )
    canary_candidate.status = "failed"
    db.query(PaperCurationJob).filter(
        PaperCurationJob.candidate_id == canary_candidate.id
    ).one().status = "failed"
    db.commit()

    retry = service.reconcile(dispatch=False, max_queued=1)

    assert retry["rollout_phase"] == "canary_in_progress"
    assert retry["retried_canary"] == 1
    assert db.query(PaperCurationJob).count() == 2
    assert canary_candidate.status == "queued"
    assert db.query(TrendingModelCandidate).count() == 1


def test_resolved_candidate_enqueues_existing_two_stage_workflow(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    paper = Paper(
        title="Existing Family Report",
        source="external",
        source_url="https://example.com/family",
        version="v1",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    release = ModelRelease(
        paper_id=paper.id,
        canonical_name="Family Flash 0731",
        publisher="org",
        aliases=[],
    )
    db.add(release)
    db.flush()
    candidate = TrendingModelCandidate(
        repo_id="org/family-flash-0731",
        author="org",
        readme_sha="2" * 64,
        readme_revision="3" * 40,
        status="resolved",
        model_release_id=release.id,
    )
    db.add(candidate)
    db.commit()
    monkeypatch.setattr(
        "backend.services.codex_add_evals_service._git_revision", lambda: "HEAD"
    )

    created = CodexPaperJobService().enqueue_resolved_candidate_workflow(
        db, candidate, get_settings(), dispatch=False
    )

    assert created is True
    workflow = db.query(PaperCurationWorkflow).one()
    assert workflow.source_candidate_id == candidate.id
    assert workflow.source_revision == "3" * 40
    job = db.query(PaperCurationJob).one()
    assert job.kind == "enrich-paper"
    assert job.trigger == "hf-trending-cron"
    assert job.priority == 25
