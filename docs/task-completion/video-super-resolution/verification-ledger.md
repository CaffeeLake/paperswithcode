# Video Super-Resolution Verification Ledger

Final audit date: 2026-07-20. Task ID: `315`.

## Final disposition

- Final task state: 334 evaluation rows, 43 source papers, and 15 benchmark pages.
- Cleanup: 36 incomparable rows deleted and 25 valid rows moved from overly broad pages to derived protocol-specific pages.
- Integrity: no duplicate `(paper, dataset, model, metric)` keys, no null `best_metric`, no harness misuse, and no task-315 metric-label mismatches.
- The global metric validator still reports four pre-existing warnings on unrelated ETH3D-relative, FLORES-101, FLORES-200-devtest, and LiveBench pages.

## Benchmark audits

| Dataset | Final rows | Audit outcome |
|---|---:|---|
| YouHQ40 (`821`) | 75 | Removed 7 PS-SR RealESRGAN-degradation rows and 8 cropped/subset AdcVSR rows. Corrected five DiffVSR cells to the standard YouHQ row, metric scales/methodology, provenance, DOVE metadata, and LiteVSR openness. |
| VideoLQ (`822`) | 82 | All rows retained. Corrected DOVE exact full-model/HF metadata, LiteVSR openness, DOVER/E_warp scale descriptions, and STCDiT additional-data status. |
| REDS4 BI (`914`) | 29 | All rows retained; EDVR parameter metadata corrected. Contract now explicitly names clips 000/011/015/020 and distinguishes REDS4 from REDSval4. |
| Vimeo-90K-T BI (`915`) | 20 | All rows retained. Corrected RVRT/VRT/EDVR parameters, EDVR Y-channel cells, IA-RT provenance, and GSMamba channel/open-weight metadata. |
| Vid4 BI (`917`) | 24 | Deleted 8 FRVSR/RRN/RBPN/SPMC rows using BD, excluded-frame, or unresolved source-native protocols. Corrected VRT/RVRT parameters, IA-RT provenance, and GSMamba channel methodology. |
| UDM10 conventional (`918`) | 18 | Deleted 2 cropped/subset AdcVSR rows. Clarified the conventional Gaussian sigma=1.6 BDx4, Y-channel, 8-pixel-crop contract and corrected affected methodology/parameters. |
| SPMCS conventional (`923`) | 2 | Deleted 2 cropped/subset AdcVSR rows and moved 8 RealBasicVSR-style rows to dataset 1541. |
| Native RealVSR (`926`) | 3 | Retained only the three source-native ICCV 2021 rows. Deleted 9 crop/original-scale rows and moved 17 later DOVE-family pixel-4x rows to dataset 1540. |
| RealVSR DOVE-family 4x (`1540`) | 17 | Final verifier: 17 pass after fixing LSGQuant supplementary provenance; no deletes or duplicates. |
| SPMCS RealBasicVSR-style (`1541`) | 8 | Final verifier: 8 pass after fixing source routes and clearing a transformer-only SparkVSR parameter count. This is a protocol-family page, not byte-identical frozen inputs. |
| UDM10 RealBasicVSR-style (`1542`) | 22 | Final verifier: 22 pass after correcting STCDiT additional-data status. This is a protocol-family page, not byte-identical frozen inputs. |

The unchanged Vimeo BI/BD and space-time pages were included in the database-wide integrity checks; no scoped cleanup was required there.

## Key comparability boundaries enforced

- BI and Gaussian-BD scores do not rank together.
- Y-channel and RGB cells are not silently mixed when the leaderboard contract fixes a channel.
- All-frame and excluded-boundary-frame Vid4 results are separated.
- Native RealVSR's registered equal-pixel-dimension camera-pair protocol is separate from later pixel-4x DOVE-family reporting.
- Conventional SPMCS/UDM10 pages are separate from independently regenerated RealBasicVSR-style complex-degradation families.
- VideoLQ remains no-reference only; full-reference PSNR/SSIM rows are excluded.
- Paper-native introduced-model cells are imported; later papers' comparator/baseline cells are discovery evidence only.
