# Image Compression field map

Research date: 2026-07-20. Task: `image-compression` (task id 429).

## Completion contract and live state

The requested contract is a holistic overview of major benchmarks, major papers and their comparison lineages, with paper-native evaluations for the top 100 live task papers. The live API currently returns only 46 papers, so the initial top-100 slice is the complete 46-paper page. All 46 initially had zero evaluations, the task had no linked datasets or configured metrics, 16 papers had official repositories, and none had linked Hugging Face artifacts. The curation pass will reconcile all 46 and expand the clearly relevant paper/tag set toward at least 100 papers rather than treating the thin initial page as complete.

The mandatory special slice is [Qwen-Image-VAE-2.0](https://arxiv.org/abs/2605.13565) plus the 16 distinct source papers/releases behind the 19 comparator model rows in its Tables 2 and 3.

## Benchmark families and comparability contracts

| Family | Canonical datasets / settings | Metrics | Contract and decision |
|---|---|---|---|
| Conventional learned lossy coding | Kodak, CLIC Professional validation/test, Tecnick/TESTIMAGES | Full bpp–PSNR/MS-SSIM curves; BD-rate against a named VTM anchor | Major wave. Never mix VTM-9.1, 17.0, 22.0, RGB/YUV conversion, padding/crop policy, or CLIC val/test. Legacy supplies a clean Kodak/VTM-17 lead. |
| CLIC challenge constrained tracks | CLIC 2019/2020 mobile/professional | Track-specific fixed-rate/perceptual score | Separate from generic CLIC Pro RD curves. Defer until an exact track contract is selected. |
| Lossless / near-lossless | ImageNet32, CIFAR-10; sometimes Kodak/DIV2K/CLIC | bpsp or bpp; epsilon for near-lossless | Major historical family. ImageNet32 bpsp is a strong initial board; near-lossless epsilon settings need separate pages. |
| Generative/perceptual ultra-low rate | Kodak, DIV2K, CLIC | bpp with LPIPS/DISTS/FID/human preference | Do not mix with PSNR-optimized RD boards. Import only when a fixed operating point and protocol are explicit. |
| Fixed-spatial VAE/tokenizer reconstruction | ImageNet 256, FFHQ 1024, OmniDoc-TokenBench 256; f8/f16/f32 plus channel width | PSNR, SSIM; OmniDoc also LPIPS, FID, NED | Separate from entropy-coded LIC because there is no bitrate/bpp. Prefer distinct spatial-compression contracts. OmniDoc is wave 1, NED primary. |
| Machine-perception compression | COCO/ImageNet downstream task accuracy under compressed input | task metric plus rate | Separate downstream protocol; TransTIC and related work require their own benchmark definitions. |
| Practical complexity | Kodak/CLIC/Tecnick | latency, MACs/pixel, parameters plus RD | Hardware/software dependent; no cross-paper latency leaderboard without normalized conditions. |

## Seven evidence surfaces

### 1. Live task page and database

The production and local APIs both returned 46 papers for `order_by=trending&page_size=100`, with no next page. All had zero evaluations. The highest-signal zero-eval papers included FTIC (2301.11189), UMGM (2203.10897), Frequency-Aware Transformer (2310.16387), TransTIC (2306.05085), QH-VAE (2208.13056), shallow-decoder LIC (2304.06244), foundation-diffusion compression (2404.08580), DCAE (2504.00496), and idempotent perceptual compression (2401.08920). There were 18 papers from 2025 and eight from 2026. Composite trending scores were null, so repository stars and recency drive much of the page order.

No Kodak, CLIC, Tecnick, or compression-specific DIV2K dataset existed. The only DIV2K match was an unrelated super-resolution leaderboard.

### 2. Semantic Scholar

Five broad/recent query variants produced 590 distinct hits, 462 title/abstract-relevant candidates, and 162 candidates from 2025/2026. Citation counts were used only as ranking signals. Historical leaders included Ballé 1611.01704 and 1802.01436, Minnen 1809.02736, Theis 1703.00395, Toderici 1608.05148/1705.05823, Agustsson 1804.02958, Mentzer 2006.09965, Cheng 2001.01568, Minnen/Singh 2007.08739, ELIC 2203.10886, WACNN/STF 2203.08450, MLIC 2211.07273, MLIC++ 2307.15421, and LIC-TCM 2303.14978.

### 3. Legacy Papers With Code dump

The exact `Image Compression` task had 22 rows across 11 dataset records. The substantial comparable leads were:

- Kodak: eight rows, all `BD-Rate over VTM-17.0` (MLIC+, MLIC++, MLIC, LIC-TCM Large, ELIC, WACNN, STF, SegPIC).
- ImageNet32: five bpsp rows (iFlow 3.88, MS-PixelCNN 3.95, L3C 4.76, plus JPEG2000/PNG comparator rows that must not be attached to unrelated paper records).
- Several one-paper downstream bit-rate datasets from 2106.10800, which are not generic image-coding boards.
- BSDS500 compressed sensing and FER2013/deconvolution rows, which are out-of-contract anomalies for this task.

Legacy is a lead source only; every surviving row needs source-paper verification.

### 4. GitHub popularity and openness

Major ecosystem signals included [CompressAI](https://github.com/InterDigitalInc/CompressAI), [tensorflow/compression](https://github.com/tensorflow/compression), the Cheng GMM/attention repository, [MLIC/MLIC++](https://github.com/JiangWeibeta/MLIC), [MambaIC](https://github.com/AuroraZengfh/MambaIC), DCAE, HPCM, AuxT, and GLIC. Official repositories and checkpoints support `is_open=true` only when the exact evaluated variant can be matched. HPCM reports VTM-22.0 numbers, so those cannot enter the VTM-17 legacy board.

### 5. Hugging Face artifacts

Generic LIC search was sparse, but exact official signals included [MambaIC](https://huggingface.co/AuroraZengfh/MambaIC), [DC-AE f32c32](https://huggingface.co/mit-han-lab/dc-ae-f32c32-sana-1.0), [VAVAE](https://huggingface.co/hustvl/vavae-imagenet256-f16d32-dinov2), and FLUX.1-dev. The official [OmniDoc-TokenBench dataset](https://huggingface.co/datasets/alibabagroup/OmniDoc-TokenBench) has 3,042 images, Apache-2.0 metadata, and links arXiv:2605.13565. No exact Qwen-Image-VAE-2.0 Table-1 checkpoint was found.

### 6. Comparison-table expansion

Repeated conventional LIC comparator lineage: ELIC, STF/WACNN, TCM, MLIC+/MLIC++, FTIC, WeConvene, CCA, DCAE, LALIC, MambaIC, HPCM, and AuxT.

Qwen-Image-VAE-2.0 Tables 2/3 expand to VTP-Large, RAE-DINOv2/SigLIP2, FLUX.1, HunyuanVideo, Qwen-Image, Wan 2.1/2.2, Cosmos-0.1, HunyuanVideo-1.5, HunyuanImage-3.0, VAVAE, StepVideo, FLUX.2, DC-AE, HunyuanImage-2.1, LTX-Video, and LTX-2. These comparator cells are external evidence and will not be imported under those source papers. Each source must be inspected for its own native results.

### 7. Recent 2025/2026 slice

High-priority conventional LIC papers with standard tables include DCAE (2504.00496), MambaIC (2503.12461), LALIC (2502.05741), HPCM (2507.19125), AuxT (2501.13751), MLICv2 (2504.19119), Scale-to-1B (2508.09075), CMamba (2502.04988), CMIC (2508.02192), S2CFormer (2502.00700), FEDS (2503.06399), GLIC (2603.25316), PICO (2605.05148), and SAAF (CVPR 2026). Recent perceptual/generative work is tracked separately because it often introduces incompatible protocols.

## Qwen-Image-VAE-2.0 mandatory slice

The paper introduces f16c64, f16c128, f32c128, and f32c192 variants. Table 2 reports ImageNet-256 and FFHQ-1K reconstruction PSNR/SSIM. Table 3 reports OmniDoc-TokenBench SSIM/PSNR/LPIPS/FID/NED. The official [OmniDoc evaluator](https://github.com/alibaba/OmniDoc-TokenBench) computes NED from raw PP-OCRv5 outputs using normalized Levenshtein similarity.

Only the Qwen variants are native to arXiv:2605.13565. Best paper-native reconstruction cells for the initial import are f16c128: ImageNet PSNR 35.90, SSIM 0.9519; FFHQ PSNR 43.10, SSIM 0.9795; OmniDoc PSNR 30.45, SSIM 0.9706, LPIPS 0.0167, FID 0.79, NED 0.9617. The four spatial-compression tiers remain available for tier-specific boards, but one best row per paper/metric is the default.

## Candidate benchmark decision table

| Benchmark | Existing DB state | Evidence surfaces | Candidate papers | Decision |
|---|---|---|---|---|
| OmniDoc-TokenBench 256 | Missing | Qwen paper, official GitHub, official HF dataset | Qwen-Image-VAE-2.0 | Wave 1 create; NED primary, plus PSNR/SSIM/LPIPS/FID. |
| ImageNet 256 VAE reconstruction | Existing ImageNet-256 row has generation semantics only | Qwen Table 2 and tokenizer/VAE papers | Qwen, VAVAE, DC-AE, RAE/VTP | Create a reconstruction-specific contract; do not reuse generation FID/IS row. |
| FFHQ 1024 VAE reconstruction | Dataset 859 exists but needs task/contract audit | Qwen Table 2 | Qwen and high-compression VAEs | Wave 1 repair/link only if resolution/protocol is explicit. |
| Kodak BD-rate vs VTM-17.0 | Missing | Legacy plus eight source papers | MLIC/MLIC++, LIC-TCM, ELIC, WACNN/STF, SegPIC | Wave 1 create and verify source-native values. |
| ImageNet32 lossless | Missing | Legacy plus L3C/iFlow sources | L3C, iFlow, MS-PixelCNN | Wave 1/2 create with bpsp; exclude comparator-only PNG/JPEG rows. |
| CLIC Professional RD | Missing | Major/recent papers, official challenge | DCAE/LALIC/MambaIC/HPCM/GLIC/SAAF | Wave 2 after selecting exact split and VTM anchor. |
| Tecnick RD | Missing | Major/recent papers | same mainline papers | Wave 2 after selecting exact VTM anchor and conversion protocol. |
| Perceptual ultra-low-rate fixed points | Missing | generative/perceptual papers | HiFiC, CDC, PerCo, diffusion codecs | Defer/split protocol; bpp and perceptual metric must be fixed. |

## Risks and exclusions

- Do not rank VTM-9.1, 17.0, and 22.0 BD-rates together.
- Do not mix CLIC validation and hidden test.
- Do not mix fixed latent spatial compression with entropy-coded bpp.
- Do not attach comparison-table baselines to other papers as external evals.
- Do not use generation IS/gFID as image-compression results.
- Do not infer openness from a paper-level HF link; match exact checkpoints.
- Do not force recent one-off protocols onto older leaderboards.

Scratch evidence is under `/tmp/image-compression/`; durable reconciliation artifacts live beside this file.
