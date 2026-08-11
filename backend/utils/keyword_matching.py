"""
Shared keyword matching utilities for linking papers to tasks and methods.

This module provides two matching strategies:
1. Simple matching: For tasks - all matching keywords are tagged
2. Longest-match priority: For methods - prevents overlapping matches (e.g., GPT-4 takes precedence over GPT)

Case-Sensitivity Rules:
- If a keyword contains at least 1 capital letter: case-sensitive matching
  * Examples: "BERT", "GPT-4", "ResNet", "VLM"
  * `find_matching_items_simple` (tasks) uses word-boundary matching with an
    optional trailing 's', so "NER" matches "NER" / "NERs" but NOT "FINER".
  * `find_matching_items_longest_match` (methods) uses substring matching to
    catch plurals (VLMs, GANs) and hierarchical compounds (LVLMs, OpenCLIP);
    the longest-match disambiguation handles overlaps.
  * Case sensitivity itself prevents false positives like CLIP vs clip.
- If a keyword is all lowercase: case-insensitive matching
  * Examples: "transformer", "attention", "object detection"
  * Uses word boundary matching to prevent false matches (e.g., "transformed" when looking for "transformer")
  * Allows an optional trailing 's' so the keyword "large language model" also
    catches the very common plural form "large language models". The optional
    's' sits inside the trailing `\b`, so partial-word false positives like
    "transformed" (when searching "transformer") are still rejected.
"""

import re
from typing import Dict, List, Set, Tuple
from collections import defaultdict


def is_case_sensitive_keyword(keyword: str) -> bool:
    """
    Determine if a keyword should use case-sensitive matching.

    Rule: If a keyword contains at least 1 capital letter, it's case-sensitive.
          If keyword is all lowercase, it's case-insensitive.

    Args:
        keyword: The keyword to check

    Returns:
        True if case-sensitive matching should be used
    """
    return any(c.isupper() for c in keyword)


def create_keyword_patterns(
    items: List[Dict],
) -> Tuple[Dict[str, List[int]], Dict[str, List[int]]]:
    """
    Create lookup structures for keyword matching (simple version for tasks).

    Args:
        items: List of dicts with 'id' and 'keywords' keys

    Returns:
        (case_sensitive_patterns, case_insensitive_patterns)
        Each pattern dict maps keyword -> list of item IDs
    """
    case_sensitive = defaultdict(list)
    case_insensitive = defaultdict(list)

    for item in items:
        item_id = item["id"]

        # Parse keywords
        keywords_list = [k.strip() for k in item["keywords"].split(",") if k.strip()]

        for keyword in keywords_list:
            if is_case_sensitive_keyword(keyword):
                case_sensitive[keyword].append(item_id)
            else:
                case_insensitive[keyword.lower()].append(item_id)

    return dict(case_sensitive), dict(case_insensitive)


def create_keyword_patterns_with_metadata(
    items: List[Dict],
) -> Tuple[Dict[str, List[Dict]], Dict[str, List[Dict]]]:
    """
    Create lookup structures for keyword matching (advanced version for methods with longest-match).

    Args:
        items: List of dicts with 'id', 'name', and 'keywords' keys

    Returns:
        (case_sensitive_patterns, case_insensitive_patterns)
        Each pattern dict maps keyword -> list of item info dicts with metadata
    """
    case_sensitive = defaultdict(list)
    case_insensitive = defaultdict(list)

    for item in items:
        item_id = item["id"]
        item_name = item.get("name", "")

        # Parse keywords
        keywords_list = [k.strip() for k in item["keywords"].split(",") if k.strip()]

        for keyword in keywords_list:
            item_info = {
                "id": item_id,
                "name": item_name,
                "keyword": keyword,
                "keyword_len": len(keyword),
            }

            if is_case_sensitive_keyword(keyword):
                case_sensitive[keyword].append(item_info)
            else:
                case_insensitive[keyword.lower()].append(item_info)

    return dict(case_sensitive), dict(case_insensitive)


# When the superseding task matches, drop the generic/subsuming task tag.
TASK_SUPERSESSION_RULES: tuple[tuple[str, str], ...] = (
    ("3d-object-detection", "object-detection"),
    ("video-frame-interpolation", "optical-flow"),
    ("video-matting", "image-matting"),
)

