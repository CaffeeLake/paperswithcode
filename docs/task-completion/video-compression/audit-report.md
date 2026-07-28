# Video Compression final database audit

Generated: 2026-07-28T14:34:15.961124Z

## Summary

- Benchmarks: 28
- Task–dataset–metric wires: 50
- Evaluations: 81 across 11 evaluation papers
- Independently verified benchmarks: 28/28
- Actionable issues: 0
- Informational evals predating later protocol-source papers: 24

## Benchmark inventory

| ID | Benchmark | Metrics | Evals / papers | Verified |
|---:|---|---|---:|:---:|
| 1648 | DAVIS 2019 Test-Dev 256x256 Video Tokenization | PSNR (↑), LPIPS (↓), SSIM (↑), FVD (↓), BPP16 (↓) | 5 / 1 | yes |
| 1655 | UVG RGB BT.709 96-frame IP32 VTM-17.0 | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 3 / 2 | yes |
| 1658 | HEVC Class B RGB BT.709 96-frame IP32 VTM-17.0 | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 3 / 2 | yes |
| 1659 | MCL-JCV RGB BT.709 96-frame IP32 VTM-17.0 | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 3 / 2 | yes |
| 1661 | HEVC Class C RGB BT.709 96-frame IP32 VTM-17.0 | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 3 / 2 | yes |
| 1663 | HEVC Class E RGB BT.709 96-frame IP32 VTM-17.0 | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 3 / 2 | yes |
| 1664 | HEVC Class D RGB BT.709 96-frame IP32 VTM-17.0 | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 3 / 2 | yes |
| 1666 | UVG RGB BT.601 96-frame IP32 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 5 / 3 | yes |
| 1668 | HEVC Class B RGB BT.601 96-frame IP32 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 5 / 3 | yes |
| 1669 | MCL-JCV RGB BT.601 96-frame IP32 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 5 / 3 | yes |
| 1670 | HEVC Class D RGB BT.601 96-frame IP32 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 5 / 3 | yes |
| 1671 | HEVC Class C RGB BT.601 96-frame IP32 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 5 / 3 | yes |
| 1672 | HEVC Class E RGB BT.601 96-frame IP32 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓), BD-Rate (MS-SSIM RGB) (↓) | 5 / 3 | yes |
| 1673 | UVG RGB BT.601 96-frame IP-1 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓) | 2 / 2 | yes |
| 1674 | MCL-JCV RGB BT.601 96-frame IP-1 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓) | 2 / 2 | yes |
| 1675 | HEVC Class C RGB BT.601 96-frame IP-1 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓) | 2 / 2 | yes |
| 1676 | HEVC Class D RGB BT.601 96-frame IP-1 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓) | 2 / 2 | yes |
| 1677 | HEVC Class B RGB BT.601 96-frame IP-1 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓) | 2 / 2 | yes |
| 1678 | HEVC Class E RGB BT.601 96-frame IP-1 VTM-13.2 LDB | BD-Rate (PSNR RGB) (↓) | 2 / 2 | yes |
| 1679 | UVG YUV420 All-Frame IP-1 Actual-Bitstream VTM-17.0 | BD-Rate (Weighted PSNR YUV420) (↓) | 1 / 1 | yes |
| 1680 | HEVC Class B YUV420 All-Frame IP-1 Actual-Bitstream VTM-17.0 | BD-Rate (Weighted PSNR YUV420) (↓) | 1 / 1 | yes |
| 1681 | MCL-JCV YUV420 All-Frame IP-1 Actual-Bitstream VTM-17.0 | BD-Rate (Weighted PSNR YUV420) (↓) | 1 / 1 | yes |
| 1682 | HEVC Class E YUV420 All-Frame IP-1 Actual-Bitstream VTM-17.0 | BD-Rate (Weighted PSNR YUV420) (↓) | 1 / 1 | yes |
| 1683 | HEVC Class C YUV420 All-Frame IP-1 Actual-Bitstream VTM-17.0 | BD-Rate (Weighted PSNR YUV420) (↓) | 1 / 1 | yes |
| 1684 | HEVC Class D YUV420 All-Frame IP-1 Actual-Bitstream VTM-17.0 | BD-Rate (Weighted PSNR YUV420) (↓) | 1 / 1 | yes |
| 1685 | MCL-JCV 17x256x256 30fps Causal 4x8x8 Video Tokenization | PSNR (↑), LPIPS (↓), SSIM (↑), FVD (↓) | 4 / 1 | yes |
| 1686 | UCF-101 Split 1 Validation 16x128x128 Video Tokenizer Reconstruction | PSNR (↑), LPIPS (↓), SSIM (↑), rFVD (↓) | 4 / 1 | yes |
| 1687 | UVG 1080p ~13M INR Video Reconstruction | Average PSNR (dB) (↑) | 2 / 2 | yes |

## Integrity checks

- Every benchmark is linked only to task 431 with `featured_rank = NULL` and `supports_harness = false`.
- Every evaluation uses exactly one wired metric, null harness, a numeric score, and a direction-consistent rank.
- No duplicate unique keys, lower/higher variant duplicates, or mixed openness tags were found.
- Introducing papers resolve to native Papers With Code URLs; introduced dates/years match the linked source papers.
- All referenced paper rows are dated and latest-version rows.
- Closed rows have no Hugging Face URL; populated Hugging Face links are official model repositories.
- Public dataset APIs, evaluation APIs, benchmark pages, paper pages, and the task page were checked.

## Independent verification coverage

All 28 current benchmarks have completed independent `verify-evals` coverage. HyTIP rows on the six BT.709 boards were deleted as `WRONG_SETUP` before this final audit because they use cropped/scene-cut data; every retained row was subsequently audited.

## Actionable blockers

- None.

## Informational chronology

24 evaluation rows predate the later paper used to formalize their protocol-specific benchmark. These are retained source-native historical results, not chronology errors; dataset dates themselves match their introducing/source paper rows.

## Global validator

The repository-wide metric validator completed with exit code 1 because it found four pre-existing mismatches, all unrelated to Video Compression: ETH3D (relative), FLORES-101, FLORES-200 devtest, and Livebench. Video Compression findings: 0. Full output: `global-validator.txt`.
