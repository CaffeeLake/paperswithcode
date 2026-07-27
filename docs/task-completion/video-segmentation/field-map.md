# Video segmentation field map

Snapshot: 2026-07-23. Task: `video-segmentation` (id 262). This map was
completed before evaluation imports. It preserves the requested scope: a
holistic overview of major benchmarks, major papers and their comparison-table
neighbors, with an explicit decision for every paper in the live top 100.

## Pre-import state

- The live task API has 233 papers. The required top-100 slice has only 9
  papers with video-segmentation evaluations and 91 with none.
- The task currently has 40 rows across 12 datasets. DAVIS 2017 val has 12
  papers; OVIS, VIPSeg, VSPW, and YouTube-VIS 2022 each have one.
- The top-100 pre-import reconciliation was: 9 already covered, 63 missing a
  benchmark, 10 requiring protocol/source-cell adjudication, 4 benchmark or
  survey papers whose comparator scores are not paper-native, and 14 papers
  that are not video-segmentation result papers.
- The task tag is broad and noisy. It combines semi-supervised VOS,
  unsupervised VOS, VIS, referring/reasoning VOS, VPS, VSS, medical video
  segmentation, matting, and several false-positive adjacent tasks.

The exact live reconciliation is in [top100-ledger.csv](top100-ledger.csv).

## Completed state

- The task now has 174 verifier-clean rows across 59 papers and 23 datasets,
  up from 40 rows across 12 datasets.
- This run added 141 surviving paper-native rows for 44 source papers and
  wired or repaired 11 benchmark pages. Forty-one previously uncovered papers
  in the requested top 100 gained evaluations.
- The final top-100 reconciliation has 48 represented papers and 52
  evidence-backed deferrals/non-result decisions. Two initially represented
  papers became deferrals after their only rows failed protocol verification.
- All 23 task-linked dataset pages were audited. Eight incompatible rows were
  removed centrally, and two MeViS rows were corrected from the 50-video
  Val^u split to the 140-video official Val-server cells.
- The issue-requested author spelling is corrected, and DVIS++, CAVIS,
  DVIS-DAQ, and LOMM now have 19 surviving paper-native evaluation rows.

## Seven research surfaces

### 1. Live task page and local database

The live trending endpoint was inventoried at 100 rows. High-signal uncovered
papers include SegGPT, PerSAM, Sa2VA, VideoLoom, DVIS++, DVIS-DAQ, MeViS,
LVOS, MOSE/MOSEv2, and numerous referring/reasoning VOS papers. Existing
coverage is concentrated on DAVIS 2017, SAM-family rows, and VidEoMT.

### 2. Semantic Scholar

Broad and recent searches covered canonical video segmentation, VOS, VIS,
VPS, VSS, benchmark names, and the requested method families. More than 500
plausible records were deduplicated before rate limiting. Historical anchors
include DAVIS, Space-Time Memory Networks, YouTube-VOS, YouTube-VIS, XMem,
AOT, MinVIS, and DVIS. The explicit 2025/2026 slice includes LOMM, MOSEv2,
Beyond Appearance, Local2Global, VidEoMT, Video Patch Pruning, SA-VIS, and
new open-world/open-vocabulary protocols.

### 3. Legacy Papers With Code

The 236 MB legacy evaluation dump was streamed. The selected, deduplicated
slice contains 67 leaderboards, 880 rows, and 239 distinct papers:

| Family | Leaderboards | Rows | Papers |
|---|---:|---:|---:|
| Semi-supervised VOS | 15 | 377 | 91 |
| Video instance segmentation | 8 | 132 | 49 |
| Video salient-object detection | 10 | 95 | 13 |
| Mixed/unspecified VOS | 12 | 91 | 22 |
| Unsupervised VOS | 6 | 76 | 37 |
| Referring VOS | 3 | 40 | 25 |
| Video panoptic segmentation | 3 | 26 | 14 |
| Video semantic segmentation | 5 | 26 | 16 |
| Other explicit video-segmentation protocols | 5 | 17 | 14 |

Strong legacy families include DAVIS 2017 val (80 rows/54 papers), DAVIS 2017
test-dev (58/36), DAVIS 2016 (78/54), YouTube-VOS 2018 (53/27), YouTube-VIS
2019 val (43/32), OVIS val (44/29), YouTube-VIS 2021 (26/19), Refer-YTVOS
(17/11), MeViS (14/14), VIPSeg (12/8), and MOSE (16/8).

### 4. GitHub

Repository activity confirms both historical and recent relevance. Snapshot
stars include `tue-mps/eomt` 615, `tue-mps/videomt` 252,
`zhang-tao-whu/DVIS` 163, `Seung-Hun-Lee/CAVIS` 116, `tue-mps/pmt` 52,
`Seung-Hun-Lee/LOMM` 34, and `SkyworkAI/DAQ-VS` 15. Historical repos such as
VisTR, SeqFormer, SipMask, and GenVIS remain useful comparison anchors. Stars
are prioritization signals, never score evidence.

### 5. Hugging Face

VidEoMT has benchmark-specific first-party checkpoints for YouTube-VIS 2019,
2021, 2022, OVIS, VIPSeg, and VSPW. First-party releases also exist for
DVIS++, DVIS-DAQ, and CAVIS. LOMM's official GitHub release is an openness
signal even without a confirmed exact HF checkpoint. Community dataset mirrors
were treated only as discovery leads.

### 6. Comparison-table expansion

The requested lineage is:

