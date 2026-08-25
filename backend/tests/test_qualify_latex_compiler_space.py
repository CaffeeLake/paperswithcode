from __future__ import annotations


def test_qualification_cases_cover_the_required_hostile_boundaries() -> None:
    from backend.scripts.qualify_latex_compiler_space import qualification_cases

    names = {case.name for case in qualification_cases()}

    assert {
        "valid-document",
        "shell-escape",
        "host-file-read",
        "network-pipe",
        "recursive-expansion",
        "process-pressure",
        "oversized-output",
        "path-traversal-archive",
        "malformed-archive",
        "hostile-pdf",
    } <= names


def test_qualification_report_is_bounded_and_never_contains_case_source() -> None:
    from backend.scripts.qualify_latex_compiler_space import QualificationCase, report

    case = QualificationCase(
        name="secret-case", bundle=b"private manuscript source", expected="failed"
    )

    payload = report([(case, "failed", 12)])

    assert payload == {
        "cases": [{"name": "secret-case", "outcome": "failed", "elapsed_ms": 12}],
        "passed": 1,
        "total": 1,
    }
    assert "private manuscript source" not in str(payload)
