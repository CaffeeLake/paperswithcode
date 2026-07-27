# Video segmentation task completion report

Completed: 2026-07-23. Task: `video-segmentation` (id `262`).

## Outcome

- Expanded the task from 40 rows / 12 datasets to 174 verifier-clean rows /
  23 datasets, representing 59 source papers.
- Added 141 surviving paper-native evaluation rows for 44 source papers.
- Reconciled the requested live top 100: 41 newly imported, 7
  already-covered, 20 missing a benchmark, 8 protocol-incompatible, 4
  benchmark/comparator-only sources, and 20 non-result/task-tag false
  positives.
- Audited every row on all 23 task-linked dataset pages. Eight incompatible
  rows were deleted, two MeViS rows were corrected to the official split, and
  numerous openness, HF artifact, parameter, additional-data, and provenance
  fields were normalized.
- Reconciled evaluation ownership with paper taxonomy: all 59 papers that own
  video-segmentation evaluations now carry the `video-segmentation` task tag.

The complete rank-by-rank contract is in
[top100-ledger.csv](top100-ledger.csv), with zero missing decisions. The
surviving import IDs are in [import-ledger.csv](import-ledger.csv), and the
benchmark audit evidence is in
[verification-ledger.md](verification-ledger.md).

## GitHub issue request

- Corrected paper `56229` to the verified author order: Narges Norouzi, Idil
  Esen Zulfikar, Niccolò Cavagnero, Tommie Kerssies, Bastian Leibe, Gijs
  Dubbelman, and Daan de Geus.
- Added and verified DVIS++ (6 rows), CAVIS (5), DVIS-DAQ (5), and LOMM (3)
  across YouTube-VIS 2019/2021/2022, OVIS, VIPSeg, and VSPW as supported by
  each source.
- Kept CAVIS's paper-native YouTube-VIS 2022 AP^L value 38.6 instead of the
  39.5 value in a later comparison table.
- Deferred LOMM's YouTube-VIS 2022 48.2/54.0 values because the source labels
  the column plain AP, not the configured AP^L.
- Re-verified all six VidEoMT rows and attached exact benchmark-specific
  official HF checkpoints where available.

Posted the matching GitHub reply at
https://github.com/tue-mps/videomt/issues/8#issuecomment-5058016120 using the
repository's configured issue-write credential.

## Benchmark wiring completed

Added or repaired MOSEv2 validation, Refer-YouTube-VOS 2021 public validation,
ReVOS, RefVOS-DAVIS, MeViS, LVOS validation, DAVIS 2017 test-dev, ReasonVOS,
Cityscapes-VPS, KITTI-STEP, YouTube-VOS 2018 official server, MOSE, and the
separate public train-derived YouTube-VOS protocol. Split and metric contracts
remain distinct.

Final largest pages are DAVIS 2017 validation (25 papers),
Refer-YouTube-VOS (22), RefVOS-DAVIS (19), MeViS (13), YouTube-VIS 2019
(11), and MOSE (10). The field-wide benchmark and lineage map is in
[field-map.md](field-map.md).

## Verification cleanup

Deleted evaluation IDs `565`, `7110`, `9080`, `9081`, `9082`, `9635`,
`13738`, and `17926` for custom split, wrong supervision, unsupervised,
class-agnostic zero-shot, prompt-refinement, or open-vocabulary contamination.
Corrected Sa2VA's MeViS score from Val^u 62.9 to official Val 46.9 and
VideoLISA's from Val^u 54.5 to official Val 44.4.

The metric validator reports no target-task mismatch. Its only findings are
four unrelated pre-existing rows on ETH3D, FLORES-101, FLORES-200 devtest,
and LiveBench. `/health` and the live task papers API both returned HTTP 200.

## Important top-100 deferrals

- LLaVA-OneVision-2 and Segment and Track Anything lost their only task rows
  because the setups were not comparable to mask-initialized DAVIS.
- MedSAM3, angiography VOS, GDKVM, Vivim, GraphEcho, and surgical-video
  methods require medical/specialty benchmark contracts.
- XMem++ uses multi-reference/custom-MOSE protocols rather than configured
  first-frame-only splits.
- Unsupervised VOS papers require separate DAVIS/FBMS/YouTube-Objects
  leaderboards rather than mixing supervision regimes.
- Dataset papers such as MOSE, MOSEv2, and LVOS expose comparator tables but
  do not introduce the comparator models; those rows remain source-paper
  work.
- Post-freeze verifier recommendations include SeC-4B on SA-V val/test and
  several missing Refer-YouTube-VOS source papers (ReferFormer+AOT, ReferDINO,
  MUTR, LoSh-S, DsHmp, HTR). They were not imported after the verification
  freeze and are recorded as the next source-paper wave.

No service restart, frontend build, nginx change, or production release was
performed.
