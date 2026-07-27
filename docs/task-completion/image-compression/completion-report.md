# Image Compression completion report

Completed: 2026-07-20. Production task: https://paperswithcode.co/tasks/image-compression

## Scope and reconciliation

- Expanded the task from 46 to 110 tagged papers by indexing/tagging 40 foundational papers, the requested Qwen paper, and all 16 distinct comparator sources from Qwen Tables 2/3.
- Reconciled the current live top 100: 100 ledger rows, zero missing decisions.
- Top-100 decisions: 8 `imported`, 48 `defer-missing-benchmark`, 37 `defer-not-comparable`, 6 `defer-not-paper-native`, and 1 `defer-missing-metric`.
- Explicitly covered the 2025/2026 slice through live-page inventory, Semantic Scholar, GitHub, Hugging Face, and source-paper comparison tables.

Durable evidence: [field map](field-map.md), [top-100 ledger](top100-ledger.csv), [paper worklist](paper-worklist.csv), [import ledger](import-ledger.csv), and [verification ledger](verification-ledger.md).

## Benchmarks created

| Dataset ID | Benchmark | Metrics | Verified rows |
|---:|---|---|---:|
| 1529 | OmniDoc-TokenBench 256 | NED, PSNR, SSIM, LPIPS, FID | 5 |
| 1530 | ImageNet 256×256 VAE Reconstruction (f16) | PSNR, SSIM | 6 |
| 1532 | Kodak BD-Rate vs VTM-17.0 | BD-Rate | 3 |
| 1533 | FFHQ 1024×1024 VAE Reconstruction (f16) | PSNR, SSIM | 2 |
| 1535 | ImageNet-32 Lossless Compression | bpsp | 3 |

Every benchmark has a native local source-paper URL, task link, metric directions, `supports_harness=false`, and `featured_rank=NULL`.

## Verified evaluation imports

Nineteen rows survived independent verification across nine source papers:

- Qwen-Image-VAE-2.0: nine rows across OmniDoc, ImageNet-256 f16, and FFHQ-1024 f16 (eval IDs 16942–16950).
- VA-VAE f16d32: two ImageNet-256 rows (17000–17001).
- FLUX.2 VAE: two official-source ImageNet-256 rows (17098–17099).
- MLIC+, MLIC++, MLICv2+: three Kodak/VTM-17 rows (16956, 16966, 17166).
- L3C, iFlow, Multiscale PixelCNN: three ImageNet-32 bpsp rows (16951, 16967, 16970).

Qwen-Image-VAE-2.0-f16c128 is stored as 324M total parameters and closed (`is_open=false`, no HF model URL) because the official release provides the OmniDoc dataset/evaluator but no exact evaluated VAE checkpoint. VA-VAE and FLUX.2 use exact official HF checkpoint URLs. MLIC+/MLIC++ and L3C are open from official code/checkpoint evidence; MLICv2+, iFlow, and Multiscale PixelCNN remain closed where no exact public checkpoint/code release could be established.

## Verifier cleanup

- Updated MLIC+ eval 16956 with 83.4M parameters and the exact VTM-17.0 Intra/YUV444 configuration.
- Deleted transient SegPIC eval 16992 because its source did not establish the strict Intra/YUV444 contract and its comparator cells conflicted with the exact-contract family.
- Recalculated Kodak ranks: MLICv2+ rank 1, MLIC++ rank 2, MLIC+ rank 3.
- All other imported rows passed unchanged; no duplicate model variants remained.

## Qwen comparator-source decisions

All comparator sources were tagged. Only VA-VAE and FLUX.2 exposed source-native results matching a configured f16 ImageNet reconstruction contract. The other sources were correctly deferred because they used f8/f32/f64, video/private datasets, rFID-only metrics, or published no native reconstruction table. Qwen's comparator cells were never copied onto other papers as external evaluations.

## Important deferred benchmark work

- Conventional LIC still needs separate CLIC Professional and Tecnick boards after selecting exact split, RGB/YUV conversion, and VTM anchor.
- VTM anchors must remain separate. Source inspection found LALIC on VTM-9.1; ELIC, LIC-TCM, FTIC, QRes-VAE, and dictionary DCAE on VTM-12.1; UMGM on VTM-14.2; MS-ILLM on VTM-19.2; and HPCM on VTM-22.0.
- Generative/perceptual codecs need fixed-bpp LPIPS/DISTS/FID or human-preference contracts rather than the PSNR/VTM board.
- Fixed f8/f32/f64 VAE reconstruction variants need separate leaderboards rather than being forced onto f16.
- Several recent paper rows have missing publication dates; this is a metadata follow-up, not an evaluation-comparability issue.

## Validation

- All 19 surviving Image Compression evaluation rows have valid configured metrics and populated `best_metric`.
- Task page, all five dataset APIs, the production task URL, and the OmniDoc benchmark URL returned HTTP 200.
- The global validator reports four unrelated pre-existing mismatches: ETH3D relative, FLORES-101, FLORES-200 devtest, and Livebench. This pass did not modify them.
