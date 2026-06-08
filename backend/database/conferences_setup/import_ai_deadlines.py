#!/usr/bin/env python3
"""
Import AI conference deadlines from the ai-deadlines YAML data.

Source: https://github.com/huggingface/ai-deadlines (src/data/conferences/*.yml).

For each conference-year block this script:
1. Upserts a `conferences` row keyed by slug ``{title-lower}-{year}`` so that
   existing proceedings rows (e.g. ``cvpr-2026``) get deadlines attached
   instead of being duplicated.
2. Sets the deadline-feature columns (tier, tags, country, city) and fills in
   missing metadata (url, start/end date, venue, location) without clobbering
   curated proceedings data.
3. Replaces the conference's `conference_deadlines` rows, computing the
   absolute UTC instant from each deadline's date + timezone.

Idempotent — safe to re-run.

Usage:
    uv run --env-file backend/keys.env \
        backend/database/conferences_setup/import_ai_deadlines.py \
        [--data-dir /path/to/ai-deadlines/src/data/conferences] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Conference, ConferenceDeadline

DEFAULT_DATA_DIR = "/root/python_projects/ai-deadlines/src/data/conferences"

# Timezone abbreviations not covered by IANA / offset parsing.
TZ_ABBREVIATIONS = {
    "AOE": -12,  # Anywhere on Earth
    "PST": -8,
    "PDT": -7,
    "EST": -5,
    "EDT": -4,
}

# Deprecated / non-canonical IANA names seen in the source data.
TZ_IANA_ALIASES = {
    "Russia/Moscow": "Europe/Moscow",
}

# Legacy single-field deadlines mapped to (type, default label).
LEGACY_DEADLINE_FIELDS = [
    ("abstract_deadline", "abstract", "Abstract Submission"),
    ("deadline", "submission", "Paper Submission"),
    ("commitment_deadline", "commitment", "Commitment"),
    ("review_release_date", "review_release", "Reviews Released"),
    ("rebuttal_period_start", "rebuttal_start", "Rebuttal Period Start"),
    ("rebuttal_period_end", "rebuttal_end", "Rebuttal Period End"),
    ("final_decision_date", "final_decision", "Final Decision"),
]


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_timezone(raw: str | None) -> timezone | ZoneInfo:
    """Resolve a source timezone string to a tzinfo. Defaults to AoE (UTC-12)."""
    if not raw:
        return timezone(timedelta(hours=-12))

    # Normalise unicode dashes (e.g. ``UTC–12:00``) to ASCII hyphen.
    cleaned = raw.strip().replace("\u2013", "-").replace("\u2014", "-")

    upper = cleaned.upper()
    if upper in TZ_ABBREVIATIONS:
        return timezone(timedelta(hours=TZ_ABBREVIATIONS[upper]))

    if upper in ("UTC", "GMT"):
        return timezone(timedelta(0))

    offset_match = re.fullmatch(
        r"(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?", upper
    )
    if offset_match:
        sign = -1 if offset_match.group(1) == "-" else 1
        hours = int(offset_match.group(2))
        minutes = int(offset_match.group(3) or 0)
        return timezone(sign * timedelta(hours=hours, minutes=minutes))

    try:
        return ZoneInfo(TZ_IANA_ALIASES.get(cleaned, cleaned))
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        print(f"  WARN: unknown timezone '{raw}', defaulting to AoE (UTC-12)")
        return timezone(timedelta(hours=-12))


def parse_deadline_instant(date_str: str | None, tz_str: str | None) -> datetime | None:
    """Parse a naive date string in its timezone and return a UTC datetime."""
    if not date_str:
        return None
    raw = str(date_str).strip()
    if not raw or raw.upper() == "TBD":
        return None

    naive: datetime | None = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if naive is None:
        print(f"  WARN: could not parse deadline date '{date_str}', skipping")
        return None

    tzinfo = parse_timezone(tz_str)
    return naive.replace(tzinfo=tzinfo).astimezone(timezone.utc)


def coerce_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def build_deadlines(block: dict) -> list[dict]:
    """Mirror ai-deadlines getAllDeadlines: new list + legacy fields, deduped."""
    conf_tz = block.get("timezone")
    collected: list[dict] = []
    seen_types: set[str] = set()

    for entry in block.get("deadlines") or []:
        if not isinstance(entry, dict):
            continue
        dtype = entry.get("type")
        collected.append(
            {
                "type": dtype,
                "label": entry.get("label"),
                "date": entry.get("date"),
                "timezone": entry.get("timezone") or conf_tz,
            }
        )
        if dtype:
            seen_types.add(dtype)

    for field, dtype, label in LEGACY_DEADLINE_FIELDS:
        if block.get(field) and dtype not in seen_types:
            collected.append(
                {
                    "type": dtype,
                    "label": label,
                    "date": block.get(field),
                    "timezone": conf_tz,
                }
            )
            seen_types.add(dtype)

    # Resolve instants and dedupe by absolute time.
    resolved: list[dict] = []
    seen_instants: set[datetime] = set()
    for item in collected:
        instant = parse_deadline_instant(item["date"], item["timezone"])
        if instant is None or instant in seen_instants:
            continue
        seen_instants.add(instant)
        resolved.append(
            {
                "type": item["type"],
                "label": item["label"],
                "deadline_at": instant,
                "timezone": item["timezone"],
            }
        )
    return resolved


def upsert_conference(db: Session, block: dict) -> Conference | None:
    title = (block.get("title") or "").strip()
    year = block.get("year")
    if not title or not year:
        print(f"  WARN: skipping block missing title/year: {block.get('id')}")
        return None

    slug = f"{slugify(title)}-{year}"
    name = f"{title} {year}"
    city = block.get("city") or None
    country = block.get("country") or None
    location = ", ".join([p for p in (city, country) if p]) or None
    tags = [str(t) for t in (block.get("tags") or []) if t]
    tier = block.get("era_rating") or None
    url = block.get("link") or None
    venue = block.get("venue") or None
    start_date = coerce_date(block.get("start"))
    end_date = coerce_date(block.get("end"))

    conference = db.query(Conference).filter(Conference.slug == slug).first()
    if conference is None:
        conference = Conference(
            name=name,
            slug=slug,
            short_name=title,
            year=int(year),
            url=url,
            start_date=start_date,
            end_date=end_date,
            venue=venue,
            location=location,
            tier=tier,
            tags=tags or None,
            country=country,
            city=city,
        )
        db.add(conference)
        db.flush()
    else:
        # Deadline feature owns these columns; always refresh them.
        conference.tier = tier
        conference.tags = tags or None
        conference.country = country
        conference.city = city
        # Fill in metadata only when missing so curated proceedings data
        # (descriptions, hero images, hf_url, etc.) is never clobbered.
        conference.url = conference.url or url
        conference.venue = conference.venue or venue
        conference.location = conference.location or location
        conference.start_date = conference.start_date or start_date
        conference.end_date = conference.end_date or end_date

    return conference


def import_data(db: Session, data_dir: Path, dry_run: bool) -> dict[str, int]:
    stats = {
        "files": 0,
        "blocks": 0,
        "conferences_upserted": 0,
        "deadlines_added": 0,
        "blocks_no_deadlines": 0,
        "skipped": 0,
    }

    yaml_files = sorted(data_dir.glob("*.yml"))
    for yaml_file in yaml_files:
        stats["files"] += 1
        with open(yaml_file, "r") as f:
            blocks = yaml.safe_load(f) or []
        if not isinstance(blocks, list):
            continue

        for block in blocks:
            if not isinstance(block, dict):
                continue
            stats["blocks"] += 1

            deadlines = build_deadlines(block)
            if not deadlines:
                stats["blocks_no_deadlines"] += 1
                continue

            if dry_run:
                stats["conferences_upserted"] += 1
                stats["deadlines_added"] += len(deadlines)
                continue

            conference = upsert_conference(db, block)
            if conference is None:
                stats["skipped"] += 1
                continue
            stats["conferences_upserted"] += 1

            # Replace deadlines for idempotency.
            db.query(ConferenceDeadline).filter(
                ConferenceDeadline.conference_id == conference.id
            ).delete()
            for d in deadlines:
                db.add(
                    ConferenceDeadline(
                        conference_id=conference.id,
                        deadline_type=d["type"],
                        label=d["label"],
                        deadline_at=d["deadline_at"],
                        timezone=d["timezone"],
                    )
                )
                stats["deadlines_added"] += 1

        if not dry_run:
            db.commit()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Import AI conference deadlines")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and count only; no DB writes",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"Data directory not found: {data_dir}")
        sys.exit(1)

    print("=" * 80)
    print("Importing AI conference deadlines" + (" (dry run)" if args.dry_run else ""))
    print(f"Source: {data_dir}")
    print("=" * 80)

    session = db_manager.session_local()
    try:
        stats = import_data(session, data_dir, args.dry_run)
        print("\n" + "=" * 80)
        print("Import complete" if not args.dry_run else "Dry run complete")
        print("=" * 80)
        for key, value in stats.items():
            print(f"  {key}: {value}")
    except Exception as exc:
        session.rollback()
        print(f"Import failed: {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
