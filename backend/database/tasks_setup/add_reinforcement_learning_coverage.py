#!/usr/bin/env python3
"""Add Reinforcement Learning task coverage, benchmarks, and seed evals.

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/tasks_setup/add_reinforcement_learning_coverage.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MIGRATION = Path("backend/database/migrations/add_reinforcement_learning_subtasks.sql")

METRICS = [
    ("Score", "higher_is_better", "unbounded", "Raw benchmark score."),
    (
        "Median Human Normalized Score",
        "higher_is_better",
        "percent",
        "Median human-normalized score across Atari games.",
    ),
    (
        "Mean Human Normalized Score",
        "higher_is_better",
        "percent",
        "Mean human-normalized score across Atari games.",
    ),
    (
        "Human Normalized Score",
        "higher_is_better",
        "percent",
        "Human-normalized reinforcement learning score.",
    ),
    (
        "Interquartile Mean",
        "higher_is_better",
        "unbounded",
        "Interquartile mean aggregate score.",
    ),
    ("Return", "higher_is_better", "unbounded", "Episode return."),
    (
        "Average Return",
        "higher_is_better",
        "unbounded",
        "Average episode return.",
    ),
    (
        "Normalized Score",
        "higher_is_better",
        "unbounded",
        "Benchmark-normalized reinforcement learning score.",
    ),
    ("Win Rate", "higher_is_better", "0-100", "Win rate percentage."),
    (
        "Median Win Rate",
        "higher_is_better",
        "0-100",
        "Median win rate percentage across evaluation runs.",
    ),
    (
        "Mean Normalized Performance",
        "higher_is_better",
        "0-1",
        "Mean normalized performance across Procgen games.",
    ),
]

SOURCE_ARXIV = {
    "ale": "1207.4708",
    "dmc": "1801.00690",
    "d4rl": "2004.07219",
    "procgen": "1912.01588",
    "smac": "1902.04043",
    "minatar": "1903.03176",
}

MAJOR_PAPER_TASKS = {
    "1312.5602": ["atari-games"],
    "1602.01783": ["atari-games"],
    "1509.02971": ["continuous-control"],
    "1707.06347": ["continuous-control"],
    "1801.01290": ["continuous-control"],
    "1802.09477": ["continuous-control"],
    "1710.02298": ["atari-games"],
    "1802.01561": ["atari-games"],
    "1909.01387": ["atari-games"],
    "2003.13350": ["atari-games"],
    "2006.04779": ["offline-reinforcement-learning"],
    "2110.06169": ["offline-reinforcement-learning"],
}

BENCHMARKS: list[dict[str, Any]] = [
    {
        "name": "Atari",
        "slug": "atari",
        "task_slugs": ["atari-games"],
        "source_key": "ale",
        "metrics": ["Score"],
        "introduced_date": date(2012, 7, 19),
        "homepage": "https://ale.farama.org/",
        "short_description": "Arcade Learning Environment benchmark for Atari 2600 games.",
        "description": (
            "The Arcade Learning Environment provides a standard interface and "
            "evaluation platform for Atari 2600 games in reinforcement learning."
        ),
    },
    {
        "name": "Atari 57 (200M, No-op Starts)",
        "slug": "atari-57-200m-noop",
        "task_slugs": ["atari-games"],
        "source_key": "ale",
        "metrics": [
            "Median Human Normalized Score",
            "Mean Human Normalized Score",
        ],
        "introduced_date": date(2012, 7, 19),
        "homepage": "https://ale.farama.org/",
        "short_description": (
            "Atari 57 aggregate at 200M frames per game with no-op starts."
        ),
        "description": (
            "Atari 57 aggregates final-agent performance across the canonical 57 "
            "Atari games at 200M frames per game with no-op starts. Human-start, "
            "Atari 100k, and maximum-over-training results are excluded."
        ),
    },
    {
        "name": "Atari 2600 Q*Bert",
        "slug": "atari-2600-qbert",
        "task_slugs": ["atari-games"],
        "source_key": "ale",
        "metrics": ["Score"],
        "introduced_date": date(2012, 7, 19),
        "homepage": "https://ale.farama.org/",
        "short_description": "Atari 2600 Q*Bert leaderboard in ALE-style evaluation.",
        "description": "Atari 2600 Q*Bert is a standard ALE game benchmark.",
    },
    {
        "name": "Atari 2600 Montezuma's Revenge",
        "slug": "atari-2600-montezumas-revenge",
        "task_slugs": ["atari-games"],
        "source_key": "ale",
        "metrics": ["Score"],
        "introduced_date": date(2012, 7, 19),
        "homepage": "https://ale.farama.org/",
        "short_description": "Hard-exploration Atari benchmark with sparse rewards.",
        "description": (
            "Montezuma's Revenge is a hard-exploration Atari benchmark with sparse "
            "rewards and long-horizon credit assignment."
        ),
    },
    {
        "name": "Atari 2600 Pong",
        "slug": "atari-2600-pong",
        "task_slugs": ["atari-games"],
        "source_key": "ale",
        "metrics": ["Score"],
        "introduced_date": date(2012, 7, 19),
        "homepage": "https://ale.farama.org/",
        "short_description": "Atari 2600 Pong leaderboard in ALE-style evaluation.",
        "description": "Atari 2600 Pong is a standard ALE game benchmark.",
    },
    {
        "name": "Atari 2600 Breakout",
        "slug": "atari-2600-breakout",
        "task_slugs": ["atari-games"],
        "source_key": "ale",
        "metrics": ["Score"],
        "introduced_date": date(2012, 7, 19),
        "homepage": "https://ale.farama.org/",
        "short_description": "Atari 2600 Breakout leaderboard in ALE-style evaluation.",
        "description": "Atari 2600 Breakout is a standard ALE game benchmark.",
    },
    {
        "name": "DeepMind Control Suite",
        "slug": "deepmind-control-suite",
        "task_slugs": ["continuous-control"],
        "source_key": "dmc",
        "metrics": ["Average Return", "Return"],
        "introduced_date": date(2018, 1, 2),
        "homepage": "https://github.com/google-deepmind/dm_control",
        "short_description": "Continuous-control benchmark suite for physics-based RL.",
        "description": (
            "The DeepMind Control Suite is a set of continuous-control tasks for "
            "reinforcement learning agents in physics-based environments."
        ),
    },
    {
        "name": "DeepMind Cheetah Run (Images)",
        "slug": "deepmind-cheetah-run-images",
        "task_slugs": ["continuous-control"],
        "source_key": "dmc",
        "metrics": ["Return", "Average Return"],
        "introduced_date": date(2018, 1, 2),
        "homepage": "https://github.com/google-deepmind/dm_control",
        "short_description": "Pixel-observation cheetah.run task from DeepMind Control.",
        "description": (
            "DeepMind Cheetah Run (Images) evaluates continuous-control agents from "
            "pixel observations on the cheetah.run task."
        ),
    },
    {
        "name": "DMC walker-walk",
        "slug": "dmc-walker-walk",
        "task_slugs": ["continuous-control"],
        "source_key": "dmc",
        "metrics": ["Average Return", "Return"],
        "introduced_date": date(2018, 1, 2),
        "homepage": "https://github.com/google-deepmind/dm_control",
        "short_description": "walker.walk task from the DeepMind Control Suite.",
        "description": "DMC walker-walk is a locomotion benchmark from DeepMind Control.",
    },
    {
        "name": "HalfCheetah-v2",
        "slug": "halfcheetah-v2",
        "task_slugs": ["continuous-control"],
        "source_key": None,
        "metrics": ["Average Return", "Return"],
        "introduced_date": date(2012, 6, 18),
        "homepage": "https://gymnasium.farama.org/environments/mujoco/half_cheetah/",
        "short_description": "MuJoCo HalfCheetah continuous-control task.",
        "description": "HalfCheetah-v2 evaluates planar locomotion in MuJoCo.",
    },
    {
        "name": "Hopper-v2",
        "slug": "hopper-v2",
        "task_slugs": ["continuous-control"],
        "source_key": None,
        "metrics": ["Average Return", "Return"],
        "introduced_date": date(2012, 6, 18),
        "homepage": "https://gymnasium.farama.org/environments/mujoco/hopper/",
        "short_description": "MuJoCo Hopper continuous-control task.",
        "description": "Hopper-v2 evaluates one-legged locomotion in MuJoCo.",
    },
    {
        "name": "Walker2d-v2",
        "slug": "walker2d-v2",
        "task_slugs": ["continuous-control"],
        "source_key": None,
        "metrics": ["Average Return", "Return"],
        "introduced_date": date(2012, 6, 18),
        "homepage": "https://gymnasium.farama.org/environments/mujoco/walker2d/",
        "short_description": "MuJoCo Walker2d continuous-control task.",
        "description": "Walker2d-v2 evaluates bipedal locomotion in MuJoCo.",
    },
    {
        "name": "Ant-v2",
        "slug": "ant-v2",
        "task_slugs": ["continuous-control"],
        "source_key": None,
        "metrics": ["Average Return", "Return"],
        "introduced_date": date(2012, 6, 18),
        "homepage": "https://gymnasium.farama.org/environments/mujoco/ant/",
        "short_description": "MuJoCo Ant continuous-control task.",
        "description": "Ant-v2 evaluates quadrupedal locomotion in MuJoCo.",
    },
    {
        "name": "Humanoid-v2",
        "slug": "humanoid-v2",
        "task_slugs": ["continuous-control"],
        "source_key": None,
        "metrics": ["Average Return", "Return"],
        "introduced_date": date(2012, 6, 18),
        "homepage": "https://gymnasium.farama.org/environments/mujoco/humanoid/",
        "short_description": "MuJoCo Humanoid continuous-control task.",
        "description": "Humanoid-v2 evaluates high-dimensional humanoid locomotion in MuJoCo.",
    },
    {
        "name": "D4RL",
        "slug": "d4rl",
        "task_slugs": ["offline-reinforcement-learning"],
        "source_key": "d4rl",
        "metrics": ["Normalized Score"],
        "introduced_date": date(2020, 4, 15),
        "homepage": "https://github.com/Farama-Foundation/D4RL",
        "short_description": "Offline reinforcement learning benchmark suite.",
        "description": (
            "D4RL provides fixed datasets for offline reinforcement learning across "
            "locomotion, navigation, manipulation, and other control domains."
        ),
    },
    {
        "name": "D4RL MuJoCo",
        "slug": "d4rl-mujoco",
        "task_slugs": ["offline-reinforcement-learning"],
        "source_key": "d4rl",
        "metrics": ["Normalized Score"],
        "introduced_date": date(2020, 4, 15),
        "homepage": "https://github.com/Farama-Foundation/D4RL",
        "short_description": "D4RL offline MuJoCo locomotion benchmark family.",
        "description": "D4RL MuJoCo covers fixed locomotion datasets of varying quality.",
    },
    {
        "name": "D4RL Maze2D",
        "slug": "d4rl-maze2d",
        "task_slugs": ["offline-reinforcement-learning"],
        "source_key": "d4rl",
        "metrics": ["Normalized Score"],
        "introduced_date": date(2020, 4, 15),
        "homepage": "https://github.com/Farama-Foundation/D4RL",
        "short_description": "D4RL offline 2D navigation benchmark family.",
        "description": "D4RL Maze2D evaluates offline goal-conditioned navigation.",
    },
    {
        "name": "D4RL AntMaze",
        "slug": "d4rl-antmaze",
        "task_slugs": ["offline-reinforcement-learning"],
        "source_key": "d4rl",
        "metrics": ["Normalized Score"],
        "introduced_date": date(2020, 4, 15),
        "homepage": "https://github.com/Farama-Foundation/D4RL",
        "short_description": "D4RL long-horizon AntMaze benchmark family.",
        "description": (
            "D4RL AntMaze evaluates offline locomotion and navigation over long "
            "horizons."
        ),
    },
    {
        "name": "D4RL Adroit",
        "slug": "d4rl-adroit",
        "task_slugs": ["offline-reinforcement-learning"],
        "source_key": "d4rl",
        "metrics": ["Normalized Score"],
        "introduced_date": date(2020, 4, 15),
        "homepage": "https://github.com/Farama-Foundation/D4RL",
        "short_description": "D4RL dexterous manipulation benchmark family.",
        "description": (
            "D4RL Adroit evaluates offline dexterous manipulation from human "
            "demonstrations."
        ),
    },
    {
        "name": "D4RL HalfCheetah-medium-v2",
        "slug": "d4rl-halfcheetah-medium-v2",
        "task_slugs": ["offline-reinforcement-learning"],
        "source_key": "d4rl",
        "metrics": ["Normalized Score"],
        "introduced_date": date(2020, 4, 15),
        "homepage": "https://github.com/Farama-Foundation/D4RL",
        "short_description": "D4RL HalfCheetah medium offline RL benchmark.",
        "description": "D4RL HalfCheetah-medium-v2 is an offline locomotion benchmark.",
    },
    {
        "name": "D4RL Hopper-medium-v2",
        "slug": "d4rl-hopper-medium-v2",
        "task_slugs": ["offline-reinforcement-learning"],
        "source_key": "d4rl",
        "metrics": ["Normalized Score"],
        "introduced_date": date(2020, 4, 15),
        "homepage": "https://github.com/Farama-Foundation/D4RL",
        "short_description": "D4RL Hopper medium offline RL benchmark.",
        "description": "D4RL Hopper-medium-v2 is an offline locomotion benchmark.",
    },
    {
        "name": "D4RL Walker2d-medium-v2",
        "slug": "d4rl-walker2d-medium-v2",
        "task_slugs": ["offline-reinforcement-learning"],
        "source_key": "d4rl",
        "metrics": ["Normalized Score"],
        "introduced_date": date(2020, 4, 15),
        "homepage": "https://github.com/Farama-Foundation/D4RL",
        "short_description": "D4RL Walker2d medium offline RL benchmark.",
        "description": "D4RL Walker2d-medium-v2 is an offline locomotion benchmark.",
    },
    {
        "name": "Procgen Hard Generalization (500 Train Levels, 200M Steps)",
        "slug": "procgen-hard-generalization-500-train-levels-200m-steps",
        "task_slugs": ["procedural-generalization"],
        "source_key": "procgen",
        "metrics": ["Mean Normalized Performance"],
        "introduced_date": date(2019, 12, 3),
        "homepage": "https://github.com/openai/procgen",
        "short_description": "Procgen hard-mode generalization from 500 training levels after 200M steps.",
        "description": (
            "Procgen hard-mode generalization evaluates agents after 200M environment steps "
            "on unseen levels, using 500 training levels per game."
        ),
    },
    {
        "name": "Procgen CoinRun",
        "slug": "procgen-coinrun",
        "task_slugs": ["procedural-generalization"],
        "source_key": "procgen",
        "metrics": ["Normalized Score", "Score"],
        "introduced_date": date(2019, 12, 3),
        "homepage": "https://github.com/openai/procgen",
        "short_description": "CoinRun environment from Procgen.",
        "description": "Procgen CoinRun is a procedurally generated RL game benchmark.",
    },
    {
        "name": "SMAC",
        "slug": "smac",
        "task_slugs": ["multi-agent-reinforcement-learning"],
        "source_key": "smac",
        "metrics": ["Win Rate", "Median Win Rate"],
        "introduced_date": date(2019, 2, 11),
        "homepage": "https://github.com/oxwhirl/smac",
        "short_description": "StarCraft Multi-Agent Challenge benchmark suite.",
        "description": (
            "SMAC evaluates cooperative multi-agent reinforcement learning methods "
            "on micromanagement scenarios built from StarCraft II."
        ),
    },
    {
        "name": "SMAC 3s5z_vs_3s6z",
        "slug": "smac-3s5z-vs-3s6z",
        "task_slugs": ["multi-agent-reinforcement-learning"],
        "source_key": "smac",
        "metrics": ["Median Win Rate"],
        "introduced_date": date(2019, 2, 11),
        "homepage": "https://github.com/oxwhirl/smac",
        "short_description": "SMAC 3s5z_vs_3s6z cooperative MARL scenario.",
        "description": "SMAC 3s5z_vs_3s6z is a cooperative StarCraft II micromanagement scenario.",
    },
    {
        "name": "SMAC MMM2",
        "slug": "smac-mmm2",
        "task_slugs": ["multi-agent-reinforcement-learning"],
        "source_key": "smac",
        "metrics": ["Median Win Rate"],
        "introduced_date": date(2019, 2, 11),
        "homepage": "https://github.com/oxwhirl/smac",
        "short_description": "SMAC MMM2 cooperative MARL scenario.",
        "description": (
            "SMAC MMM2 is a challenging cooperative StarCraft II micromanagement "
            "scenario."
        ),
    },
    {
        "name": "MinAtar",
        "slug": "minatar",
        "task_slugs": ["atari-games"],
        "source_key": "minatar",
        "metrics": ["Score"],
        "introduced_date": date(2019, 3, 7),
        "homepage": "https://github.com/kenjyoung/MinAtar",
        "short_description": "Minimal Atari-like RL testbed.",
        "description": (
            "MinAtar is a lightweight Atari-inspired testbed for reproducible "
            "reinforcement learning experiments."
        ),
    },
]

EVALS: list[dict[str, Any]] = [
    {
        "paper_arxiv": "2003.13350",
        "task_slug": "atari-games",
        "dataset_slug": "atari-2600-qbert",
        "model_name": "Agent57",
        "metric": "Score",
        "score": "580328.14",
        "rank": 1,
        "methodology": "Legacy PwC Atari 2600 Q*Bert row; raw ALE score.",
    },
    {
        "paper_arxiv": "2004.12919",
        "task_slug": "atari-games",
        "dataset_slug": "atari-2600-montezumas-revenge",
        "model_name": "Go-Explore",
        "metric": "Score",
        "score": "43791",
        "rank": 1,
        "methodology": "Legacy PwC Montezuma's Revenge row; raw ALE score.",
    },
    {
        "paper_arxiv": "1511.06581",
        "task_slug": "atari-games",
        "dataset_slug": "atari-2600-pong",
        "model_name": "Duel noop",
        "metric": "Score",
        "score": "21.0",
        "rank": 1,
        "methodology": "Legacy PwC Atari 2600 Pong row; raw ALE score with no-op evaluation.",
    },
    {
        "paper_arxiv": "2004.13649",
        "task_slug": "continuous-control",
        "dataset_slug": "deepmind-cheetah-run-images",
        "model_name": "DrQ",
        "metric": "Return",
        "score": "660",
        "rank": 3,
        "methodology": "Legacy PwC DeepMind Cheetah Run (Images) row; pixel-observation return.",
    },
    {
        "paper_arxiv": "2009.04416",
        "task_slug": "procedural-generalization",
        "dataset_slug": "procgen-hard-sample-efficiency-full-distribution-100m-steps",
        "model_name": "PPG",
        "metric": "Mean Normalized Performance",
        "score": "0.757",
        "rank": 1,
        "methodology": (
            "PPG Procgen hard-mode sample efficiency: full level distribution, "
            "100M environment steps, source-defined mean normalized performance."
        ),
    },
    {
        "paper_arxiv": "2211.16068",
        "task_slug": "multi-agent-reinforcement-learning",
        "dataset_slug": "smac-3s5z-vs-3s6z",
        "model_name": "ACE",
        "metric": "Median Win Rate",
        "score": "100",
        "rank": 1,
        "methodology": "Legacy PwC SMAC 3s5z_vs_3s6z row; median win rate.",
    },
    {
        "paper_arxiv": "2211.16068",
        "task_slug": "multi-agent-reinforcement-learning",
        "dataset_slug": "smac-mmm2",
        "model_name": "ACE",
        "metric": "Median Win Rate",
        "score": "100",
        "rank": 1,
        "methodology": "Legacy PwC SMAC MMM2 row; median win rate.",
    },
    {
        "paper_arxiv": "2110.06169",
        "task_slug": "offline-reinforcement-learning",
        "dataset_slug": "d4rl-halfcheetah-medium-v2",
        "model_name": "IQL",
        "metric": "Normalized Score",
        "score": "47.4",
        "rank": 1,
        "methodology": (
            "IQL paper Table 1; averaged D4RL normalized score on "
            "halfcheetah-medium-v2."
        ),
    },
    {
        "paper_arxiv": "2110.06169",
        "task_slug": "offline-reinforcement-learning",
        "dataset_slug": "d4rl-hopper-medium-v2",
        "model_name": "IQL",
        "metric": "Normalized Score",
        "score": "66.3",
        "rank": 1,
        "methodology": "IQL paper Table 1; averaged D4RL normalized score on hopper-medium-v2.",
    },
    {
        "paper_arxiv": "2110.06169",
        "task_slug": "offline-reinforcement-learning",
        "dataset_slug": "d4rl-walker2d-medium-v2",
        "model_name": "IQL",
        "metric": "Normalized Score",
        "score": "78.3",
        "rank": 1,
        "methodology": "IQL paper Table 1; averaged D4RL normalized score on walker2d-medium-v2.",
    },
]


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )

    paper_id = PaperService(session).add_paper(
        {
            "arxiv_id": metadata.arxiv_id,
            "title": metadata.title,
            "abstract": metadata.abstract,
            "version": metadata.version,
            "date_published": metadata.published.date() if metadata.published else None,
            "primary_category": metadata.primary_category,
            "all_categories": metadata.categories,
            "is_latest_version": True,
        }
    )
    paper = session.get(Paper, paper_id)
    if metadata.authors:
        for order, author_name in enumerate(metadata.authors, start=1):
            author = session.query(Author).filter(Author.name == author_name).first()
            if not author:
                author = Author(name=author_name)
                session.add(author)
                session.flush()
            session.add(
                PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=order)
            )
        session.flush()
    return paper


def paper_url_for(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def ensure_metric(session, spec: tuple[str, str, str, str]) -> int:
    name, direction, scale, description = spec
    row = session.execute(
        text("SELECT id, direction, scale FROM metrics WHERE name = :name"),
        {"name": name},
    ).fetchone()
    if row:
        metric_id = int(row.id)
        if row.direction != direction or row.scale != scale:
            session.execute(
                text(
                    "UPDATE metrics SET direction = :direction, scale = :scale "
                    "WHERE id = :id"
                ),
                {"direction": direction, "scale": scale, "id": metric_id},
            )
        return metric_id

    return int(
        session.execute(
            text(
                """
                INSERT INTO metrics (name, direction, full_name, scale, description)
                VALUES (:name, :direction, :name, :scale, :description)
                RETURNING id
                """
            ),
            {
                "name": name,
                "direction": direction,
                "scale": scale,
                "description": description,
            },
        ).scalar_one()
    )


def task_id(session, slug: str) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"),
        {"slug": slug},
    ).one()
    return int(row.id)


def link_paper_to_task(session, paper_id: int, task_slug: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            SELECT :paper_id, id, 'manual' FROM tasks WHERE slug = :slug
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "slug": task_slug},
    )


def ensure_dataset(session, spec: dict[str, Any], source_paper: Paper | None) -> int:
    source_paper_url = paper_url_for(source_paper) if source_paper else None
    source_paper_id = source_paper.id if source_paper else None
    source_paper_title = source_paper.title if source_paper else None
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": spec["slug"]},
    ).fetchone()
    if row:
        dataset_id = int(row.id)
    else:
        dataset_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO datasets (
                        name, slug, description, short_description, homepage,
                        introduced_date, introduced_year, paper_url,
                        introducing_paper_id, introducing_paper_title
                    )
                    VALUES (
                        :name, :slug, :description, :short_description, :homepage,
                        :introduced_date, :introduced_year, :paper_url,
                        :introducing_paper_id, :introducing_paper_title
                    )
                    RETURNING id
                    """
                ),
                {
                    "name": spec["name"],
                    "slug": spec["slug"],
                    "description": spec["description"],
                    "short_description": spec["short_description"],
                    "homepage": spec["homepage"],
                    "introduced_date": spec["introduced_date"],
                    "introduced_year": spec["introduced_date"].year,
                    "paper_url": source_paper_url,
                    "introducing_paper_id": source_paper_id,
                    "introducing_paper_title": source_paper_title,
                },
            ).scalar_one()
        )

    session.execute(
        text(
            """
            UPDATE datasets
            SET name = :name,
                description = :description,
                short_description = :short_description,
                homepage = :homepage,
                introduced_date = COALESCE(introduced_date, :introduced_date),
                introduced_year = COALESCE(introduced_year, :introduced_year),
                paper_url = :paper_url,
                introducing_paper_id = :introducing_paper_id,
                introducing_paper_title = :introducing_paper_title,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ),
        {
            "id": dataset_id,
            "name": spec["name"],
            "description": spec["description"],
            "short_description": spec["short_description"],
            "homepage": spec["homepage"],
            "introduced_date": spec["introduced_date"],
            "introduced_year": spec["introduced_date"].year,
            "paper_url": source_paper_url,
            "introducing_paper_id": source_paper_id,
            "introducing_paper_title": source_paper_title,
        },
    )
    return dataset_id


def wire_benchmark(
    session,
    dataset_id: int,
    task_slug_value: str,
    metric_names: list[str],
    metric_ids: dict[str, int],
) -> None:
    target_task_id = task_id(session, task_slug_value)
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET supports_harness = FALSE
            """
        ),
        {"task_id": target_task_id, "dataset_id": dataset_id},
    )

    for metric_name in metric_names:
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {
                "task_id": target_task_id,
                "dataset_id": dataset_id,
                "metric_id": metric_ids[metric_name],
            },
        )


