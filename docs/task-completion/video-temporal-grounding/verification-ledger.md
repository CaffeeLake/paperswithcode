# Video Temporal Grounding verification ledger

All leaderboard audits use task ID 430. Every changed benchmark was checked against
its paper/release source for split, metric, setup, model identity, score, openness,
HF linkage, parameter count, and duplicate variants.

| Dataset | Contract | Final rows | Verdict |
|---|---|---:|---|
| 57 CharadesSTA | canonical 12,408 train / 3,720 test | 51 | PASS after metadata remediation; final Temporal-RLT delta independently verified |
| 700 ActivityNet Captions | val_1, 17,505 queries | 1 | PASS |
| 1566 QVHighlights MR Test | official hidden test, MR only | 13 | PASS |
| 1567 Ego4D NLQ v2 Validation | official v2 val, 4,552 queries | 3 | PASS after VideoMind-Ego metadata/open correction |
| 1568 DiDeMo | original fixed-grid, four-annotator test | 0 | PASS; intentionally empty |
| 1569 TACoS Test | canonical 10,146 / 4,589 / 4,083 split | 9 | PASS after metadata remediation |
| 1570 MAD v1 Corpus Test | full-corpus test, 15 R@K/tIoU metrics | 4 | PASS after openness correction |
| 1571 Charades-TimeLens | corrected 3,363-query test | 4 | PASS after auxiliary-data correction |
| 1572 QVHighlights-TimeLens | corrected validation temporal grounding | 4 | PASS |
| 1573 MomentSeeker Text-Only | TimeLens2 1,000-example subset | 1 | PASS |
| 1574 ActivityNet-TimeLens | corrected 4,500-query test | 4 | PASS |
| 1575 VUE-TR Vision-Only | TimeLens2 525-example subset | 1 | PASS |
| 1576 VUE-TR-V2 Vision-Only | TimeLens2 715-example subset | 1 | PASS |
| 1577 MomentSeeker | native full multimodal benchmark | 0 | PASS; intentionally empty |
| 1578 VUE-TR-V2 | native multimodal AUC protocol | 0 | PASS; intentionally empty |
| 1579 VUE-TR | native multimodal AUC protocol | 0 | PASS; intentionally empty |
| 1580 ActivityNet Captions val_2 | 4,885 videos / 17,031 queries | 15 | PASS after metadata remediation; final Temporal-RLT delta independently verified |

## Remediation log

- Deleted MQVTG eval `17522`: alternate 4,436-example TACoS split was not
  comparable to the configured 4,083-example canonical test.
- Corrected `is_open` to true for EaTR (`17459`, `17460`), LVTR-CLIP
  (`17462`, `17463`), BM-DETR ActivityNet/TACoS (`17481`, `17482`), and
  Multimodal Guidance on MAD (`17475`) after official reproducible release checks.
- Corrected VideoMind-Ego `17445` to closed because the exact NaQ-trained Ego
  checkpoint is not released.
- Corrected TimeLens-8B sibling rows `17391`-`17393` to
  `uses_additional_data=true` for TimeLens-100K training.
- Corrected source-table references in VideoMind/VideoMind-Ego methodology and
  removed an unsupported BM-DETR repository-file claim.
- Clarified that public Video-OPD artifacts are Round 1, not the selected Round 3
  leaderboard checkpoint; Round 3 rows remain closed.
- Attached missing official code links where independently verified, including
  TD-DETR, EaTR, LVTR, BM-DETR, and the TACoS source-paper metadata.

## Automated validation

`validate_evaluation_metrics.py` accepts every task-430 row and finds no missing
`best_metric` values or safe metric-name standardizations. Four unrelated global
rows remain flagged: ETH3D, FLORES-101, FLORES-200, and LiveBench.
