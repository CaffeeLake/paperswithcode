"""Index and tag the curated top-100 3D Pose Estimation paper ledger.

The list combines legacy Papers With Code coverage, Semantic Scholar citation
signals, local trending/repository signals, comparison-table expansion, and an
explicit recent/animal-pose slice. Missing arXiv papers are fetched in batches
from the official arXiv API before every selected paper receives a manual task
link.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/tasks_setup/add_3d_pose_estimation_coverage.py
"""

from __future__ import annotations

import time
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.models.database import Paper as DBPaper
from backend.services.paper_service import PaperService

TASK_SLUG = "3d-pose-estimation"

CURATED_ARXIV_IDS = (
    "1907.00837",
    "1607.08128",
    "1705.03098",
    "1909.12828",
    "1611.09813",
    "1811.11742",
    "2103.10455",
    "2305.20091",
    "1704.02447",
    "2008.12272",
    "1808.05942",
    "1612.06524",
    "2103.16507",
    "2210.06551",
    "2008.03713",
    "1712.03453",
    "1701.00295",
    "2203.00859",
    "1805.04095",
    "1907.11346",
    "1511.09439",
    "2111.12707",
    "1611.09010",
    "1803.09722",
    "2011.08627",
    "1903.02330",
    "1711.08585",
    "2105.04668",
    "2103.14304",
    "2309.17448",
    "2207.06400",
    "1712.01337",
    "2312.07531",
    "2103.16385",
    "1902.09868",
    "1909.01203",
    "1905.04266",
    "2303.16160",
    "2105.02465",
    "2004.13985",
    "1904.05547",
    "1607.02046",
    "2007.09389",
    "2310.16288",
    "1604.02703",
    "2005.04551",
    "2203.07628",
    "2108.06428",
    "1901.04111",
    "2303.17472",
    "2402.14654",
    "2104.14643",
    "1904.04812",
    "2207.13820",
    "2004.11822",
    "2004.03686",
    "2211.16940",
    "2307.05853",
    "1509.06720",
    "1803.04775",
    "2007.07227",
    "2303.11579",
    "1904.01324",
    "2006.07778",
    "1804.01110",
    "2111.04076",
    "2501.01770",
    "2108.07181",
    "2107.13788",
    "2011.14679",
    "2404.16752",
    "2107.07797",
    "2404.00658",
    "2303.18246",
    "2503.21751",
    "2008.11469",
    "2303.11726",
    "2004.02186",
    "2211.15692",
    "1908.07201",
    "2503.07499",
    "2602.05755",
    "2501.02771",
    "2503.23331",
    "2506.02853",
    "2509.00649",
    "2501.05264",
    "2508.17239",
    "2507.19852",
    "2211.12497",
    "2511.08872",
    "2508.14431",
    "2508.06757",
    "2103.13282",
    "2308.11737",
    "2407.06141",
    "2409.00449",
    "2309.05073",
    "2009.05389",
)

# Exact-phrase backfill produced these clear false positives for the narrower
# articulated-body task. Remove only their auto links; preserve all other tags.
AUTO_FALSE_POSITIVES = (
    "2212.04420",  # speech-to-motion generation
    "2211.03295",  # general-purpose visual backbone
    "2003.12753",  # garment reconstruction
    "2303.02760",  # Human-Art is a 2D pose/detection dataset paper
    "2402.09883",  # rotoscope animation / video segmentation
    "2511.18173",  # pose-conditioned egocentric video generation
    "2407.04384",  # category-level object pose
    "2605.31597",  # semantic object correspondence
    "2308.10146",  # hand-only 3D pose
    "2503.20220",  # category-level car mesh / rigid pose
    "2412.04464",  # deformable-object point-map reconstruction
    "2602.06211",  # rigid drone pose
    "2603.02936",  # rigid drone-gate pose
    "2509.06426",  # biomechanics analysis consuming pose estimates
    "2408.00672",  # coaching feedback / video generation
    "2508.10934",  # camera pose and depth estimation
    "2506.21552",  # pose-conditioned video prediction
    "2502.19769",  # hand-object understanding
    "2410.19846",  # 3D pose of orchard fruit, not articulated-body pose
    "2407.13083",  # acoustic rendering that consumes an input body pose
    "2309.08480",  # text-driven pose correction / generation
    "2306.08103",  # diffusion image generation using object-pose annotations
)


class ArxivMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        item = dict(attrs)
        name = item.get("name")
        content = item.get("content")
        if name and name.startswith("citation_") and content:
            self.values.setdefault(name, []).append(content)


def _fetch_metadata(arxiv_ids: list[str]) -> dict[str, dict]:
    metadata: dict[str, dict] = {}
    for arxiv_id in arxiv_ids:
        request = urllib.request.Request(
            f"https://arxiv.org/abs/{arxiv_id}",
            headers={"User-Agent": "paperswithcode.co task curation/1.0"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            parser = ArxivMetaParser()
            parser.feed(response.read().decode("utf-8"))
        values = parser.values
        authors = []
        for author in values.get("citation_author", []):
            parts = [part.strip() for part in author.split(",", 1)]
            authors.append(" ".join(reversed(parts)) if len(parts) == 2 else author)
        metadata[arxiv_id] = {
            "arxiv_id": arxiv_id,
            "version": "v1",
            "title": values["citation_title"][0],
            "abstract": values.get("citation_abstract", [None])[0],
            "date_published": datetime.strptime(
                values["citation_date"][0], "%Y/%m/%d"
            ).date(),
            "primary_category": None,
            "all_categories": None,
            "authors": authors,
        }
        time.sleep(0.2)
    return metadata


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        existing = {
            row[0]
            for row in db.execute(
                text(
                    """
                    SELECT DISTINCT arxiv_id
                    FROM papers
                    WHERE arxiv_id = ANY(:ids)
                    """
                ),
                {"ids": list(CURATED_ARXIV_IDS)},
            )
        }
        missing = [
            arxiv_id for arxiv_id in CURATED_ARXIV_IDS if arxiv_id not in existing
        ]
        metadata = _fetch_metadata(missing)
        unresolved = sorted(set(missing) - set(metadata))
        if unresolved:
            raise RuntimeError(f"arXiv metadata unresolved: {unresolved}")

        paper_service = PaperService(db)
        created = 0
        for arxiv_id in missing:
            item = metadata[arxiv_id]
            paper = DBPaper(
                arxiv_id=arxiv_id,
                version=item["version"],
                title=item["title"],
                abstract=item["abstract"],
                date_published=item["date_published"],
                primary_category=item["primary_category"],
                all_categories=item["all_categories"],
                is_latest_version=True,
                citation_count=0,
                urls_extracted=False,
            )
            db.add(paper)
            db.flush()
            paper_service._replace_paper_authors(paper.id, item["authors"])
            created += 1

        task_id = db.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"), {"slug": TASK_SLUG}
        ).scalar_one()
        db.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                SELECT p.id, :task_id, 'manual'
                FROM papers p
                WHERE p.arxiv_id = ANY(:ids) AND p.is_latest_version
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"task_id": task_id, "ids": list(CURATED_ARXIV_IDS)},
        )
        db.execute(
            text(
                """
                DELETE FROM paper_tasks pt
                USING papers p
                WHERE pt.paper_id = p.id
                  AND pt.task_id = :task_id
                  AND pt.source = 'auto'
                  AND p.arxiv_id = ANY(:ids)
                """
            ),
            {"task_id": task_id, "ids": list(AUTO_FALSE_POSITIVES)},
        )
        db.commit()
        tagged = db.execute(
            text("SELECT count(*) FROM paper_tasks WHERE task_id = :task_id"),
            {"task_id": task_id},
        ).scalar_one()
        print(f"created={created} curated=100 task_total={tagged}")
    finally:
        db.close()
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
