# Autonomous Driving verification ledger

This ledger records one source-driven audit per changed or high-risk leaderboard.
Verifier findings override optimistic import-worker results. Net additions are not
counted as complete until their benchmark contract passes here.

## Audit scope

- CARLA Leaderboard 1.0 — exact SENSORS-track version, route set, and DS/RC/IP.
- CARLA Town05 Long — fixed Town05 Long route protocol only.
- CARLA Town05 Short — fixed Town05 Short route protocol only.
- Bench2Drive v0.0.3 — current 220-route evaluator; DS and SR.
- NAVSIM v1 — navtest PDMS; do not mix NAVSIM v2 EPDMS.
- nuScenes ST-P3 planning — exact horizon aggregation and collision evaluator.
- CARLA Longest6 — exact 36-route TransFuser-defined CARLA 0.9.10 protocol.
- Occ3D-nuScenes — 0.4 m, 17-class, camera-visible validation contract.
- SurroundOcc-nuScenes dense labels — Poisson-reconstructed label contract only.
- OpenLane-V2 Lane Segment v1.0 — reduced DET_l+TOP_ll aggregation only.
- DriveLM Graph VQA — P1-P3 aggregate, fixed judge and 799-frame validation split.
- AutoTrust — paper-release reference pool and normalized overall score.

## Audit results

### CARLA Leaderboard 1.0 (`1591`) — passed

Independent audit kept all six rows: `17656`-`17661`. The verifier confirmed
the LB1 SENSORS contract (CARLA 0.9.10/0.9.10.1, 100 secret-route evaluations),
paper ownership, best introduced variant per metric, variant-disambiguating model
names, and public official code/weight archives. No LB2, Longest6, comparator,
duplicate, or split contamination was present; no corrections were required.

### CARLA Town05 Long (`1590`) — final pass

Final independent audit kept `17654`-`17655`, `17709`-`17711`, and
`17762`-`17764`. TransFuser is the exact Table 1a nine-run ClearNoon result;
LAW and SSR report the inherited Town05 Long contract with exact paper-table
cells. The latter papers do not restate every route/weather detail, but no
conflicting setup evidence exists. Infraction Score correctly maps to the
multiplicative Infraction Penalty. Ownership, variants, openness, duplicates,
and metadata all passed; no corrections were required.

### CARLA Town05 Short (`1592`) — final pass

Independent audit kept `17652`-`17653`. These are the primary nine-run Table 1a
TransFuser means on the exact CARLA 0.9.10 ClearNoon ten-route short protocol.
The paper reports no aggregate Infraction Penalty cell. A different ablation
configuration and comparator rows were correctly excluded; openness and null
metadata fields are supported by the official repository and sources.

### Bench2Drive v0.0.3 (`1593`) — final pass with metadata fixes

Independent audit kept all 12 rows: LEAD `17700`-`17701`, TF++
`17759`-`17760`, VADv2 `17721`-`17722`, ReCogDrive `17705`-`17706`,
Drive-JEPA `17731`-`17732`, and WoTE `17718`-`17719`. All use the full official
220-route DS/SR protocol; v0.0.3's multi-ability-only change does not alter
these metrics. The verifier corrected `uses_additional_data=true` on LEAD and
ReCogDrive's four rows because their training uses separately collected and
multi-dataset data. All scores, ownership, variants, open/closed artifact state,
parameters, and duplicates otherwise passed; no row was deleted.

### nuScenes Open-Loop Planning, ST-P3 (`1595`) — final pass

Independent audit kept all 18 rows: VAD `17662`-`17667`, LAW
`17712`-`17717`, and Senna `17724`-`17729`. Every row uses the strict
camera-only, no-ego-status VAD/ST-P3 aggregation (2 Hz samples from 0.5 s
through each horizon) and cumulative occupancy/ego-footprint collision rates in
percentage points. Best introduced variants, DriveX additional-data metadata,
and exact artifact openness all passed. In particular, Senna stays closed
because the public VLM weights do not include the evaluated E2E integration.
No fixes or deletions were required.

### NAVSIM v1 (`1594`) — final pass with metadata fixes

