# Head Pose Estimation field map

Research snapshot: 2026-07-28. Task: `head-pose-estimation` (`task_id=432`).

## Scope and comparability boundary

Head pose estimation predicts a human head's yaw, pitch, and roll or its full
6-DoF rigid pose. The central comparable setting is monocular RGB head/face
input. The field also contains RGB-D, full-rotation, multi-person, infrared,
fisheye, radar, and medical-volume variants; those require separate
leaderboards and must not be mixed with conventional short-range RGB results.

Training on 300W-LP and testing on AFLW2000 or BIWI is a common cross-dataset
protocol. It is distinct from training and testing on a BIWI subject split.
Euler-angle mean absolute error (MAE), geodesic rotation error (GE), vector MAE
(MAEV), and translation error measure different quantities and must not rank
against each other.

## Seven-surface evidence map

### 1. Live task page and local database

The new live task page initially contained 11 manually reviewed papers, zero
linked benchmarks, and zero evaluation rows. The initial live-page
reconciliation is in [top100-ledger.csv](top100-ledger.csv). Because the user
requested top-100 coverage, the field-discovery worklist must expand the task
paper set before the final ledger is regenerated.

The highest-citation live papers are Hopenet (`1710.00925`, 621 citations),
Deep Label Distribution Learning (`1611.01731`, 500), img2pose (`2012.07791`,
157), and 6DRepNet (`2202.12555`, 151). None had local evaluation rows at the
start of this pass.

### 2. Semantic Scholar

Seven alias searches produced 668 raw title-relevant hits and 87 raw 2025/2026
candidates before modality and downstream-task filtering. High-signal work
includes Hopenet, FSA-Net, WHENet (`2005.10353`), 6DRepNet, 6DRepNet360
(`2309.07654`), SRHP/WRHP (`2401.05807`), TRG (`2407.14136`), DirectMHP
(`2302.01110`), TokenHPE, POSEidon (`1611.10195`), Face-from-Depth
(`1712.05277`), and the 2025/2026 papers listed below.

False positives are especially common: “HPE” often means human pose
estimation; gaze, face reenactment, talking-head generation, body pose from
head-mounted cameras, and generic face alignment papers often mention head
pose without evaluating it as an output.

### 3. Legacy Papers With Code

The legacy dump duplicated the same Head Pose Estimation subtree three times
under different task paths. After deduplication it contains 10 leaderboards,
75 result rows, and 30 unique source papers:

| Benchmark | Rows | Unique papers | Legacy metrics | Initial decision |
|---|---:|---:|---|---|
| BIWI | 29 | 23 | cross-dataset/in-domain MAE, GE, aligned errors, MAEV, translation MAE | Wave 1, split by protocol |
| AFLW2000 | 25 | 20 | MAE, GE, MAEV, translation MAE | Wave 1, split by metric |
| Panoptic | 6 | 3 | GE | Wave 1 full-range |
| AFLW | 6 | 5 | MAE | Wave 2 |
| ARKitFace | 3 | 2 | rotation/translation MAE | Wave 1 6-DoF |
| WFLW | 2 | 2 | mean/yaw/pitch/roll MAE | Wave 2 |
| COFW | 1 | 1 | yaw/pitch MAE | Wave 2 or defer |
| CMU Panoptic + 300W-LP | 1 | 1 | MAE | Defer pending protocol split |
| Pointing'04 | 1 | 1 | MAE | Defer: one-paper legacy page |
| BJUT-3D | 1 | 1 | MAE | Defer: one-paper page and suspicious scale |

The most reusable comparison-table seeds are Hopenet, WHENet, 6DRepNet,
6DRepNet360, SRHP/WRHP, TRG, img2pose, FSA-Net, Hybrid Coarse-Fine
(`1901.06778`), MNN (`2202.02299`), DAD-3DHeads (`2204.03688`), PerspNet
(`2205.04126`), SPIGA (`2210.07233`), and DLDL (`1611.01731`).

### 4. GitHub popularity and reproducibility

Strong official repository signals include:

| Paper/model | Official repository | Stars | Release evidence |
|---|---|---:|---|
| Hopenet | `natanielruiz/deep-head-pose` | 1,663 | code, weights, 300W-LP/AFLW2000/BIWI |
| 6DRepNet | `thohemp/6DRepNet` | 666 | weights and native protocol tables |
| FSA-Net | `shamangary/FSA-Net` | 632 | code, weights, two BIWI protocols |
| img2pose | `vitoralbiero/img2pose` | 614 | pretrained models and eval notebooks |
| DAD-3DHeads | `PinataFarms/DAD-3DHeads` | 507 | benchmark code and dataset |
| WHENet | `Ascend-Research/HeadPoseEstimation-WHENet` | 506 | full-range implementation |
| SynergyNet | `choyingw/SynergyNet` | 418 | code and weights |
| DirectMHP | `hnuzhy/DirectMHP` | 118 | AGORA-HPE/CMU-HPE and public weights |
| TRG | `asw91666/TRG-Release` | 106 | ARKitFace/BIWI code and weights |

Repository popularity is a discovery and open-source signal, not score
provenance. Third-party demos, ports, forks, MediaPipe/PnP examples, gaze
toolkits, and OpenFace must not create evaluation rows unless the source paper
itself reports a comparable result.

### 5. Hugging Face artifacts

