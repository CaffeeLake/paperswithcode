# Stereo Matching completion report

Completion date: 2026-07-21 UTC. Task: `Stereo Matching` (`tasks.id=324`, `stereo-matching`).

## Outcome

The task now has 16 configured benchmark datasets and 156 verified paper-native evaluation rows representing 46 distinct papers. Every benchmark has exactly one configured metric, `supports_harness=false`, and `featured_rank=NULL`. The final state has no duplicate `(paper_id, dataset_id, model_name, best_metric)` rows, no non-null harnesses, no unconfigured or missing `best_metric` values, and no incorrect ranks.

The import-and-audit pass produced 193 provisional rows. Benchmark verifiers deleted 37 rows that mixed incompatible masks, thresholds, resolutions, training regimes, or protocols, leaving 156. No Robust Vision Challenge model row remains: RVC is a composite cross-benchmark training/evaluation protocol and was not collapsed into the ordinary KITTI or ETH3D leaderboards. The Booster-H FoundationStereo result was corrected to BP-2 **10.29** under the half-resolution `NoOcc/Cons`, all-classes contract.

## Live-paper completion contract

The research snapshot contained only 87 papers on the live task page, not 100. The complete live inventory was therefore the contract: all 87 papers were reconciled rather than padding the scope with 13 arbitrary search results. Each was inspected and either led to paper-native evaluation work or received an evidence-backed decision such as specialized/missing benchmark, incompatible protocol, comparator-only evidence, or not being a stereo-result paper.

The historical spine is well represented: Scene Flow/DispNet, PSMNet, AANet, HITNet, RAFT-Stereo, CREStereo, UniMatch/GMStereo, IGEV/IGEV++, CroCo-Stereo, and related official-test papers. The explicit 2025/2026 slice was also inspected, including FoundationStereo, DEFOM-Stereo, Fast-FoundationStereo, LAS-family work, S2M2, MatchAttention, MonSter++, WAFT-Stereo, Stereo Anywhere, Stereo Any Video, SMoE-Stereo, and recent robustness/efficiency papers. A paper appearing in a comparison table was treated as a discovery lead; its comparator score was never assigned to that paper unless the paper's own source reported the evaluated model and cell.

The durable evidence is split across the [field map](field-map.md), [87-paper reconciliation ledger](top100-ledger.csv), [paper worklist](paper-worklist.csv), [source-worker import ledger](import-ledger.csv), and [benchmark verification ledger](verification-ledger.md).

## Seven-surface field map

The field map was built before imports from seven independent surfaces:

1. **Live page and database:** the full 87-paper page, existing paper/task metadata, local trending signals, repositories, projects, and initially absent stereo benchmark wiring.
2. **Semantic Scholar:** 800 raw results across broad and recent searches, 573 deduplicated candidates, and 476 broad relevance matches, used to recover both classics and 2025/2026 work.
3. **Legacy Papers With Code:** 28 relevant rows across eight historical task/dataset tables and 14 source papers, used as leads while rejecting stale aliases and server-side re-evaluations without paper-native provenance.
4. **GitHub:** popularity and official repository evidence for major implementations, weights, and reproducible configurations. OpenStereo reproduction results remained OpenStereo results rather than being reassigned to comparator papers.
5. **Hugging Face:** official model repositories and exact-checkpoint evidence, supplemented by official GitHub/Drive releases because this field is not HF-centric.
6. **Comparison tables:** recurring baselines and benchmark families were expanded into source-paper leads, not bulk-imported comparator rows.
7. **Recent-paper review:** the 2025/2026 slice was explicitly adjudicated for established leaderboards, genuinely new protocols, and non-result/dataset-only work.

## Benchmark families covered

The final 16 leaderboards cover five complementary families:

