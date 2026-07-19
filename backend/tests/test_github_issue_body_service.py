import pytest

from backend.cli import build_parser
from backend.services.github_issue_body_service import (
    PaperEvaluation,
    RankingPlacement,
    TaskLink,
    compute_placement,
    render_issue_body,
    render_ranking_paragraphs,
)
from backend.utils.paper_reference import normalize_paper_reference


def evaluation(
    evaluation_id: int,
    score: str,
    *,
    dataset_name: str = "Benchmark",
    dataset_slug: str = "benchmark",
    metric: str = "Accuracy",
) -> PaperEvaluation:
    return PaperEvaluation(
        id=evaluation_id,
        paper_id=1,
        task_id=2,
        task_name="Task",
        task_slug="task",
        dataset_id=3,
        dataset_name=dataset_name,
        dataset_slug=dataset_slug,
        model_name="Model",
        best_metric=metric,
        metrics={metric: score},
    )


def placement(
    evaluation_id: int,
    rank: int,
    *,
    entries: int = 5,
    dataset_name: str = "Benchmark",
    dataset_slug: str = "benchmark",
    metric: str = "Accuracy",
    model_name: str = "Model",
) -> RankingPlacement:
    return RankingPlacement(
        evaluation_id=evaluation_id,
        task_slug="task",
        dataset_name=dataset_name,
        dataset_slug=dataset_slug,
        model_name=model_name,
        metric_name=metric,
        rank=rank,
        leaderboard_entries=entries,
    )


def test_compute_placement_uses_competition_rank_and_preserves_ties():
    target = evaluation(1, "98.5")
    rows = [target, evaluation(2, "98.6"), evaluation(3, "98.5")]

    result = compute_placement(target, rows, "higher_is_better")

    assert result is not None
    assert result.rank == 2
    assert result.leaderboard_entries == 3


def test_compute_placement_supports_lower_is_better_and_plus_minus_values():
    target = evaluation(1, "1.2±0.1", metric="Error")
    rows = [target, evaluation(2, "0.9", metric="Error")]

    result = compute_placement(target, rows, "lower_is_better")

    assert result is not None
    assert result.rank == 2


def test_ranking_paragraphs_omit_single_entry_and_rank_below_fourth():
    paragraphs = render_ranking_paragraphs(
        [
            placement(1, 1, entries=1),
            placement(2, 5, entries=20),
            placement(3, 4, dataset_name="Included", dataset_slug="included"),
        ]
    )

    assert len(paragraphs) == 1
    assert "ranks fourth" in paragraphs[0]
    assert "Included" in paragraphs[0]
    assert "#4" not in paragraphs[0]


def test_ranking_paragraphs_group_metrics_and_cap_links():
    placements = [
        placement(1, 1, dataset_name="A", dataset_slug="a", metric="Accuracy"),
        placement(2, 1, dataset_name="A", dataset_slug="a", metric="F1"),
        placement(3, 1, dataset_name="B", dataset_slug="b"),
        placement(4, 1, dataset_name="C", dataset_slug="c"),
        placement(5, 1, dataset_name="D", dataset_slug="d"),
        placement(6, 1, dataset_name="E", dataset_slug="e"),
    ]

    paragraphs = render_ranking_paragraphs(placements)
    text = "\n".join(paragraphs)

    assert "two metrics on A" in text
    assert text.count("https://paperswithcode.co/benchmark/") == 4
    assert "E" not in text


def test_render_issue_body_is_compact_and_verification_is_explicit():
    tasks = (TaskLink(name="Robotics", slug="robotics", evaluation_count=6),)
    rankings = (
        placement(
            9926,
            2,
            entries=118,
            dataset_name="LIBERO-Long",
            dataset_slug="libero-long",
            metric="Success Rate",
            model_name="LingBot-VA",
        ),
    )

    unverified = render_issue_body("2601.21998", 6, tasks, rankings, False)
    verified = render_issue_body("2601.21998", 6, tasks, rankings, True)

    assert "6 paper-native evaluations" in unverified
    assert "6 verified paper-native evaluations" in verified
    assert "ranks second" in verified
    assert "Copy PwC badge" in verified
    assert "**" not in verified
    assert "rank #" not in verified
    assert verified.count("https://paperswithcode.co/benchmark/") == 1


def test_normalize_paper_reference_accepts_url_arxiv_and_external_id():
    assert (
        normalize_paper_reference("https://paperswithcode.co/paper/2601.21998")
        == "2601.21998"
    )
    assert normalize_paper_reference("2601.21998") == "2601.21998"
    assert normalize_paper_reference("2601.21998v3") == "2601.21998"
    assert normalize_paper_reference("55623") == "55623"


def test_render_multiple_tasks_caps_task_links_without_broken_grammar():
    tasks = tuple(
        TaskLink(name=f"Task {index}", slug=f"task-{index}", evaluation_count=5 - index)
        for index in range(4)
    )

    body = render_issue_body("2601.21998", 10, tasks, (), False)

    assert body.count("https://paperswithcode.co/tasks/") == 3
    assert "and 1 additional task page" in body


def test_pwc_cli_parses_github_issue_body_command():
    args = build_parser().parse_args(
        [
            "github-issue",
            "body",
            "2601.21998",
            "--task",
            "robotics",
            "--verified",
            "--json",
        ]
    )

    assert args.paper == "2601.21998"
    assert args.task == "robotics"
    assert args.verified
    assert args.json


def test_pwc_cli_requires_explicit_publish_confirmation():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["github-issue", "create", "2601.21998"])

    args = build_parser().parse_args(
        [
            "github-issue",
            "create",
            "2601.21998",
            "--verified",
            "--confirm",
            "PUBLISH",
        ]
    )
    assert args.confirm == "PUBLISH"
