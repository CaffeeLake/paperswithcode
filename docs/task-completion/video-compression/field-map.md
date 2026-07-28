# Video Compression field map

Research started: 2026-07-28. Task: `video-compression` (task id 431).

## Completion contract and live state

The requested contract is a thorough, holistic overview of the field: major
benchmarks, major papers, papers they compare against, and paper-native
evaluations, with an explicit reconciliation of the live task page's top 100
papers.

The initial live API has 132 tagged papers. Its first 100 papers contain only
five papers with any evaluation row in the database, and four of those have
rows only for other tasks. The task initially has one leaderboard:

| Dataset id | Benchmark | Metrics | Eval rows / papers |
|---:|---|---|---:|
| 1648 | DAVIS 2019 Test-Dev 256x256 Video Tokenization | BPP16, FVD, LPIPS, PSNR, SSIM | 5 / 1 |

The current DAVIS rows are all from InfoTok (arXiv:2512.16975). The validated
initial top-100 ledger has 66 `defer-missing-benchmark`, 20
`not-a-results-paper`, 10 `defer-not-comparable`, three
`defer-not-paper-native`, and one `already-covered` decision. Full text was
inspected for 84 papers; 16 new or unavailable sources use explicitly weaker
title/abstract evidence. A complete pass therefore needs to build the missing
standard-codec and tokenizer benchmark families before most paper-native
results can be imported.

## Benchmark families and comparability contracts

| Family | Canonical datasets / settings | Metrics | Contract and decision |
|---|---|---|---|
| Learned codec rate-distortion, practical low delay | UVG, MCL-JCV, HEVC Classes B-E; YUV420; all frames; intra-period -1 | BD-Rate against a named VTM version using weighted PSNR | Major wave. Separate by anchor, colorspace, frame count, and intra period. DCVC-FM establishes a clean VTM-17.0 contract. |
| Learned codec rate-distortion, historical short GOP | UVG, MCL-JCV, HEVC Classes B-E; RGB or YUV420; usually 96 frames and intra-period 12/32 | BD-Rate or full bpp-PSNR/MS-SSIM curves | Historically important but incompatible with the all-frame/single-I-frame contract. Split by RGB/YUV and GOP. |
| Random-access / B-frame coding | HEVC common test classes and sometimes UVG/MCL-JCV under random access | BD-Rate against HM/VTM | Separate from low-delay P-frame coding. DCVC-B and related papers belong here. |
| Fixed-protocol video-tokenizer reconstruction | UCF-101 split 1, MCL-JCV, DAVIS, Kinetics/WebVid-derived validation sets; explicit frame count, resolution, FPS, and latent compression | PSNR, SSIM, LPIPS, rFVD/FVD, bits or latent compression | Major wave. Never mix different resolutions, frame counts, continuous/discrete latent widths, or reconstruction FVD with generation FVD. |
| Implicit neural video representation | UVG, usually seven 1080p sequences and a fixed model-size budget | Average PSNR, model size, sometimes bpp/MS-SSIM and encoding time | Major adjacent family. Keep separate from entropy-coded codec RD because model size and per-video fitting are different rate definitions. |
| Generative/perceptual ultra-low-bitrate coding | UVG, MCL-JCV, HEVC classes, or private video sets | LPIPS, DISTS, FVD, VMAF, human preference, BD-rate | Split by reference codec and operating point. Do not place perceptual/generative rows on a PSNR-optimized board without an exact common protocol. |
| Domain-specific compression | HDR, volumetric/4D Gaussian, Earth-system, conferencing, semantic/VLM compression | Domain-specific metrics and datasets | Track in the top-100 ledger, but defer one-off protocols unless multiple independent papers establish a reusable benchmark. |

## Seven evidence surfaces

### 1. Live task page and local database

