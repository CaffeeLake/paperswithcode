#!/usr/bin/env python3
"""
Merge GitHub repository rows that differ only by URL casing.

GitHub repo URLs are case-insensitive; duplicate rows cause the same repo to
appear twice on paper pages. This script:
1. Groups repositories by lower(url) for github.com URLs
2. Keeps the best canonical row (normalized lowercase URL, then most stars)
3. Reassigns paper_repositories and repository_star_history to the keeper
4. Deletes duplicate repository rows
"""

from __future__ import annotations

import sys

from sqlalchemy import func, text

from backend.database.connection import db_manager
from backend.models.database import PaperRepository
from backend.models.database import Repository
from backend.models.database import RepositoryStarHistory
from backend.utils.github_utils import normalize_github_url, parse_github_url


def pick_keeper(repos: list[Repository]) -> Repository:
    normalized = normalize_github_url

    def score(repo: Repository) -> tuple:
        canon = normalized(repo.url)
        is_canonical = repo.url == canon if canon else False
        return (is_canonical, repo.num_stars or 0, -repo.id)

    return max(repos, key=score)


def dedupe_github_repositories() -> dict[str, int]:
    session = db_manager.session_local()
    stats = {
        "duplicate_groups": 0,
        "repos_removed": 0,
        "paper_links_merged": 0,
        "paper_links_reassigned": 0,
        "star_history_moved": 0,
        "star_history_dropped": 0,
    }

    try:
        groups = session.execute(
            text(
                """
                SELECT lower(url) AS url_key
                FROM repositories
                WHERE url ILIKE 'https://github.com/%'
                   OR url ILIKE 'http://github.com/%'
                GROUP BY lower(url)
                HAVING COUNT(*) > 1
                """
            )
        ).fetchall()

        stats["duplicate_groups"] = len(groups)

        for group_idx, (url_key,) in enumerate(groups, start=1):
            repos = (
                session.query(Repository)
                .filter(func.lower(Repository.url) == url_key)
                .order_by(Repository.id)
                .all()
            )
            if len(repos) < 2:
                continue

            keeper = pick_keeper(repos)
            canon_url = normalize_github_url(keeper.url) or keeper.url.lower()
            keeper.url = canon_url
            parsed_owner, parsed_name = parse_github_url(canon_url)
            keeper.owner = keeper.owner or parsed_owner
            keeper.name = keeper.name or parsed_name
            keeper.num_stars = max(r.num_stars or 0 for r in repos)

            for dup in repos:
                if dup.id == keeper.id:
                    continue

                for link in (
                    session.query(PaperRepository)
                    .filter(PaperRepository.repository_id == dup.id)
                    .all()
                ):
                    existing = (
                        session.query(PaperRepository)
                        .filter(
                            PaperRepository.paper_id == link.paper_id,
                            PaperRepository.repository_id == keeper.id,
                        )
                        .first()
                    )
                    if existing:
                        existing.is_official = existing.is_official or link.is_official
                        session.delete(link)
                        stats["paper_links_merged"] += 1
                    else:
                        session.add(
                            PaperRepository(
                                paper_id=link.paper_id,
                                repository_id=keeper.id,
                                is_official=link.is_official,
                            )
                        )
                        session.delete(link)
                        stats["paper_links_reassigned"] += 1
                    session.flush()

                for history in (
                    session.query(RepositoryStarHistory)
                    .filter(RepositoryStarHistory.repository_id == dup.id)
                    .all()
                ):
                    conflict = (
                        session.query(RepositoryStarHistory)
                        .filter(
                            RepositoryStarHistory.repository_id == keeper.id,
                            RepositoryStarHistory.snapshot_at == history.snapshot_at,
                        )
                        .first()
                    )
                    if conflict:
                        session.delete(history)
                        stats["star_history_dropped"] += 1
                    else:
                        session.add(
                            RepositoryStarHistory(
                                repository_id=keeper.id,
                                num_stars=history.num_stars,
                                snapshot_at=history.snapshot_at,
                                created_at=history.created_at,
                            )
                        )
                        session.delete(history)
                        stats["star_history_moved"] += 1
                    session.flush()

                session.delete(dup)
                stats["repos_removed"] += 1

            if group_idx % 200 == 0:
                session.commit()
                print(f"  committed through group {group_idx}/{len(groups)}...")

        session.commit()
        return stats
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    print("=" * 80)
    print("Deduplicating GitHub repositories (case-insensitive URL merge)")
    print("=" * 80)

    stats = dedupe_github_repositories()

    print(f"Duplicate URL groups processed: {stats['duplicate_groups']:,}")
    print(f"Repository rows removed:          {stats['repos_removed']:,}")
    print(f"Paper links merged:               {stats['paper_links_merged']:,}")
    print(f"Paper links reassigned:           {stats['paper_links_reassigned']:,}")
    print(f"Star history rows moved:          {stats['star_history_moved']:,}")
    print(f"Star history rows dropped:        {stats['star_history_dropped']:,}")
    print("=" * 80)

    session = db_manager.session_local()
    try:
        remaining = session.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                    SELECT lower(url)
                    FROM repositories
                    WHERE url ILIKE 'https://github.com/%'
                       OR url ILIKE 'http://github.com/%'
                    GROUP BY lower(url)
                    HAVING COUNT(*) > 1
                ) x
                """
            )
        ).scalar()
        print(f"Remaining duplicate groups: {remaining}")
        if remaining:
            sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
