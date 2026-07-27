# Autonomous Driving task completion report

## Scope and outcome

This pass completed the live top-100 reconciliation for Autonomous Driving and
mapped the field across the live task page, local database, legacy Papers With
Code dump, Semantic Scholar, current Papers With Code trends, Hugging Face
artifacts, GitHub implementations, and comparison tables in major papers.

The task began with 363 papers, no linked benchmark datasets, and no task-native
evaluation rows. It now has:

- 24 explicitly versioned benchmark datasets linked to task `316`;
- 21 populated task-native leaderboards;
- 90 verified task-native evaluation rows across 25 source papers;
- 3 additional verified rows for top-100 papers on their correct specialized
  leaderboards (FB-BEV on nuScenes 3D detection and DDRNet on Cityscapes);
- 100/100 live top papers with an explicit decision and source-backed reason.

No production process, frontend build, nginx reload, or service restart was
performed.

## Top-100 reconciliation

Final decision counts:

| Decision | Papers |
|---|---:|
| Imported in this pass | 26 |
| Already covered on an existing leaderboard | 6 |
| Not a results paper | 13 |
| Benchmark/source paper with no paper-native model row | 11 |
| Protocol-incomparable or false-positive task tag | 5 |
| Exact benchmark not yet configured | 39 |
| **Total** | **100** |

The ledger references 102 evaluation cells across the 32 imported/already-
covered papers. Every zero-eval high-signal paper (at least 100 citations or 200
repository stars) received source-level inspection. This exposed several useful
boundaries: UniAD/ComDrive aggregation is not ST-P3, LMDrive is LangAuto rather
than Town05, SimScale/Drive-JEPA v2 navtest is not NAVSIM v1 or navhard, and the
highly cited DLV verification paper is an Autonomous Driving false-positive.

Recent coverage was handled explicitly. Of 33 papers from 2025, eight were
imported, one was already covered, and the remainder were assigned evidence-
backed survey/source/protocol decisions. Of the three 2026 papers, Chat2Scenic
and Drive-JEPA were imported and StandardE2E was retained as a benchmark/source
paper rather than receiving comparator rows.

## Benchmark coverage added

The 24 linked contracts are deliberately split where evaluator semantics differ:

| Family | Contracts |
|---|---|
| Closed-loop CARLA | Town05 Long, Town05 Short, Leaderboard 1.0, Longest6, Bench2Drive v0.0.3 |
| NAVSIM/planning | NAVSIM v1 PDMS, NAVSIM v2 one-stage navtest EPDMS, NAVSIM v2 two-stage navhard EPDMS, strict nuScenes ST-P3 planning |
| Language-guided driving | LangAuto Long, Short, Tiny, Notice, Sequential |
| Occupancy/map | Occ3D 17-class, PG-Occ 15-class, SurroundOcc dense labels, OpenLane-V2 canonical, OpenLane-V2 Lane Segment |
| Driving language/reasoning | DriveLM Graph VQA, AutoTrust, Ego3D-Bench |
| Scenario/attention | Chat2Scenic regulation-grounded generation, DriverGaze360 panoramic attention |

Three contracts intentionally remain empty: canonical OpenLane-V2 v1.0,
AutoTrust, and NAVSIM v2 navhard. AutoTrust reports only prior/external models;
navhard was separated from one-stage navtest; and no paper-owned canonical
OpenLane-V2 row passed the import rules in this wave.

## Evaluation imports

Task-native imports cover historical and current chains rather than only recent
leaderboard leaders:

- CARLA lineage: TransFuser/MMFN, Latent TransFuser, TF++, PlanT, LAW, SSR.
- Bench2Drive: LEAD/TFv6, TF++, VADv2, ReCogDrive, Drive-JEPA, WoTE.
- NAVSIM v1: Drive-JEPA, ReflectDrive, ReCogDrive, VADv2, WoTE, LEAD/LTFv6,
  LAW.
- NAVSIM v2 navtest: Drive-JEPA and SimScale DiffusionDrive.
- Strict ST-P3: VAD, LAW, and Senna, with ego-status variants excluded.
- Language-guided/reasoning: LMDrive across five LangAuto protocols, DriveLM,
  Chat2Scenic, Ego3D-VLM, and DriverGaze360.
- Occupancy/map: CTF-Occ, SurroundOcc, PG-Occ, and LaneSegNet.

Top-100 papers whose native taxonomy is specialized were not forced onto the
umbrella task. FB-BEV received official-test mAP/NDS rows on nuScenes 3D Object
Detection (`dataset 677`, `task 333`), and DDRNet received its official-test
Cityscapes mIoU row (`dataset 74`, `task 3`).

## Independent verification and cleanup

Every populated task-native leaderboard received a final verifier pass; the two
changed specialized leaderboards were also fully audited. No imported score row
was deleted. Important verifier corrections were:

- SimScale `17755`: corrected from the best GTRS subfamily row (84.8) to the
  paper's overall best introduced NAVSIM v2 variant, DiffusionDrive with
  pseudo-expert co-training (EPDMS 85.9, 61M parameters).
- `uses_additional_data`: corrected for LEAD, ReCogDrive, ReflectDrive, VADv2,
  LTFv6+LEAD, DriveLM, Chat2Scenic, and FB-BEV where pretraining/external data
  was source-evident.
- Openness: CTF-Occ `17691` and DDRNet `17761` changed from open to closed
  because exact evaluated checkpoints/training artifacts are not accessible.
- DriverGaze360 `17751`-`17754`: exact parameter count set to 55,571,934 from
  the released implementation.
- SurroundOcc methodology now records FCOS3D initialization.

The pre-existing Cityscapes leaderboard mixed validation and official-test
rows. The verifier retained official-test IDs `17761`, `7454`, `7456`, and
`7465`, and removed 18 wrong-split/non-server rows:
`6178`, `6104`, `6117`, `6152`, `7210`, `639`, `16641`, `559`, `835`,
`12381`, `12388`, `12393`, `12398`, `12232`, `10316`, `6201`, `10038`,
and `15059`.

## Remaining field gaps

The deferred papers provide a concrete next benchmark backlog rather than
ambiguous failures. Major missing specialized families include:

- online vectorized HD-map construction on nuScenes/Argoverse2;
- Argoverse v1.1 and INTERACTION v1.2 motion forecasting;
- Waymo traffic-scene generation and custom safety-critical CARLA generation;
- automotive camera/lidar novel-view synthesis and long-video generation;
- KITTI-360 semantic/panoptic label transfer;
- Highway-env language-agent driving and SMARTS 2.0 planning;
- indoor VLN/Matterport3D2, which should not remain under Autonomous Driving.

These were not collapsed into superficially similar datasets. Their exact
splits, route suites, label regimes, metrics, and available artifacts are
recorded in `top100-ledger.csv` and `paper-worklist.csv`.

## Validation

The final evaluation metric validator accepts all rows added or changed in this
pass and reports no missing `best_metric` values or safe standardizations. It
continues to flag four unrelated pre-existing mismatches outside this task:
ETH3D relative, FLORES-101, FLORES-200 devtest, and Livebench.

Supporting artifacts:

- `field-map.md` — seven-surface field map and protocol risks;
- `top100-ledger.csv` — complete live top-100 decisions;
- `paper-worklist.csv` — paper/benchmark/comparator/artifact worklist;
- `import-ledger.csv` — surviving evaluation IDs and skipped outcomes;
- `verification-ledger.md` — per-benchmark audit results and cleanup.
