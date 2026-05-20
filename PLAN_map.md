# Plan: Preserve mAP Metric Labels

## Problem

`backend/database/validate_evaluation_metrics.py` currently treats `mAP` as a naming inconsistency and suggests converting it to `AP`. That is too broad. For object detection, pose estimation, and segmentation benchmarks, many official sources report the metric as `mAP`, often with variants such as `mAP val 50-95`, `mAP box 50-95`, `mAP mask 50-95`, or `mAP pose 50-95`.

The YOLOv8 rows are a clear example: Ultralytics' official YOLOv8 documentation reports `mAP val 50-95` for COCO and Open Images detection, and the database rows correctly store those scores under `mAP`.

## Goal

Keep source-faithful `mAP` labels where the benchmark reports mean Average Precision, while still allowing real metric-name cleanup for accidental aliases.

## Proposed Fix

1. Update `validate_evaluation_metrics.py` so it no longer includes the blanket rule:

   ```python
   "AP": ["mAP", "mean AP"]
   ```

2. Replace the global alias rule with leaderboard-aware validation:

   - If a leaderboard is configured with `mAP`, `mAP` is valid.
   - If a leaderboard is configured with `AP`, `AP` is valid.
   - Do not rewrite `mAP` to `AP` unless the exact `(task_id, dataset_id)` leaderboard only allows `AP` and the source/provenance clearly used `AP` as the canonical metric.

3. Audit the currently affected 123 rows before any mutation:

   - Group by `(task, dataset, best_metric)`.
   - Confirm whether the configured leaderboard metric is `mAP` or `AP`.
   - Check source methodology for ambiguous rows.
   - Leave YOLOv8, YOLO26, COCO detection, COCO keypoints, Open Images, LVIS, and similar detection/pose/segmentation rows as `mAP` when their sources report mAP.

4. Add a dry-run report that distinguishes:

   - `valid_source_label`: metric key matches the source and configured leaderboard.
   - `leaderboard_mismatch`: metric key is not configured for the leaderboard.
   - `possible_alias`: source likely used an alias, but needs review.

5. Only after the audit, apply targeted fixes for rows that are truly inconsistent.

## Verification

After implementation:

1. Run:

   ```bash
   uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py
   ```

2. Confirm the validator no longer flags all `mAP` rows as inconsistent.

3. Spot-check YOLOv8:

   - `YOLOv8x` on `COCO val2017` remains `mAP = 53.9`.
   - `YOLOv8n` through `YOLOv8x` on `Open Images V7` remain `mAP`.
   - YOLOv8 pose rows remain `mAP` for COCO keypoints.

4. Confirm leaderboard pages still rank those rows correctly.
