# Autonomous Driving field map

Status: seven-surface research gate complete. This is the pre-import field map for
task `316` (`autonomous-driving`). Final database outcomes will be reconciled in
`completion-report.md` and `verification-ledger.md`.

## Scope and live-page stocktake

The completion contract is the top 100 trending papers on the live
[`autonomous-driving`](https://paperswithcode.co/tasks/autonomous-driving) page,
plus a holistic map of the wider field: major benchmarks, major papers, papers
they compare to, and paper-native evaluations.

- The live task has 363 papers. At stocktake it had no linked datasets, configured
  metrics, or evaluations.
- The top-100 snapshot contains 3 papers from 2026, 32 from 2025, 23 from 2024,
  19 from 2023, 11 from 2022, and 12 older/undated papers.
- All 100 initially have zero evaluation rows for task 316. Only six have any
  evaluation elsewhere in the DB (10 rows total), on adjacent perception tasks.
- The top 100 includes about 76 result/method papers, 11 benchmark/dataset/platform
  papers, seven surveys/roadmaps, and six obvious off-task or tangential papers.
- The durable reconciliation is in [top100-ledger.csv](top100-ledger.csv); the
  source-paper queue is in [paper-worklist.csv](paper-worklist.csv).

This page is unusually heterogeneous. It mixes end-to-end driving and planning
with 3D detection, occupancy, online HD mapping, LiDAR segmentation, motion
forecasting, driving VLMs/VLAs, world models, simulation, scenario generation,
and several taxonomy false positives. The curation boundary is therefore a
benchmark protocol, not the broad task label alone.

## Evidence surfaces

### 1. Live task page and local database

The task-native high-signal cluster is UniAD, VAD/VADv2, TransFuser, MMFN,
Bench2Drive, NAVSIM, LMDrive, DriveLM, ReCogDrive, Senna, PlanT, and newer
NAVSIM/Bench2Drive papers such as SimScale, LEAD, ReflectDrive, Drive-JEPA, RAP,
GaussianFusion, and PRIX. Popular official repositories reinforce this cluster:
UniAD and NAVSIM are both around 4.7k stars, BEVFusion around 3.2k,
Bench2Drive around 1.9k, TransFuser around 1.6k, VAD/VADv2 around 1.3k, and
DriveLM around 1.3k at the research snapshot.

The only top-100 papers with existing DB evals are BEVFusion, the nuScenes source
paper, FRNet, UniTR, DeepInteraction++, and AD-L-JEPA. Those rows belong to
3D detection/segmentation leaderboards, not task 316. The broad task currently
cannot render any leaderboard.

### 2. Semantic Scholar citation and keyword searches

Broad and subarea searches covered autonomous driving, end-to-end driving,
planning, CARLA, NAVSIM/Bench2Drive, BEV, occupancy, 3D perception, and driving
VLA terminology. Citation anchors include KITTI, nuScenes, CARLA, Waymo Open
Dataset, CenterPoint, UniAD, TransFuser, MMFN, VAD, Argoverse 2, and the Waymo
Open Motion Dataset. Citation count was only one signal; current task-page,
GitHub, and artifact activity were also used.

The explicit 2025/2026 search recovered a larger current chain beyond the live
top 100: AutoVLA, FutureSightDrive, Orion, OpenDriveVLA, Diffusion-Planner,
GAIA-2, SimLingo, GoalFlow, DriveTransformer, Pseudo-Simulation/NAVSIM v2,
AlphaDrive, DriveMoE, DriveSuprim, Hydra-MDP++, DiffVLA, Raw2Drive, and
Impromptu VLA. These papers are comparison and follow-up leads; they are not
automatically imported unless their own results match a configured protocol.

### 3. Legacy Papers With Code dump

The exact legacy `Autonomous Driving` task is thin: 23 rows over CARLA
Leaderboard, Town05 Long, Town05 Short, and ApolloCar3D. CARLA source-paper leads
include ReasonNet, InterFuser, TCP, Hidden Biases/TF++, Learning from All
Vehicles, TransFuser, GRI, World on Rails, NEAT, MMFN, Learning by Cheating, and
CILRS. Town05 Long/Short contain MMFN/TransFuser rows and must remain separate
from the official CARLA Leaderboard protocol.

The historical field is fragmented across specialized tasks. Major legacy
families include nuScenes/KITTI/Waymo 3D detection; Argoverse and nuScenes motion
forecasting; nuScenes open-loop planning; Occ3D-nuScenes occupancy; nuScenes BEV
segmentation; CULane/TuSimple/CurveLanes/OpenLane lane detection; SemanticKITTI
and nuScenes LiDAR segmentation; and nuScenes/Waymo tracking. Legacy rows are
discovery evidence only: many challenge rows lack a source paper, and several
families mix splits, modalities, or metric scales.

### 4. GitHub repository popularity

Popular current repositories include UniAD, NAVSIM, BEVFusion, Bench2Drive,
TransFuser, VAD/VADv2, DriveLM, SurroundOcc, DiffusionDrive, SparseDrive,
OpenDriveVLA, AutoVLA, ReCogDrive, and OpenEMMA. Official READMEs were used to
map repositories to papers, protocol versions, checkpoints, and reproducibility
evidence. Stars and recency are field signals, never score provenance.

Open-source status will be decided per evaluated variant. Public weights or a
documented reproducible official GitHub pipeline can justify `is_open=true`
without an HF URL; `hf_model_url` is set only for an exact official checkpoint.

### 5. Hugging Face artifacts

The Hub search found strong exact artifacts for Bench2Drive datasets/zoo,
NAVSIM baselines, UniAD 2.0, Diffusion-Planner, DiffusionDrive, OpenDriveVLA,
AutoVLA, and OneVL NAVSIM. Cards and metadata are retained in
`/tmp/autonomous-driving/hf/` during this run. These establish artifact and open
availability signals, but a card is score evidence only when it reports the exact
evaluated variant and protocol.

### 6. Comparison-table expansion

The task-native comparison graph repeatedly points to these chains:

- CARLA: CILRS, LBC, World on Rails, NEAT, TransFuser/MMFN, TCP, InterFuser,
  PlanT, TF++, ReasonNet, LMDrive, and current vision-language agents.
- nuScenes planning: ST-P3, UniAD, AD-MLP/Rethinking Open-Loop Evaluation,
  VAD/VADv2, SparseDrive, Senna, and recent diffusion/VLA planners.
- Bench2Drive: TCP, AD-MLP, UniAD, VAD, Think2Drive, DriveTransformer,
  SimLingo, and recent world-model/VLA systems.
- NAVSIM: PDM-Closed, TransFuser, Ego-MLP baselines, Hydra-MDP,
  DiffusionDrive/Diffusion-Planner, ReCogDrive, and newer NAVSIM v2 systems.
- Occupancy: MonoScene, TPVFormer, SurroundOcc, OccFormer, OpenOccupancy,
  FB-OCC, OccNet, and OccRWKV.
- Online maps: HDMapNet, VectorMapNet, MapTR/MapTRv2, and LaneSegNet.

Comparator cells are used to discover source papers and protocols. They are not
posted as external evaluations; each paper must supply its own native row.

### 7. Explicit 2025/2026 slice

Thirty-five of the top 100 are from 2025/2026. High-priority task-native rows are
SimScale, LEAD, ReflectDrive, ReCogDrive, Drive-JEPA, RAP, GaussianFusion, PRIX,
and StandardE2E. The recent broader search additionally surfaced AutoVLA,
OpenDriveVLA, Orion, SimLingo, DriveTransformer, Diffusion-Planner, and NAVSIM v2
work. Recent protocols are kept separate when their evaluator changed; NAVSIM v1
PDMS is not NAVSIM v2 EPDMS, and CARLA Leaderboard 2.1 is not comparable with
2.0/1.0.

Because Semantic Scholar's 2026 index was effectively empty, the required 2026
slice was supplemented with HF paper search and GitHub creation/release evidence.
High-signal 2026 work includes UniDriveVLA, OneVL, SparseDriveV2,
Hyper-Diffusion-Planner, MindDrive, BLUE, BridgeDrive, and the task-page papers
Drive-JEPA, StandardE2E, and Chat2Scenic. SparseDriveV2 is a useful protocol
sentinel because its official release reports three incompatible leaderboards:
NAVSIM v1 PDMS, NAVSIM v2 EPDMS, and Bench2Drive DS/SR. New families such as
Fail2Drive, Bench2Drive-Robust, ReactSim-Bench, DrivingGen, EgoDyn-Bench,
HiDrive, and KITScenes remain separate discovery candidates.

Exact open-artifact evidence was found for UniAD 2.0, Diffusion-Planner,
DiffusionDrive, AutoVLA, OpenDriveVLA, NAVSIM baselines, OneVL, UniDriveVLA,
SparseDriveV2, BLUE, BridgeDrive, and MindDrive. OpenEMMA is explicitly an open
reproduction, not the paper-native Waymo EMMA checkpoint, and must not be used as
score or weight provenance for the latter.

## Candidate benchmark families and contracts

| Family | Candidate benchmark | Canonical contract | Evidence | Decision |
|---|---|---|---|---|
| Closed-loop end-to-end | CARLA Leaderboard 1.0 | Sensor track/version-fixed; Driving Score, Route Completion, Infraction Penalty | live, legacy, GitHub, official leaderboard | wave 1 add |
| Closed-loop end-to-end | Town05 Long | Fixed Town05 Long routes; DS/RC/IS | legacy, MMFN/TransFuser | wave 1 add separately |
| Closed-loop end-to-end | Town05 Short | Fixed Town05 Short routes; DS/RC/IS | legacy, MMFN/TransFuser | wave 1 add separately |
| Multi-ability closed loop | Bench2Drive v0.0.3 | 220 routes; Driving Score and Success Rate; current evaluator only | live, GitHub, HF, source paper | wave 1 add |
| Non-reactive planning | NAVSIM v1 | Official split/evaluator; PDMS only | live, GitHub, HF, source paper | wave 1 add |
| Pseudo-closed-loop planning | NAVSIM v2 | Official version; EPDMS only | recent, GitHub, comparison papers | wave 2 add separately |
| Closed-loop planning | nuPlan Test14/Val14 | Exact challenge/split and reactive/non-reactive simulator; NR-CLS/R-CLS/OLS kept separate | official devkit, current papers | wave 2 split |
| Open-loop planning | nuScenes planning (ST-P3 protocol) | Exact evaluator; horizon-fixed L2 and collision | live, legacy, UniAD/VAD chain | wave 1, high-risk |
| Driving VQA | DriveLM Graph VQA | Official split/task aggregate; metric labels exactly as source benchmark | live, GitHub, source paper | wave 2 add |
| Trustworthiness VQA | AutoTrust | Paper-release six-model reference pool; overall five-dimension normalized mean; judge/attack/setup fixed | live, GitHub, source paper | added separately |
| 3D occupancy | Occ3D-nuScenes | Official camera-only/current split; mIoU | live, legacy, GitHub | wave 2 add |
| Surround occupancy | SurroundOcc-nuScenes / OpenOccupancy | Dataset-label version and modality fixed; mIoU | live, legacy, source papers | wave 2 split |
| Online HD mapping | OpenLane-V2 | Dataset version and TOP metric fixed | live, GitHub, source paper | wave 2 add |
| 3D perception | nuScenes | Existing specialized detection/segmentation contracts; mAP/NDS/mIoU | DB, live, legacy | reuse under specialized tasks |
| LiDAR semantics | SemanticKITTI | Official val/test and label regime fixed; mIoU | DB, legacy | reuse under specialized task |
| Motion forecasting | Argoverse / Waymo Motion | Split and K fixed; minADE/minFDE/MR variants separated | legacy, S2 | specialized-task follow-up |
| Lane perception | CULane/TuSimple/OpenLane | Dataset-specific F1/Accuracy/TOP; never collapse | legacy, source papers | specialized-task follow-up |

CARLA Leaderboard 2.0 and 2.1 remain discovery candidates, not aliases of 1.0.
The official CARLA site states that 2.1 changed the infraction score and should
not be compared with 2.0. Likewise, NAVSIM v2 replaces PDMS with EPDMS and a
pseudo-closed-loop aggregation. Separate rows are required before importing.

## Major protocol risks

1. CARLA papers mix Leaderboard 1.0/2.0/2.1, Town05 Long/Short, Longest6,
   sensor vs map tracks, route sets, simulator versions, and privileged inputs.
2. Bench2Drive changed evaluator versions and fixed bugs. Only current v0.0.3
   220-route scores belong together; Dev10/mini/older releases are separate.
3. NAVSIM v1 PDMS and v2 EPDMS are different quantities. Version-specific
   evaluator bugs and test splits must be recorded in methodology.
4. nuScenes open-loop planning is especially risky: ST-P3/UniAD/VAD code can
   average horizon errors differently, and open-loop L2/collision has known weak
   correlation with closed-loop driving. Do not merge by label alone.
5. nuScenes detection mixes camera, LiDAR, radar-camera, temporal settings,
   extra data, and occasional 0-1 versus 0-100 scales.
6. Occupancy labels with the same nuScenes base data (Occ3D, SurroundOcc,
   OpenOccupancy, SSCBench, OccNet) are not interchangeable.
7. Source benchmark papers often report comparator baselines but introduce no
   model. Such papers can source a dataset row without receiving comparator evals.
8. Several top-100 papers are surveys or obvious mistags (TADPOLE, Editable
   Neural Networks, D-IF, agentic-system design). They should receive explicit
   ledger decisions, not fabricated autonomous-driving results.

## Initial database stocktake

Task 316 has zero benchmark wiring. Existing reusable rows elsewhere include
nuScenes (`677`), SemanticKITTI (`678`), Waymo Open Dataset (`679`), KITTI 3D
Object Detection (`777`), BDD100K val/test (`850`/`851`), ONCE (`1043`), and
Argoverse 2 3D Object Detection (`1317`). CARLA, Town05, Bench2Drive, NAVSIM,
nuPlan, DriveLM, AutoTrust, Occ3D/OpenOccupancy, and OpenLane-V2 were not found by
name and require benchmark workers before any paper worker can use them.

The first write wave is deliberately task-native: CARLA Leaderboard 1.0, Town05
Long, Town05 Short, Bench2Drive v0.0.3, NAVSIM v1, and a separately named
nuScenes ST-P3 planning contract. Later waves depend on the first verifier results
and will not force adjacent perception protocols onto the broad task page.

The task-native benchmark waves created and linked the following contracts:

| Dataset id | Slug | Metrics |
|---:|---|---|
| 1590 | `carla-town05-long` | Driving Score, Route Completion, Infraction Penalty |
| 1591 | `carla-leaderboard-1-0` | Driving Score, Route Completion, Infraction Penalty |
| 1592 | `carla-town05-short` | Driving Score, Route Completion, Infraction Penalty |
| 1593 | `bench2drive-v0-0-3` | Driving Score, Success Rate |
| 1594 | `navsim-v1` | PDMS |
| 1595 | `nuscenes-open-loop-planning-st-p3` | horizon-specific L2 and Collision Rate at 1s/2s/3s |
| 1596 | `carla-longest6` | Driving Score, Route Completion, Infraction Penalty |
| 1597 | `occ3d-nuscenes` | mIoU |
| 1598 | `openlane-v2-v1-0` | OLS |
| 1599 | `surroundocc-nuscenes-dense-labels` | mIoU |
| 1600 | `openlane-v2-lane-segment-v1-0` | Lane Segment OLS |
| 1601 | `drivelm-graph-vqa` | DriveLM P1-3 GPT Score (ChatGPT-3.5) |
| 1602 | `autotrust` | AutoTrust Overall Trustworthiness Score |
| 1605 | `navsim-v2-navhard` | EPDMS |
| 1606 | `langauto` | Driving Score, Route Completion, Infraction Penalty |
| 1607 | `langauto-short` | Driving Score, Route Completion, Infraction Penalty |
| 1608 | `langauto-tiny` | Driving Score, Route Completion, Infraction Penalty |
| 1609 | `langauto-notice` | Infraction Penalty |
| 1610 | `langauto-sequential` | Driving Score, Route Completion, Infraction Penalty |
| 1611 | `occ3d-nuscenes-pg-occ-15-class` | mIoU |
| 1612 | `chat2scenic-regulation-grounded-scenario-generation` | Compilation Success Rate (CSR), Framework Accuracy (FA) |
| 1613 | `ego3d-bench` | Accuracy, RMSE (m) |
| 1614 | `drivergaze360-panoramic-driver-attention` | KLD, SIM, CC, NSS |
| 1615 | `navsim-v2-navtest` | EPDMS |

All links use `supports_harness=false`, `featured_rank=NULL`, and native source
paper URLs. ST-P3 arXiv `2207.07601` and Occ3D arXiv `2304.14365` were indexed
locally as papers `104466` and `104467` before dataset creation because their
protocol source rows were initially missing. Separate Occ3D, SurroundOcc, and
LaneSegNet rows prevent superficially identical mIoU/OLS labels from collapsing
incompatible label sets or aggregation contracts. AutoTrust freezes the source
paper's six-model normalization pool so later leaderboard additions cannot
renormalize its historical scores.

NAVSIM v2 is represented only by the official corrected two-stage
`navhard_two_stage` pseudo-closed-loop contract; one-stage v2/navtest EPDMS is
still a separate unwired protocol. LangAuto is split by route-length and
instruction regime because its Long, Short, Tiny, Notice, and Sequential scores
are not interchangeable with one another or with the older fixed Town05 routes.
PG-Occ's Occ3D evaluation is also isolated because its official evaluator drops
class indices 0 and 12 before averaging, unlike the 17-class Occ3D contract.
Chat2Scenic freezes the full 123-case, no-split CARLA 0.9.15/Scenic 3.1.0
release suite; only its two headline percent metrics are leaderboard fields.
Ego3D-Bench freezes all 8,675 validation QA rows and reports only the aggregate
eight-category multiple-choice Accuracy and two-category numeric-distance RMSE;
source/category diagnostics stay out of the leaderboard.
DriverGaze360 fixes the town-disjoint five-camera panoramic saliency setup.
NAVSIM v2 navtest is the corrected v2.2 one-stage EPDMS contract and remains
separate from both NAVSIM v1 PDMS and the two-stage navhard product score.
