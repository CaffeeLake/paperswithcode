# Image Editing Task Completion Report

Snapshot: 2026-07-22 UTC. Task: `image-editing` (`tasks.id=18`).

## Outcome

- Reconciled the final live top 100 after ranking drift and recorded a terminal decision for every paper.
- Twenty-seven current top-100 papers retain 38 verified paper-native evaluation rows.
- Thirty-nine papers were inspected at the original-paper and official-artifact level but report no result compatible with the seven configured leaderboard contracts.
- Two papers had unsupported existing rows removed; 18 are adjacent/off-task results, 12 are benchmark or dataset contributions without an eligible introduced-model row, and two are surveys.
- Final task coverage is 42 comparable rows from 29 papers across seven benchmark datasets, up from 26 mixed-quality rows across five datasets before the pass.
- Added the historical MagicBrush mask-free single-turn and PIE-Bench boards; repaired and expanded GEdit, ImgEdit, PICABench, KRIS-Bench, and RISEBench.

## Final leaderboard coverage

| Benchmark | Dataset | Rows | Papers | Verified leader |
|---|---:|---:|---:|---|
| GEdit-Bench | 346 | 18 | 18 | JoyAI-Image-Edit (w/ PE), `8.290` |
| ImgEdit-Bench | 339 | 12 | 12 | LongCat-Image-Edit, `4.50` |
| PIE-Bench | 1617 | 4 | 4 | Metric-specific: FlashEdit / EARL / VAREdit |
| RISEBench | 349 | 3 | 3 | EditThinker-8B, `17.8` |
| KRIS-Bench | 348 | 2 | 2 | ReasonEdit-Q, `61.57` |
| MagicBrush single-turn, mask-free | 1616 | 2 | 2 | MGIE leads every populated metric |
| PICABench superficial prompt | 146 | 1 | 1 | Qwen-Image-Edit+SFT, `62.13` |

Every benchmark received a separate verifier. No final leaderboard contains duplicate papers, unsupported harness rows, or a task-scoped metric-label mismatch.

## Top-100 disposition

| Disposition | Papers |
|---|---:|
| Retained paper-native configured evaluation | 27 |
| Source-audited; no compatible configured result | 39 |
| Unsupported existing evaluation removed | 2 |
| Adjacent/off-task result paper | 18 |
| Benchmark or dataset contribution without eligible introduced-model row | 12 |
| Survey | 2 |
| Missing decision | 0 |

The live task grew from 803 to 804 papers during the work. The final ledger follows the current ordering and includes the four papers that entered the top 100. It also corrects the stale identity previously attached to paper `103994`: the actual paper is `Let RGB Be the Language of Vision` (arXiv `2607.12450`).

## Major paper and comparison spine

The verified modern general-editing spine includes JoyAI, Mage-Flow, FireRed, NextFlow, UniWorld-V2, ReasonEdit, RegionE, EditThinker, LongCat, Emu3.5, Z-Image, Qwen-Image-Edit, SenseNova-U1, Step1X, VIBE, BAGEL, OmniGen2, and Skywork UniPic on GEdit; and LongCat, UniWorld-V2, NextFlow, ChronoEdit, Emu3.5, ReasonEdit, Mage-Flow, Qwen-Image-Edit, VIBE, BLIP3o-NEXT, ViBT, and Skywork UniPic on ImgEdit.

The historical/reference-metric spine is preserved separately: MGIE and ICEdit on MagicBrush; FlashEdit, EARL, GRAG, and VAREdit on PIE-Bench. Reasoning and realism are also separate contracts: ReasonEdit/BAGEL on KRIS, EditThinker/Uni-Edit/BAGEL on RISE, and the PICABench paper's best SFT variant on PICABench.

Comparison-table evidence was used to discover important papers, not to misattribute scores. In particular, the 12 PICABench comparator rows attached to Qwen, OmniGen2, Step1X, HiDream, and other papers were removed because their source was the later PICABench paper rather than the comparator papers themselves.

## Protocol decisions and cleanup

- GEdit is English Full, 606 cases, GPT-family VIEScore `G_O` on 0-10. DreamLite's Qwen2.5-VL `Q_O` row was removed.
- ImgEdit is the full Basic single-turn nine-category Overall under GPT-4.1 or an explicit official-protocol statement. Ten wrong-judge or undocumented-judge rows were removed.
- PICABench is all 900 superficial-prompt cases with GPT-5 PICAEval Overall Accuracy. External comparator rows and a weaker same-paper SFT variant were removed; the retained unreleased SFT checkpoint is correctly marked closed.
- KRIS and RISE use native 0-100 scales. BAGEL values were corrected from `0.6018` to `60.18` and `0.119` to `11.9` respectively.
- MagicBrush keeps single-turn/multi-turn and mask-free/mask-provided protocols separate. MagicQuill's brush-mask run was therefore not imported into the mask-free board.
- PIE-Bench is the original 700-image, ten-edit-type suite. PIE-Bench++, partial subsets, and raw/canonical scale mixtures were excluded; VAREdit CLIP values were normalized to the canonical 0-100 table surface.
- Later-paper comparator values, component metrics, proprietary oracle variants, ablations, partial category averages, custom human studies, and similarly named metrics from different datasets were excluded.

## Emerging benchmark map

The field map also documents important separate future boards: Edit-Compass, UniREditBench, UnicBench, SpotEdit, REDEdit-Bench, I2EBench, ICE-Bench editing splits, and GEditBench v2. They were not collapsed into the seven current boards because their judges, splits, inputs, or aggregation rules differ materially. GEditBench v2 Elo in particular is not a replacement for GEdit v1 absolute `G_O`.

## Integrity checks

- Task API: HTTP 200; 804 papers.
- Dataset API: exactly seven task-linked datasets with row counts `18, 12, 4, 3, 2, 2, 1`.
- Evaluation API: 42 rows from 29 unique papers.
- Current top 100: 100 rows, rank sequence 1-100, IDs exactly match the live API, 27 covered papers / 38 retained rows, and no missing decision.
- Import ledger: 94 normalized rows, no malformed CSV records; 42 retained, 42 audited-no-compatible, and 10 recorded verifier deletions.
- Metric validator: zero image-editing mismatches and all evaluations have `best_metric`; four unrelated global warnings remain on ETH3D, FLORES-101, FLORES-200, and LiveBench.

## Artifacts

- `field-map.md`: seven-surface field map, benchmark contracts, comparison graph, and emerging-board recommendations.
- `top100-ledger.csv`: final live ordering and terminal disposition for all 100 papers.
- `import-ledger.csv`: normalized paper-worker and verifier outcomes, including retained and deleted evaluation IDs.
- `verification-ledger.md`: benchmark-by-benchmark action summary and final rankings.
