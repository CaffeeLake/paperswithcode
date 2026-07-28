# Head Pose Estimation verification ledger

Verification date: 2026-07-28. Every changed benchmark was audited by one
focused `verify-evals` worker against the releasing papers and, where
available, official repositories or model artifacts.

| Dataset | Benchmark | Before | After | Result |
|---:|---|---:|---:|---|
| 1649 | AFLW2000-3D, 300W-LP cross-dataset | 12 | 12 | All rows passed. Six extra-data flags were corrected and source limitations on filtering/crops were made explicit. |
| 1650 | CMU Panoptic full-range | 4 | 1 | Kept WRHP-6D + Opal (GE 7.45); removed three lower representation/loss ablations under the one-best-release rule. |
| 1651 | BIWI cross-dataset | 14 | 14 | All rows passed the no-BIWI-training rule. Eight extra-data flags and one source-limit note were corrected. |
| 1652 | AGORA-HPE full-range multi-person | 2 | 2 | Both DirectMHP tiers passed. Exact repository aggregates resolved the paper's rounded-axis inconsistency. |
| 1653 | BIWI 70/30 in-domain | 6 | 4 | Removed WQuatNet and GADS-Hybrid because their sources do not disclose split granularity or exact units. |
| 1654 | CMU-HPE full-range multi-person | 2 | 2 | Both DirectMHP tiers passed; matching coverage, thresholds, and pretrained initialization were verified. |
| 1660 | ARKitFace 6DoF | 13 | 7 | Retained end-to-end PerspNet and latest TRGv2. Removed six privileged-input PerspNet variants using GT boxes and/or masks. |

## Material deletions

Eleven evaluation rows were removed because they were ablations, privileged
input protocols, or not reproducibly tied to the benchmark split:

- `18224`, `18225`, `18226`: lower WRHP representation/loss ablations.
- `18230`, `18289`: under-specified BIWI 70/30 splits.
- `18279`–`18284`: PerspNet rows using GT boxes and/or GT masks.

These database deletions are recoverable only by re-importing the source rows.

## Cross-cutting checks

- Every surviving row is tied to its releasing paper; comparator-table
  baselines were never imported under the later paper.
- The BIWI cross-dataset and BIWI in-domain leaderboards remain separate.
- MAE, MAEV, geodesic rotation error, translation MAE, and ADD remain separate
  metric rankings.
- No evaluation uses an unlinked benchmark, lacks `best_metric`, or duplicates
  `(paper, benchmark, model, metric)`.
- Open/closed status is based on exact official implementations or checkpoints,
  not merely the existence of a GitHub repository.
- TRG was refreshed to arXiv v2. The refresh preserved the historical v1 row
  and copied curated state to the latest paper; only latest-version rows are
  counted in the completion totals.

The repository-wide metric validator accepts every Head Pose Estimation row.
It still reports four unrelated pre-existing mismatches on ETH3D,
FLORES-101, FLORES-200, and LiveBench.