Independent audit kept all seven rows: `17730`, `17704`, `17707`, `17723`,
`17720`, `17702`, and `17708`. Scores use the original navtest five-component
PDMS on a 0-100 scale; v2 EPDMS and oracle rows are absent. The verifier set
`uses_additional_data=true` on ReflectDrive, ReCogDrive, VADv2, and LTFv6+LEAD
because their source methods use pretrained/external driving corpora. Scores,
ownership, best variants, openness, HF links, parameter counts, ranks, and
duplicates otherwise passed; no deletion was required.

### CARLA Longest6 (`1596`) — final pass

Independent audit kept all nine rows: PlanT `17668`-`17670`, TF++
`17671`-`17673`, and Latent TransFuser `17674`-`17676`. The verifier confirmed
the original 36-route CARLA 0.9.10/0.9.10.1 contract rather than Longest6 v2,
the papers' per-metric best introduced variants, Infraction Score mapping,
ownership, live public artifacts, parameters, ranks, and duplicates. No fix or
deletion was required.

### Occ3D-nuScenes (`1597`) — final pass with openness fix

Independent audit kept `17691` at mIoU 28.53 on the exact 17-class,
camera-visible, 0.4 m nuScenes-validation contract. It corrected
`is_open=true` to `false`: the current official repository exposes dataset and
visibility utilities but no accessible exact CTF-Occ training branch/checkpoint
or HF artifact. Score, ownership, parameters, and duplicates otherwise passed.

### SurroundOcc-nuScenes Dense Labels (`1599`) — final pass

Independent audit kept `17677` at mIoU 20.30 on the exact nuScenes-validation
Poisson-reconstructed dense-label contract (200x200x16, 0.5 m). Public official
training/inference/label-generation code and the exact public checkpoint support
`is_open=true`. The verifier added FCOS3D initialization to methodology; score,
ownership, HF/parameter fields, and duplicates required no correction.

### OpenLane-V2 Lane Segment v1.0 (`1600`) — final pass

Independent audit kept `17678` at Lane Segment OLS 29.7. The verifier
recomputed the reduced score from DET_l 31.8 and TOP_ll 7.6, confirmed the
re-annotated subset_A split and isolation from canonical four-term OLS/devkit
v2.1.0, and verified the exact official public HF checkpoint. Parameters remain
unset because the cited 6.74M figure is not the full final model.

### DriveLM Graph VQA (`1601`) — final pass with metadata fix

Independent audit kept `17690` at 72.51 on the exact 799-frame P1-P3
ChatGPT-3.5 aggregate. It confirmed paper ownership, 3.955B total parameters,
closed exact weights, and oracle/comparator exclusions. The verifier set
`uses_additional_data=true` because DriveLM-Agent initializes from web-scale
BLIP-2-Flan-T5-XL and clarified LoRA/predicted graph context methodology.

### LangAuto Long (`1606`) — final pass

Independent audit kept `17733`-`17735` on the exact 32-route, all-eight-town,
greater-than-500m language-guided contract. Per-metric best LMDrive variants,
CARLA metric semantics, exact official open HF checkpoints, 7B sizing, ranks,
and duplicates all passed.

### LangAuto Short (`1607`) — final pass

Independent audit kept `17736`-`17738` on the exact 16-route, all-eight-town,
150-500m language-guided contract. Per-metric best LMDrive variants, official
open HF checkpoints, 7B sizing, and duplicate/rank state all passed.

### LangAuto Tiny (`1608`) — final pass

Independent audit kept `17739`-`17741` on the exact 16-route, all-eight-town,
less-than-150m language-guided contract. Per-metric best variants, CARLA score
semantics, exact open HF checkpoints, 7B sizing, ranks, and duplicates passed.

### LangAuto Notice (`1609`) — final pass

Independent audit kept `17742` at Infraction Penalty 0.91. The verifier
confirmed this is the aggregate higher-is-better Infraction Score, not one of
the paper's per-kilometer collision/violation diagnostics, and verified the
best Vicuna-v1.5 variant, exact public HF checkpoint, and 7B size.

### LangAuto Sequential (`1610`) — final pass

