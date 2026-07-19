# Image Restoration Field Map

Generated 2026-07-19 for task `image-restoration` (task ID 321).

## Completion scope and starting state

- Live task page: 485 papers; the top-100 slice is persisted in `top100-ledger.csv`.
- Direct task benchmarks, configured metrics, and task evaluation rows before this pass: 0 / 0 / 0.
- Top-100 direct coverage before this pass: 0/100. Nine papers already have 121 paper-native rows on semantically specific peer tasks, chiefly image/video super-resolution and video restoration; these should not be duplicated onto the umbrella task.
- The exact legacy `Image Restoration` table is only UHDM (2 rows). Historical restoration coverage is distributed across adjacent legacy tasks: super-resolution (732 rows/67 datasets), deblurring (263 rows across two task labels), dehazing (109/14), denoising (116 across two labels), inpainting (51/12), blind face restoration (40/4), and rain removal (6/2).

## Benchmark families and comparability contracts

| Family | Major benchmarks | Canonical metrics | Required protocol separation | Initial decision |
|---|---|---|---|---|
| Real denoising | SIDD, DND | PSNR/SSIM | sRGB vs RAW; validation/test/hidden server | Wave 1 |
| Gaussian denoising | CBSD68/BSD68, Kodak24, McMaster, Urban100 at sigma 15/25/50 | PSNR/SSIM | gray vs color; known vs blind sigma; RGB vs Y | Wave 1/2, split by noise level |
| Motion deblurring | GoPro, HIDE, RealBlur-R, RealBlur-J | PSNR/SSIM | synthetic vs real; native training vs GoPro transfer | Wave 1 |
| Defocus deblurring | DPDD indoor/outdoor/combined | PSNR/SSIM/MAE/LPIPS | single-image vs dual-pixel | Wave 2 |
| Deraining | Rain100L/H, Test100/1200/2800, SPA-Data, RainDrop, RealRain1K | PSNR/SSIM | RGB vs Y; synthetic vs real | Wave 1/2 |
| Dehazing | SOTS Indoor/Outdoor, Haze4K, O/I/NH/Dense-Haze | PSNR/SSIM | indoor/outdoor; synthetic/real; ITS/OTS training | Wave 1/2 |
| Desnow/weather | Snow100K, CSD, SRRS, Outdoor-Rain, WeatherBench | PSNR/SSIM or challenge score | synthetic vs real; challenge formulas | Wave 2; WeatherBench standalone |
| Classical SR | Set5/14, BSD100, Urban100, Manga109 at exact x2/x3/x4/x8 | PSNR/SSIM | scale, bicubic degradation, crop, Y/RGB, self-ensemble | Already represented on peer task; do not duplicate |
| Real/blind SR | RealSR, DRealSR, DIV2K-Val/Real-ESRGAN x4 | PSNR/SSIM and perceptual metrics | exact test-set version/crop; fidelity vs perceptual | Already represented on peer task; do not duplicate |
| JPEG artifact removal | Classic5, LIVE1 at q=10/20/30/40 | PSNR/SSIM/PSNR-B | quality factor; gray vs color | Wave 2 |
| Low light | LOL-v1, LOL-v2 Real/Synthetic, SID, SMID, SDSD, SICE | PSNR/SSIM/LPIPS | paired vs unpaired; RAW/sRGB; exact version/subset | Wave 1/2 |
| All-in-one | 3D: SOTS+Rain100L+CBSD68; 5D adds GoPro+LOL-v1; CDD-11/10D | PSNR/SSIM or defined aggregate | joint model vs per-task; 3D/5D/10D/unseen/mixed | Separate protocol-specific leaderboards |
| Real unified/challenge | RAIM 2025, LoViF 2026 | challenge-defined composite/user score | exact track/subtask and formula | Defer pending standalone benchmark wiring |
| Demoireing | UHDM | PSNR | exact UHD demoireing protocol | Wave 2; exact legacy Image Restoration lead |

## Major papers and comparison-table expansion

Historical/high-impact anchors include DnCNN (1608.03981), Noise2Noise (1803.04189), DeblurGAN (1711.07064), EDSR (1707.02921), RCAN (1807.02758), RESIDE (1712.04143), PReNet (1901.09221), FFA-Net (1911.07559), MIRNet (2003.06792), MPRNet (2102.02808), Uformer (2106.03106), SwinIR (2108.10257), Restormer (2111.09881), AirNet (2112.05903), NAFNet (2204.04676), PromptIR (2306.13090), DiffBIR (2308.15070), Retinexformer (2303.06705), MambaIR (2402.15648), AdaIR (2403.14614), and AutoDIR (2310.10123).

