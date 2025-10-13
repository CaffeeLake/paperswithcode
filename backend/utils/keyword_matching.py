"""
Shared keyword matching utilities for linking papers to tasks and methods.

This module provides two matching strategies:
1. Simple matching: For tasks - all matching keywords are tagged
2. Longest-match priority: For methods - prevents overlapping matches (e.g., GPT-4 takes precedence over GPT)

Case-Sensitivity Rules:
- If a keyword contains at least 1 capital letter: case-sensitive matching
  * Examples: "BERT", "GPT-4", "ResNet", "VLM"
  * Uses substring matching to catch plurals (VLMs, GANs) and compounds (LVLMs, OpenCLIP)
  * Case sensitivity prevents false positives (CLIP vs clip)
- If a keyword is all lowercase: case-insensitive matching
  * Examples: "transformer", "attention", "object detection"
  * Uses word boundary matching to prevent false matches (e.g., "transformed" when looking for "transformer")
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

    # Find case-sensitive matches
    # For case-sensitive keywords (usually acronyms), use substring matching
    # This catches plurals (VLMs, GANs) and compounds (LVLMs, OpenCLIP)
    # Case sensitivity prevents false positives (CLIP vs clip)
    for keyword, item_ids in case_sensitive_patterns.items():
        if keyword in text:
            matched_items.update(item_ids)

    # Find case-insensitive matches
    # For case-insensitive keywords (phrases), use word boundary
    # This prevents matching "transformed" when looking for "transformer"
    text_lower = text.lower()
    for keyword_lower, item_ids in case_insensitive_patterns.items():
        pattern = r"\b" + re.escape(keyword_lower) + r"\b"
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

    # Find case-insensitive matches
    text_lower = text.lower()
    for keyword_lower, item_list in case_insensitive_patterns.items():
        for match in re.finditer(r"\b" + re.escape(keyword_lower) + r"\b", text_lower):
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