The live task page returns 132 papers. The initial top 100 is dominated by
2024-2026 learned codecs, video tokenizers/VAEs, neural video representations,
and several adjacent or false-positive compression papers. Only InfoTok has
Video Compression evals. High-signal zero-eval papers include DCVC-RT
(2502.20762), DCVC-FM (2402.17414), VidTok (2412.13061), OmniTokenizer
(2406.09399), Image and Video Tokenization with BSQ (2406.07548), WF-VAE
(2411.17459), HNeRV (2304.02633), LARP (2410.21264), HyTIP (2508.02072),
Spatiotemporal Entropy Model (2104.06083), T-GVC (2507.07633), ECVC
(2410.09706), Context Modulation (2505.14541), L-STEC (2512.12790), and
OpenDCVCs (2508.04491).

The live ordering contains several adjacent papers that are not compression
results papers (video generation/restoration, VLM token pruning, saliency,
image compression, and Gaussian-splatting work). Every such row still requires
an explicit top-100 ledger decision rather than silent exclusion.

### 2. Semantic Scholar citation and recent coverage

The broad and 2025/2026 searches cover both the learned-codec lineage and the
new video-tokenizer/VAE line. Historical anchors include DVC, Scale-Space Flow,
HLVC, RLVC, FVC, Deep Contextual Video Compression, CANF-VC, VCT, MMVC, and the
DCVC-TCM/HEM/DC/FM sequence. Recent candidates include DCVC-RT, ECVC, Context
Modulation, HyTIP, EHVC, L-STEC, T-GVC, generative neural codecs, VidTok,
WF-VAE, InfoTok, MambaVideo, Hi-VAE, and adaptive/flexible tokenizers.

Citation counts are only one signal: recent papers and official implementation
repositories are retained even when citation counts are still low.

### 3. Legacy Papers With Code dump

The exact legacy `Video Compression` task has zero datasets and zero
evaluation rows. Canonical UVG/MCL-JCV/HEVC codec RD coverage is absent.

The strongest adjacent legacy evidence is:

- UVG Video Reconstruction: seven implicit-representation rows using Average
  PSNR and Model Size (HiNeRV, CoordFlow, FFNeRV, HNeRV, E-NeRV, PS-NeRV,
  NeRV).
- UCF-101 tokenizer/video generation: FVD16/FVD128, Inception Score, and KVD16
  rows including MAGVIT, MAGVIT-v2, LARP, TATS, and OmniTokenizer.
- Kinetics-600 12-frame 64x64 prediction: FVD rows with explicit conditioning
  and prediction lengths.
- BAIR Robot Pushing: FVD/SSIM/PSNR/LPIPS rows with train/prediction lengths.

These are leads only. Generation FVD cannot be imported as reconstruction FVD,
and UVG model size cannot be treated as codec bitrate.

### 4. GitHub popularity and openness

The field has strong implementation signals around CompressAI-derived codecs,
the DCVC/OpenDCVC family, PyTorchVideoCompression, NeRV-family repositories,
VidTok, OmniTokenizer, BSQ, Cosmos Tokenizer, WF-VAE, and recent flexible video
tokenizers. Repository popularity is used to find major/open papers and exact
checkpoints, not as proof of an evaluation score.

For each imported model, openness must be established for the exact evaluated
variant. Public code without the exact weights can justify reproducibility only
when the repository supplies the training/evaluation path and public data; a
row-level Hugging Face URL requires an exact official checkpoint.

### 5. Hugging Face artifact coverage

Hugging Face paper/model/dataset searches expose recent tokenizer and VAE
releases more reliably than older learned codecs. Candidate artifact families
include Cosmos Tokenizer, VidTok, WF-VAE, CV-VAE, OmniTokenizer, BSQ, and
InfoTok/InfoTok-Flex. Exact checkpoint-to-table matching remains mandatory;
later post-trained or differently shaped checkpoints are not linked to a row
that used another protocol.

### 6. Comparison-table expansion

