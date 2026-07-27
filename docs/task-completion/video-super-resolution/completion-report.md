# Video Super-Resolution Task Completion Report

Completed 2026-07-20 for `https://paperswithcode.co/tasks/video-super-resolution` (task ID `315`).

## Outcome

The task now has a source-grounded map of the classical, real-world/generative, and specialized video-super-resolution literature, plus a row-by-row reconciliation of the live top 100 papers.

| Measure | Starting state | Final state | Change |
|---|---:|---:|---:|
| Evaluation rows | 167 | 334 | +167 net |
| Source papers with task evals | 22 | 43 | +21 |
| Benchmark pages | 12 | 15 | +3 protocol-specific pages |
| Top-100 papers with task evals | 19 | 41 | +22 |

During the import pass, 203 paper-native rows were created. Verification then removed 18 newly imported and 18 pre-existing incomparable rows, moved 25 valid rows onto protocol-correct derived pages, and retained 185 newly created rows. The final import ledger contains 199 extant rows affected by this completion pass: 174 imported in place, 11 imported then moved, and 14 pre-existing rows moved.

## Top-100 reconciliation

Every live top-100 paper has a durable decision in `top100-ledger.csv`:

| Decision | Papers | Meaning |
|---|---:|---|
| Already covered | 19 | Existing rows survived source and benchmark verification. |
| Imported | 22 | Paper-native cells were added to a compatible configured or newly derived page. |
| Deferred: missing benchmark | 40 | The paper evaluates a specialized/custom set without a reusable configured contract. |
| Deferred: not comparable | 8 | The source uses a conflicting degradation, crop, frame subset, causal mode, or other setup. |
| Not a results paper | 11 | No paper-native VSR result table suitable for ingestion. |

This is full top-100 coverage as a curation decision, not an attempt to force all 100 papers onto generic leaderboards. The 59 papers without rows are explicitly justified in the ledger.

## Field overview

The historical comparison spine is:

`SRCNN / ESPCN -> VESPCN / SPMC / TOFlow / FRVSR / DUF / RBPN -> EDVR / PFNL / RSDN / RRN -> BasicVSR / IconVSR / BasicVSR++ -> VRT / RVRT / TTVSR / PSRT -> IA-RT / MIA-VSR / EvTexture -> recent diffusion, Mamba, and streaming systems`.

The major reusable benchmark families now represented are Vid4 BI/BD, REDS4 BI, Vimeo-90K-T BI/BD, conventional UDM10 and SPMCS, native RealVSR, VideoLQ, YouHQ40, Vimeo90K Fast/Medium, and three explicitly derived modern-protocol pages. Legacy research also identified MSU, Xiph/UVG, SAT-MTB-VSR, and deblatting families, but those were deferred because they are third-party, codec-specific, niche, or a different task.

Recent comparison chains repeatedly connect RealBasicVSR, RealViformer, MGLD-VSR, StableVSR, Upscale-A-Video, VEnhancer, STAR, DOVE, SeedVR/SeedVR2, FlashVSR, SparkVSR, and the newer one-step diffusion systems. Comparator cells were used to discover sources; only each introducing paper's own eligible model cells were imported.

## New benchmark pages

- RealVSR 4x restoration (DOVE protocol), dataset `1540`: separates later pixel-4x reporting from the native RealVSR camera-pair protocol.
- SPMCS 4x RealBasicVSR degradation, dataset `1541`: separates complex synthetic degradations from the conventional SPMCS page.
- UDM10 4x RealBasicVSR degradation, dataset `1542`: separates complex synthetic degradations from the conventional Gaussian-BD page.

SPMCS 1541 and UDM10 1542 are deliberately labeled protocol-family leaderboards. Papers independently regenerate stochastic low-quality inputs, so cross-paper ranking is approximate even though the degradation family, scale, dataset, and metrics match.

## Durable artifacts

- `field-map.md`: seven-surface research synthesis, benchmark contracts, major-paper chain, artifact signals, and risks.
- `top100-ledger.csv`: all 100 papers with final decision, reason, benchmark names, and evaluation IDs.
- `paper-worklist.csv`: source-paper worker queue used for the import waves.
- `import-ledger.csv`: every extant imported or protocol-moved row with source and model metadata.
- `verification-ledger.md`: benchmark-by-benchmark PASS/FIX/DELETE summary and comparability boundaries.

The global metric validator is clean for task 315. Its four remaining warnings are pre-existing and belong to unrelated ETH3D-relative, FLORES, and LiveBench leaderboards.
