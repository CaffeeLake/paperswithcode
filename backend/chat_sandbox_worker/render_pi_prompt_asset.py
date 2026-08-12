"""Emit the deterministic canonical Pi prompt asset during image publication."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from backend.chat_sandbox_worker.prompt import render

DATE_SENTINEL = "2000-01-01"
MODEL_SENTINEL = "__PWC_SELECTED_MODEL__"
USER_SENTINEL = "__PWC_HF_USERNAME__"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    value = render(
        current_date=date.fromisoformat(DATE_SENTINEL),
        selected_model=MODEL_SENTINEL,
        web_search_enabled=False,
        hf_username=USER_SENTINEL,
        agent_harness="pi",
    )
    args.output.write_text(value, encoding="utf-8")


if __name__ == "__main__":
    main()