The DCVC-FM comparison lineage contains CANF-VC, DCVC, DCVC-TCM, DCVC-HEM,
DCVC-DC, HM, VTM, and ECM. DCVC-RT continues from DCVC-DC/DCVC-FM. The wider
codec lineage repeatedly includes DVC, Scale-Space Flow, HLVC, RLVC, ELF-VC,
FVC, VCT, and MMVC.

The tokenizer lineage repeatedly includes MaskGIT, TATS, MAGVIT/MAGVIT-v2,
OmniTokenizer, CV-VAE, Open-Sora VAEs, CogVideoX VAE, Cosmos Tokenizer,
VidTok, WF-VAE, LARP, ElasticTok, BSQ, and newer adaptive tokenizers.
Comparator cells are discovery evidence only; each comparator paper needs its
own source-native inspection before an eval can be attached to it.

### 7. Explicit 2025/2026 slice

The live top 100 contains a large 2025/2026 slice. It includes practical
real-time codecs, long-context and generative codecs, HDR/domain-specific
compression, mobile/video VAEs, adaptive/flexible tokenizers, and several
July 2026 papers not yet mirrored by Hugging Face's paper reader. Those newest
papers require direct arXiv/project-page sourcing. The final ledger will mark
each as imported, already covered, deferred for a missing benchmark/metric,
non-comparable, not paper-native, or not a results paper.

## Primary-paper protocol evidence

DCVC-FM (arXiv:2402.17414) gives a clean strict board definition in Table 4:
YUV420, all frames, intra-period -1, weighted YUV PSNR, BD-Rate against
VTM-17.0. Its source-native values are:

| Dataset | DCVC-FM BD-Rate vs VTM-17.0 |
|---|---:|
| UVG | -20.7% |
| MCL-JCV | -10.3% |
| HEVC Class B | -18.2% |
| HEVC Class C | -32.2% |
| HEVC Class D | -41.2% |
| HEVC Class E | -30.2% |

The paper also reports RGB and YUV420 96-frame/intra-period-32 tables and a
96-frame/intra-period--1 table. Those values must remain on separate boards.

VidTok (arXiv:2412.13061) defines a reusable MCL-JCV tokenizer contract:
causal 4x8x8 compression, 17x256x256 input, 30 FPS, with PSNR, SSIM, LPIPS,
and FVD. BSQ (arXiv:2406.07548) defines a distinct UCF-101 split-1
reconstruction contract with train and validation results, explicit bit width,
PSNR, SSIM, LPIPS, and rFVD. OmniTokenizer (arXiv:2406.09399) reports
reconstruction FVD on UCF-101 and Moments-in-Time but not the full BSQ metric
set, so its rows require a metric-compatible board rather than forced reuse.

## Candidate benchmark decision table

| Benchmark | Existing DB state | Evidence surfaces | Candidate papers | Preliminary decision |
|---|---|---|---|---|
| UVG YUV420 all-frames IP=-1 BD-Rate vs VTM-17.0 | Missing | DCVC-FM, DCVC-RT/current codec tables | DCVC-FM, DCVC-RT, later DCVC-family papers | Wave 1 create. |
| MCL-JCV YUV420 all-frames IP=-1 BD-Rate vs VTM-17.0 | Missing | DCVC-FM, DCVC-RT/current codec tables | same | Wave 1 create. |
| HEVC Classes B-E YUV420 all-frames IP=-1 BD-Rate vs VTM-17.0 | Missing | DCVC-FM, DCVC-RT/current codec tables | same | Wave 1 create as class-specific boards. |
| MCL-JCV 17x256x256 causal 4x8x8 tokenizer reconstruction | Missing | VidTok source table; tokenizer comparison lineage | VidTok and later papers using the exact protocol | Wave 1 create. |
| UCF-101 split-1 video-tokenizer reconstruction | Existing UCF101 row is classification-only | BSQ source table; tokenizer papers; legacy generation leads | BSQ and exact-protocol successors | Wave 1 create a reconstruction-specific board. |
| DAVIS 2019 Test-Dev 256x256 tokenization | Existing id 1648 | InfoTok source table | InfoTok/InfoTok-Flex | Existing, verify after broader imports. |
| UVG fixed-budget implicit neural representation | Missing | legacy plus NeRV-family primary papers | NeRV, E-NeRV, PS-NeRV, FFNeRV, HNeRV, HiNeRV, CoordFlow | Wave 2 after fixing model-size/rate contract. |
| UCF-101 generation FVD16 | Existing UCF101 row is classification-only | legacy MAGVIT/LARP lineage | MAGVIT, MAGVIT-v2, LARP, OmniTokenizer | Defer to Video Generation unless reconstruction relevance is explicit. |
| Kinetics-600 12-frame 64x64 prediction | Existing row is classification-only | legacy | MAGVIT, MAGVIT-v2, LARP, OmniTokenizer | Defer/split as Video Prediction, not generic compression. |
| Domain-specific HDR/volumetric/Earth/compressed-VLM boards | Mostly missing | live page and recent papers | one-off paper clusters | Defer until adoption/protocol evidence is established. |

