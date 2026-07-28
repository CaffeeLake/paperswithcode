#!/usr/bin/env python3
"""Render bounded public task taxonomy JSON as prompt-ready Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def render(payload: dict[str, Any], *, maximum_tasks_per_area: int = 12) -> str:
    areas = payload.get("results")
    if not isinstance(areas, list):
        raise ValueError("taxonomy response must contain a results list")

    lines = [
        "## Available research areas and representative tasks",
        "",
        (
            "The public catalog currently uses the areas below. Up to "
            f"{maximum_tasks_per_area} visible top-level tasks are shown per area, "
            "ordered by paper coverage. Task slugs are included for precise CLI "
            "queries; use `pwc --help` to inspect the live command surface."
        ),
    ]
    for area in sorted(areas, key=lambda item: str(item.get("name") or "").casefold()):
        name = str(area.get("name") or "").strip()
        tasks = area.get("tasks")
        if not name or not isinstance(tasks, list):
            continue
        visible_tasks = [
            task
            for task in tasks
            if isinstance(task, dict)
            and task.get("is_visible") is not False
            and str(task.get("name") or "").strip()
            and str(task.get("slug") or "").strip()
        ]
        visible_tasks.sort(
            key=lambda task: (
                -int(task.get("paper_count") or 0),
                str(task.get("name") or "").casefold(),
            )
        )
        lines.extend(("", f"### {name}", ""))
        for task in visible_tasks[:maximum_tasks_per_area]:
            lines.append(
                f"- `{str(task['slug']).strip()}` — {str(task['name']).strip()}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maximum-tasks-per-area", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.maximum_tasks_per_area <= 25:
        parser.error("--maximum-tasks-per-area must be 1-25")
    payload = json.load(sys.stdin)
    sys.stdout.write(
        render(payload, maximum_tasks_per_area=args.maximum_tasks_per_area)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
