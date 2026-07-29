#!/usr/bin/env python3
"""Install immutable HF subject roles in both protected app environments."""

from __future__ import annotations

import argparse
import os
import re

from deploy.configure_host_env import (
    CONFIG_ROOT,
    assign,
    read_lines,
    write_env,
)

SUBJECT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,254}")


def normalized_subjects(values: list[str]) -> str:
    subjects = sorted({value.strip() for value in values if value.strip()})
    if any(SUBJECT_PATTERN.fullmatch(subject) is None for subject in subjects):
        raise ValueError("Malformed immutable Hugging Face subject")
    return ",".join(subjects)


def install(admin_subjects: list[str], contributor_subjects: list[str]) -> None:
    values = {
        "PWC_ADMIN_HF_SUBJECTS": normalized_subjects(admin_subjects),
        "PWC_CONTRIBUTOR_HF_SUBJECTS": normalized_subjects(contributor_subjects),
        "PWC_CONTRIBUTOR_DIRECT_EDITS_ENABLED": "false",
    }
    for environment, group in (
        ("production", "pwc-production"),
        ("staging", "pwc-staging"),
    ):
        path = CONFIG_ROOT / f"{environment}.env"
        current = read_lines(path)
        if not current:
            raise RuntimeError(f"Protected environment does not exist: {path}")
        write_env(path, assign(current, values), group)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-subject", action="append", default=[])
    parser.add_argument("--contributor-subject", action="append", default=[])
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo")
    if not args.admin_subject:
        parser.error("at least one --admin-subject is required")
    install(args.admin_subject, args.contributor_subject)
    print(
        "installed immutable role allowlists "
        f"(admins={len(set(args.admin_subject))}, "
        f"contributors={len(set(args.contributor_subject))}); "
        "direct contributor edits remain disabled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
