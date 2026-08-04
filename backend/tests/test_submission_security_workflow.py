import argparse
import asyncio
import json
import uuid

import pytest

from backend.cli import build_parser
from backend.cli_submissions import decide_submission
from backend.services.pending_edit_service import PendingEditError, PendingEditService
from backend.services.thumbnail_service import ThumbnailService
from backend.utils.exceptions import ThumbnailGenerationError


def test_taxonomy_payloads_require_application_context():
    with pytest.raises(PendingEditError, match="task_ids"):
        PendingEditService._validate_payload(
            "new_benchmark", {"name": "Bench", "description": "Description"}
        )
    with pytest.raises(PendingEditError, match="both task_id and dataset_id"):
        PendingEditService._validate_payload(
            "new_metric",
            {
                "name": "Score",
                "description": "Description",
                "direction": "higher_is_better",
                "task_id": 1,
            },
        )
    with pytest.raises(PendingEditError, match="source URL"):
        PendingEditService._validate_payload(
            "new_conference", {"name": "Venue 2027", "year": 2027}
        )


def test_taxonomy_payload_normalizes_typed_fields():
    payload = PendingEditService._validate_payload(
        "new_metric",
        {
            "name": "  Accuracy ",
            "description": "  Correct predictions  ",
            "direction": "higher_is_better",
            "task_id": 7,
            "dataset_id": 9,
        },
    )
    assert payload == {
        "name": "Accuracy",
        "description": "Correct predictions",
        "direction": "higher_is_better",
        "task_id": 7,
        "dataset_id": 9,
    }


def test_submission_cli_requires_explicit_environment():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["submissions", "list", "--json"])
    args = parser.parse_args(
        ["submissions", "show", "42", "--environment", "production", "--json"]
    )
    assert args.id == 42
    assert args.environment == "production"


def test_codex_terminal_decisions_are_fail_closed(tmp_path):
    artifact = {
        "decision": "approve",
        "rationale": "Verified",
        "sources": [],
        "duplicate_checks": [],
        "confidence": 1,
        "unresolved_questions": [],
        "model": "test-model",
        "workflow_version": "v1",
        "codex_task_id": "task",
        "reviewed_revision": "abc",
        "material_changes": [],
    }
    review_file = tmp_path / "review.json"
    review_file.write_text(json.dumps(artifact))
    args = argparse.Namespace(
        id=1,
        environment="production",
        decision="approve",
        resolved_payload_file=None,
        review_file=review_file,
        review_run_id=uuid.uuid4(),
        confirm="APPLY_SUBMISSION_REVIEW",
        json=True,
    )
    with pytest.raises(ValueError, match="apply is disabled"):
        decide_submission(args)


def test_arbitrary_webpage_screenshots_are_disabled():
    with pytest.raises(ThumbnailGenerationError, match="disabled"):
        asyncio.run(
            ThumbnailService._capture_external_page_screenshot(
                object(), "https://example.com/page"
            )
        )
