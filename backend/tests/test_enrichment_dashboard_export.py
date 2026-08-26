from datetime import date, datetime, timezone

from backend.services.enrichment_dashboard_export import build_snapshot, write_snapshot


class Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    def __init__(
        self, jobs, evaluations, gaps, trending_models=None, trending_decisions=None
    ):
        self.results = iter(
            [
                Result(jobs),
                Result(evaluations),
                Result(gaps),
                Result(trending_models or []),
                Result(trending_decisions or []),
            ]
        )

    def execute(self, *_args, **_kwargs):
        return next(self.results)


def test_snapshot_groups_jobs_and_deduplicates_gap_paper_pairs(tmp_path):
    timestamp = datetime(2026, 8, 25, 2, tzinfo=timezone.utc)
    jobs = [
        {
            "id": "job-1",
            "paper_id": 1,
            "paper_title": "Paper",
            "kind": "enrich-paper",
            "status": "completed",
            "created_at": timestamp,
            "mutation_result": {"status": "applied"},
            "error": None,
        },
        {
            "id": "job-2",
            "paper_id": 1,
            "paper_title": "Paper",
            "kind": "add-evals",
            "status": "completed",
            "created_at": timestamp,
            "mutation_result": {"evaluations_created": 2},
            "error": None,
        },
    ]
    evaluations = [
        {
            "id": 4,
            "paper_id": 1,
            "paper_title": "Paper",
            "task": "QA",
            "dataset": "Test",
            "model_name": "M",
            "harness": None,
            "best_metric": "Accuracy",
            "metrics": {"Accuracy": 90},
            "source_url": "https://example.test",
            "created_at": timestamp,
        }
    ]
    gap = {
        "identity_key": "gap",
        "canonical_name": "NewBench",
        "gap_type": "dataset_missing",
        "canonical_url": "https://example.test/bench",
        "review_status": "candidate",
        "distinct_paper_count": 1,
        "paper_id": 1,
        "paper_title": "Paper",
        "created_at": timestamp,
    }
    snapshot = build_snapshot(
        FakeDB(jobs, evaluations, [gap, gap]), date(2026, 8, 25), date(2026, 8, 25)
    )
    assert snapshot["daily"] == [
        {
            "day": "2026-08-25",
            "enrichment_jobs": 1,
            "enrichment_applied": 1,
            "enrichment_noops": 0,
            "enrichment_failed": 0,
            "evaluation_jobs": 1,
            "evaluations_created": 2,
            "benchmark_gap_reports": 1,
        }
    ]
    assert len(snapshot["benchmark_gaps"]) == 1
    assert snapshot["trending_models"] == []
    assert snapshot["trending_model_decisions"] == []


def test_write_snapshot_creates_json(tmp_path):
    path = tmp_path / "snapshot.json"
    write_snapshot({"schema_version": 1, "generated_at": "now"}, path)
    assert path.exists()
