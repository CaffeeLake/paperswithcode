# Depth Anything V2 Evaluation Results - Improvements Summary

**Paper**: Depth Anything V2 (ArXiv: 2406.09414)
**Paper ID**: 32904
**Date**: November 10, 2025

## Overview

Comprehensive improvement of evaluation results for the Depth Anything V2 paper, adding 22 new evaluation entries and fixing 2 existing entries.

## What Was Added

### Before Improvements
- **6 evaluations total**
  - 2 on KITTI (ViT-G zero-shot, ViT-L fine-tuned)
  - 2 on NYUv2 (ViT-G zero-shot, ViT-L fine-tuned)
  - 2 on segmentation tasks (ADE20K, CityScapes)

### After Improvements
- **28 evaluations total** (22 new + 6 existing)
  - Complete coverage of Table 2: Zero-shot relative depth estimation
  - Complete coverage of Table 3: DA-2K evaluation benchmark
  - Fixed best_metric inconsistencies

## Detailed Changes

### 1. Table 2: Zero-shot Relative Depth Estimation (18 new evaluations)

Added comprehensive results for all model sizes (ViT-S, ViT-B, ViT-L, ViT-G) across 5 benchmarks:

#### KITTI Dataset (3 new)
- ✓ Depth Anything V2 (ViT-S): AbsRel=0.078, delta1=0.936
- ✓ Depth Anything V2 (ViT-B): AbsRel=0.078, delta1=0.939
- ✓ Depth Anything V2 (ViT-L): AbsRel=0.074, delta1=0.946
- (ViT-G already existed)

#### NYUv2 Dataset (3 new)
- ✓ Depth Anything V2 (ViT-S): AbsRel=0.053, delta1=0.973
- ✓ Depth Anything V2 (ViT-B): AbsRel=0.049, delta1=0.976
- ✓ Depth Anything V2 (ViT-L): AbsRel=0.045, delta1=0.979
- (ViT-G already existed)

#### Sintel Dataset (4 new - dataset created)
- ✓ Depth Anything V2 (ViT-S): AbsRel=0.500, delta1=0.718
- ✓ Depth Anything V2 (ViT-B): AbsRel=0.495, delta1=0.734
- ✓ Depth Anything V2 (ViT-L): AbsRel=0.487, delta1=0.752
- ✓ Depth Anything V2 (ViT-G): AbsRel=0.506, delta1=0.772

**Note**: Created Sintel dataset (ID=220) with proper metadata:
- Full name: MPI Sintel Dataset
- Description: Synthetic dataset for optical flow and depth estimation
- URL: http://sintel.is.tue.mpg.de/

#### ETH3D Dataset (4 new)
- ✓ Depth Anything V2 (ViT-S): AbsRel=0.142, delta1=0.851
- ✓ Depth Anything V2 (ViT-B): AbsRel=0.137, delta1=0.858
- ✓ Depth Anything V2 (ViT-L): AbsRel=0.131, delta1=0.865
- ✓ Depth Anything V2 (ViT-G): AbsRel=0.132, delta1=0.862

#### DIODE Dataset (4 new)
- ✓ Depth Anything V2 (ViT-S): AbsRel=0.073, delta1=0.942
- ✓ Depth Anything V2 (ViT-B): AbsRel=0.068, delta1=0.950
- ✓ Depth Anything V2 (ViT-L): AbsRel=0.066, delta1=0.952
- ✓ Depth Anything V2 (ViT-G): AbsRel=0.065, delta1=0.954

### 2. Table 3: DA-2K Evaluation Benchmark (4 new evaluations)

Added complete results for the newly proposed DA-2K benchmark:

- ✓ Depth Anything V2 (ViT-S): Accuracy=95.3%
- ✓ Depth Anything V2 (ViT-B): Accuracy=97.0%
- ✓ Depth Anything V2 (ViT-L): Accuracy=97.1%
- ✓ Depth Anything V2 (ViT-G): Accuracy=97.4%

**Note**: Created DA-2K dataset (ID=277) with proper metadata:
- Full name: Depth Anything 2K Evaluation Benchmark
- Description: Versatile evaluation benchmark with ~1K high-resolution images and ~2K sparse pixel-pair annotations across 8 scenarios
- URL: https://depth-anything-v2.github.io
- Introduced by: Depth Anything V2 paper (2406.09414)

### 3. Bug Fixes (2 corrections)

