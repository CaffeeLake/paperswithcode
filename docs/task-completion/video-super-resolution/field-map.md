# Video Super-Resolution Field Map

Generated 2026-07-20 for task `video-super-resolution` (task ID 315).

## Completion scope and starting state

- User contract: build a holistic map of major benchmarks, major papers, comparison-table baselines, and paper-native evaluations, with an explicit reconciliation of the top 100 live task-page papers.
- The live page has 107 papers. The top-100 trending slice is persisted in `top100-ledger.csv`.
- Starting state: 12 configured benchmark pages, 167 task evaluation rows, and 22 distinct source papers overall. In the live top 100, 19 papers had task-native rows and 81 had none.
- Thirty-seven top-100 papers are from 2025/2026. Every one is included in the ledger and recent-paper worklist rather than being inferred from citations alone.

## Seven-surface research map

### 1. Live page and local database

The current task is split across three materially different evaluation worlds: classical distortion-oriented VSR, real-world/generative VSR, and space-time/specialized VSR. The existing database already wires the reusable major families: Vid4 BI/BD, REDS4 BI, Vimeo-90K-T BI/BD, UDM10, SPMCS, VideoLQ, RealVSR, YouHQ40, and the Vimeo90K Fast/Medium space-time splits.

Coverage is uneven. Classical pages contain 2-11 source papers each. The recent VideoLQ/YouHQ40 pages contain many metric rows but only 3-8 papers. The live top 100 is dominated by recent diffusion, streaming, event, arbitrary-scale, and space-time papers, so a dataset-name match alone is unsafe.

### 2. Semantic Scholar and citation anchors

Historical citation anchors include ESPCN (`1609.05158`), EDVR (`1905.02716`), BasicVSR (`2012.02181`), BasicVSR++ (`2104.13371`), TDAN (`1812.02898`), FRVSR (`1801.04590`), Detail-Revealing VSR (`1704.02738`), RBPN (`1903.10128`), VRT (`2201.12288`), RVRT (`2206.02146`), and RealBasicVSR (`2111.12704`).

The canonical comparison chain recovered from source tables is: SRCNN/ESPCN -> VESPCN/SPMC/TOFlow/FRVSR/DUF/RBPN -> EDVR/PFNL/RSDN/RRN -> BasicVSR/IconVSR/BasicVSR++ -> VRT/RVRT/TTVSR/PSRT -> IART/MIA-VSR/EvTexture -> recent diffusion and streaming systems.

### 3. Legacy Papers With Code

Streaming `evaluation-tables.json` found 16 `Video Super-Resolution` leaderboards with 246 rows and two `Space-time Video Super-resolution` leaderboards with eight rows. Together they reference 64 titled source papers and 197 model labels.

The legacy core is Vid4 BI/BD, REDS4, Vimeo-90K-T, UDM10, SPMCS, and Vimeo90K Fast/Medium. It also exposes three MSU benchmark families, Xiph/Ultra Video Group HD, SAT-MTB-VSR, and deblatting datasets. Those are not wave-1 imports: MSU scores are generally third-party rather than paper-native; SAT-MTB-VSR is one-paper/niche; Xiph/UVG mixes protocols; and deblatting is a different task.

### 4. GitHub adoption signal

High-signal official repositories include TecoGAN (6.1k stars), FlashVSR (1.7k), EDVR (1.6k), VRT (1.5k), STAR (1.5k), Upscale-A-Video (1.5k), EvTexture (1.2k), RealBasicVSR (1.1k), Zooming Slow-Mo (932), BasicVSR++ (810), SparkVSR (690), RBPN (453), RVRT (450), DLoRAL (352), Stream-DiffVSR (310), IART (233), TTVSR (223), DOVE (207), StableVSR (178), MGLD-VSR (165), and RealViformer (89).

Official GitHub code/checkpoints justify `is_open=true` even without a row-level HF URL. Application/toolbox popularity such as Video2X, Waifu2x GUIs, and BasicSR is adoption evidence only, not paper-native evaluation evidence.

### 5. Hugging Face artifact signal

Exact official model artifacts were found for SeedVR/SeedVR2, FlashVSR v1 and v1.1, SparkVSR final and Stage-1, STAR variants, Stream-DiffVSR, and StableVSR. Exact variant mapping is mandatory: FlashVSR v1.1 must not silently replace the paper-v1 row; SparkVSR Stage-1 is not the final model; STAR light/heavy and SeedVR/SeedVR2 3B/7B are distinct variants.

Core benchmark dataset coverage on the Hub is thin and mostly community mirrors. VSR-120K is still unreleased/not found and is a training corpus, not a test leaderboard. DOVE HQ-VSR is likewise training data.

### 6. Comparison-table expansion

BasicVSR/BasicVSR++/TTVSR tables recover the classical baseline chain above. DOVE, SeedVR, SeedVR2, STAR, FlashVSR, SparkVSR, and recent diffusion papers repeatedly compare RealBasicVSR, RealViformer, MGLD-VSR, StableVSR, Upscale-A-Video, VEnhancer, STAR, DOVE, SeedVR/SeedVR2, and FlashVSR.

