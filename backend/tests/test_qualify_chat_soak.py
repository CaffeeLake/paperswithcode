from backend.scripts.qualify_chat_soak import CONFIRMATION, parser


def test_soak_qualifier_parser_has_bounded_explicit_controls(tmp_path):
    release = tmp_path / "release"
    args = parser().parse_args(
        [
            "--followup-sessions",
            "13",
            "--followups-per-session",
            "4",
            "--clean-cancellations",
            "20",
            "--forced-cancellations",
            "10",
            "--release-dir",
            str(release),
            "--confirm",
            CONFIRMATION,
        ]
    )

    assert args.followup_sessions == 13
    assert args.followups_per_session == 4
    assert args.clean_cancellations == 20
    assert args.forced_cancellations == 10
    assert args.release_dir == release
