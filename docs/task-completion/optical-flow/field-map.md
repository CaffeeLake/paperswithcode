# Optical Flow field map (2026-07-18)

Task: `optical-flow` (task id 323)
Live papers after completion: 100
Completion result: all 100 live task papers reconciled; 33 papers have 126 verified paper-native evaluation rows across 12 configured benchmark contracts (11 populated, RobustSpring intentionally empty).

## Coverage diagnosis

- The task initially had 79 papers, zero linked datasets, and zero direct Optical Flow evaluation rows. It now has 100 papers, 12 linked benchmark contracts, and 126 verified rows from 33 papers. The taxonomy remains deliberately broad: some live rows use optical flow only as a component of interpolation, tracking, generation, segmentation, action recognition, or another downstream task, and those receive explicit no-row decisions in the ledger.
- Legacy Papers With Code has strong Optical Flow Estimation coverage across supervised, self/unsupervised, training-set, and test-server protocols. Its highest-density families are MPI Sintel Clean/Final, KITTI 2012, KITTI 2015, and Spring.
- Missing field anchors were resolved into the live task, including RAFT, PWC-Net, FlowNet, FlowNet2, SPyNet, GMA, FlowFormer, FlowFormer++, SEA-RAFT, GMFlowNet, MaskFlownet, LiteFlowNet, UFlow, ARFlow, and UPFlow.
- Current discovery surfaces show active 2025/2026 work: DPFlow, MEMFOF, UFM, FlowSeek, WAFT, FlowIt, Flow-Anything, GenOpticalFlow, and a new real-world generalization benchmark built from TAP-Flow, Slow Flow, and FlowFactor. RobustSpring is now an explicit corruption/robustness extension of Spring.

## Benchmark families and contracts

| Priority | Benchmark family | Canonical contract | Evidence surfaces | Decision |
|---:|---|---|---|---|
| 1 | MPI Sintel Clean test | Official hidden test server, Clean pass, Average End-Point Error (lower is better); keep warm-start/multi-frame variants explicit | Live papers, legacy PwC (27 rows), official Sintel site, comparison tables | Wave 1 benchmark |
| 2 | MPI Sintel Final test | Official hidden test server, Final pass, Average End-Point Error; do not mix with Clean | Live papers, legacy PwC (27 rows), official Sintel site, comparison tables | Wave 1 benchmark |
| 3 | KITTI 2015 optical-flow test | Official test server, `Fl-all` outlier percentage (lower is better); retain foreground/background only as separate configured metrics if used | Legacy PwC (16 rows), RAFT/FlowFormer/SEA-RAFT comparisons, KITTI benchmark | Wave 1 benchmark |
| 4 | KITTI 2012 optical-flow test | Official test server; Average End-Point Error and/or official outlier metric with exact visibility convention | Legacy PwC (12 rows), classic and lightweight optical-flow papers | Wave 1 benchmark after source-contract check |
| 5 | Spring optical flow | Official high-resolution test server; `1px total`, EPE, and Fl are distinct metrics; source-submitted zero-shot rows must say so | Legacy PwC (10 rows), official live leaderboard, recent DPFlow/MEMFOF/WAFT | Wave 1 benchmark |
| 6 | MPI Sintel Clean/Final unsupervised | Same passes but no target benchmark supervision; Average End-Point Error; never merge with supervised/fine-tuned test rows | Legacy PwC (5 rows each), UFlow/ARFlow/UPFlow/MDFlow | Wave 1 separate protocol boards |
| 7 | KITTI 2015 unsupervised | `Fl-all`, no target benchmark labels during training; never merge with supervised/fine-tuned test rows | Legacy PwC (4 rows), UFlow/ARFlow/UPFlow/MDFlow | Wave 1 separate protocol board |
| 8 | KITTI 2012 unsupervised | Average End-Point Error under unsupervised/no-target-label protocol | Legacy PwC (2 rows), ARFlow/UPFlow | Wave 2 due low row count |
| 9 | KITTI 2015 train | Public training split, EPE and F1-all; not comparable with hidden test-server Fl-all | Legacy PwC (17 rows), many architecture papers | Wave 2; preserve split explicitly |
| 10 | DSEC-Flow | Event-camera optical flow with exact test/train split and event/frame input mode; canonical EPE/outlier metrics | Live TMA/event papers, current event-flow literature | Wave 2 after source-paper and metric verification |
| 11 | MVSEC optical flow | Per-sequence event-camera protocols; indoor flying sequences and input windows differ across papers | Event-flow classics and live papers | Defer until protocol-specific boards are designed |
| 12 | RobustSpring | Spring corruptions; robustness deltas must remain separate from clean accuracy metrics and corruption aggregation must be fixed | Official Spring site, ICLR 2026 RobustSpring, SEA-RAFT baseline | Emerging wave |
| 13 | Middlebury optical flow | Classic hidden test benchmark with per-sequence and aggregate interpolation/endpoint errors | Historical field literature and implementations | Historical follow-up; verify current official aggregate contract |
| 14 | FlyingChairs / FlyingThings3D validation | Synthetic training/validation sets; EPE depends on split and training recipe and is not a hidden test benchmark | FlowNet family and most learned flow papers | Defer generic boards unless split/training contract is explicit |
| 15 | HD1K | Automotive high-resolution flow; reported validation/test conventions vary | RAFT-family comparison tables | Defer until split contract is explicit |
| 16 | LayeredFlow / TAP-Flow / FlowFactor | Real-world/generalization diagnostics; zero-shot checkpoint and aggregation matter | 2025/2026 comparison tables and benchmark papers | Emerging wave; do not force onto Sintel/KITTI boards |

## Major paper clusters

