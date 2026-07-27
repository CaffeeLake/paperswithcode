# Image editing verification ledger

This ledger records row-level audit outcomes after the paper-native import wave.
Verifier findings override import-worker decisions. Final counts appear in
[`completion-report.md`](completion-report.md).

## Leaderboard contracts

| Benchmark | Dataset id | Contract | Status |
|---|---:|---|---|
| GEdit-Bench | 346 | English Full set (606); GPT-family/VIEScore `G_O`, 0-10, higher | Verified: 18 rows |
| ImgEdit-Bench | 339 | Full Basic single-turn nine-category Overall, GPT-4.1, 1-5, higher | Verified: 12 rows |
| PICABench | 146 | Superficial-prompt Overall PICAEval Accuracy (%), GPT-5, higher | Verified: 1 row |
| KRIS-Bench | 348 | Full 1,267-instance/22-task GPT-4o Overall, normalized 0-100, higher | Verified: 2 rows |
| RISEBench | 349 | RISEBench-360 GPT-4.1 solved-case Overall Accuracy (%), higher | Verified: 3 rows |
| MagicBrush Single-turn, Mask-free | 1616 | Official 535-session single-turn mask-free; L1/L2 lower, CLIP-I/DINO/CLIP-T higher | Verified: 2 rows |
| PIE-Bench | 1617 | Original 700-image/10-edit-type suite; five separately directed metrics | Verified: 4 rows |

## Audit outcomes

### GEdit-Bench (dataset 346)

- Audited all 19 pre-cleanup rows; final count 18.
- Deleted DreamLite eval `6331`: the paper reports Qwen2.5-VL `Q_O`, not the configured GPT-family `G_O`.
- Updated six retained rows for best-variant selection or source/model metadata; SenseNova now uses its stronger paper-native 8B result (`7.47`).
- Final top three: JoyAI `8.290`, Mage-Flow `8.271`, FireRed `7.943`.
- No duplicate papers or invalid configured labels remain.

### ImgEdit-Bench (dataset 339)

- Audited all 22 pre-cleanup rows; final count 12.
- Deleted ten rows whose source used the wrong judge or did not establish GPT-4.1/official-protocol comparability: evals `15054`, `17778`, `17767`, `17795`, `17802`, `6330`, `13796`, `5629`, `17794`, and `17785`.
- Updated retained LongCat, BLIP3o-NEXT, and Skywork UniPic metadata.
- Final top three: LongCat `4.50`, UniWorld-V2 `4.49`, NextFlow RL `4.49`.
- Exactly one retained row per paper; no invalid configured labels remain.

### PICABench (dataset 146)

- Deleted external comparison-table evals `464`-`475` as wrong-paper provenance.
- Deleted lower same-paper FLUX SFT eval `476`; retained only best introduced variant eval `17804`, Qwen-Image-Edit+SFT at `62.13`.
- Corrected eval `17804` to closed because the exact SFT adapter was not released.
- Final count is one row with no duplicates.

### MagicBrush Single-turn, Mask-free (dataset 1616)

- Verified both rows and retained their scores: MGIE eval `17786` and ICEdit eval `17788`.
- Corrected `uses_additional_data=true` for both.
- Final L1 ranking: MGIE `0.057`, ICEdit `0.060`; MGIE also leads every other populated metric. No L2 value is reported.

### KRIS-Bench (dataset 348)

- Corrected BAGEL Self-CoT eval `752` from stale decimal `0.6018` to native 0-100 value `60.18`, repaired the metric key, and added exact source/model metadata.
- Retained ReasonEdit-Q eval `17774` at `61.57` as the best paper-native variant.
- Final ranking: ReasonEdit-Q `61.57`, BAGEL Self-CoT `60.18`; no duplicates or KRIS validator mismatch.

### RISEBench (dataset 349)

- Corrected BAGEL Self-CoT eval `751` from `0.119` to native percentage `11.9` and repaired its metric key and provenance.
- Retained EditThinker eval `17797` at `17.8` and Uni-Edit eval `17783` at `17.2`; marked Uni-Edit as using additional task-specific training data.
- Final ranking: EditThinker `17.8`, Uni-Edit `17.2`, BAGEL Self-CoT `11.9`; no duplicates or RISE validator mismatch.

### PIE-Bench (dataset 1617)

- Verified all four paper-native rows; no deletions or additions.
- Corrected VAREdit eval `17787` CLIP values from raw cosine `0.260/0.225` to the canonical PIE table surface `26.0/22.5`.
- Final metric leaders: FlashEdit for background PSNR (`25.33`) and LPIPS (`62.25`, lower); EARL for structure distance (`35.00`, lower); VAREdit for whole/edit-region CLIP (`26.0`/`22.5`).
- Final count is four papers with no duplicates or PIE validator mismatch.

## Final integrity

- Task-scoped evaluation count: 42 rows from 29 papers.
- Per-dataset counts: GEdit 18, ImgEdit 12, PIE 4, RISE 3, KRIS 2, MagicBrush 2, PICABench 1.
- No duplicate paper within any leaderboard, no harness rows, and no image-editing metric-label mismatch.
- `validate_evaluation_metrics.py` reports all evaluations have `best_metric`. Its four remaining warnings are unrelated rows on ETH3D, FLORES-101, FLORES-200, and LiveBench.