# Image and video task phrases frequently co-occur in related-work sections.
# When a paper's title clearly identifies only one modality, prefer that task
# over an automatic tag caused by the abstract mentioning the neighboring
# modality. Titles that explicitly cover both modalities remain unchanged.
# When neither modality is named in the title, keep both only for coordinated
# contribution/evaluation evidence; genuinely broad edge cases can be manually
# tagged.
_MODALITY_TASK_PAIRS: tuple[tuple[str, str], ...] = (
    ("image-editing", "video-editing"),
    ("image-generation", "video-generation"),
    ("image-understanding", "video-understanding"),
)

_TITLE_TASK_PATTERNS: dict[str, tuple[str, ...]] = {
    "image-editing": (
        r"\bimage[- ]edit(?:ing|s)?\b",
        r"\btext[- ]guided image edit(?:ing|s)?\b",
        r"\binstruction[- ](?:based|guided) image edit(?:ing|s)?\b",
        r"\bimage[- ]to[- ]image edit(?:ing|s)?\b",
    ),
    "video-editing": (
        r"\bvideo[- ]edit(?:ing|s)?\b",
        r"\btext[- ]guided video edit(?:ing|s)?\b",
        r"\binstruction[- ](?:based|guided) video edit(?:ing|s)?\b",
        r"\bvideo[- ]to[- ]video edit(?:ing|s)?\b",
    ),
    "image-generation": (
        r"\bimage generation\b",
        r"\btext[- ]to[- ]image\b",
        r"\bimage synthesis\b",
    ),
    "video-generation": (
        r"\bvideo generation\b",
        r"\btext[- ]to[- ]video\b",
        r"\bimage[- ]to[- ]video\b",
        r"\bvideo synthesis\b",
    ),
    "image-understanding": (
        r"\bimage understanding\b",
        r"\bimage reasoning\b",
        r"\bimage perception\b",
        r"\bimage (?:visual )?question answering\b",
    ),
    "video-understanding": (
        r"\bvideo understanding\b",
        r"\bvideo reasoning\b",
        r"\bvideo perception\b",
        r"\bvideo (?:visual )?question answering\b",
        r"\bvideo[- ]language model\b",
        r"\bvideo LLM\b",
    ),
}

_JOINT_TITLE_TASK_PATTERNS: dict[tuple[str, str], tuple[str, ...]] = {
    ("image-editing", "video-editing"): (
        r"\b(?:image(?:s)?\s+(?:and|&|/)\s+video(?:s)?|video(?:s)?\s+(?:and|&|/)\s+image(?:s)?)\s+edit(?:ing|s)?\b",
        r"\bimage edit(?:ing|s)?\s+(?:and|&|/)\s+video edit(?:ing|s)?\b",
    ),
    ("image-generation", "video-generation"): (
        r"\b(?:image(?:s)?\s+(?:and|&|/)\s+video(?:s)?|video(?:s)?\s+(?:and|&|/)\s+image(?:s)?)\s+(?:generation|synthesis)\b",
        r"\bimage generation\s+(?:and|&|/)\s+video generation\b",
    ),
    ("image-understanding", "video-understanding"): (
        r"\b(?:image(?:s)?\s+(?:and|&|/)\s+video(?:s)?|video(?:s)?\s+(?:and|&|/)\s+image(?:s)?)\s+(?:understanding|reasoning|perception)\b",
        r"\bimage understanding\s+(?:and|&|/)\s+video understanding\b",
    ),
}


def _has_title_task_signal(title: str, task_slug: str) -> bool:
    """Return whether a title explicitly names a modality-specific task."""
    return any(
        re.search(pattern, title, re.IGNORECASE)
        for pattern in _TITLE_TASK_PATTERNS[task_slug]
    )


_JOINT_TASK_EVIDENCE_PATTERN = re.compile(
    r"\b(?:we\s+stud(?:y|ied)|propos\w*|introduc\w*|present\w*|achiev\w*|evaluat\w*|"
    r"experiment\w*|demonstrat\w*|support\w*|generaliz\w*|appl(?:y|ies|ied)|"
    r"validat\w*|outperform\w*|cover\w*|encompass\w*)\b",
    re.IGNORECASE,
)
_JOINT_TASK_BACKGROUND_PATTERN = re.compile(
    r"\b(?:existing|prior|recent)\b|"
    r"\b(?:models?|transformers?|MLLMs?|DiTs?)\b.{0,80}\b(?:have|has)\s+"
    r"(?:already\s+)?(?:achieved|demonstrated|enabled)\b",
    re.IGNORECASE,
)


