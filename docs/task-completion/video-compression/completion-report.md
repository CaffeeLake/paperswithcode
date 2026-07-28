# Video Compression completion report

Completed: 2026-07-28. Task: `video-compression` (id 431).

## Outcome

The task grew from one benchmark, five evaluation rows, and one covered paper
to 28 strict benchmark boards, 81 evaluation rows, and 11 covered papers.
There are 50 task-dataset-metric links. All boards are unfeatured and have no
harness.

| Measure | Before | After | Delta |
|---|---:|---:|---:|
| Benchmarks | 1 | 28 | +27 |
| Evaluation rows | 5 | 81 | +76 |
| Papers with Video Compression evals | 1 | 11 | +10 |

The implemented benchmark families cover:

- RGB BT.709, first 96 frames, IP32, VTM-17.0 on UVG, MCL-JCV, and HEVC B-E.
- RGB BT.601, first 96 frames, IP32, VTM-13.2 LDB on the same six datasets.
- RGB BT.601, first 96 frames, IP=-1, VTM-13.2 LDB on the same six datasets.
- YUV420, all frames, IP=-1, actual bitstreams including headers, VTM-17.0 on
  the same six datasets.
- DAVIS, MCL-JCV, and UCF-101 video-tokenizer reconstruction under three
  explicitly different clip/split/compression protocols.
- Full-resolution seven-sequence UVG reconstruction by per-video implicit
  neural representations in the 12.66M-13.07M capacity band.

The 11 source-native papers with retained rows are DCVC-HEM, DCVC-DC,
DCVC-FM, ECVC, DCMVC, DCVC-RT, VidTok, BSQ, InfoTok, HiNeRV, and CoordFlow.

## Top-100 reconciliation

The final public task API has 136 papers. Its exact live top 100 was re-fetched
after canonical paper indexing and reconciled row by row:

| Decision | Papers |
|---|---:|
| imported | 9 |
| already-covered | 1 |
| defer-missing-benchmark | 59 |
| defer-not-comparable | 10 |
| defer-not-paper-native | 3 |
| not-a-results-paper | 18 |

The top 100 now contains 80 Video Compression evaluation rows across ten
papers. CoordFlow supplies the remaining task row outside the live top 100.
The ledger has exactly 100 unique ranks and paper ids, valid decisions and
non-empty reasons for every row, and `topN_missing_decision = 0`.

Deferred papers were not silently dropped. Most require a distinct protocol
for a different frame count, resolution, split, colorspace, anchor, rate
definition, generation/reconstruction metric, or domain-specific dataset.
Comparison-table baselines remain discovery evidence rather than evaluation
sources.

## Verification and cleanup

An independent `verify-evals` worker audited every one of the 28 boards.
The final read-only database audit found:

- zero metric-payload or task-dataset-metric wiring errors;
- zero duplicate keys or duplicate same-paper variants;
- zero rank inconsistencies;
- zero chronology, source-paper, native-URL, latest-version, openness, or
  Hugging Face inconsistencies;
- zero harness or featured-rank issues; and
- 105 of 105 checked public/API/source URLs returning HTTP 200.

Verification removed 12 HyTIP rows as `WRONG_SETUP`. HyTIP crops frames to
multiples of 64 and inserts scene-cut intra frames, while the native DCVC
boards score their original-resolution, fixed-IP32 pipeline. HyTIP's own DCVC
re-runs materially differ from the native results, so a separate
cropped/scene-cut benchmark would be required.

The legacy NeRV, E-NeRV, PS-NeRV, HNeRV, and FFNeRV fixed-capacity values were
also excluded: they are comparator cells in HiNeRV, not native results in the
cited original papers. Only the source-native HiNeRV and CoordFlow rows were
imported on that board.

The global metric validator has no Video Compression findings. Its four
remaining findings are pre-existing and unrelated: ETH3D, FLORES-101,
FLORES-200, and LiveBench.

## Durable evidence

- `field-map.md`: seven-surface field map, protocol taxonomy, and selection
  rationale.
- `benchmark-ledger.csv`: all 28 benchmark contracts, metrics, counts, dates,
  and source papers.
- `import-ledger.csv`: all 81 retained evaluation rows.
- `paper-worklist.csv`: final live top-100 paper decisions and evidence.
- `top100-ledger.csv` and `top100-report.md`: exact ordered reconciliation.
- `verification-ledger.md` and `audit-report.md`: independent per-board and
  cross-cutting validation.
