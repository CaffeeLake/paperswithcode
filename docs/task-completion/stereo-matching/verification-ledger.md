# Stereo Matching verification ledger

Audit date: 2026-07-21. One benchmark-level verifier audited each of the 16 stereo-matching datasets after paper-native imports. Verifier decisions override importer assumptions. All leaderboards use `supports_harness=false` and lower-is-better metrics.

## Summary

| Dataset | Contract | Rows | Verifier disposition and notable evidence |
|---|---|---:|---|
| 1549 — Scene Flow Stereo Test | Held-out 4,370-pair FlyingThings3D stereo test, standard dense EPE protocol; no Cleanpass-only ablations or altered disparity masks. | 27 → 24 | Keep 24; metadata fixed. Delete `17327` because 0.6044 is a Cleanpass ablation-table result, `17252` because it masks at `d < 400`, and `17394` because its released evaluator uses `d < 255` plus an edge mask. |
| 1550 — KITTI 2012 Stereo Test | Official hidden test; non-occluded pixels; absolute Out-Noc 3px. | 21 → 20 | Keep 20; metadata fixed. Delete `17417`, which reports the wrong 2px threshold. |
| 1551 — KITTI 2015 Stereo Test | Official hidden test; all pixels; D1-all requires error greater than both 3px and 5% of ground-truth disparity. | 32 → 30 | Keep 30; metadata fixed. Delete `17302` (SMoEStereo-RVC) and `17396` (CREStereo++ RVC): both are fixed cross-benchmark Robust Vision Challenge models trained under a distinct composite protocol. |
| 1552 — ETH3D Low-res Two-view Stereo Test (Nonocc) | Official hidden test at dense coverage; non-occluded mask; Bad 1.0. | 17 → 16 | Keep 16; metadata fixed. Delete `17397` centrally. Its official score was verified, but it is the CREStereo++ RVC composite-training variant and the RVC contract remains separate from this ordinary leaderboard. |
| 1554 — Middlebury v3 Stereo Test (Half, Nonocc) | Official hidden test; H inputs; server upsampling; non-occluded Bad 2.0. | 4 → 1 | Keep 1. Delete `17333`, `17286`, and `17277`, whose source results use full-resolution `F` inputs rather than `H`. |
| 1555 — KITTI 2015 Stereo Zero-Shot | Public training split; fixed target-excluded weights; all evaluated pixels; exact KITTI D1 conjunction. | 20 → 8 | Keep 8; metadata fixed. Delete `17233`, `17257`, `17314`, `17298`, `17292`, `17335`, `17398`, `17263`, `17316`, `17403`, `17433`, and `17425` because their cells use NOC masks, raw Bad-3, or another non-D1 formulation. |
| 1556 — ETH3D Stereo Zero-Shot | Public low-resolution two-view training scenes; fixed weights with no ETH3D training/adaptation; non-occluded BP-1. | 20 → 20 | Keep all 20. Target-including benchmark recipes were distinguished from paper-native target-excluded cells; additional-data, open-status, and exact checkpoint metadata were normalized. |
| 1557 — Middlebury 2014 Stereo Zero-Shot (Half, Nonocc) | Public training scenes; H inputs; fixed target-excluded weights; non-occluded BP-2. | 17 → 16 | Keep 16; metadata fixed. Delete `17299`, which evaluates an all-valid-pixel mask instead of the non-occluded mask. |
| 1558 — KITTI 2012 Stereo Zero-Shot | Public training split; fixed target-excluded weights; all evaluated pixels; exact KITTI D1 conjunction. | 15 → 4 | Keep 4; metadata fixed. Delete `17232`, `17313`, `17256`, `17293`, `17297`, `17315`, `17400`, `17311`, `17266`, `17432`, and `17424` because their source cells use NOC masks, raw Bad-3, or a different D1 definition. |
| 1559 — Booster-Q Stereo Zero-Shot | Booster balanced quarter-resolution evaluation; fixed Booster-excluded weights; source-compatible non-occluded BP-2. | 4 → 4 | Keep all 4; metadata normalized. Half/full-resolution, other thresholds, and Booster-trained rows were excluded during verification. |
| 1560 — Spring Stereo Test | Official hidden stereo test at native full resolution; total mask including benchmark-defined sky/unmatched regions; 1px total. | 1 → 1 | Keep the single paper-native official submission; metadata normalized. Optical-flow rows and benchmark-paper comparators were excluded. |
| 1561 — DrivingStereo Weather Zero-Shot | Original full-resolution 500-frame Cloudy, Foggy, Rainy, and Sunny subsets; fixed target-excluded weights; source-reported Overall D1 aggregate. | 6 → 3 | Keep 3. Delete `17355` for an incorrect OR formula, `17306` for importing the KITTI conjunction rather than absolute DrivingStereo D1, and `17239` because the model was trained on DrivingStereo target data. |
| 1562 — Dynamic Replica Video Stereo Test | Official DynamicStereo first-150-frame Dynamic Replica test protocol; temporal EPE (TEPE). | 3 → 3 | Keep all 3; metadata normalized. Static EPE and altered temporal windows were excluded. |
| 1563 — MPI Sintel Stereo Clean Video | DynamicStereo temporal-disparity protocol on Sintel Clean sequences; TEPE. | 2 → 2 | Keep both; metadata normalized. Final-pass and optical-flow metrics were kept separate. |
| 1564 — MPI Sintel Stereo Final Video | DynamicStereo temporal-disparity protocol on Sintel Final sequences; TEPE. | 3 → 3 | Keep all 3; metadata normalized. Clean-pass and static disparity results were kept separate. |
| 1565 — Booster-H Stereo Zero-Shot | Booster balanced half-resolution official evaluation; fixed Booster-excluded weights; NoOcc/Cons, all classes, BP-2. | 1 → 1 | Fix and keep `17251`: official Booster-H hidden result is BP-2 **10.29**, half resolution, `NoOcc/Cons`, all classes. The prior source-ambiguous paper value was replaced with the exact official leaderboard cell. |

