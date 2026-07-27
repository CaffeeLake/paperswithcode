# Video segmentation verification ledger

Snapshot: 2026-07-23. Task id: `262`.

Imports were frozen before benchmark verification. Each audit uses one exact
dataset/split/metric contract and checks paper-native provenance, model mode,
duplicate rows, openness, official weights/Hugging Face links, parameter
metadata, additional-data usage, and rank order.

## Completed audits

| Dataset id | Leaderboard contract | Verdict | Corrections / cleanup decision |
|---:|---|---|---|
| 606 | YouTube-VIS 2019 validation, closed-set mask AP | 11 compatible rows; 2 incompatible rows | Delete `9635` (HQ-SAM-L prompt-based zero-shot mask refinement) and `9080` (VideoCutLER class-agnostic zero-shot train-split duplicate). Kept paper-native DVIS++ `17820` at 68.3 and documented that the released checkpoint filename says 68.8. |
| 607 | YouTube-VIS 2021 validation, closed-set mask AP | 9 compatible rows; 2 incompatible rows | Delete `17926` (OMG-Seg open-vocabulary setup) and `9081` (VideoCutLER class-agnostic zero-shot duplicate). VidEoMT `6279` now links its exact official benchmark checkpoint. |
| 608 | YouTube-VIS 2022 long-video subset, AP^L | 4/4 pass | VidEoMT and CAVIS/DVIS-family provenance and release metadata normalized. LOMM remains deliberately absent because its source column is plain AP, not proven AP^L. |
| 609 | OVIS validation, mask AP | 7/7 pass | VidEoMT `6281` now links its exact official OVIS checkpoint; no score or identity changes. |
| 610 | VIPSeg validation, closed-set VPQ | 7/7 pass | VidEoMT `6282` now uses the exact official checkpoint and raw 322,652,414 parameter count. OMG-Seg `17924` provenance corrected from Table 6 to Table 7. |
| 611 | VSPW validation, mIoU | 3/3 pass | VidEoMT `6283` corrected to additional-data=true and linked to the exact official checkpoint. PMT `17932` had an unsupported input-resolution claim removed. |
| 266 | YouTube-VOS public train-derived 2,758/690-video split, J&F | 2/2 pass | DINOv3 `564` and LingBot-Vision `12386` use the same training-free label-propagation protocol. Both now record external pretraining; DINOv3 has its exact official gated HF model and raw 6,716,035,072 parameter count. This page is intentionally separate from official challenge-server results. |
| 267 | MOSE official validation, J&F | 10 compatible rows; 1 wrong split | Delete DINOv3 `565`: its 55.6 result uses a custom 1,206/301 partition of MOSE training data. Corrected additional-data/openness and release metadata on the ten surviving rows. |
| 263 | DAVIS 2017 validation, first-frame ground-truth mask, J&F | 25 compatible rows; 2 wrong setups | Delete LLaVA-OneVision-2 `7110` (language-conditioned point tracking converted through SAM 2) and VideoCutLER `9082` (annotation-free unsupervised protocol). Corrected SAM 3, DINOv3, SAM 2, EdgeTAM, and DINO provenance/artifact metadata; ranks recalculated. |
| 1168 | DAVIS 2016 validation, first-frame ground-truth mask, J&F | 5 compatible rows; 1 wrong supervision setup | Delete SAM-Track `13738`: its 92.0 result initializes from a generated click/SAM annotation rather than the provided first-frame mask. XMem and MobileVOS metadata/provenance corrected. |
| 1621 | LVOS v1 validation, first-frame mask at 480p, J&F | 3/3 pass | SAM2Long, EfficientTAM, and Cutie use the exact official long-video validation protocol. SAM2Long's checkpoint parameter count normalized to 224,400,000 across its rows. |
| 1620 | ReVOS official validation, overall referring+reasoning J&F | 8/8 pass | VideoLoom, Sa2VA, Omni-R1, ViLLa, InstructSeg, GLUS, VISA, and DecAF all use the overall benchmark score rather than component columns. Corrected additional-data metadata on Sa2VA and VISA. |
| 1623 | ReasonVOS official zero-shot evaluation, J&F | 3/3 pass | DecAF, GLUS, and VideoLISA are paper-native overall scores. Corrected VideoLISA external-pretraining metadata. |
| 1622 | DAVIS 2017 official test-dev server, first-frame ground-truth mask, J&F | 4/4 pass | Cutie, DEVA, STCN, and SAM-PT are paper-native, unique, and split-compatible. DEVA's OVIS-trained variant now records additional data and exact component provenance. |
| 1182 | RefVOS-DAVIS public DAVIS 2017 validation, referring-expression J&F | 19/19 pass | All rows use text-referred object segmentation rather than ordinary mask-initialized DAVIS. They are unique paper-native best variants and report overall J&F. Corrected additional-data metadata on Sa2VA, VISA, VideoLISA, and DEVA. |
| 595 | SA-V official validation, first-frame ground-truth mask, J&F | 4/4 pass | SAM 3, SAM2Long, SAM 2, and EdgeTAM are paper-native and split-compatible. Corrected additional-data flags, SAM2Long parameters, and SAM 2's exact HF link. SeC-4B 82.7 is a verified post-freeze follow-up, not imported. |
| 596 | SA-V official test, first-frame ground-truth mask, J&F | 6/6 pass | SAM 3, SAM2Long, SAM 2, EfficientTAM, EdgeTAM, and SAM-I2V pass. Corrected additional-data flags, SAM2Long methodology, and SAM 2's exact HF link. SeC-4B 81.7 is a verified post-freeze follow-up, not imported. |
| 1183 | MeViS 140-video official Val server, J&F | 13/13 pass after two split corrections | Sa2VA `17846` corrected from Val^u 62.9 to official Val 46.9; VideoLISA `17895` corrected from Val^u 54.5 to official Val 44.4. Corrected additional-data and openness metadata. Dataset text now explicitly forbids mixing the 50-video Val^u split. |
| 1618 | Refer-YouTube-VOS 2021 public validation, overall J&F | 22/22 pass | All rows are paper-native introduced models on the 202-video public validation protocol. Corrected five additional-data flags, removed a base-only/non-exact HF link from DecAF, and recalculated ranks. |
| 1619 | MOSEv2 official validation, J&F | 1/1 pass | SeC-4B `17886` is a paper/official-release-native result with exact public HF weights and raw parameter count. |
| 1624 | Cityscapes-VPS official validation, VPQ | 1/1 pass | TarViS `17922`, paper Table 2, shared multi-task Swin-L model and VPS target. |
| 1625 | KITTI-STEP official validation, STQ | 1/1 pass | TarViS `17923`, paper Table 2; normalized the source's 0.72 ratio to the configured 0–100 STQ scale. |
| 1626 | YouTube-VOS 2018 official validation server, J&F/G | 6/6 pass | Cutie, 2-shot XMem, STCN, UniRef++, HQ-SAM-PT, and SegGPT all use the standard first-frame-mask server protocol. Corrected UniRef++ methodology and SegGPT additional-data metadata. |

## Central cleanup

Deleted exactly eight incompatible rows after all audits: `565`, `7110`,
`9080`, `9081`, `9082`, `9635`, `13738`, and `17926`. These covered,
respectively, a custom MOSE split; language/point-tracking DAVIS; two
class-agnostic zero-shot VideoCutLER VIS rows; unsupervised DAVIS; prompt-based
HQ-SAM VIS; click-initialized DAVIS; and open-vocabulary YTVIS21. Ranks were
recalculated on every affected leaderboard.

No verifier imported new evaluation rows after the import freeze.

## Audit queue

None. All 23 dataset pages linked to task 262 were audited.