- **Standard dense stereo:** Scene Flow test EPE; official KITTI 2012 Out-Noc 3px and KITTI 2015 D1-all hidden tests; ETH3D dense non-occluded Bad 1.0; and Middlebury v3 half-resolution non-occluded Bad 2.0.
- **Target-excluded zero-shot stereo:** KITTI 2012/2015, ETH3D, and Middlebury 2014, kept separate from benchmark-specific fine-tuning and from incompatible NOC/raw-bad-pixel formulations.
- **Non-Lambertian and adverse-domain zero shot:** Booster-Q, Booster-H, and the four-weather DrivingStereo aggregate.
- **High-resolution official testing:** Spring Stereo, retaining its native total-mask 1px protocol rather than optical-flow or benchmark-paper comparator rows.
- **Temporal video stereo:** Dynamic Replica and MPI Sintel Clean/Final under the DynamicStereo TEPE contract, separate from static disparity and optical-flow metrics.

## Source-worker import pass

Source workers inspected introducing papers, official project repositories, model cards, and hidden-test submissions. They imported only models introduced by the source paper. Comparison-table baselines, OpenStereo reproductions of other papers, later benchmark-server re-evaluations, and lower-scoring duplicate variants were excluded from the paper-native import contract.

The pass intentionally separated ordinary benchmark-trained submissions from target-excluded zero-shot models, and separated static pairwise stereo from temporal video protocols. Training data, target-domain adaptation, exact model variant, parameter count, source URL, and methodology were recorded when the primary source supported them. Provisional breadth was followed by a stricter benchmark-level audit; 193 rows entered verification and 156 survived.

## Verifier cleanup

One verifier audited every row on each benchmark. The 37 deletions were not arbitrary pruning:

- Scene Flow lost three incompatible evaluator/ablation variants.
- KITTI 2012 hidden test lost one 2px row from its 3px leaderboard.
- KITTI 2015 hidden test lost two RVC composite-protocol rows.
- ETH3D hidden test lost one RVC composite-protocol row.
- Middlebury hidden test lost three full-resolution rows from the half-resolution leaderboard.
- KITTI 2015 zero shot lost 12 NOC/raw-Bad-3 or otherwise non-D1 rows.
- Middlebury zero shot lost one all-valid-pixel row from the non-occluded leaderboard.
- KITTI 2012 zero shot lost 11 NOC/raw-Bad-3 or alternate-D1 rows.
- DrivingStereo lost three rows using the wrong formula or target-domain training.

All other benchmark audits either retained the complete set or normalized supported metadata. Ranks were recalculated and then independently checked against each metric's lower-is-better direction, including ties.

## Final leaderboard inventory

| Dataset ID | Benchmark | Metric | Rows |
|---:|---|---|---:|
| 1549 | Scene Flow Stereo Test | EPE | 24 |
| 1550 | KITTI 2012 Stereo Test | Out-Noc 3px | 20 |
| 1551 | KITTI 2015 Stereo Test | D1-all | 30 |
| 1552 | ETH3D Low-res Two-view Stereo Test (Nonocc) | Bad 1.0 | 16 |
| 1554 | Middlebury v3 Stereo Test (Half, Nonocc) | Bad 2.0 | 1 |
| 1555 | KITTI 2015 Stereo Zero-Shot | D1 | 8 |
| 1556 | ETH3D Stereo Zero-Shot | BP-1 | 20 |
| 1557 | Middlebury 2014 Stereo Zero-Shot (Half, Nonocc) | BP-2 | 16 |
| 1558 | KITTI 2012 Stereo Zero-Shot | D1 | 4 |
| 1559 | Booster-Q Stereo Zero-Shot | BP-2 | 4 |
| 1560 | Spring Stereo Test | 1px total | 1 |
| 1561 | DrivingStereo Weather Zero-Shot | Overall D1 | 3 |
| 1562 | Dynamic Replica Video Stereo Test | TEPE | 3 |
| 1563 | MPI Sintel Stereo Clean Video | TEPE | 2 |
| 1564 | MPI Sintel Stereo Final Video | TEPE | 3 |
| 1565 | Booster-H Stereo Zero-Shot | BP-2 | 1 |
|  | **Total** |  | **156** |

## Open-source and Hugging Face corrections