## Implemented coverage

The completed task has 28 benchmark boards, 50 task-dataset-metric links, and
81 evaluation rows from 11 source papers. Twenty-seven boards were added
around the pre-existing DAVIS tokenizer board.

| Implemented family | Boards | Eval rows | Source-native papers |
|---|---:|---:|---|
| RGB BT.709, first 96 frames, IP32, VTM-17.0 | 6 | 18 | DCVC-DC, DCVC-FM |
| RGB BT.601, first 96 frames, IP32, VTM-13.2 LDB | 6 | 30 | DCVC-HEM, ECVC, DCMVC |
| RGB BT.601, first 96 frames, IP=-1, VTM-13.2 LDB | 6 | 12 | ECVC, DCMVC |
| YUV420, all frames, IP=-1, actual bitstreams, VTM-17.0 | 6 | 6 | DCVC-RT Large |
| DAVIS, MCL-JCV, and UCF-101 tokenizer reconstruction | 3 | 13 | InfoTok, VidTok, BSQ |
| UVG full-resolution, fixed-capacity per-video INR reconstruction | 1 | 2 | HiNeRV, CoordFlow |

Every board is unfeatured and has no evaluation harness. Chronology matches
the linked source paper on all 28 boards. The imported paper set is:
DCVC-HEM, DCVC-DC, DCVC-FM, ECVC, DCMVC, DCVC-RT, VidTok, BSQ, InfoTok,
HiNeRV, and CoordFlow.

Independent verification removed all 12 initially imported HyTIP cells from
the six BT.709 boards. HyTIP crops frames to multiples of 64 and inserts intra
frames at scene cuts; its own DCVC re-runs differ materially from the native
DCVC values, so those cells are a distinct protocol rather than comparable
rows. Verification also confirmed that the legacy NeRV, E-NeRV, PS-NeRV,
HNeRV, and FFNeRV fixed-capacity values came from HiNeRV's comparison table,
not from those papers' native result tables. They were not imported.

## Risks and exclusions

- Never mix VTM versions or anchor codecs in one BD-Rate metric.
- Never mix RGB with YUV420, 96 frames with all frames, or intra-period 12/32
  with intra-period -1.
- Never mix low-delay P-frame coding with random-access/B-frame coding.
- Never mix reconstruction FVD/rFVD with generation or prediction FVD.
- Never merge MCL-JCV/DAVIS/UCF results that use different frame counts,
  resolutions, frame rates, or latent compression factors.
- Do not treat model size as entropy-coded bitrate.
- Do not attach comparison-table baselines to another paper as external evals.
- Do not infer row-level openness or a Hugging Face link from a related/later
  checkpoint.
- Remove or explicitly defer false-positive task tags only with source-backed
  evidence; do not let irrelevant top-page papers disappear from the ledger.

Scratch evidence is stored under `/tmp/video-compression/`. Durable paper,
import, verification, and top-100 ledgers live beside this field map.