- Classical and variational foundations: Horn–Schunck, Lucas–Kanade, Brox et al. warping, EpicFlow, and DeepFlow. These establish the pre-deep-learning comparator lineage but often lack arXiv-native local rows.
- First deep generation: FlowNet, FlowNet2, SPyNet, PWC-Net, LiteFlowNet/2/3, HD3, VCN, IRR-PWC, and Maskflownet.
- Recurrent/correlation era: RAFT, GMA, SeparableFlow, SCV, GMFlow, GMFlowNet, FlowFormer/++, CRAFT, and DEQ-Flow.
- Current efficiency and scale: SEA-RAFT, MemFlow, VideoFlow, StreamFlow, NeuFlow, RPKNet, RAPIDFlow, DPFlow, MEMFOF, WAFT, FlowSeek, UFM, and FlowIt.
- Self/unsupervised: UnFlow, DDFlow, SelFlow, ARFlow, UFlow, UPFlow, MDFlow, SemARFlow, FlowDA, and GenOpticalFlow.
- Event-based and multimodal: EV-FlowNet, E-RAFT, TMA, DSEC-flow methods, EMatch, EDCFlow, and event-RGB fusion methods. These require separate input/protocol leaderboards.
- Adjacent uses that should not automatically produce Optical Flow evals: frame interpolation (RIFE), point tracking (TAPTR/Particle Video/CoWTracker), video generation/editing, segmentation, action recognition, scene flow, stereo, and optical-flow-conditioned downstream models.
- Explicit exclusion: DeFlow (arXiv `2401.16122`) estimates 3D LiDAR point-cloud scene flow on Argoverse 2 Sensor data using 3-way EPE and dynamic-point accuracy. It is not a 2D image optical-flow paper and must not be attached to the Sintel, KITTI optical-flow, Spring, DSEC, or RobustSpring leaderboards.

## Comparison-table expansion

Repeated comparator lineages found across legacy and major paper tables include FlowNet/FlowNet2 → SPyNet/PWC-Net/LiteFlowNet → RAFT → GMA/GMFlow/FlowFormer → SEA-RAFT/DPFlow/MEMFOF/WAFT. Unsupervised tables repeatedly compare UnFlow, DDFlow, SelFlow, ARFlow, UFlow, UPFlow, and MDFlow. These comparator rows are discovery leads only; each paper gets its own source-native import worker.

## Current repository and artifact signals

- High-star official or canonical repositories include NVIDIA FlowNet2, NVlabs PWC-Net, GMFlow, SEA-RAFT, LiteFlowNet, SelFlow, FastFlowNet, VideoFlow, and the broad PTLFlow/MMFlow implementation suites.
- Hugging Face search is sparse but includes DeepMind Perceiver optical-flow weights, an OpenCV RAFT deployment, and official-looking MEMFOF checkpoint families. Exact row-level links require variant-level confirmation.
- Repository openness can justify `is_open=true` without an HF model URL when official checkpoints or reproducible training/evaluation scripts are released.

## Recent 2025/2026 checklist

- Live/task-page: UFM, MEMFOF, Future Optical Flow Prediction, ReynoldsFlow, FlowSeek, DPFlow, several event-flow papers, GenOpticalFlow, DA-Flow, and CoWTracker.
- Citation/search: Flow-Anything, EDCFlow, ST-FlowNet, MambaFlow, WAFT, FlowIt, and the real-world generalization/FlowFactor benchmark paper.
- Official benchmark signals: MEMFOF and DPFlow appear on Spring; WAFT appears on Spring in 2026; RobustSpring launched in 2025 and was presented at ICLR 2026.
- Decision rule: import only source-native rows on a configured matching protocol; otherwise defer as a new benchmark/split rather than mixing it into an older board.

## Comparability risks

- MPI Sintel Clean versus Final, train versus hidden test, two-frame versus multi-frame/warm-start, and fine-tuned versus cross-dataset/zero-shot.
- KITTI 2012 versus 2015, train versus test server, EPE versus F1/Fl, foreground/background/all, and supervised versus no-target-label training.
- Spring accuracy versus RobustSpring corruption robustness, source-submitted zero-shot rows versus author submissions, and EPE/Fl/1px/WAUC metric direction.
- Event camera input representation, temporal window, event-only versus event+RGB, per-sequence MVSEC aggregation, and DSEC split.
- Runtime/FPS is hardware, resolution, iteration count, precision, and deployment-stack dependent; do not rank it without a strict hardware/protocol board.
- Legacy comparator tables can contain values transcribed from other papers. They are leads, never authority for external eval imports.

## Candidate paper worklist

The authoritative worklist is `top100-ledger.csv`: a fresh live trending-order snapshot of exactly 100 papers. Every row has a terminal reconciliation decision. The distribution is 33 imported-and-verified papers, 35 adjacent-task papers with no Optical Flow leaderboard row, 24 papers whose distinct/custom protocol was not forced onto an incompatible board, and 8 benchmark/dataset source papers. `import-ledger.csv` records every imported paper, evaluation ID, model variant, and configured benchmark.

## Field-map gate status

Seven evidence surfaces are represented: live page/API, local DB, Semantic Scholar broad/recent queries, streamed legacy PwC, GitHub popularity/repository mapping, Hugging Face artifact searches, and comparison-table/official-benchmark expansion.

Completion checks passed for all Optical Flow rows: no duplicate evaluation identities, every row has `best_metric` and `best_rank`, all configured metrics are lower-is-better with the intended scale, and each populated leaderboard received an independent source-level verifier pass. Verification repaired external-data flags, exact-checkpoint openness, selected source URLs, parameter metadata, and the RobustSpring parent link; it made no score deletions or paper-ownership changes. The global metric validator reports four pre-existing mismatches on unrelated ETH3D, FLORES-101, FLORES-200, and LiveBench leaderboards and no Optical Flow mismatch.