def _has_joint_task_evidence(text: str, task_pair: tuple[str, str]) -> bool:
    """Return whether a sentence claims work on both modality tasks."""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if _JOINT_TASK_BACKGROUND_PATTERN.search(sentence):
            continue
        if not _JOINT_TASK_EVIDENCE_PATTERN.search(sentence):
            continue
        if any(
            re.search(pattern, sentence, re.IGNORECASE)
            for pattern in _JOINT_TITLE_TASK_PATTERNS[task_pair]
        ):
            return True
    return False


def _resolve_image_video_task_conflicts(
    matched_task_ids: Set[int],
    slug_to_id: Dict[str, int],
    text: str,
    title: str,
) -> Set[int]:
    """Prefer the single image/video modality clearly identified by a title."""
    result = set(matched_task_ids)
    title_lower = title.lower()
    title_has_image = bool(re.search(r"\bimages?\b", title_lower))
    title_has_video = bool(re.search(r"\bvideos?\b", title_lower))

    for image_slug, video_slug in _MODALITY_TASK_PAIRS:
        image_id = slug_to_id.get(image_slug)
        video_id = slug_to_id.get(video_slug)
        if image_id not in result or video_id not in result:
            continue

        if any(
            re.search(pattern, title, re.IGNORECASE)
            for pattern in _JOINT_TITLE_TASK_PATTERNS[(image_slug, video_slug)]
        ):
            continue

        image_signal = _has_title_task_signal(title, image_slug)
        video_signal = _has_title_task_signal(title, video_slug)
        if image_signal != video_signal:
            result.discard(video_id if image_signal else image_id)
        elif title_has_image != title_has_video:
            result.discard(video_id if title_has_image else image_id)
        elif _has_joint_task_evidence(text, (image_slug, video_slug)):
            continue
        else:
            result.discard(image_id)
            result.discard(video_id)

    return result


# Strong Image Classification signals — explicit task/benchmark mentions that justify
# keeping an image-classification tag even when an audio-classification tag also matched.
_STRONG_IMAGE_CLASSIFICATION_PATTERNS: tuple[str, ...] = (
    r"\bimage classifications?\b",
    r"\bcifar-?10\b",
    r"\bcifar-?100\b",
    r"\bilsvrc\b",
    r"\bvtab\b",
)


def has_strong_image_classification_signal(text: str) -> bool:
    """Return True when text explicitly signals an image-classification benchmark/task."""
    if not text:
        return False
    text_lower = text.lower()
    return any(
        re.search(pattern, text_lower)
        for pattern in _STRONG_IMAGE_CLASSIFICATION_PATTERNS
    )


def apply_task_supersession_rules(
    matched_task_ids: Set[int],
    slug_to_id: Dict[str, int],
    text: str | None = None,
    title: str | None = None,
) -> Set[int]:
    """Remove subsumed task IDs when a more specific task also matched."""
    result = set(matched_task_ids)
    for superseding_slug, excluded_slug in TASK_SUPERSESSION_RULES:
        superseding_id = slug_to_id.get(superseding_slug)
        excluded_id = slug_to_id.get(excluded_slug)
        if superseding_id in result and excluded_id is not None:
            result.discard(excluded_id)

    # Audio papers often cite ViT/ImageNet/ResNet as cross-modal pretraining baselines.
    # Drop image-classification unless the abstract also names an IC benchmark/task.
    audio_task_id = slug_to_id.get("audio-classification")
    image_task_id = slug_to_id.get("image-classification")
    if (
        text
        and audio_task_id in result
        and image_task_id in result
        and not has_strong_image_classification_signal(text)
    ):
        result.discard(image_task_id)

    if title:
        result = _resolve_image_video_task_conflicts(
            result, slug_to_id, text or "", title
        )

    return result


