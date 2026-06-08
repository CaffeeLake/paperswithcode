"""Pick a Hugging Face dataset URL for a benchmark from source-paper HF artifacts."""

from __future__ import annotations

import re
from typing import Optional

from backend.utils.hf_utils import normalize_hf_artifact_url


def _normalize_match_key(value: str) -> str:
    """Lowercase alphanumeric key for fuzzy name/slug/repo matching."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def hf_dataset_repo_to_url(repo_id: str) -> Optional[str]:
    """Convert an HF dataset repo id (org/name) to a canonical dataset URL."""
    if not repo_id or "/" not in repo_id:
        return None
    return normalize_hf_artifact_url(f"https://huggingface.co/datasets/{repo_id}")


def pick_hf_dataset_url(
    *,
    dataset_name: str,
    dataset_slug: Optional[str],
    hf_dataset_repo_ids: list[str],
) -> Optional[str]:
    """
    Choose one HF dataset URL for a benchmark from linked repo ids.

    - Exactly one repo id -> use it.
    - Multiple repo ids -> use only when one clearly matches name or slug.
    - Otherwise -> None (ambiguous).
    """
    repo_ids = [r for r in (hf_dataset_repo_ids or []) if r and "/" in r]
    urls = []
    for repo_id in repo_ids:
        url = hf_dataset_repo_to_url(repo_id)
        if url and url not in urls:
            urls.append(url)

    if not urls:
        return None
    if len(urls) == 1:
        return urls[0]

    name_key = _normalize_match_key(dataset_name)
    slug_key = _normalize_match_key(dataset_slug or "")
    keys = {k for k in (name_key, slug_key) if k}
    if not keys:
        return None

    matched: list[str] = []
    for repo_id in repo_ids:
        url = hf_dataset_repo_to_url(repo_id)
        if not url:
            continue
        repo_name = repo_id.split("/", 1)[-1]
        repo_key = _normalize_match_key(repo_name)
        full_key = _normalize_match_key(repo_id.replace("/", "-"))
        if repo_key in keys or full_key in keys:
            if url not in matched:
                matched.append(url)

    if len(matched) == 1:
        return matched[0]
    return None
