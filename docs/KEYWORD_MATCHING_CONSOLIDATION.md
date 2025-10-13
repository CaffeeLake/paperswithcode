# Keyword Matching Logic Consolidation

**Date**: October 13, 2025
**Status**: ✅ Completed

## Overview

Consolidated keyword matching logic across the codebase to ensure consistent tagging of papers with tasks and methods. Created a shared module that implements two distinct matching strategies optimized for different use cases.

## Changes Made

### 1. Created Shared Keyword Matching Module

**File**: `backend/utils/keyword_matching.py`

This module provides:
- **Case-sensitivity detection**: Automatically determines if keywords should use case-sensitive or case-insensitive matching
- **Two matching strategies**:
  - `find_matching_items_simple()` - For tasks (all matching keywords are tagged)
  - `find_matching_items_longest_match()` - For methods (prevents overlapping matches)
- **Pattern creation functions**:
  - `create_keyword_patterns()` - Simple patterns for tasks
  - `create_keyword_patterns_with_metadata()` - Advanced patterns with metadata for longest-match

### 2. Updated Core Scripts

All three scripts now use the shared module with appropriate strategies:

#### Daily Import CRON Job
**File**: `cron/daily/import_hf_daily_papers.py`
- **Tasks**: Uses `find_matching_items_simple()`
- **Methods**: Uses `find_matching_items_longest_match()`
- Automatically tags new papers from Hugging Face with relevant tasks and methods

#### Methods Bulk Linking
**File**: `backend/database/methods_setup/link_papers_by_keywords.py`
- Uses `find_matching_items_longest_match()`
- Prevents a paper from being tagged with both "GPT" and "GPT-4"
- Only the longest matching keyword is used

#### Tasks Bulk Linking
**File**: `backend/database/tasks_setup/link_papers_by_task_keywords.py`
- Uses `find_matching_items_simple()`
- A paper can have multiple task tags (e.g., "image classification" AND "object detection")

## Matching Strategy Details

### Simple Matching (Tasks)
- **Use case**: Task categories where papers can belong to multiple categories
- **Behavior**: All matching keywords are tagged
- **Example**: A paper about image classification using transformers gets tagged with BOTH "image classification" AND "transformer" tasks

### Longest-Match Priority (Methods)
- **Use case**: Method names with hierarchical relationships (GPT, GPT-2, GPT-3, GPT-4)
- **Behavior**: Only the longest matching keyword is tagged
- **Example**: A paper mentioning "GPT-4" only gets tagged with "GPT-4" (not "GPT")
- **Implementation**: Tracks character positions to prevent overlapping matches

## Case-Sensitivity Rules

Both matching strategies use the same case-sensitivity rules:

### Case-Sensitive Keywords (contain at least 1 capital letter)
- **Examples**: BERT, VLM, GPT-4, ResNet, CLIP
- **Matching**: Substring matching
- **Why**:
  - Catches plurals (VLMs, GANs)
  - Catches compounds (LVLMs, OpenCLIP)
  - Prevents false positives (CLIP vs clip)

### Case-Insensitive Keywords (all lowercase)
- **Examples**: transformer, attention, object detection, dropout
- **Matching**: Word boundary matching (`\b...\b`)
- **Why**:
  - Prevents false matches (e.g., "transformed" when looking for "transformer")
  - Allows natural language variations

## Database Status

Current state after keyword-based tagging:
- **Papers (latest versions)**: 53,404
- **Tasks with keywords**: 30
- **Methods with keywords**: 189
- **Paper-task links**: 45,731 (~0.86 links per paper)
- **Paper-method links**: 128,552 (~2.4 links per paper)

## Cleanup Recommendations

### Scripts that Can Be Archived

The following one-off and legacy data import scripts are no longer needed with the keyword-based approach:

#### Methods Setup (`backend/database/methods_setup/`)
- ✅ **Keep**: `link_papers_by_keywords.py` (core bulk linking script)
- ✅ **Keep**: `export_methods_to_csv.py` (utility)
- ✅ **Keep**: `import_methods.py` (initial data setup - archive for reference)
- 📦 **Archive**: All `add_*_papers.py` scripts:
  - `add_dust3r_papers.py`
  - `add_dust3r_method.py`
  - `add_mcp_papers.py`
  - `add_spectrogram_papers.py`