Comparator cells are discovery leads only. Each comparator requires its own source-paper worker; no score is attached to another paper from a later comparison table.

### 7. Explicit 2025/2026 slice

Priority general-VSR papers include STAR, SeedVR, SeedVR2, DOVE, DLoRAL, FlashVSR, Stream-DiffVSR, RealisVSR, RealViformer, VSRM, InfVSR, DC-VSR, DiffVSR, PatchVSR, DGAF-VSR, DUO-VSR, LiteVSR, SparkVSR, and newer online/streaming models. Space-time, event-assisted, reference-guided, medical, anime, face, microscopy, compressed-domain, and arbitrary-scale papers remain in the ledger but are not forced onto generic VSR leaderboards.

## Benchmark families and contracts

| Family | Dataset IDs | Canonical metrics | Contract | Decision |
|---|---|---|---|---|
| Vid4 x4 BI | 917 | PSNR, SSIM | Bicubic x4; do not mix BD, event input, arbitrary-scale, or causal-only setup | Wave 1 |
| Vid4 x4 BD | 922 | PSNR, SSIM | Gaussian blur sigma 1.6 then x4 subsampling | Wave 1 |
| REDS4 x4 BI | 914 | PSNR, SSIM | Held-out REDS4, bicubic x4 | Wave 1 |
| Vimeo-90K-T x4 BI | 915 | PSNR, SSIM | Septuplet test split, bicubic x4 | Wave 1 |
| Vimeo-90K-T x4 BD | 921 | PSNR, SSIM | BasicVSR++ blur-downsample contract | Wave 1 |
| UDM10 x4 | 918 | PSNR, SSIM | PFNL/UDM10 x4; verify each degradation pipeline | Wave 1 |
| SPMCS x4 | 923 | PSNR, SSIM | Detail-Revealing VSR test set, x4 | Wave 1 |
| VideoLQ | 822 | BRISQUE, CLIP-IQA, DOVER, E_warp, FasterVQA, MUSIQ, NIQE, NRQM, PI | Unpaired/no GT; never accept PSNR/SSIM | Wave 1 recent |
| RealVSR | 926 | PSNR, SSIM, LPIPS | Paired captured test set; verify alignment/crop and whether a paper instead treats LQ as unpaired | Wave 1 recent |
| YouHQ40 | 821 | PSNR, SSIM, LPIPS, DISTS, CLIP-IQA, MUSIQ, NIQE, DOVER, FasterVQA, E_warp | RealBasicVSR synthetic-degradation protocol; exact pipeline/crop must match | Wave 1 recent |
| Vimeo90K Fast/Medium | 927, 928 | PSNR, SSIM | Space-time VSR, luminance-channel Zooming Slow-Mo protocol | Wave 2 specialized |
| MSU benchmark families | missing | subjective/IQA/FPS/codec BD-rate metrics | Third-party and codec-specific; not paper-native by default | Defer |

## Major papers and worklist expansion

Historical anchors already covered include EDVR, BasicVSR/IconVSR, BasicVSR++, VRT, RVRT, TTVSR, RRN, Zooming Slow-Mo, and IART. Important historical gaps surfaced by legacy include DUF, SOF-VSR, VESPCN, FRVSR, RBPN, RSDN, PFNL, TOFlow, TecoGAN, and several Vid4 BI/BD rows. These enter the separate paper worklist when their source-native cells match the configured contracts.

Recent source workers prioritize papers whose own tables report configured metrics on configured reusable datasets. Online/causal, reference-guided, event-assisted, joint-deblurring, blind-kernel, or space-time variants are deferred when the page contract would make them incomparable.

## Principal risks and decisions

- BI versus BD is a hard boundary; the generic legacy `Vid4 - 4x` label is insufficient.
- RGB versus Y-channel, border crop, frame-weighted versus sequence-weighted averaging, and PSNR/SSIM implementation must be sourced rather than assumed.
- VideoLQ is unpaired. Full-reference scores cannot be placed there.
- RealVSR/MVSR4x and modern generative synthetic sets differ in alignment, crop, and degradation pipeline even when labels look similar.
- Streaming FPS/latency depends on hardware, resolution, frame count, and causal state. It is not a universal quality leaderboard metric.
- Event/RGB, reference-free/reference-guided, online/offline, spatial-only/space-time, and generic/domain-specific rows are incompatible modes.
- New MovieLQ, RealisVideo-4K, RealVideo10, AIGC28/38, REDS30, OpenVid30, MVSR4x, and similar sets remain candidates until independently adopted or separately wired.
- The live page contains two latest-version rows for arXiv `2006.11161`; only one canonical iSeeBetter source row should receive evaluations.

## Initial import waves

Wave 1 is source-paper imports onto the 10 reusable spatial-VSR benchmark families. Wave 2 covers the two existing space-time pages and high-confidence historical comparator gaps. Specialized or one-paper protocols are documented as deferrals rather than diluted into generic leaderboards. Every changed benchmark receives a final verifier worker before completion.
