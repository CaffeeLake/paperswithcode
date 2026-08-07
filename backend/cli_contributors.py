"""Internal contributor-access commands for the repository maintenance CLI."""

from __future__ import annotations

import argparse
import os

from huggingface_hub import HfApi

from deploy.configure_host_env import (
    CONFIG_ROOT,
    assign,
    read_lines,
    shared_role_values,
    write_env,
)
from deploy.configure_role_allowlists import normalized_subjects


def register_contributor_commands(commands: argparse._SubParsersAction) -> None:
    contributor = commands.add_parser(
        "contributor",
        help="Manage the protected contributor allowlist (internal only)",
    )
    contributor_commands = contributor.add_subparsers(
        dest="contributor_command",
        required=True,
    )
    add = contributor_commands.add_parser(
        "add",
        help="Add a Hugging Face user to both protected environments",
    )
    add.add_argument("username", help="Hugging Face username")
    add.set_defaults(handler=add_contributor_command)


def resolve_hf_identity(username: str) -> tuple[str, str]:
    """Return the canonical username and immutable OAuth subject."""

    user = HfApi().get_user_overview(username.strip())
    canonical_username = user.username
    subject = getattr(user, "_id", None)
    if not isinstance(subject, str):
        raise ValueError(f"Hugging Face did not return an immutable ID for {username}")
    normalized_subjects([subject])
    return canonical_username, subject


def add_contributor(username: str) -> dict[str, str]:
    canonical_username, subject = resolve_hf_identity(username)
    environments = {
        name: read_lines(CONFIG_ROOT / f"{name}.env")
        for name in ("production", "staging")
    }
    missing = [name for name, lines in environments.items() if not lines]
    if missing:
        raise ValueError(
            "Protected environment does not exist: "
            + ", ".join(str(CONFIG_ROOT / f"{name}.env") for name in missing)
        )

    roles = shared_role_values(*environments.values())
    admin_subjects = set(filter(None, roles["PWC_ADMIN_HF_SUBJECTS"].split(",")))
    contributor_subjects = set(
        filter(None, roles["PWC_CONTRIBUTOR_HF_SUBJECTS"].split(","))
    )
    if subject in admin_subjects:
        status = "already-admin"
    elif subject in contributor_subjects:
        status = "already-contributor"
    else:
        contributor_subjects.add(subject)
        value = normalized_subjects(list(contributor_subjects))
        for environment, group in (
            ("production", "pwc-production"),
            ("staging", "pwc-staging"),
        ):
            write_env(
                CONFIG_ROOT / f"{environment}.env",
                assign(
                    environments[environment],
                    {"PWC_CONTRIBUTOR_HF_SUBJECTS": value},
                ),
                group,
            )
        status = "added"

    return {
        "status": status,
        "username": canonical_username,
        "hf_subject": subject,
    }


def add_contributor_command(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise ValueError("contributor management must be run through sudo")
    result = add_contributor(args.username)
    print(
        f"{result['status']}: @{result['username']} "
        f"({result['hf_subject']}); service restart required"
    )
    return 0
