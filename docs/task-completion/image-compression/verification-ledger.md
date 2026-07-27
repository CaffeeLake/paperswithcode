# Image Compression verification ledger

Audit date: 2026-07-20. All five changed leaderboards were audited independently under the `verify-evals` rules.

## OmniDoc-TokenBench 256 — dataset 1529 / task 429

Contract: 3,042 text-rich 256×256 images; PSNR/SSIM/LPIPS/reconstruction FID; NED is mean normalized Levenshtein similarity over raw PP-OCRv5 strings. `supports_harness=false`.

- PASS: 16942 SSIM 0.9706
- PASS: 16943 PSNR 30.45
- PASS: 16944 LPIPS 0.0167
- PASS: 16945 FID 0.79
- PASS: 16946 NED 0.9617

All match arXiv:2605.13565 Table 3 for Qwen-Image-VAE-2.0-f16c128. The 324M parameter count is Table 1's 76M encoder plus 248M decoder. `is_open=false` and no HF model URL are correct because only the benchmark/evaluator is released, not the evaluated checkpoint.

## ImageNet 256 VAE reconstruction f16 — dataset 1530 / task 429

Contract: ImageNet validation reconstruction at 256×256 and effective f16 spatial compression; PSNR/SSIM; no generation metrics. `supports_harness=false`.

- PASS: 16947–16948 Qwen-Image-VAE-2.0-f16c128, PSNR 35.90 / SSIM 0.9519.
- PASS: 17000–17001 VA-VAE-f16d32 (DINOv2), PSNR 27.96 / SSIM 0.79; official exact HF checkpoint linked.
- PASS: 17098–17099 FLUX.2 VAE, PSNR 31.4632 / SSIM 0.9038 from the official BFL representation report; official VAE weights linked.

No duplicates or protocol mixing were found.

## FFHQ 1024 VAE reconstruction f16 — dataset 1533 / task 429

Contract: FFHQ reconstruction at 1K and f16; PSNR/SSIM. `supports_harness=false`.

- PASS: 16949 PSNR 43.10.
- PASS: 16950 SSIM 0.9795.

Both match arXiv:2605.13565 Table 2. Closed/no-HF checkpoint metadata is correct.

## Kodak BD-Rate vs VTM-17.0 — dataset 1532 / task 429

Strict contract: 24 Kodak 768×512 images; PSNR BD-Rate percentage relative to exact VTM-17.0 Intra in YUV444. Other VTM anchors, MS-SSIM, or underspecified configurations are excluded.

- PASS: 17166 MLICv2+ −20.46, 84.3M parameters, rank 1.
- PASS: 16966 MLIC++ −13.39, 83.5M parameters, rank 2.
- FIX/PASS: 16956 MLIC+ −11.39, rank 3. Set `num_parameters=83400000` and strengthened methodology with `encoder_intra_vtm.cfg`, PNG→YUV444p, and `InputChromaFormat=444`.
- DELETE: 16992 SegPIC −8.18. The source only states generic VTM-17.0; it does not establish the strict Intra/YUV444 configuration and its comparator cells disagree materially with the exact-contract family.

Ranks were recalculated after cleanup.

## ImageNet-32 lossless — dataset 1535 / task 429

Contract: lossless coding on ImageNet-32 validation, bits per subpixel (lower is better). `supports_harness=false`.

- PASS: 16967 iFlow 3.88, rank 1.
- PASS: 16970 Multiscale PixelCNN 3.95, rank 2; 3.92 in the source is training, not validation.
- PASS: 16951 L3C 4.76, rank 3; official exact ImageNet32 checkpoint supports `is_open=true`.

PNG/JPEG comparator rows were correctly absent.

## Validation

All 19 surviving task evaluation rows match configured metric labels and have `best_metric` set. The global validator still reports four unrelated pre-existing leaderboard mismatches: ETH3D relative, FLORES-101, FLORES-200 devtest, and Livebench. None was introduced or modified by this pass.
