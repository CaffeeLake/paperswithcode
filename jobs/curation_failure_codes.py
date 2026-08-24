"""Stable machine-readable failure codes shared by curation workers and API."""

AWAITING_MARKDOWN = "awaiting_markdown"


def format_failure(code: str, detail: str) -> str:
    return f"[{code}] {detail}"


def parse_failure_code(error: str | None) -> str | None:
    if not error or not error.startswith("[") or "]" not in error:
        return None
    return error[1 : error.index("]")]
