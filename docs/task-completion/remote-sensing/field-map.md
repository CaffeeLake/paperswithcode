# Remote Sensing field map

Status: seven-surface research gate complete. This document preserves the initial
stocktake and research rationale; final database outcomes are summarized in
`completion-report.md` and `verification-ledger.md`.

## Scope and live-page stocktake

The completion contract is the top 100 trending papers on the live
[`remote-sensing`](https://paperswithcode.co/tasks/remote-sensing/) task page, plus a
holistic map of the wider field. The task is broad: satellite, aerial, UAV, SAR,
hyperspectral, LiDAR, and multimodal Earth-observation work is mixed on one paper
feed.

- Initial snapshot: `tasks.id = 318`, `slug = remote-sensing`, 676 live papers.
- Top-100 snapshot: 100/100 have no evaluation row for task 318; 40/100 are from
  2025 or 2026.
- Initial leaderboard state: task 318 had no `task_datasets` rows, configured
  metrics, or evaluations. The completed state has 62 dataset rows, 78 metric
  contracts, and 66 verified evaluations.
- The durable paper reconciliation is in [top100-ledger.csv](top100-ledger.csv).
  The source-paper queue is in [paper-worklist.csv](paper-worklist.csv).

The top-100 paper mix is unusually heterogeneous. A title/abstract pass found
substantial clusters in foundation/pretraining, vision-language models, semantic
segmentation/buildings/roads, change detection, aerial object detection/counting,
generation/super-resolution, classification, and SAR/hyperspectral/LiDAR. Several
papers are benchmark or dataset introductions; others are surveys, tools, or broad
models whose remote-sensing result is only one downstream evaluation.

## Evidence surfaces

### 1. Live task page and local database

The live page is dominated by recent benchmark/VLM work at the top, followed by
high-impact foundation models and application papers. Prominent examples include
RSHR-Bench, DINOv3, SegEarth-OV3, RAMEN, GeoChat, LSKNet, ChangeMamba,
RemoteCLIP, SSL4EO-S12, SatlasPretrain, Prithvi-EO-2.0, and FLAIR. The local DB
has only sparse relevant dataset rows under other tasks (for example DIOR under
object detection, LoveDA under image segmentation, and EuroSAT under image
classification), so task 318 cannot currently surface a leaderboard.

### 2. Semantic Scholar citation and keyword searches

Broad, subarea, benchmark-name, and explicit 2025-2026 searches recover both the
classic dataset papers and the newer foundation-model chain. High-citation field
anchors include DOTA, NWPU-RESISC45, EuroSAT, AID, DIOR, BIT, UNetFormer,
ChangeFormer, LoveDA, BigEarthNet, iSAID, SpaceNet, xView, xBD, and SEN12MS.
The modern comparison chain includes SatMAE, Scale-MAE, RemoteCLIP,
SpectralGPT, CROMA, GEO-Bench, SSL4EO-S12, DOFA, Prithvi-EO-2.0, AnySat,
TerraMind, Galileo, and OlmoEarth. Citation count is treated as only one signal:
newer benchmark and model papers are also ranked by the live page, repository
activity, and artifact use.

### 3. Legacy Papers With Code dump

Legacy PwC confirms that `Remote Sensing` itself was empty while its evaluations
were fragmented across narrower and generic tasks. The strongest historical
families are:

- Aerial object detection: DOTA (57 rows), HRSC2016 (9), DIOR-R (8), DIOR (4),
  xView (3), DOTA 1.0 (2), FAIR1M-2.0 (3).
- Change detection: LEVIR-CD (25), WHU-CD (20), CDD (16), SYSU-CD (9),
  S2Looking (9), DSIFN-CD (9), WHU Building (7), LEVIR+ (7), and OSCD
  3-channel/13-channel variants.
- Remote-sensing segmentation: ISPRS Potsdam, LoveDA, iSAID, Vaihingen,
  INRIA Aerial, SpaceNet, DeepGlobe, Chesapeake roads, Massachusetts Roads,
  and WHU Buildings.
- Scene/land-cover representation: RESISC45, EuroSAT, UC Merced, BigEarthNet,
  SAT-4/SAT-6, CropHarvest, and FireRisk.
- Hyperspectral classification: Pavia University, Indian Pines, Kennedy Space
  Center, Houston, Salinas, and Botswana.
- Additional credible families: xBD building-damage assessment, xView3-SAR,
  and multispectral super-resolution (Sen2Venus/OLI2MSI).

High-signal legacy papers include MTP, RVSA, ChangeMamba, DDPM-CD,
SSL4EO-S12, FG-MAE, and the canonical dataset papers for DOTA, LoveDA,
EuroSAT, RESISC45, BigEarthNet, SpaceNet, and xBD.

### 4. GitHub popularity

Popular paper-linked repositories include GeoChat, ChangeMamba, RemoteCLIP,
LoveDA, SSL4EO-S12, TerraMind, SpectralGPT, Prithvi-EO-2.0, SatMAE, AnySat,
Galileo, GEO-Bench, PANGAEA, Scale-MAE, CROMA, DOFA, SkySense, and
SkySense++. The largest generic repositories (TorchGeo, Raster Vision, curated
lists) are field/tooling signals rather than score sources. Repository popularity
is used only as a field and source-availability signal. Scores still require a
primary paper, official README, or model card. Public checkpoints, model-zoo
links, reproducible configs, and exact Hugging Face links are recorded per paper
before setting `is_open` or `hf_model_url`.

### 5. Hugging Face artifacts

The strongest exact artifact signals are TerraMind, Prithvi-EO-2.0, OlmoEarth,
GeoChat, RemoteCLIP, AnySat, Galileo, DOFA, FLAIR-HUB, and newer
EarthMind/TerraScope resources. TerraMind and Prithvi cards expose public,
ungated weights plus official evaluation configs; OlmoEarth also exposes public
weights, with paper linkage established through its official release rather than
HF tags. These are strong `is_open` signals. The top-100 snapshot contains
substantial additional HF activity for recent VLM, dataset, and foundation-model
papers, but an artifact is not sufficient score evidence unless it ties the exact
variant to a comparable benchmark result.

### 6. Comparison-table expansion

The legacy tables and major foundation-model papers repeatedly point to the same
backbone evaluation suite: EuroSAT/RESISC45/BigEarthNet for classification,
DOTA/DIOR/xView for detection, LoveDA/Potsdam/Vaihingen/iSAID for segmentation,
and LEVIR-CD/WHU-CD/CDD/S2Looking for change detection. The top-100 source-paper
inspection will add paper-native model rows only; comparator columns are used to
discover source papers, not imported as external evaluations.

Repeated comparator chains are:

- Foundation models: ImageNet pretraining, SeCo, SatMAE/SatMAE++, Scale-MAE,
  SSL4EO-S12/L, SatlasPretrain, RVSA/RingMo, CROMA, DOFA, SpectralGPT,
  Prithvi, RemoteCLIP, DINOv2 and satellite-adapted DINO variants.
- Change detection: FC-Siam variants, STANet, BIT, SNUNet-CD, ChangeFormer,
  ChangeStar, ChangeMamba, and CDMaskFormer.
- Segmentation: U-Net, DeepLabV3+, SegFormer, Swin/UPerNet, UNetFormer, and
  newer Mamba backbones; open-vocabulary papers repeat MaskCLIP, SCLIP, SAN,
  CAT-Seg, and SegEarth-OV.
- Oriented detection: Oriented R-CNN, RoI Transformer, ReDet, RTMDet, LSKNet,
  and recent DETR/DINO-style methods.
- Remote-sensing VLMs: LLaVA/Qwen-VL/InternVL families, GeoChat, LHRS-Bot,
  SkyEyeGPT, EarthDial, plus closed GPT/Gemini comparators.

### 7. Explicit 2025/2026 slice

Forty of the top 100 live-page papers are from 2025/2026 (32 from 2025 and eight
from 2026). The high-priority paper-native 2025 slice includes DINOv3, RAMEN,
MAESTRO, RSCoVLM, RS-EoT, FarSLIP, Falcon, Galileo, LWGANet, RoMA,
Text2Earth, NUDT4MSTAR, JL1-CD, DisasterM3, and Dome-DETR. All eight 2026
rows were explicitly adjudicated: Count Anything/CLOC, SemiEarth, CHMv2,
Forest-Change, D3R-DETR, SocioSeg, Utonia, and ABot-Earth 0.5.

Outside the top-100 slice, current benchmark introductions also include
[REOBench](https://arxiv.org/abs/2505.16793),
[BRSIC](https://arxiv.org/abs/2503.04592), and
[VLRS-Bench](https://arxiv.org/abs/2602.07045). These recent protocols must not
be forced onto older leaderboards: corruption robustness, multilingual captioning,
reasoning, ultra-high-resolution VQA, and open-vocabulary segmentation each need
their own benchmark contract if they have repeatable paper-native rows.

## Candidate benchmark families and contracts

| Family | Candidate benchmarks | Canonical contract | Initial wave |
|---|---|---|---|
| Aerial oriented detection | DOTA, DIOR-R, FAIR1M, HRSC2016 | official test/version; mAP; keep AP50/VOC07/VOC12 separate | wave 1 candidate |
| Aerial horizontal detection | DIOR, xView | official split; AP50 or mAP exactly as configured | wave 1 candidate |
| Binary change detection | LEVIR-CD, WHU-CD, CDD, S2Looking, DSIFN-CD, JL1-CD | fixed test split; F1 (and IoU/OA only when separately configured) | wave 1 candidate |
| Semantic change detection | SECOND | fixed split; SeK/Fscd contract, not binary F1 | defer/split protocol |
| Land-cover segmentation | LoveDA, Potsdam, Vaihingen, iSAID, FLAIR | official split; mIoU; aliases normalized | wave 1 candidate |
| Buildings/roads/disaster | SpaceNet, INRIA, WHU Buildings, Massachusetts Roads, xBD | challenge/version-specific; APLS/F1/IoU/damage metric separated | wave 2 candidate |
| Scene classification | EuroSAT, RESISC45, UC Merced, AID | stated train/test split; Accuracy | wave 1 candidate |
| Multi-label land cover | BigEarthNet | official test vs arbitrary split; modality and micro/macro metrics separated | wave 1 candidate |
| Hyperspectral classification | Pavia University, Indian Pines, KSC, Houston, Salinas | dataset plus train-sample regime; OA/AA/Kappa split by protocol | defer/split protocol |
| SAR/ATR | MSTAR, NUDT4MSTAR, xView3-SAR | standard/depression configuration and metric stated | wave 2 candidate |
| Remote-sensing VLMs | GEOBench-VLM, RSVQA, VRSBench, RSHR-Bench, VLRS-Bench | benchmark-defined task aggregate; closed/open variants kept distinct | wave 1/2 candidate |
| Foundation-model robustness | REOBench and downstream suite | corruption severity/task contract; do not mix clean scores | wave 2 candidate |
| Crop/time series | CropHarvest, PASTIS, TimeSen2Crop | geography/year/split; metric exact | wave 2 candidate |
| Super-resolution | Sen2Venus, OLI2MSI and paper-specific RS SR sets | scale factor and degradation fixed; PSNR/SSIM separated | defer/split protocol |

### Database stocktake and selected import waves

Only seven relevant rows currently exist, all outside task 318: DIOR (`264`, mAP),
LoveDA (`272`, mIoU), EuroSAT (`574`, Accuracy), GEO-Bench classification
suite (`275`, Accuracy), GEO-Bench (`876`, Accuracy/mIoU), PANGEABench (`877`,
Accuracy/mIoU), and SpectralEarth (`878`, F1/mIoU). GEO-Bench 275 and 876
share the same introducing paper and represent different suite scopes; only the
explicitly selected protocol will be linked, not both blindly. DIOR and LoveDA
also need their direct-arXiv `paper_url` values normalized to native local paper
URLs.

| Benchmark | Current DB row | Selected task-318 contract | Evidence surfaces | Decision |
|---|---:|---|---|---|
| DIOR | 264 | official detection split; mAP | live papers, legacy, S2 | wave 1 reuse/repair |
| LoveDA | 272 | official test; mIoU | live papers, legacy, S2, GitHub | wave 1 reuse/repair |
| EuroSAT | 574 | declared fixed split; Accuracy | live papers, legacy, S2 | wave 1 reuse |
| GEO-Bench | 876 | suite-defined protocols; Accuracy and mIoU only | live papers, S2, GitHub | wave 1 reuse/audit |
| PANGEABench | 877 | suite-defined protocols; Accuracy and mIoU only | live papers, S2, GitHub | wave 1 reuse/audit |
| SpectralEarth | 878 | suite-defined F1/mIoU contracts | HF, DB, hyperspectral/FM papers | wave 2 reuse/audit |
| DOTA v1.0 | missing | official oriented-detection protocol; mAP | live papers, legacy, S2, GitHub | wave 1 add |
| DIOR-R | missing | rotated boxes; mAP | live papers, legacy | wave 1 add |
| FAIR1M v1.0 | missing | official oriented-detection protocol; mAP | live papers, legacy, S2 | wave 1 add |
| HRSC2016 | missing | VOC07 and VOC12 contracts separated | live papers, legacy | wave 1 add |
| AI-TOD-v2 | missing | official tiny-object split; mAP | 2025/2026 top-page papers | wave 1 add |
| LEVIR-CD | missing | official binary-CD test; F1 | live papers, legacy, S2 | wave 1 add |
| WHU-CD | missing | official binary-CD test; F1 | live papers, legacy | wave 1 add |
| CDD | missing | official binary-CD test; F1 | live papers, legacy | wave 1 add |
| S2Looking | missing | official binary-CD test; F1 | live papers, legacy | wave 1 add |
| ISPRS Potsdam | missing | official semantic segmentation split; mIoU | live papers, legacy | wave 1 add |
| ISPRS Vaihingen | missing | official semantic segmentation split; mIoU | live papers, legacy | wave 1 add |
| iSAID | missing | official instance/semantic contract kept explicit | live papers, legacy, S2 | wave 1 add |
| NWPU-RESISC45 | missing | declared train ratio; Accuracy | live papers, legacy, S2 | wave 1 add |
| AID | missing | declared train ratio; Accuracy | live papers, S2 | wave 1 add |
| UC Merced | missing | declared fixed split; Accuracy | live papers, legacy | wave 1 add |
| BigEarthNet | missing | official cleaned test/modality; mAP | live papers, legacy, S2 | wave 1 add |
| RSICD | missing | retrieval direction and R@K/mR explicit | live VLM papers, HF | wave 1 add |
| RSVQA | missing | question regime/split; Accuracy | live VLM papers, DB source paper | wave 1 add |
| xView | missing | challenge split; mAP | legacy, S2, DB source paper | wave 2 add |
| SYSU-CD | missing | official binary-CD test; F1 | live papers, legacy | wave 2 add |
| DSIFN-CD | missing | official binary-CD test; F1 | live papers, legacy | wave 2 add |
| FLAIR | missing | official land-cover split; mIoU | live page, HF, DB source paper | wave 2 add |
| SpaceNet | missing | challenge/version-specific metric | legacy, S2, DB source paper | wave 2 split |
| xBD | missing | official damage-assessment metric/split | live page, legacy, S2 | wave 2 add |
| JL1-CD | missing | CAR partition; F1 | 2025 top-page paper, DB source paper | wave 2 add |
| VRSBench / GEOBench-VLM / RSHR-Bench | missing | benchmark-native VQA/grounding aggregates kept separate | live page, recent search, HF | wave 2 add |
| NUDT4MSTAR | missing | operating-condition split; OA | 2025 top-page paper, DB source paper | wave 2 add |

The remaining one-paper/custom generation, canopy-height, LST, LiDAR, scientific
compression, and geospatial-prediction protocols stay deferred until they have a
reusable cross-paper contract. Hyperspectral classics are also deferred until their
train-sample regimes can be represented as separate leaderboards.

## Major comparability risks

1. Dataset aliases hide distinct or duplicated contracts: DOTA vs DOTA 1.0;
   Potsdam/Vaihingen variants; WHU Building vs WHU-CD; duplicated change-detection
   task names.
2. Metric labels and scales vary (`F1`, `F1-score`, `OA`, `Overall Accuracy`,
   `mIoU`, percentages versus decimals). Stored metric names will be canonical and
   source values normalized only when the quantity is provably identical.
3. Hyperspectral results mix 15/200 samples per class, 1/5/10% training, disjoint
   splits, and unrestricted setups. These cannot share a single ranking.
4. BigEarthNet mixes official/arbitrary splits, Sentinel-1/Sentinel-2/multimodal
   input, data fractions, and micro/macro metrics.
5. DOTA/DIOR/HRSC results mix benchmark versions, multiscale/extra-data settings,
   oriented versus horizontal boxes, AP50 versus mAP, and VOC07 versus VOC12.
6. Change detection mixes binary/semantic tasks, 3-channel/13-channel OSCD,
   labeled fractions, crop sizes, and synthetic additional data.
7. VLM benchmarks often contain multiple subtasks and proprietary comparator
   models. Only the source paper's introduced model/benchmark rows will be imported;
   proprietary variants must be marked closed.

## Field-map gate

Breadth is sufficient: the research set contains many benchmark families and far
more than ten candidate benchmarks. Imports remain gated on the completed top-100
source inspection, final candidate ranking, source-paper resolution, and exact
metric/split contracts.
