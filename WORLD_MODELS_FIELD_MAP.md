# World Models field map (2026-07-17)

Task: `world-models` (task id 26)
Live papers: 937
Completion contract: top 100 papers by live trending order, plus a separate historical-major-paper wave.

## Coverage diagnosis

- The live top 100 is a recency slice: 98 papers are from 2026 and 2 are from 2025. All 100 initially had zero evaluation rows on the World Models task.
- The task initially exposed one dataset, `Cityscapes Video Prediction` (dataset id 834), with five actual Re2Pix rows from one paper. Its five configured metrics mix video quality, semantic prediction, and pseudo-depth quantities, so it requires a protocol audit rather than serving as a general field leaderboard.
- Legacy Papers With Code had no `World Models` task. Relevant historical results are fragmented across Atari Games (64 datasets, 2,518 rows), Continuous Control (73 datasets, 116 rows), and Video Prediction (19 datasets, 124 rows).
- Citation discovery is materially different from trending discovery. Historical anchors missing from the live top 100 include World Models, PlaNet, Dreamer, SimPLe, MuZero, DreamerV2/V3, IRIS, TD-MPC2, STORM, DIAMOND, Genie, GAIA-1, Vista, DINO-WM, and V-JEPA 2.

## Benchmark families and contracts

| Priority | Benchmark family | Canonical contract | Evidence | Decision |
|---:|---|---|---|---|
| 1 | LIBERO Spatial/Object/Goal/Long | Separate suite success rates; same checkpoint, observations, episodes, and evaluation code | Repeated in current WAM/VLA papers and official repos; existing dataset rows 800-803 | Robotics only: retain results on the canonical Robotics boards |
| 2 | WorldModelBench | Exact conditioning mode and judge/version; Total and configured component metrics only | Benchmark paper 2502.20694; repeated by Qwen-RobotWorld and unified world models | Wave 1: add benchmark with source-defined metrics |
| 3 | DreamGen Bench | Source-defined video-to-policy correlation/evaluation cells; preserve robot/domain split | Introduced by DreamGen 2505.12705; reused by Qwen-RobotWorld | Wave 1: add after source-contract inspection |
| 4 | WorldScore | Keep Static and Dynamic aggregates separate; do not collapse component scores | Benchmark paper 2504.00983; existing dataset id 911 is linked only to 3D Generation with `Average` | Wave 1: repair/link with canonical metrics |
| 5 | GameWorld Score / Matrix-Game-MC | Preserve game/version, input context, action vocabulary, horizon, and four score pillars | MineWorld/Matrix-Game/LingBot/Infinite-World comparison cluster | Wave 1 if source contract is explicit |
| 6 | MIND | Separate perspective/action-space protocols; memory, scene, action, and quality metrics are not interchangeable | Benchmark paper 2602.08025 and official dataset/code | Wave 1: add as an emerging diagnostic benchmark |
| 7 | Atari 100K | 26 games, exactly 100K interactions; Mean and Median Human-Normalized Score with scale explicit | Strong legacy and citation coverage; existing dataset id 1088 | Atari Games only: retain world-model paper tags, but keep control scores off the World Models page |
| 8 | CALVIN ABC-D / long-horizon | Keep ABC-D split and chain-length/average-length metrics distinct from single-task success | Existing datasets 235 and 805; recurring robot world-model use | Robotics only: merged imported results into the canonical Robotics boards |
| 9 | RoboTwin / RoboTwin 2.0 | Separate versions, task subsets, embodiments, episodes, and domain randomization | Fast-WAM, GigaWorld, ImageWAM and official artifacts | Robotics only: retain versioned RoboTwin 2.0 boards under Robotics |
| 10 | AgentWorldBench | Per-domain format/factuality/consistency/realism/quality plus documented overall | Qwen-AgentWorld 2606.24597 and official HF dataset | Wave 2: add; do not mix downstream agent-policy benchmarks |
| 11 | StEvo-Bench / WBench / WorldBench | Benchmark-native diagnostic criteria with exact evaluator/version | Top-100 benchmark papers and official datasets/repos | Emerging wave; one-paper boards until independent adoption exists |
| 12 | Visual DMC | Per environment, pixel input, fixed action repeat and interaction budget | PlaNet/Dreamer/TD-MPC family; legacy image-control boards | Defer generic aggregate; create protocol-specific boards only |
| 13 | Driving world models | Dataset, views, resolution, conditioning frames, horizon, controls, and FID/FVD implementation fixed | GAIA-1/DriveDreamer/Drive-WM/Vista comparison cluster | Defer generic nuScenes/Cityscapes board; split protocols first |
| 14 | Classical video prediction | Dataset + resolution + conditioning/prediction horizon + stochastic sampling fixed | Legacy KTH (31), Moving MNIST (30), Kinetics-600, BAIR, Cityscapes | Historical follow-up; never merge generic PSNR/SSIM/FVD rows |

## Major paper clusters

