"""
Shared dataset utilities for the evaluation extraction pipeline.

This module provides helper functions for working with dataset information
across multiple pipeline steps.
"""

import json
import re
from typing import Optional, Union


def merge_dataset_details(base: Optional[dict], updates: Optional[dict]) -> dict:
    """
    Merge dataset detail dictionaries, preferring non-null update values.

    Args:
        base: Base dataset details dictionary
        updates: Updates to merge into base

    Returns:
        Merged dictionary
    """
    merged: dict = dict(base) if base else {}
    if isinstance(updates, dict):
        for key, value in updates.items():
            if value is not None:
                merged[key] = value
    return merged


def extract_dataset_id(result: Union[str, dict]) -> Optional[int]:
    """
    Extract dataset ID from step result (structured output or legacy string format).

    Args:
        result: Step result (dict or string)

    Returns:
        Dataset ID if found, None otherwise
    """
    if isinstance(result, dict):
        # Structured output from step_2 or step_4
        if "dataset" in result and isinstance(result["dataset"], dict):
            return result["dataset"].get("id")
        # Direct dataset dict
        return result.get("id")
    # String format
    if isinstance(result, str):
        # Try parsing as JSON first
        try:
            data = json.loads(result)
            if isinstance(data, dict) and "id" in data:
                return data.get("id")
        except (json.JSONDecodeError, ValueError):
            pass
        # Fallback to regex pattern matching
        match = re.search(r"ID[=:]?\s*(\d+)", result, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def parse_dataset_info(result: Union[str, dict]) -> Optional[dict]:
    """
    Parse dataset information from step result (structured output).

    Args:
        result: Step result (dict or string)

    Returns:
        Dataset info dictionary if found, None otherwise
    """
    if isinstance(result, dict):
        # step_2 returns {"found": bool, "reasoning": str, "dataset": {...}}
        if result.get("found") and "dataset" in result:
            return result["dataset"]
        # Direct dataset dict
        if "id" in result and "name" in result:
            return result
    # String format (JSON)
    if isinstance(result, str):
        try:
            data = json.loads(result)
            if isinstance(data, dict) and "id" in data and "name" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass
    return None