def evaluation_exists(
    session,
    paper_id: int,
    task_id_value: int,
    dataset_id: int,
    model_name: str,
    metric: str,
) -> bool:
    row = session.execute(
        text(
            """
            SELECT id FROM evaluations
            WHERE paper_id = :paper_id
              AND task_id = :task_id
              AND dataset_id = :dataset_id
              AND model_name = :model_name
              AND COALESCE(harness, '') = ''
              AND best_metric = :metric
            LIMIT 1
            """
        ),
        {
            "paper_id": paper_id,
            "task_id": task_id_value,
            "dataset_id": dataset_id,
            "model_name": model_name,
            "metric": metric,
        },
    ).fetchone()
    return row is not None


async def main() -> None:
    session = db_manager.session_local()
    try:
        session.execute(text(MIGRATION.read_text()))

        metric_ids = {}
        for spec in METRICS:
            metric_ids[spec[0]] = ensure_metric(session, spec)

        source_papers = {
            key: await ensure_arxiv_paper(session, arxiv_id)
            for key, arxiv_id in SOURCE_ARXIV.items()
        }

        for spec in BENCHMARKS:
            source_paper = source_papers.get(spec["source_key"])
            dataset_id = ensure_dataset(session, spec, source_paper)
            for slug in spec["task_slugs"]:
                wire_benchmark(session, dataset_id, slug, spec["metrics"], metric_ids)
                if source_paper:
                    link_paper_to_task(session, int(source_paper.id), slug)
            if source_paper:
                link_paper_to_task(
                    session, int(source_paper.id), "reinforcement-learning"
                )

        for arxiv_id, task_slugs in MAJOR_PAPER_TASKS.items():
            paper = await ensure_arxiv_paper(session, arxiv_id)
            link_paper_to_task(session, int(paper.id), "reinforcement-learning")
            for slug in task_slugs:
                link_paper_to_task(session, int(paper.id), slug)

        eval_service = EvaluationService(session)
        for spec in EVALS:
            paper = await ensure_arxiv_paper(session, spec["paper_arxiv"])
            target_task_id = task_id(session, spec["task_slug"])
            dataset_row = session.execute(
                text("SELECT id FROM datasets WHERE slug = :slug"),
                {"slug": spec["dataset_slug"]},
            ).one()
            dataset_id = int(dataset_row.id)
            link_paper_to_task(session, int(paper.id), spec["task_slug"])
            link_paper_to_task(session, int(paper.id), "reinforcement-learning")

            if evaluation_exists(
                session,
                int(paper.id),
                target_task_id,
                dataset_id,
                spec["model_name"],
                spec["metric"],
            ):
                continue

            eval_service.create_evaluation(
                paper_id=int(paper.id),
                task_id=target_task_id,
                dataset_id=dataset_id,
                model_name=spec["model_name"],
                methodology=spec["methodology"],
                metrics={spec["metric"]: spec["score"]},
                best_metric=spec["metric"],
                best_rank=spec["rank"],
                external_source_url=paper_url_for(paper),
                is_open=True,
            )

        session.commit()
        logger.info("Reinforcement Learning coverage added successfully.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