- 📦 **Archive**: `populate_paper_methods.py` (legacy import from JSON)
- 📦 **Archive**: `import_annotated_methods.py` (one-off import)
- 📦 **Archive**: `update_method_images.py`, `update_method_links.py`, `update_mcp_description.py` (manual updates)
- 📦 **Archive**: `update_methods_from_json.py` (legacy)

#### Tasks Setup (`backend/database/tasks_setup/`)
- ✅ **Keep**: `link_papers_by_task_keywords.py` (core bulk linking script)
- ✅ **Keep**: `populate_tasks.py` (initial data setup - archive for reference)
- ✅ **Keep**: `cleanup_duplicate_tasks.py` (utility)
- 📦 **Archive**: All manual linking scripts:
  - `add_asr_papers.py`
  - `add_ocr_papers.py`
  - `add_ocr_keyword_papers.py`
  - `add_whisper_papers.py`
  - `link_vlm_papers.py`
  - `link_machine_translation_papers.py`
- 📦 **Archive**: Task-specific population scripts:
  - `populate_image_classification_papers.py`
  - `populate_object_detection_papers.py`
  - `annotate_object_detection_papers.py`
  - `check_object_detection_coverage.py`
- 📦 **Archive**: Domain-specific imports:
  - `import_time_series_papers_tasks.py`
  - `import_robotics_papers_tasks.py`
- 📦 **Archive**: Legacy imports:
  - `populate_paper_tasks_from_json.py`
  - `populate_paper_tasks_from_csv.py`
  - `populate_tasks_from_csv.py`
  - `add_papers_from_csv.py`
- 📦 **Archive**: Maintenance scripts:
  - `fix_task_areas.py`
  - `extract_tasks.py`
  - `show_sample_links.py`

### Recommended Archive Structure

```
backend/database/
├── methods_setup/
│   ├── link_papers_by_keywords.py  ✅ Active
│   ├── export_methods_to_csv.py    ✅ Utility
│   └── archive/                    📦 Historical scripts
│       ├── add_dust3r_papers.py
│       ├── populate_paper_methods.py
│       └── ...
├── tasks_setup/
│   ├── link_papers_by_task_keywords.py  ✅ Active
│   ├── cleanup_duplicate_tasks.py       ✅ Utility
│   └── archive/                         📦 Historical scripts
│       ├── add_asr_papers.py
│       ├── populate_paper_tasks_from_json.py
│       └── ...
```

## Testing

To verify the setup is working correctly:

### 1. Test the shared module
```bash
cd /root/python_projects/paperswithcode
uv run --env-file backend/keys.env python -c "
from backend.utils.keyword_matching import find_matching_items_simple, find_matching_items_longest_match
print('✓ Module imports successfully')
"
```

### 2. Run bulk linking scripts (optional - only if you want to re-tag all papers)
```bash
# Clear and rebuild method links
uv run --env-file backend/keys.env backend/database/methods_setup/link_papers_by_keywords.py

# Clear and rebuild task links
uv run --env-file backend/keys.env backend/database/tasks_setup/link_papers_by_task_keywords.py
```

### 3. Test daily CRON job (dry run)
```bash
# The daily job will automatically tag new papers going forward
uv run --env-file backend/keys.env cron/daily/import_hf_daily_papers.py
```

## Benefits

1. **Consistency**: All three scripts use the same keyword matching logic from a shared module
2. **Maintainability**: Changes to matching logic only need to be made in one place
3. **Clarity**: Clear separation between simple matching (tasks) and longest-match (methods)
4. **Automation**: New papers are automatically tagged with relevant tasks and methods
5. **Scalability**: Adding new keywords to the database automatically updates all future papers

## Future Enhancements

Possible improvements for the future:
- Add keyword synonym support (e.g., "LLM" → "large language model")
- Implement keyword weighting/confidence scores
- Add machine learning-based tagging as a complement to keyword matching
- Create admin UI for managing keywords and reviewing suggested matches
