# Video Compression verification ledger

Audit date: 2026-07-28. Every benchmark was assigned to an independent
`verify-evals` worker after its final import.

| Benchmark ids | Protocol family | Result |
|---|---|---|
| 1648 | DAVIS 2019 test-dev, 256x256 tokenizer reconstruction | PASS; five InfoTok rows retained |
| 1655, 1658, 1659, 1661, 1663, 1664 | RGB BT.709, first 96 frames, IP32, VTM-17.0 | PASS after removing 12 HyTIP `WRONG_SETUP` rows and recalculating ranks |
| 1666, 1668, 1669, 1670, 1671, 1672 | RGB BT.601, first 96 frames, IP32, VTM-13.2 LDB | PASS; 30 rows retained |
| 1673, 1674, 1675, 1676, 1677, 1678 | RGB BT.601, first 96 frames, IP=-1, VTM-13.2 LDB | PASS; 12 rows retained |
| 1679, 1680, 1681, 1682, 1683, 1684 | YUV420, all frames, IP=-1, actual bitstreams including headers, VTM-17.0 | PASS; six DCVC-RT Large rows retained |
| 1685 | MCL-JCV 17x256x256, 30 FPS, causal 4x8x8 tokenizer reconstruction | PASS; four VidTok rows retained |
| 1686 | UCF-101 split-1 validation, 16x128x128 tokenizer reconstruction | PASS; four BSQ rows retained; stale official homepage repaired |
| 1687 | UVG full-resolution, seven-sequence, 12.66M-13.07M per-video INR reconstruction | PASS; HiNeRV and CoordFlow retained; non-native legacy comparison rows excluded |

## Cross-cutting checks

- Metric values and directions match the cited source cells.
- Each row belongs to the exact task, dataset, and configured metric.
- Same-paper variants obey best-per-metric rules.
- Ranks were recomputed after cleanup.
- Duplicate evaluation keys and duplicate same-paper variants are absent.
- `is_open`, parameter counts, and Hugging Face links were checked for the
  exact evaluated variant rather than inferred from a related release.
- All 28 boards are unfeatured and have no harness.
- Benchmark chronology matches the linked source-paper date on all 28 boards.
- Public task, benchmark, paper, source, and official dataset links were
  checked; the obsolete UCF-101 URL was replaced with its current official
  page.

The repository-wide metric validator reports four pre-existing mismatches on
ETH3D, FLORES-101, FLORES-200, and LiveBench. None belongs to Video
Compression or to a row changed by this completion pass.