- Foundational model-based control: World Models, PlaNet, Dreamer, SimPLe, MuZero, DreamerV2, DreamerV3, TD-MPC/2, and Masked World Models.
- Sample-efficient Atari: SimPLe, DreamerV2, IRIS, TWM, STORM, and DIAMOND. Repeated non-world-model comparators such as EfficientZero, SPR, and DrQ are discovery leads, not importable comparator rows.
- Interactive video/game: Genie, GameNGen, Oasis, MineWorld, Matrix-Game 1/2, LingBot-World, Infinite-World, Causal Forcing(++), and MIND-World.
- Robot/world-action models: UniSim, iVideoGPT, Video Prediction Policy, DINO-WM, V-JEPA 2, WorldVLA, DreamGen, DreamZero, Motus, Cosmos Policy, LingBot-VA, Fast-WAM, ImageWAM, and GigaWorld-Policy.
- Driving: GAIA-1/2, DriveDreamer, Drive-WM, Vista, DriveDreamer4D, and Cosmos Predict.
- Evaluation/physics: WorldModelBench, WorldScore, GameWorld Score, MIND, StEvo-Bench, WBench, WorldBench, RBench, EWMBench, and PBench.

## Current artifact and repository signals

- 89 of the live top 100 already have a mapped GitHub repository, but only six expose linked HF models in the live payload.
- High-signal open repositories include NVIDIA Cosmos, SANA-WM, LingBot-World, LeWorldModel, SenseNova-U1, StarVLA, DreamZero, stable-worldmodel, GigaWorld, Fast-WAM, and Qwen-AgentWorld.
- Official but currently under-linked HF releases exist for LingBot-World, Fast-WAM, LeWorldModel, HY-World 2.0, SANA-WM, Qwen-AgentWorld, DreamX-World, DreamZero, GigaWorld, minWM, Causal Forcing++, AlayaWorld, Kairos, RynnWorld, VLA-JEPA, and LingBot-VA.
- Popular historical repositories outside the top-100 recency slice include LWM, DreamerV3, DIAMOND, Matrix-Game, DreamerV2, IRIS, TD-MPC2, Vista, and Motus.

## Comparability risks

- Interactive generation: text/image/video conditioning, context-memory mode, first/third person, open/closed loop, horizon, FPS, resolution, generation chunking, action vocabulary, and judge version.
- Robotics: suite version, task subset, cameras/proprioception, episodes/retries, action chunking, pretrained data, zero-shot versus finetuned, simulator versus real robot, and checkpoint version.
- Atari: 26-game 100K versus full 55/57-game training; raw versus human-normalized scores; mean versus median; decimal versus percentage scale.
- Continuous control: state versus pixels, task subset, interaction budget, action repeat, and seed aggregation.
- Driving/video prediction: views, resolution, conditioning and prediction horizon, split, sample count, and FID/FVD implementation.
- Benchmark papers' comparator tables are discovery evidence only. Evaluation rows must come from the paper or official artifact that introduced the evaluated model.

## Evidence surfaces completed

1. Live task page/API and local DB stocktake.
2. Semantic Scholar broad and 2025/2026 searches across four query families.
3. Streamed legacy PwC evaluation and dataset dumps.
4. GitHub topic/keyword/repository mapping and star signals.
5. Hugging Face model/dataset/card discovery plus official GitHub backlinks.
6. Comparison-table expansion across foundational, Atari, interactive-video, robot, driving, and evaluation clusters.
7. Explicit recent-paper check: all top-100 ranks plus additional 2025/2026 citation and artifact candidates.

## Completion outcome

- After taxonomy refinement, the task has 12 direct world-model benchmark contracts, 31 evaluation rows, and 9 evaluated papers. The populated families are WorldScore, MIND, Cityscapes Video Prediction, DreamGen Bench, WorldModelBench, and AgentWorldBench; WBench and StEvo-Bench remain configured for future paper-native results.
- Among the live top 100, 8 papers contribute 26 direct world-model evaluation rows. Nine additional top-100 papers have robot-policy results retained on Robotics rather than duplicated on World Models.
- Historical Atari 100K results for TWM, IRIS, DIAMOND, and STORM are retained on Atari Games. Their genuinely world-model-centric papers remain eligible for the World Models paper taxonomy, but downstream control scores no longer appear as World Models leaderboards.
- LIBERO and Push-T reuse their existing Robotics boards. RoboTwin 2.0 was moved to Robotics as a distinct versioned benchmark, while the four duplicate CALVIN rows were merged into the canonical Robotics CALVIN boards and removed.
- WBench and StEvo-Bench are configured but intentionally empty: their introducing papers report results for external systems rather than a new paper-native model. This keeps them available for future first-party results without misattributing comparator rows.
- Five candidate rows were removed during independent verification: a StarVLA aggregate inconsistent with its printed suite cells, a Qwen-RobotWorld WorldModelBench result with unconfirmed conditioning mode, two Push-T rows attached to the wrong paper/protocol, and a derived DIAMOND median not printed by the source paper.
- All retained World Models rows have populated ranks. The global metric validator reports no World Models mismatch; its four remaining findings are unrelated pre-existing rows on ETH3D relative, FLORES-101, FLORES-200 devtest, and Livebench.
