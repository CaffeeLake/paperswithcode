from types import SimpleNamespace

import pytest

from backend import cli_contributors


def env(contributors: str = "") -> dict[str, str]:
    return {
        "PWC_ADMIN_HF_SUBJECTS": "PWC_ADMIN_HF_SUBJECTS=admin-subject",
        "PWC_CONTRIBUTOR_HF_SUBJECTS": (f"PWC_CONTRIBUTOR_HF_SUBJECTS={contributors}"),
    }


def test_resolve_hf_identity_uses_immutable_id(monkeypatch):
    monkeypatch.setattr(
        cli_contributors,
        "HfApi",
        lambda: SimpleNamespace(
            get_user_overview=lambda username: SimpleNamespace(
                username="Canonical", _id="immutable-subject"
            )
        ),
    )

    assert cli_contributors.resolve_hf_identity("renamed") == (
        "Canonical",
        "immutable-subject",
    )


def test_add_contributor_preserves_and_updates_both_environments(monkeypatch):
    environments = {
        "production.env": env("existing-subject"),
        "staging.env": env("existing-subject"),
    }
    writes = []
    monkeypatch.setattr(
        cli_contributors, "resolve_hf_identity", lambda _: ("fm1320", "new-subject")
    )
    monkeypatch.setattr(
        cli_contributors,
        "read_lines",
        lambda path: environments[path.name],
    )
    monkeypatch.setattr(
        cli_contributors,
        "write_env",
        lambda path, lines, group: writes.append((path.name, lines, group)),
    )

    result = cli_contributors.add_contributor("fm1320")

    assert result["status"] == "added"
    assert [item[0] for item in writes] == ["production.env", "staging.env"]
    assert all(
        item[1]["PWC_CONTRIBUTOR_HF_SUBJECTS"]
        == "PWC_CONTRIBUTOR_HF_SUBJECTS=existing-subject,new-subject"
        for item in writes
    )


def test_add_contributor_rejects_diverged_environment_allowlists(monkeypatch):
    environments = {
        "production.env": env("one-subject"),
        "staging.env": env("other-subject"),
    }
    monkeypatch.setattr(
        cli_contributors, "resolve_hf_identity", lambda _: ("fm1320", "new-subject")
    )
    monkeypatch.setattr(
        cli_contributors,
        "read_lines",
        lambda path: environments[path.name],
    )

    with pytest.raises(ValueError, match="differs"):
        cli_contributors.add_contributor("fm1320")


def test_add_contributor_command_requests_supported_environment_refresh(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli_contributors.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        cli_contributors,
        "add_contributor",
        lambda _: {
            "status": "added",
            "username": "fm1320",
            "hf_subject": "immutable-subject",
        },
    )

    assert (
        cli_contributors.add_contributor_command(SimpleNamespace(username="fm1320"))
        == 0
    )
    assert "refresh environments with pwc-deploy" in capsys.readouterr().out