## Cross-leaderboard corrections

- The audit began with 193 rows and finished with 156 rows: 37 verifier or central deletions, 0 duplicate rows, and 46 represented papers.
- Ranks were recalculated after every deletion or numeric correction and checked against each metric's lower-is-better direction, including tied ranks.
- `uses_additional_data` was corrected when a model relied on external pretraining, pseudo-labels, mixed datasets, or foundation-model priors even if its stereo head was trained on the target benchmark's nominal training split.
- `is_open` was checked at the exact evaluated-variant level. README-only placeholders and repositories without the evaluated implementation/checkpoint were not treated as open releases.
- Hugging Face links were normalized to official model-repository roots when the repository contains the exact checkpoint. Variant-specific files were checked for WAFT-Stereo, MatchAttentionXL, MonSter++, StereoBase, LightStereo, and LAS-family releases.
- Paper provenance, source URLs, publication dates, parameter counts, and methodology text were corrected where supported by the introducing paper, official project repository/model card, or official benchmark result page.
- No comparator or lower-scoring duplicate variant was retained merely because a later paper reproduced its score.

## Evidence policy and validation

The verifiers traced stored values to paper-native tables and methodology, then used official KITTI, ETH3D, Middlebury, Booster, and Spring result pages where the contract required a hidden-test submission. Dynamic Replica and Sintel temporal rows were checked against the DynamicStereo TEPE protocol. Repository and Hugging Face inspections were used only for training configuration, exact checkpoint identity, and open-status evidence; they did not replace paper-native score provenance.

All 156 surviving stereo-matching rows have configured metric labels and `best_metric` values consistent with their leaderboard. The global evaluation validator still reports four unrelated pre-existing metric mismatches—ETH3D relative, FLORES-101, FLORES-200 devtest, and Livebench. None belongs to these 16 stereo-matching datasets.
