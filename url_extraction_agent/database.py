"""Trusted VPS boundary for selecting and persisting URL extraction work."""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.project_page_service import ProjectPageService
from backend.services.repository_service import RepositoryService
from backend.utils.github_utils import parse_github_url
from backend.utils.verify_url import verify_url
from url_extraction_agent.schema import (
    AgentAttempt,
    PaperCandidate,
    PersistResult,
)

LOG_DIR = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "scripts"
    / "logs"
)


def _logger() -> logging.Logger:
    logger = logging.getLogger("extract_urls_hourly")
    if logger.handlers:
        return logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(
        LOG_DIR / f"extract_urls_hourly_{datetime.now():%Y%m%d}.log"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def _home_cte(mode: str) -> str:
    if mode == "composite":
        return """
        home_pool AS (
            SELECT DISTINCT ON (p.id)
                p.id AS paper_id,
                p.date_published,
                p.trending_score,
                r.id AS repository_id,
                r.num_stars
            FROM papers p
            LEFT JOIN paper_repositories pr
              ON pr.paper_id = p.id AND pr.is_official = TRUE
            LEFT JOIN repositories r ON r.id = pr.repository_id
            WHERE p.is_latest_version = TRUE
              AND p.trending_score IS NOT NULL
              AND p.trending_score_updated_at >= NOW() - INTERVAL '24 hours'
            ORDER BY p.id, r.num_stars DESC NULLS LAST
        ),
        home_repo_ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY repository_id
                    ORDER BY date_published DESC NULLS LAST, paper_id DESC
                ) AS repo_rank
            FROM home_pool
        ),
        home_top AS (
            SELECT paper_id
            FROM home_repo_ranked
            WHERE repository_id IS NULL OR repo_rank = 1
            ORDER BY trending_score DESC NULLS LAST,
                     num_stars DESC NULLS LAST, paper_id DESC
            LIMIT 30
        )
        """
    return """
        home_pool AS (
            SELECT DISTINCT ON (p.id)
                p.id AS paper_id,
                p.date_published,
                r.id AS repository_id,
                r.trending_score,
                r.num_stars
            FROM papers p
            JOIN paper_repositories pr
              ON pr.paper_id = p.id AND pr.is_official = TRUE
            JOIN repositories r
              ON r.id = pr.repository_id
             AND r.trending_score IS NOT NULL
             AND r.trending_score_updated_at >= NOW() - INTERVAL '24 hours'
            WHERE p.is_latest_version = TRUE
            ORDER BY p.id, r.trending_score DESC NULLS LAST,
                     r.num_stars DESC NULLS LAST
        ),
        home_repo_ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY repository_id
                    ORDER BY date_published DESC NULLS LAST, paper_id DESC
                ) AS repo_rank
            FROM home_pool
        ),
        home_top AS (
            SELECT paper_id
            FROM home_repo_ranked
            WHERE repo_rank = 1
            ORDER BY trending_score DESC NULLS LAST, num_stars DESC NULLS LAST
            LIMIT 30
        )
    """


def _selection_sql(mode: str) -> str:
    scoped_score = (
        "COALESCE(CASE WHEN p.trending_score_updated_at >= "
        "NOW() - INTERVAL '24 hours' THEN p.trending_score END, -1.0)"
        if mode == "composite"
        else "COALESCE(rs.repo_trending_score, -1.0)"
    )
    return f"""
    WITH
    repo_stats AS (
        SELECT
            pr.paper_id,
            MAX(r.num_stars) AS max_stars,
            MAX(
                CASE WHEN r.trending_score_updated_at >= NOW() - INTERVAL '24 hours'
                     THEN r.trending_score END
            ) AS repo_trending_score
        FROM paper_repositories pr
        JOIN repositories r ON r.id = pr.repository_id
        WHERE pr.is_official = TRUE
        GROUP BY pr.paper_id
    ),
    link_state AS (
        SELECT
            p.id AS paper_id,
            (
                SELECT r.url
                FROM paper_repositories pr
                JOIN repositories r ON r.id = pr.repository_id
                WHERE pr.paper_id = p.id AND pr.is_official = TRUE
                ORDER BY (r.source = 'hf_api') DESC, r.id
                LIMIT 1
            ) AS github_url,
            (
                SELECT pp.url
                FROM paper_project_pages ppp
                JOIN project_pages pp ON pp.id = ppp.project_page_id
                WHERE ppp.paper_id = p.id AND pp.is_official = TRUE
                ORDER BY (pp.source = 'hf_api') DESC, pp.id
                LIMIT 1
            ) AS project_page_url
        FROM papers p
    ),
    {_home_cte(mode)},
    scoped_papers AS (
        SELECT
            p.id AS paper_id,
            p.date_published,
            {scoped_score} AS trend_score,
            COALESCE(rs.max_stars, -1) AS max_stars
        FROM papers p
        LEFT JOIN repo_stats rs ON rs.paper_id = p.id
        WHERE p.is_latest_version = TRUE
    ),
    task_ranked AS (
        SELECT
            pt.task_id,
            sp.paper_id,
            ROW_NUMBER() OVER (
                PARTITION BY pt.task_id
                ORDER BY sp.trend_score DESC, sp.max_stars DESC,
                         sp.date_published DESC NULLS LAST, sp.paper_id DESC
            ) AS rn
        FROM paper_tasks pt
        JOIN scoped_papers sp ON sp.paper_id = pt.paper_id
    ),
    method_ranked AS (
        SELECT
            pm.method_id,
            sp.paper_id,
            ROW_NUMBER() OVER (
                PARTITION BY pm.method_id
                ORDER BY sp.trend_score DESC, sp.max_stars DESC,
                         sp.date_published DESC NULLS LAST, sp.paper_id DESC
            ) AS rn
        FROM paper_methods pm
        JOIN scoped_papers sp ON sp.paper_id = pm.paper_id
    ),
    conference_ranked AS (
        SELECT
            pc.conference_id,
            sp.paper_id,
            ROW_NUMBER() OVER (
                PARTITION BY pc.conference_id
                ORDER BY sp.trend_score DESC, sp.max_stars DESC,
                         sp.date_published DESC NULLS LAST, sp.paper_id DESC
            ) AS rn
        FROM paper_conferences pc
        JOIN scoped_papers sp ON sp.paper_id = pc.paper_id
    ),
    eligible AS (
        SELECT p.*, ls.github_url, ls.project_page_url
        FROM papers p
        JOIN link_state ls ON ls.paper_id = p.id
        WHERE p.source = 'arxiv'
          AND p.is_latest_version = TRUE
          AND p.arxiv_id IS NOT NULL AND p.arxiv_id <> ''
          AND p.abstract IS NOT NULL AND p.abstract <> ''
          AND p.urls_extracted = FALSE
          AND (ls.github_url IS NULL OR ls.project_page_url IS NULL)
    ),
    recent_top AS (
        SELECT id AS paper_id
        FROM eligible
        ORDER BY created_at DESC NULLS LAST,
                 date_published DESC NULLS LAST, id DESC
        LIMIT 30
    ),
    priority_union AS (
        SELECT paper_id, 1 AS priority, 'recent_hf' AS priority_source
        FROM recent_top
        UNION ALL
        SELECT paper_id, 2, 'home'
        FROM home_top
        UNION ALL
        SELECT paper_id, 3, 'task'
        FROM task_ranked WHERE rn <= 20
        UNION ALL
        SELECT paper_id, 3, 'method'
        FROM method_ranked WHERE rn <= 20
        UNION ALL
        SELECT paper_id, 3, 'conference'
        FROM conference_ranked WHERE rn <= 12
    ),
    priority_best AS (
        SELECT DISTINCT ON (pu.paper_id)
            pu.paper_id, pu.priority, pu.priority_source
        FROM priority_union pu
        JOIN eligible e ON e.id = pu.paper_id
        ORDER BY pu.paper_id, pu.priority, pu.priority_source
    ),
    fallback AS (
        SELECT
            e.id AS paper_id,
            4 AS priority,
            'backlog' AS priority_source
        FROM eligible e
        WHERE NOT EXISTS (
            SELECT 1 FROM priority_best pb WHERE pb.paper_id = e.id
        )
        ORDER BY e.date_published DESC NULLS LAST, e.id DESC
    ),
    queue AS (
        SELECT * FROM priority_best
        UNION ALL
        SELECT * FROM fallback
    )
    SELECT
        e.id AS paper_id,
        e.arxiv_id,
        e.title,
        e.abstract,
        e.github_url IS NULL AS missing_github,
        e.project_page_url IS NULL AS missing_project_page,
        e.github_url AS known_github_url,
        e.project_page_url AS known_project_page_url,
        q.priority,
        q.priority_source
    FROM queue q
    JOIN eligible e ON e.id = q.paper_id
    ORDER BY q.priority, e.date_published DESC NULLS LAST, e.id DESC
    LIMIT :limit
    """


def select_candidates(db: Session, limit: int = 100) -> list[PaperCandidate]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    mode = get_settings().trending_ranking_mode
    rows = db.execute(text(_selection_sql(mode)), {"limit": limit}).mappings()
    return [PaperCandidate.model_validate(dict(row)) for row in rows]


def canonicalize_github_url(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
        "github.com",
        "www.github.com",
    }:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not owner or not repo:
        return None
    return f"https://github.com/{owner}/{repo}"


def canonicalize_project_page_url(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or not host:
        return None
    if host in {"github.com", "huggingface.co", "arxiv.org"}:
        return None
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path or "/",
            "",
            parsed.query,
            "",
        )
    )


