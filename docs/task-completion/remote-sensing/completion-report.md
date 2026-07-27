# Remote Sensing task completion report

Completed 2026-07-20 for task 318 (`remote-sensing`). The goal was a holistic field map plus a paper-by-paper reconciliation of the live top-100 task papers, their benchmark contracts, and paper-native evaluations.

## Outcome

- Reconciled exactly 100 ranked papers in `top100-ledger.csv` and `paper-worklist.csv`.
- Expanded task 318 from no leaderboard wiring to 62 dataset rows, 78 dataset/metric contracts, and 66 verified evaluations from 24 top-100 papers.
- Created or repaired the major detection, change-detection, segmentation, scene-classification, retrieval, VQA/grounding, SAR, and foundation-model suite benchmark families.
- Imported only models introduced by each source paper. Comparison-table baselines were used for field discovery and source-paper expansion, never copied as external evaluations.
- Independently audited every leaderboard containing a new evaluation. The final database has no task-318 evaluation without a configured metric, no null rank, and no exact duplicate key.

## Top-100 reconciliation

| Decision | Papers | Meaning |
|---|---:|---|
| `imported` | 24 | At least one paper-native result survived exact protocol verification |
| `defer-missing-benchmark` | 52 | The paper uses a specialized reusable benchmark not yet represented in task 318 |
| `defer-not-comparable` | 13 | A similarly named benchmark exists, but split, modality, evaluator, aggregation, or setup differs |
| `defer-not-paper-native` | 8 | Dataset/benchmark paper reports baselines or comparison models rather than a model introduced by the paper |
| `not-a-results-paper` | 2 | Survey/tool/resource row without an importable paper-native leaderboard result |
| `defer-missing-metric` | 1 | RSMamba reports P/R/F1 on fixed scene splits while configured contracts require repeated-run Accuracy |

Imported top-100 ranks: 3, 7, 16, 22, 27, 33, 35, 36, 38, 41, 43, 45, 49, 52, 53, 56, 57, 69, 74, 80, 85, 86, 88, and 99. The CSV ledgers give the exact source table, model variant, evaluation ID, openness evidence, HF artifact, parameter count, and deferral reason for every paper.

## Field coverage

The field map combines seven evidence surfaces: live task/DB state, Semantic Scholar citation and recent-paper searches, the legacy Papers With Code dump, GitHub activity, Hugging Face artifacts, comparison-table expansion, and an explicit 2025/2026 slice.

The central benchmark structure now covers:

- Oriented and horizontal aerial detection: DOTA v1.0, DIOR, DIOR-R, FAIR1M v1.0, HRSC2016, AI-TOD-v2, and xView.
- Binary change detection: LEVIR-CD, CDD, S2Looking, SYSU-CD, DSIFN-CD, JL1-CD, and protocol-specific WHU-CD children.
- Semantic and instance segmentation: LoveDA, ISPRS Potsdam/Vaihingen, iSAID semantic/instance variants, and FLAIR.
- Scene and land-cover classification: EuroSAT protocol children, NWPU-RESISC45 train-ratio children, AID children, UC Merced children, and BigEarthNet-S2 official test.
- Vision-language evaluation: RSICD and RSITMD in both retrieval directions, RSVQA low/high-resolution splits, VRSBench VQA/grounding, GEOBench-VLM, and RSHR-Bench task children.
- Foundation-model suites: GEO-Bench, PANGEABench, and SpectralEarth.
- Additional task infrastructure: NUDT4MSTAR operating-condition children and RSHR caption/VQA variants.

Repeated comparison chains were mapped across foundation models (SatMAE, Scale-MAE, SSL4EO, CROMA, DOFA, Prithvi, DINO, RVSA), change detection (BIT, ChangeFormer, ChangeStar, ChangeMamba, CDMaskFormer), segmentation (U-Net, DeepLabV3+, SegFormer, UPerNet, UNetFormer), detection (Oriented R-CNN, ReDet, LSKNet, RTMDet/DETR), and remote-sensing VLMs (GeoChat, RemoteCLIP, SkyCLIP, LHRS-Bot, EarthDial, Qwen/InternVL families).

## Verified imported coverage

