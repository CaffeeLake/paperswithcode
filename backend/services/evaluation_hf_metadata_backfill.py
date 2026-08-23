"""Conservative one-time Hugging Face metadata planning for evaluations."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from huggingface_hub.errors import HfHubHTTPError

from backend.services.evaluation_entry_identity import (
    EvaluationDisplayEntryKey,
    evaluation_display_entry_key,
    serialize_evaluation_display_entry_key,
)

_REPO_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_SEPARATOR = re.compile(r"[\s_.-]+")


def canonical_hf_model_url(value: str | None) -> str | None:
    """Return an official Hub model root URL, rejecting every other URL shape."""
    if not value:
        return None
    if value != value.strip():
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != "huggingface.co"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    parts = parsed.path.split("/")
    if (
        len(parts) != 3
        or parts[0] != ""
        or not all(_REPO_PART.fullmatch(part) for part in parts[1:])
    ):
        return None
    return f"https://huggingface.co/{parts[1]}/{parts[2]}"


def normalized_model_variant(value: str | None) -> str:
    """Compare separator variants without losing alphanumeric token boundaries."""
    if not value:
        return ""
    return "\x1f".join(
        part for part in _SEPARATOR.split(value.casefold().strip()) if part
    )


def _repo_id(url: str) -> str:
    return url.removeprefix("https://huggingface.co/")


def _normalized_repo_name(repo_id: str) -> str:
    return normalized_model_variant(repo_id.rsplit("/", 1)[-1])


def _same_repository(left: str, right: str) -> bool:
    return left.casefold() == right.casefold()


def _direct_repo_id(model_name: str | None) -> str | None:
    if not model_name:
        return None
    parts = model_name.strip().split("/")
    if len(parts) != 2 or not all(_REPO_PART.fullmatch(part) for part in parts):
        return None
    return "/".join(parts)


def _safetensors_total(model_info: Any) -> int | None:
    safetensors = getattr(model_info, "safetensors", None)
    total = (
        safetensors.get("total")
        if isinstance(safetensors, dict)
        else getattr(safetensors, "total", None)
    )
    return total if isinstance(total, int) and total >= 0 else None


@dataclass(frozen=True)
class EvaluationRow:
    id: int
    paper_id: int
    task_id: int
    dataset_id: int
    model_name: str | None
    harness: str | None
    hf_model_url: str | None
    num_parameters: int | None


@dataclass(frozen=True)
class MetadataProposal:
    hf_model_url: str | None = None
    num_parameters: int | None = None


@dataclass
class BackfillPlan:
    proposals: dict[int, MetadataProposal] = field(default_factory=dict)
    sibling_url_conflicts: dict[str, list[int]] = field(default_factory=dict)
    sibling_count_conflicts: dict[str, list[int]] = field(default_factory=dict)
    ambiguous_matches: dict[str, list[str]] = field(default_factory=dict)
    unavailable_repositories: list[str] = field(default_factory=list)
    missing_safetensors: list[str] = field(default_factory=list)
    unchanged_rows: list[int] = field(default_factory=list)
    sibling_groups: dict[str, list[int]] = field(default_factory=dict)


class EvaluationMetadataBackfill:
    """Builds a bounded, fill-only plan before any caller writes a row."""

    def __init__(
        self, lookup_repository: Callable[[str], Any], *, max_lookups: int = 250
    ):
        self.lookup_repository = lookup_repository
        self.max_lookups = max_lookups

    def plan(
        self, rows: Iterable[EvaluationRow], paper_hf_models: dict[int, list[str]]
    ) -> BackfillPlan:
        rows = list(rows)
        result = BackfillPlan()
        groups: dict[EvaluationDisplayEntryKey, list[EvaluationRow]] = defaultdict(list)
        for row in rows:
            if row.model_name:
                groups[
                    evaluation_display_entry_key(
                        row.paper_id,
                        row.task_id,
                        row.dataset_id,
                        row.model_name,
                        row.harness,
                    )
                ].append(row)
            else:
                result.unchanged_rows.append(row.id)

        repo_metadata: dict[str, Any | None] = {}

        def lookup(repo_id: str) -> Any | None:
            cache_key = repo_id.casefold()
            if cache_key in repo_metadata:
                return repo_metadata[cache_key]
            if len(repo_metadata) >= self.max_lookups:
                result.unavailable_repositories.append(f"{repo_id}:lookup_limit")
                repo_metadata[cache_key] = None
                return None
            try:
                repo_metadata[cache_key] = self.lookup_repository(repo_id)
            except HfHubHTTPError:
                repo_metadata[cache_key] = None
                result.unavailable_repositories.append(repo_id)
            return repo_metadata[cache_key]

        for entry_key, siblings in groups.items():
            paper_id, _task_id, _dataset_id, model_name, _harness = entry_key
            sibling_ids = [row.id for row in siblings]
            model_key = normalized_model_variant(model_name)
            group_id = serialize_evaluation_display_entry_key(entry_key)
            result.sibling_groups[group_id] = sibling_ids
            urls_by_repo: dict[str, str] = {}
            for row in siblings:
                url = canonical_hf_model_url(row.hf_model_url)
                if url:
                    urls_by_repo.setdefault(_repo_id(url).casefold(), url)
            counts = {
                row.num_parameters for row in siblings if row.num_parameters is not None
            }
            if len(urls_by_repo) > 1:
                result.sibling_url_conflicts[group_id] = sibling_ids
                continue
            if len(counts) > 1:
                result.sibling_count_conflicts[group_id] = sibling_ids
                result.unchanged_rows.extend(sibling_ids)
                continue

            selected_url = next(iter(urls_by_repo.values()), None)
            selected_count = next(iter(counts), None) if len(counts) == 1 else None
            if selected_url is None:
                candidates = set()
                for paper_url in paper_hf_models.get(paper_id, []):
                    url = canonical_hf_model_url(paper_url)
                    if url and _normalized_repo_name(_repo_id(url)) == model_key:
                        candidates.add(_repo_id(url))
                if direct_repo := _direct_repo_id(siblings[0].model_name):
                    candidates.add(direct_repo)
                if len(candidates) != 1:
                    if candidates:
                        result.ambiguous_matches[group_id] = sorted(candidates)
                    result.unchanged_rows.extend(sibling_ids)
                    continue
                candidate = next(iter(candidates))
                model_info = lookup(candidate)
                if model_info is None:
                    result.unchanged_rows.extend(sibling_ids)
                    continue
                canonical_id = getattr(model_info, "id", None)
                if not isinstance(canonical_id, str) or not _same_repository(
                    canonical_id, candidate
                ):
                    result.unavailable_repositories.append(candidate)
                    result.unchanged_rows.extend(sibling_ids)
                    continue
                selected_url = f"https://huggingface.co/{canonical_id}"
            model_info = None
            if selected_count is None:
                selected_repo = _repo_id(selected_url)
                model_info = lookup(selected_repo)
                canonical_id = getattr(model_info, "id", None)
                if (
                    model_info is not None
                    and isinstance(canonical_id, str)
                    and _same_repository(canonical_id, selected_repo)
                ):
                    selected_count = _safetensors_total(model_info)
                    if selected_count is None:
                        result.missing_safetensors.append(selected_repo)
                elif model_info is not None:
                    result.unavailable_repositories.append(selected_repo)

            for row in siblings:
                proposal = MetadataProposal(
                    hf_model_url=selected_url if row.hf_model_url is None else None,
                    num_parameters=selected_count
                    if row.num_parameters is None
                    else None,
                )
                if (
                    proposal.hf_model_url is not None
                    or proposal.num_parameters is not None
                ):
                    result.proposals[row.id] = proposal
                else:
                    result.unchanged_rows.append(row.id)

        result.unavailable_repositories = sorted(set(result.unavailable_repositories))
        result.missing_safetensors = sorted(set(result.missing_safetensors))
        result.unchanged_rows = sorted(
            set(result.unchanged_rows) - set(result.proposals)
        )
        return result


def apply_fill_only(
    rows_by_id: dict[int, Any], proposals: dict[int, MetadataProposal]
) -> list[int]:
    """Apply a reviewed plan without overwriting metadata added since dry-run."""
    changed: list[int] = []
    for row_id, proposal in proposals.items():
        row = rows_by_id.get(row_id)
        if row is None:
            continue
        row_changed = False
        if proposal.hf_model_url is not None and row.hf_model_url is None:
            row.hf_model_url = proposal.hf_model_url
            row_changed = True
        if proposal.num_parameters is not None and row.num_parameters is None:
            row.num_parameters = proposal.num_parameters
            row_changed = True
        if row_changed:
            changed.append(row_id)
    return changed


def verify_applied_fill_only(
    rows_by_id: dict[int, Any], proposals: dict[int, MetadataProposal]
) -> None:
    """Fail closed if an apply did not leave each proposed field in place."""
    for row_id, proposal in proposals.items():
        row = rows_by_id.get(row_id)
        if row is None:
            continue
        if (
            proposal.hf_model_url is not None
            and row.hf_model_url != proposal.hf_model_url
        ):
            raise RuntimeError(
                f"evaluation {row_id} did not retain its proposed Hub URL"
            )
        if (
            proposal.num_parameters is not None
            and row.num_parameters != proposal.num_parameters
        ):
            raise RuntimeError(f"evaluation {row_id} did not retain its proposed count")


def verify_sibling_consistency(
    rows_by_id: dict[int, Any], sibling_groups: dict[str, list[int]]
) -> int:
    """Verify that applied groups remain unambiguous after the write transaction."""
    verified_groups = 0
    for group_id, row_ids in sibling_groups.items():
        rows = [rows_by_id[row_id] for row_id in row_ids if row_id in rows_by_id]
        urls = {
            _repo_id(url).casefold()
            for row in rows
            if (url := canonical_hf_model_url(row.hf_model_url))
        }
        counts = {row.num_parameters for row in rows if row.num_parameters is not None}
        if len(urls) > 1:
            raise RuntimeError(f"sibling URL conflict after apply for {group_id}")
        if len(counts) > 1:
            raise RuntimeError(f"sibling count conflict after apply for {group_id}")
        verified_groups += 1
    return verified_groups