Across sixteen inspected primary papers, repeated comparison-table leads were: MPRNet (10 papers), Restormer and DnCNN (7 each), SwinIR (6), MIRNet/RIDNet/FFDNet/PromptIR (5 each), Uformer/NAFNet/AirNet/CycleISP (4 each), and DRUNet/IPT/RCAN/TransWeather (3 each). Comparator cells are discovery evidence only; each model requires its own source-paper worker.

## Current and recent work

The explicit 2025 native-table slice includes MB-TaylorFormer V2 (2501.04486), HVI/CIDNet (2502.20272), DFPIR (2505.12630), DCPT (2501.15510), UniRestore (2501.13134), WeatherBench (2509.11642), LucidFlux (2509.22414), HYPIR (2507.20590), InvSR (2412.09013; CVPR 2025), JarvisIR (2504.04158), FAPE-IR (2511.14099), and AnyIR (2504.14249). The explicit 2026 slice includes OPIR (2601.10192), ClearAIR (2601.02763), DATPRL-IR (2603.01725), CWP-Net (2603.03839), LoViF (2604.19445), MLLM-MoFE (2605.11444), fast SR consistency flow (2605.12377), and QuReC (2607.15097).

Recent papers must remain on their source-native contracts: 3D/5D/10D all-in-one, unseen or mixed degradations, challenge tracks, and perceptual real-world restoration are not interchangeable with classical single-degradation leaderboards.

## GitHub and Hugging Face signals

Highest-signal official repositories include SUPIR (5.6k stars), SwinIR (5.5k), DiffBIR (4.1k), NAFNet (3.1k), StableSR (2.7k), Restormer (2.6k), InvSR (1.4k), MPRNet (1.4k), LucidFlux (1.3k), HYPIR (1.2k), DreamClear (1.2k), HVI-CIDNet (827), DA-CLIP (814), PMRF (752), InstructIR (742), OSEDiff (656), and SeeSR (647).

Exact official HF model evidence exists for StableSR, DiffBIR-v2, HYPIR, InvSR, DreamClear, InstructIR, DA-CLIP, PMRF, LucidFlux, FAPE-IR, and JarvisIR. Restormer, MPRNet, NAFNet, SwinIR, Retinexformer, OSEDiff, SeeSR, and SUPIR have strong official GitHub code/checkpoint evidence and may be `is_open=true` without a row-level HF URL.

## Risks and curation decisions

- The task is an umbrella, not one leaderboard. Noise level, blur type/training domain, haze regime, SR scale/degradation, RAW/sRGB, paired/unpaired, and joint all-in-one protocol must be encoded in separate dataset/leaderboard identities.
- Legacy data is lead evidence only: it contains contaminated task assignments, duplicate GoPro/HIDE families, mixed splits/protocols, and SSIM stored both as fractions and percentages.
- Challenge and benchmark papers mainly contain external comparator rows. Import only each paper's introduced model from its original source.
- The nine top-100 papers already evaluated on peer tasks are `already-covered`; duplicating their rows onto task 321 would create redundant rankings.
- Obvious adjacent/non-results papers in the top 100 will be marked `not-a-results-paper` only after source inspection; absence of task-native scores is not itself enough.

## Initial benchmark waves

Wave 1 prioritizes broadly reused, paper-native, comparable leaderboards: SIDD, DND, GoPro, HIDE, RealBlur-R, RealBlur-J, Rain100L, SOTS Indoor, LOL-v1, and CBSD68 sigma 15/25/50. Wave 2 covers DPDD protocol splits, broader haze/rain/weather sets, JPEG quality-factor boards, UHDM, and protocol-specific all-in-one suites. Existing image-super-resolution leaderboards remain on the peer task and are referenced from the ledger rather than duplicated.

## Completion result

- The task now has 15 configured benchmark leaderboards, 227 verified evaluation rows, and 39 distinct source papers. It started with no direct benchmarks or evaluations.
- The live top-100 slice is fully adjudicated in `top100-ledger.csv`: 36 papers have 205 paper-native task rows; the remaining 64 have concrete source-backed decisions (42 missing a configured benchmark, 8 not paper-native, 7 protocol-incomparable, 5 not restoration-results papers, and 2 missing a configured metric).
- Final protocol splits include Rain100L Y versus RGB, RealBlur in-domain versus GoPro-only transfer, SOTS Indoor versus Outdoor, and CBSD68 color fixed-noise levels sigma 15/25/50. Rows that mixed these contracts were moved, corrected, or removed.
- Every populated leaderboard received a final source-first `verify-evals` audit. There are no duplicate paper/dataset/model/metric keys, no non-null harness values, and no image-restoration metric-wiring mismatches.
- The global metric validator still reports four unrelated pre-existing mismatches on ETH3D (relative), FLORES-101, FLORES-200 devtest, and LiveBench; none belongs to task 321.