`MaskTrack R-CNN / VisTR / SeqFormer / Mask2Former → MinVIS / IDOL / GenVIS
→ DVIS → DVIS++ → DVIS-DAQ / CAVIS → LOMM / VidEoMT`.

Repeated adjacent comparators include CTVIS, TCOVIS, NOVIS, VITA, UNINEXT,
TarViS, Video K-Net, Tube-Link, and Video-kMaX. Comparator values will not be
copied from later papers; each source paper gets its own worker.

### 7. Recent papers

The 2025/2026 slice was explicitly adjudicated. Standard closed-set candidates
go to existing VIS/VOS leaderboards. Continual, sparse-label,
open-vocabulary, open-world, aerial, medical, and reasoning protocols are
separated or deferred until an exact benchmark contract exists.

## Benchmark families and contracts

| Benchmark family | Canonical split/metric | Current state | Decision |
|---|---|---|---|
| DAVIS 2017 | val J&F | Wired, 12 papers | Wave 1 import/verify |
| DAVIS 2017 | test-dev J&F | Missing | Add separately |
| DAVIS 2016 | val J&F | Wired, 3 papers | Wave 1 import/verify |
| YouTube-VOS | edition-specific overall J&F | Wired thinly, edition label ambiguous | Repair source; preserve editions |
| MOSE | val J&F | Wired, 4 papers | Repair source; import |
| LVOS / MOSEv2 | long/complex VOS J&F | Missing | Add; do not import dataset-paper comparators |
| YouTube-VIS 2019 | val mask AP | Wired, 4 papers | Issue/comparator waves |
| YouTube-VIS 2021 | val mask AP | Wired, 3 papers | Issue/comparator waves |
| YouTube-VIS 2022 | long subset AP^L | Wired, 1 paper | Strict protocol gate |
| OVIS | val mask AP | Wired, 1 paper | Issue/comparator waves |
| VIPSeg | val VPQ | Wired, 1 paper | Issue/universal waves |
| VSPW | val mIoU | Wired, 1 paper | Issue/universal waves |
| Refer-YTVOS | J&F | Missing | Add, high top-100 demand |
| Ref-DAVIS17 | J&F | Exists under referring task | Link/verify |
| MeViS | J&F | Exists under referring task | Link/verify |
| ReVOS / ReasonVOS | J&F (reasoning extras excluded) | Missing | Add separately |
| Cityscapes-VPS | VPQ | Missing | Universal wave |
| KITTI-STEP | STQ | Missing | Universal wave |
| FBMS / YouTube-Objects | unsupervised protocol | Missing | Defer until supervision-specific pages |
| BURST | HOTA/OWTA by protocol | Missing | Defer/split |
| Medical/surgical datasets | Dice/IoU/HD by dataset | Missing | Defer to domain-specific contracts |

## Immediate issue chain: paper-native values

Only configured headline metrics are eligible. Online/offline mode and backbone
must remain in the row identity/methodology.

| Paper/variant | YTVIS19 AP | YTVIS21 AP | YTVIS22 AP^L | OVIS AP | VIPSeg VPQ | VSPW mIoU |
|---|---:|---:|---:|---:|---:|---:|
| DVIS++ ViT-L online | 67.7 | 62.3 | 37.5 | 49.6 | 56.0 | 62.8 |
| DVIS++ ViT-L offline refiner | 68.3 | 63.9 | 50.9 | 53.4 | 58.0 | 63.8 |
| DVIS-DAQ ViT-L online | 68.3 | 62.4 | 42.0 | 53.7 | 57.4 | — |
| DVIS-DAQ ViT-L offline refiner | 69.2 | 64.5 | — | 57.1 | — | — |
| CAVIS ViT-L online | 68.9 | 64.6 | 38.6 | 53.2 | 56.9 | — |
| CAVIS ViT-L temporal refiner | 69.4 | 65.3 | — | 57.1 | 58.5 | — |
| LOMM ViT-L online | 69.1 | 65.0 | unresolved | 51.7 | — | — |
| LOMM ViT-L offline refiner | 70.1 | 66.2 | unresolved | — | — | — |
| VidEoMT ViT-L/DINOv2 online | 68.6 | 63.1 | 42.6 | 52.5 | 55.2 | 64.9 |

LOMM labels its YouTube-VIS 2022 column `AP`, not `AP_L`, so its 48.2/54.0
scores are deferred from the existing AP^L leaderboard. CAVIS's own appendix
reports 38.6; a later VidEoMT comparison reports 39.5. Paper-native policy uses
38.6 unless the CAVIS release proves a later checkpoint.

## Major paper worklist

Wave 1 completed the requested DVIS++, CAVIS, DVIS-DAQ, LOMM, and VidEoMT
chain. The top-100 and comparison-table waves then covered VIS ancestors,
universal VPS/VSS methods, VOS, referring VOS, and reasoning VOS. Every
top-100 paper now has an imported/already-covered status or an explicit
evidence-backed defer/not-results decision in the ledger.

## Risks

- Never merge DAVIS editions, val/test-dev, or supervised/unsupervised modes.
- Preserve YouTube-VOS and YouTube-VIS editions.
- Do not rank AP, AP^L, J&F, mIoU, VPQ, STQ, HOTA, OWTA, EAO, and
  Tube-Boundary AP as aliases.
- Exclude component metrics, FPS, parameter counts, thing/stuff,
  seen/unseen, and common/uncommon subscores unless separately configured.
- Universal models cross VOS, VIS, VPS, and VSS in one paper; each row retains
  its exact dataset, split, mode, and prompt/reference setup.
- Benchmark papers' comparator rows are discovery leads, not paper-native
  evaluation imports.
