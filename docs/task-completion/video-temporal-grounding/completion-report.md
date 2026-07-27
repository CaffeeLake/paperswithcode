# Video Temporal Grounding completion report

## Outcome

The task is now populated and audited end to end.

- Task: `video-temporal-grounding` (ID 430), under Video Understanding.
- Starting state: 135 tagged papers, 0 task benchmarks, 0 task eval rows.
- Final state: **17 protocol-specific benchmarks, 111 evaluation rows, 60 source
  papers**.
- Top-100 coverage: **59 imported**, **26 defer-not-comparable**, **13
  not-a-results-paper**, **1 defer-missing-benchmark**, and **1
  defer-not-paper-native**.
- The 60 evaluated papers comprise 59 frozen top-100 papers plus major comparison
  paper 2D-TAN (1912.03590).
- Every one of the frozen top 100 has a terminal decision in
  `top100-ledger.csv`.

## Field coverage

The completion pass reconciled the live task page, local DB, streamed legacy PwC
dumps, Semantic Scholar citation/recent searches, GitHub releases, Hugging Face
artifacts, major-paper comparison tables, and an explicit 2025/2026 checklist.

The resulting coverage spans:

- foundational and classical grounding: TALL/CTRL provenance, 2D-TAN,
  Moment-DETR, UMT, UniVTG, UnLoc, VLG-Net, BAM-DETR, BM-DETR, D3G, and related
  specialist models;
- long-video and egocentric work: MAD, SOONet, Multimodal Guidance, DeCafNet,
  HieraMamba, and Ego4D-NLQ v2/OSGNet;
- video-LLMs and recent systems: TimeLens, TimeLens2, TempSamp-R1, VideoMind,
  ARC-Hunyuan-Video, TRACE, VTG-LLM/GPT, Grounded-VideoLLM, Time-R1,
  Foresee-to-Ground, Video-OPD, VideoTG-R1, TaRO, UniTime, T2SGrid, SlotVTG,
  SMORE, and others recorded in the import ledger.

Comparison-table baselines were used to discover source papers, never posted as
external evals. Each import attaches only to the paper that introduces the model or
system.

## Benchmark design

The task deliberately keeps incompatible protocols separate:

- ActivityNet `val_1` and `val_2` are distinct leaderboards.
- Original Charades/QVHighlights/ActivityNet and the three TimeLens
  reannotations are distinct.
- QVHighlights moment retrieval is separate from highlight detection.
- Ego4D-NLQ is explicitly v2 validation.
- MAD is a full-corpus retrieval board, not single-video grounding.
- Native VUE-TR/V2 multimodal AUC boards are distinct from TimeLens2 vision-only
  R@1/mIoU subsets.
- Native MomentSeeker is distinct from the TimeLens2 text-only subset.
- DiDeMo retains its fixed-grid four-annotator contract.

No benchmark was pinned (`featured_rank` remains NULL).

## Top-100 reconciliation

The exact row-by-row outcome is in `top100-ledger.csv`; the actionable worklist is
in `paper-worklist.csv`.

The non-import decisions are substantive:

- spatio-temporal tube/box grounding, video-corpus retrieval, grounded QA,
  online/refusal-aware grounding, and video-query retrieval are
  `defer-not-comparable` rather than being mixed with temporal interval boards;
- surveys, libraries, analysis papers, and acronym false positives are
  `not-a-results-paper`;
- LifelongMemory is `defer-missing-benchmark` because it uses Ego4D-NLQ v1 while
  only v2 validation is configured;
- MomentSeeker is `defer-not-paper-native`: the current paper reports reproduced
  baselines, while its older introduced V-Embedder scores use an incompatible
  candidate-retrieval protocol.

## Verification and cleanup

Every one of the 17 benchmark contracts received an independent verifier pass.
The final leaderboard counts and contracts are in `benchmark-ledger.csv`, every
evaluation ID is in `import-ledger.csv`, and detailed audit outcomes are in
`verification-ledger.md`.

The only score/split deletion was MQVTG TACoS eval `17522`, which used an alternate
split. Other remediation normalized open/closed tags, auxiliary-data flags,
methodology references, and official source links. Final counts are 87 open rows
and 24 closed rows.

## Tooling and checks

The maintenance CLI now supports idempotent task, benchmark, and metric creation,
including repeatable task/metric arguments for benchmark setup. Threshold-specific
metrics were created through `pwc metric add`; all benchmark population used the
CLI/API rather than ad hoc SQL writes.

Checks:

- `backend/tests/test_maintenance_cli.py`: **7 passed**.
- Evaluation metric validator: all task-430 rows valid; four unrelated global
  mismatches remain on ETH3D, FLORES-101, FLORES-200, and LiveBench.
- Task, paper, dataset, and task-scoped evaluation API checks returned HTTP 200.
- No production restart, frontend build, nginx reload, or deployment was performed.

## Durable artifacts

- `field-map.md` — seven-surface field map and protocol decisions.
- `top100-ledger.csv` — frozen top-100 reconciliation.
- `paper-worklist.csv` — per-paper class, priority, and final decision.
- `benchmark-ledger.csv` — final benchmark contracts and row counts.
- `import-ledger.csv` — every imported evaluation ID.
- `verification-ledger.md` — per-benchmark audit and remediation log.

Task page: https://paperswithcode.co/tasks/video-temporal-grounding