def find_matching_items_simple(
    text: str,
    case_sensitive_patterns: Dict[str, List[int]],
    case_insensitive_patterns: Dict[str, List[int]],
) -> Set[int]:
    """
    Find all items whose keywords appear in the text using simple matching.

    This is appropriate for TASKS where all matching categories should be tagged.
    If text contains both "object detection" and "image classification", both tasks are tagged.

    Args:
        text: The text to search (title + abstract)
        case_sensitive_patterns: Case-sensitive keyword patterns
        case_insensitive_patterns: Case-insensitive keyword patterns

    Returns:
        Set of item IDs that match
    """
    if not text:
        return set()

    matched_items = set()

    # Find case-sensitive matches.
    # Word-boundary matching (with optional trailing 's' for plurals) keeps
    # acronyms like "NER" or "VLM" from substring-matching inside unrelated
    # words such as "FINER" or "OpenCLIP". Compound acronyms that should
    # still be tagged (LVLMs, MLLMs, ...) are expected to be added as their
    # own keywords on the task.
    for keyword, item_ids in case_sensitive_patterns.items():
        pattern = r"\b" + re.escape(keyword) + r"s?\b"
        if re.search(pattern, text):
            matched_items.update(item_ids)

    # Find case-insensitive matches.
    # Word-boundary matching prevents substring false positives like matching
    # "transformed" when looking for "transformer". The trailing `s?` allows
    # the common English plural so e.g. keyword "large language model" still
    # tags a paper that writes "Large Language Models" in its abstract.
    text_lower = text.lower()
    for keyword_lower, item_ids in case_insensitive_patterns.items():
        pattern = r"\b" + re.escape(keyword_lower) + r"s?\b"
        if re.search(pattern, text_lower):
            matched_items.update(item_ids)

    return matched_items


def find_matching_items_longest_match(
    text: str,
    case_sensitive_patterns: Dict[str, List[Dict]],
    case_insensitive_patterns: Dict[str, List[Dict]],
) -> Set[int]:
    """
    Find all items whose keywords appear in the text using longest-match priority.

    This is appropriate for METHODS where hierarchical names exist (GPT, GPT-2, GPT-3, GPT-4).
    If text contains "GPT-4", only the GPT-4 method is tagged (not GPT).

    Implements longest-match priority: if multiple keywords match overlapping text,
    only the longest keyword is counted.

    Args:
        text: The text to search (title + abstract)
        case_sensitive_patterns: Case-sensitive keyword patterns (with metadata)
        case_insensitive_patterns: Case-insensitive keyword patterns (with metadata)

    Returns:
        Set of item IDs that match
    """
    if not text:
        return set()

    matched_items = set()
    matched_positions = set()  # Track which character positions we've already matched

    # Store all potential matches with their positions
    all_matches = []

    # Find case-sensitive matches
    # For case-sensitive keywords (usually acronyms), use substring matching
    # This catches plurals (VLMs, GANs) and compounds (LVLMs, OpenCLIP)
    # Case sensitivity prevents false positives (CLIP vs clip)
    for keyword, item_list in case_sensitive_patterns.items():
        for match in re.finditer(re.escape(keyword), text):
            start, end = match.span()
            for item_info in item_list:
                all_matches.append(
                    {
                        "start": start,
                        "end": end,
                        "length": end - start,
                        "item_id": item_info["id"],
                        "keyword": keyword,
                    }
                )

    # Find case-insensitive matches.
    # Allow an optional trailing 's' (plural) inside the closing word boundary,
    # mirroring the `find_matching_items_simple` rule so plural forms like
    # "transformers" / "language models" still tag the underlying method/task.
    text_lower = text.lower()
    for keyword_lower, item_list in case_insensitive_patterns.items():
        for match in re.finditer(
            r"\b" + re.escape(keyword_lower) + r"s?\b", text_lower
        ):
            start, end = match.span()
            for item_info in item_list:
                all_matches.append(
                    {
                        "start": start,
                        "end": end,
                        "length": end - start,
                        "item_id": item_info["id"],
                        "keyword": keyword_lower,
                    }
                )

    # Sort matches by length (longest first), then by position
    all_matches.sort(key=lambda x: (-x["length"], x["start"]))

    # Apply longest-match rule: only keep matches that don't overlap with longer matches
    for match in all_matches:
        match_positions = set(range(match["start"], match["end"]))

        # Check if this match overlaps with any already-accepted match
        if not match_positions.intersection(matched_positions):
            matched_items.add(match["item_id"])
            matched_positions.update(match_positions)

    return matched_items
