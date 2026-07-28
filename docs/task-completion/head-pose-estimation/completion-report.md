# Head Pose Estimation completion report

Completed: 2026-07-28.

## Outcome

The live Head Pose Estimation task now has a broad, protocol-aware field map,
an exact 100-paper coverage ledger, seven major benchmark pages, and 42
verified paper-native evaluation rows from 16 releasing papers.

The exact top-100 roster is fully represented on the live task:

- 100 rows, 100 unique papers, 100 manual task links.
- 30 arXiv papers and 70 non-arXiv papers with canonical DOI sources.
- 16 papers with imported native evaluations.
- 25 result papers queued for source-table audit on an existing benchmark.
- 25 papers deferred because no comparable live benchmark exists.
- 13 papers deferred for protocol or relevance review.
- 10 methodology papers, 7 benchmark-source papers, and 4 surveys indexed
  without forced evaluation rows.
- Zero papers without an explicit decision.

The task currently exposes 118 latest-version papers in total. The additional
18 are previously curated task papers or benchmark/source papers outside the
balanced top-100 roster.

## Benchmarks completed

| Benchmark | Dataset | Metrics | Verified rows |
|---|---:|---|---:|
| AFLW2000-3D Head Pose (300W-LP Cross-Dataset) | 1649 | MAE, MAEV, geodesic error | 12 |
| CMU Panoptic Full-Range Head Pose | 1650 | Geodesic error | 1 |
| BIWI Head Pose (Cross-Dataset) | 1651 | MAE, MAEV, geodesic error | 14 |
| AGORA-HPE Full-Range Multi-Person Head Pose | 1652 | MAE | 2 |
| BIWI Head Pose (70/30 In-Domain) | 1653 | MAE | 4 |
| CMU-HPE Full-Range Multi-Person Head Pose | 1654 | MAE | 2 |
| ARKitFace 6DoF Head Pose | 1660 | rotation MAE, geodesic error, translation MAE, ADD | 7 |

The live pages intentionally separate cross-dataset BIWI from BIWI-trained
in-domain evaluation, Panoptic test-set GE from DirectMHP's CMU-HPE validation
MAE, and end-to-end multi-person detection from cropped single-person input.

## Paper-native imports

The 42 surviving rows come from Hopenet, 6DRepNet, WHENet, 6DRepNet360,
SRHP/WRHP, WQuatNet, DirectMHP, TRGv2, PerspNet, FSA-Net, NLML-HPE, GADS,
img2pose, QuatNet, MNN, and MFDNet.

Comparison tables in these papers were used to find important predecessors,
but no comparator number was posted under the comparing paper. Eleven
initially imported rows were removed during independent benchmark verification:
three lower WRHP ablations, two under-specified BIWI 70/30 results, and six
PerspNet oracle-input variants.

Two additional source checks prevented corrupt rows before publication:

- WHENet was resolved to local paper `104610`, not the adjacent 6DRepNet360
  record `104609`.
- DirectMHP's AGORA values 11.72 and 11.02 are roll errors, not overall MAE;
  the verified aggregate scores are 13.23 and 11.94.

## Coverage that remains intentionally deferred

The legacy PwC dump contained 10 deduplicated benchmark families, 75 rows, and
30 unique source papers. Lower-adoption families remain documented rather than
being mixed into the seven core pages:

- AFLW, WFLW, and COFW landmark-derived pose protocols.
- Pandora and ICT-3DHP depth-specific evaluation.
- Pointing'04, BJUT-3D, DD-Pose, DriveAHead, SASE, AutoPOSE, infrared, fisheye,
  radar, and medical-volume settings.
- Relative-pose methods such as VGGT-HPE, which require an anchor and are not
  comparable to absolute head-pose estimators.

## Artifacts

- `field-map.md`: seven-surface research map and benchmark-wave rationale.
- `top100-ledger.csv`: exact top-100 coverage and decision ledger.
- `paper-worklist.csv`: paper-by-paper benchmark/evaluation worklist.
- `import-ledger.csv`: all 42 surviving evaluation rows with provenance and
  methodology.
- `verification-ledger.md`: benchmark-level audits, corrections, and deletions.

Non-arXiv papers were created from canonical DOI records using Semantic Scholar
metadata. Nine records exposed only a publication year; those dates were
normalized to January 1 of that year and remain candidates for later
day/month enrichment. This normalization does not affect benchmark
comparability or score provenance.