def _has_official_urls(db: Session, paper_id: int) -> tuple[bool, bool]:
    row = (
        db.execute(
            text("""
            SELECT
                EXISTS (
                    SELECT 1 FROM paper_repositories
                    WHERE paper_id = :paper_id AND is_official = TRUE
                ) AS has_github,
                EXISTS (
                    SELECT 1
                    FROM paper_project_pages ppp
                    JOIN project_pages pp ON pp.id = ppp.project_page_id
                    WHERE ppp.paper_id = :paper_id AND pp.is_official = TRUE
                ) AS has_project_page
        """),
            {"paper_id": paper_id},
        )
        .mappings()
        .one()
    )
    return bool(row["has_github"]), bool(row["has_project_page"])


async def persist_attempt(db: Session, attempt: AgentAttempt) -> PersistResult:
    logger = _logger()
    paper = db.execute(
        text("SELECT id FROM papers WHERE id = :id AND arxiv_id = :arxiv_id"),
        {"id": attempt.paper_id, "arxiv_id": attempt.arxiv_id},
    ).first()
    if paper is None:
        return PersistResult(
            paper_id=attempt.paper_id,
            status="skipped",
            message="paper no longer exists or identifier changed",
        )

    has_github, has_project = _has_official_urls(db, attempt.paper_id)
    github_saved = False
    project_saved = False
    validation_failed = False

    if attempt.findings and attempt.findings.github_url and not has_github:
        github_url = canonicalize_github_url(str(attempt.findings.github_url))
        if github_url and await verify_url(github_url):
            owner, name = parse_github_url(github_url)
            RepositoryService(db).create_repository_for_paper(
                paper_id=str(attempt.paper_id),
                url=github_url,
                owner=owner,
                name=name,
                num_stars=0,
                is_official=True,
                source="ai_extraction",
                skip_if_official_exists=True,
            )
            github_saved = True
        else:
            validation_failed = True
            logger.warning("Rejected GitHub URL for paper %s", attempt.paper_id)

    if attempt.findings and attempt.findings.project_page_url and not has_project:
        page_url = canonicalize_project_page_url(str(attempt.findings.project_page_url))
        if page_url and await verify_url(page_url):
            ProjectPageService(db).create_project_page_for_paper(
                paper_id=str(attempt.paper_id),
                url=page_url,
                is_official=True,
                source="ai_extraction",
                skip_if_official_exists=True,
            )
            project_saved = True
        else:
            validation_failed = True
            logger.warning("Rejected project page URL for paper %s", attempt.paper_id)

    complete = attempt.attempt_complete and not validation_failed
    if complete:
        db.execute(
            text("""
                UPDATE papers
                SET urls_extracted = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = :paper_id
            """),
            {"paper_id": attempt.paper_id},
        )
        db.commit()

    if complete:
        status = "persisted"
        message = "conclusive attempt committed"
    elif github_saved or project_saved:
        status = "partial"
        message = attempt.failure_reason or "partial findings saved; retry required"
    else:
        status = "retry"
        message = attempt.failure_reason or "attempt incomplete"

    return PersistResult(
        paper_id=attempt.paper_id,
        status=status,
        github_saved=github_saved,
        project_page_saved=project_saved,
        urls_extracted=complete,
        message=message,
    )