`is_open` was audited at the exact evaluated-variant level. Official code, weights, or source-complete reproduction instructions can justify an open row without a Hugging Face URL; a repository placeholder or unrelated base model cannot. This corrected both false closed classifications and overly optimistic open classifications.

Hugging Face URLs were normalized to official repository roots only when the source tied the repository to the exact evaluated variant. The audit checked variant-specific artifacts for WAFT-Stereo, MatchAttentionXL, MonSter++, StereoBase, LightStereo, and LAS-family releases. S2M2 illustrates the caution required: its public Booster weights do not match its Middlebury/ETH3D submission weights, so one artifact link cannot be propagated across those rows.

## Deferred specialized protocols

Several important directions remain deliberately outside the generic stereo leaderboards because they need their own contracts or broader adoption:

- Robust Vision Challenge composite models and RobustSpring corruption deltas;
- Stereo Anywhere LayeredFlow/MonoTrap illusion and non-Lambertian protocols;
- StereoCarla generalizable-driving evaluation;
- event/event-frame asymmetric stereo such as DSEC/MVSEC variants;
- endoscopic SCARED/Hamlyn, omnidirectional/fisheye, transparent-object, and application-specific robotic stereo;
- joint semantic-stereo, confidence/uncertainty-only, satellite/MVS, tactile, restoration, and data-generation papers where generic matcher scores would be comparator or downstream evidence rather than paper-native model results.

These were not silently dropped: they remain documented in the paper ledger and worklist as concrete follow-up candidates.

## Remaining limitations

- The task page supplied 87 papers rather than the requested 100. Coverage is complete for that frozen live-page contract, but no claim is made that the database contains every stereo paper ever published.
- The 156 rows represent 46 papers. The remaining live papers are reconciled decisions, not fabricated evaluations: many are datasets, synthesis/restoration studies, MVS or application-specific work, comparator-only studies, or require a missing specialized leaderboard.
- Some newer or specialized leaderboards remain thin: Middlebury hidden test, Spring, Booster-H, and temporal Sintel currently have one to three paper-native rows. Thin but valid leaderboards were retained rather than padded with comparator scores.
- Exact parameter counts and HF links remain blank when the primary source does not support an exact evaluated-variant match. GitHub/Drive-based releases are common in stereo matching.
- Each configured dataset intentionally exposes one canonical ranking metric. Secondary metrics and incompatible masks/resolutions should become explicit separate leaderboards rather than extra columns that blur the contract.

## Final validation

Read-only SQL validation confirmed:

- 16 `task_datasets`; every row has one metric, `supports_harness=false`, and `featured_rank=NULL`;
- 156 evaluations and 46 distinct represented papers;
- zero duplicate `(paper_id, dataset_id, model_name, best_metric)` groups;
- zero null/unconfigured `best_metric` rows, zero non-null harnesses, and zero rank mismatches;
- zero model names containing `RVC`; methodology references to “non-RVC” only identify ordinary submissions;
- Booster-H eval `17251` stores BP-2 10.29 at rank 1.

API smoke validation returned HTTP 200 for `/api/v1/tasks/324`, `/api/v1/tasks/324/page`, `/api/v1/tasks/324/papers`, `/api/v1/datasets/1549`, and the benchmark-evaluation route. All 16 dataset evaluation endpoints returned HTTP 200 and exactly the row counts listed above.

`uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py` completed in dry-run mode with all stereo rows valid. It reported four unrelated, pre-existing global mismatches:

1. 3D understanding / ETH3D (relative): `Accuracy` against allowed `F1` and `Overall (Chamfer)`;
2. Machine Translation / FLORES-101: `chrF++` against allowed `spBLEU`;
3. Machine Translation / FLORES-200 devtest: `chrF++` against allowed `COMET-22` and `spBLEU`;
4. Reasoning / Livebench: `Accuracy` against allowed `Score` and `Score (0-10)`.

None belongs to task 324 or any of its 16 stereo-matching datasets, so they are not failures of this completion pass.