Fixed `best_metric` inconsistencies for ViT-G models:

- ✓ Evaluation ID 484 (ViT-G on KITTI): Changed best_metric from "AbsRel" → "delta1"
- ✓ Evaluation ID 485 (ViT-G on NYUv2): Changed best_metric from "AbsRel" → "delta1"

**Rationale**: For depth estimation, delta1 (accuracy threshold, higher is better) is the standard primary metric, not AbsRel (error metric, lower is better). This aligns with:
- The paper's presentation in Table 2
- All other model variants (ViT-S, ViT-B, ViT-L)
- Standard depth estimation evaluation practices

## Final Statistics

### Evaluations by Dataset

| Dataset    | Task                 | Count | Models                                    |
|------------|----------------------|-------|-------------------------------------------|
| DA-2K      | Depth estimation     | 4     | ViT-S, ViT-B, ViT-L, ViT-G               |
| DIODE      | Depth estimation     | 4     | ViT-S, ViT-B, ViT-L, ViT-G               |
| ETH3D      | Depth estimation     | 4     | ViT-S, ViT-B, ViT-L, ViT-G               |
| KITTI      | Depth estimation     | 5     | ViT-S, ViT-B, ViT-L, ViT-G, ViT-L (ft)  |
| NYUv2      | Depth estimation     | 5     | ViT-S, ViT-B, ViT-L, ViT-G, ViT-L (ft)  |
| Sintel     | Depth estimation     | 4     | ViT-S, ViT-B, ViT-L, ViT-G               |
| ADE20K     | Image segmentation   | 1     | Large                                     |
| CityScapes | Image segmentation   | 1     | Large                                     |
| **Total**  |                      | **28**|                                           |

### Coverage Completeness

- ✅ **Table 2** (Zero-shot depth): 100% coverage (all 5 benchmarks × 4 models = 20 evaluations)
- ✅ **Table 3** (DA-2K): 100% coverage (4 models)
- ✅ **Table 4** (Fine-tuned metric depth): Partial coverage (2 evaluations on KITTI and NYUv2)
- ✅ **Segmentation tasks**: Complete (2 evaluations)

## Scripts Created

1. **improve_depth_anything_v2_evaluations.py**
   - Main script to add all 22 new evaluations
   - Creates Sintel and DA-2K datasets if needed
   - Checks for existing evaluations to avoid duplicates
   - Comprehensive error handling and progress reporting

2. **fix_depth_anything_v2_best_metrics.py**
   - Fixes best_metric for ViT-G evaluations
   - Updates evaluation IDs 484 and 485

## Verification

All evaluations verified with:
- ✓ Correct paper_id (32904)
- ✓ Correct task_id (16 for depth estimation, 3 for segmentation)
- ✓ Correct dataset_ids
- ✓ Correct metrics from paper tables
- ✓ Consistent best_metric values (delta1 for depth, Accuracy for DA-2K)
- ✓ Proper model naming conventions

## Impact

This comprehensive update ensures:

1. **Complete benchmark coverage**: All major depth estimation benchmarks from the paper are now represented
2. **Model scale comparison**: Users can compare performance across all 4 model sizes (25M to 1.3B parameters)
3. **New benchmark visibility**: DA-2K benchmark is now discoverable and linked to the paper
4. **Consistent metadata**: All evaluations follow the same naming and metric conventions
5. **Leaderboard accuracy**: Proper best_metric ensures correct ranking on leaderboards

## API Endpoints Affected

The following API endpoints now return improved data:

- `GET /api/v1/papers/32904` - Shows all 28 evaluations
- `GET /api/v1/papers/arxiv/2406.09414` - Same as above
- `GET /api/v1/evaluations/?paper_id=32904` - Lists all evaluations
- `GET /api/v1/datasets/277` - New DA-2K dataset
- `GET /api/v1/datasets/277/evaluations` - DA-2K leaderboard
- `GET /api/v1/datasets/220` - Sintel dataset
- `GET /api/v1/datasets/220/evaluations` - Sintel leaderboard
- `GET /api/v1/tasks/16/papers` - Depth Anything V2 appears with more evaluations

## Notes

- The original extraction (step_1.json) only captured a subset of results
- The aligned_results.json had 6 evaluations, missing most of Table 2 and all of Table 3
- This manual improvement ensures comprehensive coverage of the paper's contributions
- All metric values double-checked against the paper's Table 2 and Table 3