async def persist_many(attempts: list[AgentAttempt]) -> list[PersistResult]:
    results: list[PersistResult] = []
    with db_manager.session_local() as db:
        for attempt in attempts:
            try:
                results.append(await persist_attempt(db, attempt))
            except Exception as exc:
                db.rollback()
                results.append(
                    PersistResult(
                        paper_id=attempt.paper_id,
                        status="retry",
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
    return results


def _read_json(path: str) -> object:
    if path == "-":
        return json.load(__import__("sys").stdin)
    return json.loads(Path(path).read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    select_parser = subparsers.add_parser("select")
    select_parser.add_argument("--limit", type=int, default=100)
    persist_parser = subparsers.add_parser("persist")
    persist_parser.add_argument("--input", default="-")
    args = parser.parse_args()

    logger = _logger()
    if args.command == "select":
        logger.info("Starting cron job: extract_urls_hourly")
        with db_manager.session_local() as db:
            candidates = select_candidates(db, args.limit)
        logger.info("Papers found: %s", len(candidates))
        print(
            json.dumps([candidate.model_dump(mode="json") for candidate in candidates])
        )
        return

    attempts = [AgentAttempt.model_validate(item) for item in _read_json(args.input)]
    results = asyncio.run(persist_many(attempts))
    processed = sum(result.urls_extracted for result in results)
    github = sum(result.github_saved for result in results)
    pages = sum(result.project_page_saved for result in results)
    retries = sum(result.status == "retry" for result in results)
    both = sum(result.github_saved and result.project_page_saved for result in results)
    neither = sum(
        not result.github_saved and not result.project_page_saved for result in results
    )
    logger.info("Papers processed: %s", processed)
    logger.info("Papers with GitHub: %s", github)
    logger.info("Papers with Project Page: %s", pages)
    logger.info("Papers with both: %s", both)
    logger.info("Papers with neither: %s", neither)
    logger.info("Papers skipped (critical errors): %s", retries)
    if processed or not attempts:
        logger.info("URL Extraction completed successfully")
        logger.info("Cron job completed successfully: extract_urls_hourly")
    elif retries:
        logger.error(
            "URL extraction FAILED: Found %s papers but processed 0 due to %s critical errors",
            len(attempts),
            retries,
        )
    print(json.dumps([result.model_dump(mode="json") for result in results]))
    if attempts and processed == 0 and retries:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