Current high-confidence artifacts include the official
`t-martyniuk/DAD-3DHeadsDataset`, `ETHZurich/biwi_kinect_head_pose`,
`HoyerChou/DirectMHP`, and `HoyerChou/SemiUHPE`. DirectMHP and SemiUHPE have
variant-specific public weights. These can support `is_open=true` and exact
row-level model links when the evaluated variant matches.

Hugging Face coverage is sparse for this classical vision field, so absence of
an HF model is not evidence that an academic result is closed. Official GitHub
weights or reproducibility scripts are sufficient open evidence.

### 6. Major-paper comparison tables

The comparison expansion centers on Hopenet, WHENet, 6DRepNet,
6DRepNet360, SRHP/WRHP, and TRG. These repeatedly compare FSA-Net, img2pose,
3DDFA/FAN, Hybrid Coarse-Fine, MNN, DAD-3DNet, SynergyNet, and full-range
variants. Comparator rows are worklist leads only; each score must be imported
from its own releasing paper.

Initial source checks already exposed legacy transcription/protocol errors:
TRG and TRG-star BIWI GE values were swapped, and SRHP mixed aligned MAE with
unaligned GE. This confirms that the legacy table cannot be copied blindly.

### 7. Explicit 2025/2026 slice

High-confidence recent work includes:

- *Unsupervised Discovery of Facial Landmarks and Head Pose* (CVPR 2025):
  BIWI and AFLW2000; unsupervised protocol.
- GADS (`2504.15751`): BIWI/AFLW2000 and synthetic augmentation.
- NLML-HPE (`2507.18429`): BIWI/AFLW2000.
- WQuatNet (2025): narrow/full-range CMU/AGORA plus BIWI/AFLW2000.
- VGGT-HPE (`2604.10106`, CVPRW 2026): relative-pose BIWI protocol with a
  known-pose anchor, which is not directly comparable to absolute estimators.
- Deep6DHead, MHPE, ContQuat, and several 2026 6DRepNet derivatives:
  candidates requiring source-table inspection.
- E(3)-Pose (`2512.04890`): fetal-MRI 3D-volume input; retained as a task paper
  but deferred from RGB leaderboards.

Radar, audio, fisheye, infrared, driver-only, and medical-volume papers are
tracked as separate-protocol candidates and are not forced into RGB rankings.

## Candidate benchmark waves

| Benchmark/protocol | Proposed source | Canonical metric(s) | Evidence | Decision |
|---|---|---|---|---|
| AFLW2000-3D, 300W-LP-trained short-range | `1511.07212` dataset source | Euler-angle MAE; GE separately | legacy 20 papers, major comparison tables, GitHub | Wave 1 |
| BIWI, 300W-LP-trained cross-dataset | BIWI source DOI; protocol from result papers | Euler-angle MAE; GE separately | legacy 23 papers, GitHub | Wave 1 |
| BIWI, in-domain 70/30 subject/frame protocol | BIWI source DOI | Euler-angle MAE | FSA-Net/6DRepNet and later papers | Wave 1, separate leaderboard |
| Panoptic full-range | `1612.03153` | GE | WHENet, 6DRepNet, SRHP/WRHP | Wave 1 |
| ARKitFace 6-DoF | `2205.04126` | rotation MAE/GE; translation MAE separately | TRG/PerspNet | Wave 1 |
| AGORA-HPE full-range multi-person | `2302.01110` | pose MAE/GE with detection protocol | DirectMHP and WQuatNet | Wave 1 |
| CMU-HPE full-range multi-person | `2302.01110` | pose MAE/GE with detection protocol | DirectMHP and WQuatNet | Wave 1 |
| AFLW | AFLW source DOI | Euler-angle MAE | five legacy papers | Wave 2 |
| WFLW pose protocol | Look at Boundary source | mean/yaw/pitch/roll MAE | SPIGA/ASMNet | Wave 2 |
| COFW pose protocol | COFW source DOI | yaw/pitch MAE | one legacy paper | Defer unless comparison expansion adds adoption |
| Pandora RGB-D | POSEidon/Pandora source | Euler-angle MAE | depth-HPE lineage | Wave 2, separate modality |
| ICT-3DHP RGB-D | dataset source | Euler-angle MAE | depth-HPE lineage | Wave 2, separate modality |
| DAD-3DHeads rotation evaluation | `2204.03688` | explicit pose metric only | DAD/SemiUHPE | Wave 2 pending metric check |

## Major risks and curation rules

- Never combine 300W-LP-to-BIWI cross-dataset results with BIWI-trained
  in-domain results.
- Never rank Euler MAE, GE, MAEV, translation error, and ADD together.
- Panoptic full-range results use a different rotation space/range than
  constrained AFLW2000 results.
- ARKitFace validation-only results need explicit split labels.
- AGORA-HPE and CMU-HPE couple head detection with multi-person pose.
- WFLW/COFW pose values may be landmark-derived rather than direct HPE.
- 300W-LP is normally training data, not a standalone test leaderboard.
- Comparator numbers from later papers are discovery evidence only.
- `is_open` is based on exact official weights/reproducibility evidence, not
  the presence or absence of an HF card.

## Gate result

The research map is broad enough to proceed. Wave 1 should wire the seven
major, repeatedly used benchmark/protocol pages first. Paper-native imports
should then cover the comparison-table worklist and the expanded live-page
top-100 ledger. Lower-adoption and incompatible-modality benchmarks remain
explicit deferrals rather than being mixed into the core rankings.