Independent audit kept `17743`-`17745` on the exact 10%-trigger regime that
merges the current and next one or two language instructions. Per-metric best
LLaVA/Vicuna variants, CARLA score semantics, exact public HF checkpoints, 7B
sizing, and duplicate/rank state all passed.

### Occ3D-nuScenes PG-Occ 15-Class (`1611`) — final pass

Independent audit kept `17746` at mIoU 15.15. Released evaluator code confirms
the exact 0.4 m camera-mask grid and deletion of indices 0 and 12 before the
15-class mean. Additional-data use, exact public v1.0 checkpoint, ownership,
null HF/parameter fields, and duplicate state all passed.

### nuScenes 3D Object Detection (`677`, task `333`) — final pass with metadata fixes

Independent full audit kept all 81 existing rows. For new FB-BEV rows
`17757`-`17758`, paper Table 2 verifies official-test mAP 53.7/NDS 62.4 for
V2-99, 640x1600, nine historical keyframes, and no TTA. The verifier set
`uses_additional_data=true` because the selected variant uses extra depth
pretraining. Public code supports openness; no exact selected checkpoint/HF
artifact or source-backed parameter count exists. No row was deleted.

### Chat2Scenic Regulation-Grounded Scenario Generation (`1612`) — final pass with metadata fixes

Independent audit kept `17747`-`17748` at CSR 76.42 and FA 58.17 on the exact
123-case Scenic 3.1.0/CARLA 0.9.15 suite. C11 is the best eligible own variant
and FA recomputes from CSR x SQ. The verifier set `uses_additional_data=true`
for the proprietary pretrained Gemini backbone and retrieval corpus and expanded
the protocol methodology. Public framework/data do not make the exact backbone
open; null HF/parameter fields and duplicate state passed.

### Ego3D-Bench (`1613`) — final pass

Independent audit kept `17749`-`17750`: GPT-4o Accuracy 73.2 and
Gemini-1.5-Pro RMSE 7.2 are the metric-wise best introduced Ego3D-VLM variants.
HF parquet confirms exactly 8,675 rows and all source/category counts. Public
framework code does not expose proprietary evaluated weights; closed status,
null HF/parameter fields, ownership, license caveat, and duplicates all passed.

### DriverGaze360 Panoramic Driver Attention (`1614`) — final pass with parameter fixes

Independent audit kept `17751`-`17754` on the exact town-disjoint five-camera,
16-frame validation setup. Native KLD/SIM/CC/NSS scores, Kinetics-400 extra-data
flag, ownership, and exact gated public HF checkpoint passed. The verifier set
`num_parameters=55,571,934` on all four rows from the released code/model
composition and clarified that `drivergaze360.pt`, not the DADA checkpoint, is
the evaluated artifact.

### Cityscapes Official Test (`74`, task `3`) — final pass with split cleanup

Independent full audit reduced 22 mixed-split rows to four official-test rows.
It retained DDRNet `17761`, DeepLabv3+ `7454`, DeepLabv3 `7456`, and DeepLab-CRF
`7465`; deleted 18 validation/non-server rows as wrong split; and set extra-data
flags on DeepLabv3/v3+ for coarse annotations. DDRNet's score and 70.2M count
passed, but `is_open` was corrected to `false` because the exact DDRNet-39 1.5x
Cityscapes checkpoint is not released.

### NAVSIM v2 navtest (`1615`) — final pass with best-variant correction

Independent audit kept `17755`-`17756` on the corrected v2.2 human-filtered,
one-stage 12,146-scene EPDMS contract. It corrected `17755` from the best
GTRS-Dense subfamily row (84.8) to the paper's overall best eligible SimScale
variant, DiffusionDrive with pseudo-expert co-training at 85.9 and 61M
parameters. Drive-JEPA remains 87.8. Both exact checkpoints are public in HF
dataset repositories, so openness is true while evaluation HF model URLs remain
null. Additional-data flags, ownership, ranks, navhard separation, and
duplicates passed; no row was deleted.

All 21 populated task-native leaderboards and both changed specialized
leaderboards completed independent verifier passes. The three empty contracts
(OpenLane-V2 canonical, AutoTrust, and NAVSIM v2 navhard) were source-validated
during benchmark creation and contain no evaluation rows to compare.