The 66 retained evaluations cover 32 metric-specific leaderboard surfaces. Representative leaders after cleanup include LAE-DINO-FT on DIOR (92.2 mAP), LSKNet on DOTA v1.0 (81.85 mAP), LEGNet on FAIR1M v1.0 (48.35 mAP), RVSA on DIOR-R (71.05 mAP), DINOv3 on GEO-Bench classification/segmentation (81.6 Accuracy / 75.9 mIoU), RAMEN on PANGEABench segmentation (60.03 mIoU), ChangeStar2 on CDD (98.0 F1), Changen2 on LEVIR-CD and S2Looking (92.5 / 69.1 F1), DINOv3 on iSAID semantic validation (71.4 mIoU), and GeoRSCLIP on all four RSICD/RSITMD retrieval directions.

The imported paper set also includes FSG-Net, DCFAM/DC-Swin, ChangeMamba, RemoteCLIP, DDPM-CD, SSL4EO-S12, SatMAE++, CDMaskFormer, TTP, LWGANet, RoMA, MTKD, SkyScript, AeroGen, and the in-domain remote-sensing representation baseline.

## Comparability cleanup

Verification materially changed the structure rather than merely checking numeric labels:

- EuroSAT was split into RGB 60/20/20, multispectral 13-band 80/20, and complete-dataset zero-shot children; a canonical RGB class-wise 80/20 child was created for future results. The generic EuroSAT row is now a metric-free parent.
- WHU-CD was split into BIT-style 6,096/762/762 patches, geographic/full-resolution testing, DDPM-CD released lists, and LWGANet's 7,432-patch preparation. The generic WHU-CD row is now a metric-free parent.
- RoMA's AID and UC Merced scores were moved away from ten/repeated-random-split leaderboards into paper-specific fixed/unspecified 50%-train children.
- AeroGen's DIOR-R row was deleted: the source uses YOLO-style mAP50 and does not identify the downstream detector unambiguously, while canonical DIOR-R uses VOC07 11-point AP.
- D3R-DETR and Dome-DETR were rejected from AI-TOD-v2 because their official evaluators use `maxDets=1500`; the configured official contract requires `maxDets=3000`.
- External-pretraining flags, exact HF repository URLs, and methodology descriptions were normalized where primary sources proved them.
- FAIR1M v1.0 metadata was corrected from later-release image counts to the introducing paper's 15,266-image original release.

## Important remaining gaps

The 52 `defer-missing-benchmark` papers are not unreviewed. Each has a named missing contract in the top-100 ledger. The largest next expansions are:

1. Building/road/disaster geometry and extraction: WHU Building, SpaceNet versions, INRIA, xBD, road-graph APLS, polygon IoU/PoLiS.
2. Open-vocabulary and semi-supervised segmentation: paper-specific labeled fractions, vocabulary sets, and training-free protocols.
3. Generation and super-resolution: dataset, scale factor, degradation, and FID/PSNR/SSIM/LPIPS contracts must be separated.
4. Recent multimodal/VLM suites: GeoChat-Bench, FIT-RSFG, LHRS-Bench, EarthDial, DisasterM3, grounding and reasoning variants.
5. Time-series/crop/canopy/point-cloud tasks: PASTIS, TreeSatAI-TS, FLAIR-HUB, canopy-height regional tests, and outdoor/remote point-cloud suites.
6. SAR and hyperspectral evaluation: MSTAR/NUDT transfer conditions and per-dataset train-sample regimes must remain explicit rather than collapsing into generic OA.

These gaps explain why importing a score from every top-100 paper would have been incorrect: many are genuinely different tasks, and several use one-off protocols that need a reusable source-backed benchmark before results can be ranked.

## Validation

- Top-100 ranks are contiguous 1–100; every row has an allowed terminal decision.
- All three CSV ledgers parse cleanly.
- Task 318 has 66 evaluations from 24 papers; all 66 have configured metric contracts and non-null ranks.
- No exact duplicate `(paper, dataset, metric, model)` keys remain.
- The repository metric validator reports no remote-sensing mismatch and no missing `best_metric` values. Its four findings are unrelated pre-existing rows: ETH3D relative, FLORES-101, FLORES-200 devtest, and Livebench.
- Read-only API smoke checks report 62 remote-sensing dataset rows and a healthy task response.

Detailed evidence lives in `field-map.md`, `top100-ledger.csv`, `paper-worklist.csv`, `import-ledger.csv`, and `verification-ledger.md` in this directory.
