#!/usr/bin/env python3
"""Apply the manually researched World Models top-100 adjudications to its CSV ledger."""

import csv
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import get_engine


LEDGER = Path("docs/task-completion/world-models/top100-ledger.csv")

# rank: (paper-native benchmark terms, important comparator-paper/model leads)
PAPER_EVIDENCE = {
    1: (
        "CVTG-2K | LongText-Bench | BizGenEval | GEdit-Bench",
        "Qwen unified models | BAGEL",
    ),
    2: ("LingBot 100-video long-horizon VBench protocol", "Yume-1.5 | HY-World 1.5"),
    3: ("AgentWorldBench", "frontier LLM simulators | agent-world models"),
    4: ("RoboTwin 2.0 | LIBERO", "Motus | GigaWorld-Policy | pi0.5"),
    5: ("MIRA Rocket League 2v2", "pixel-space and latent world-model ablations"),
    6: (
        "RxBrain-Bench-EVQA | WorldPred | JointPlan",
        "Cosmos3-Nano | Wan2.2-TI2V | RoboBrain2.5",
    ),
    7: (
        "qualitative infinite-duration generation",
        "LingBot-World | Genie 3 | Matrix-Game 2.0",
    ),
    8: (
        "Rynn4DDataset | custom real-robot tasks",
        "2D policy and pretraining ablations",
    ),
    9: ("survey tables only", "VideoPhy | WorldModelBench | Physics-IQ | WorldScore"),
    10: ("RoboTwin 2.0 | LIBERO", "X-VLA | pi0.5 | Motus"),
    11: ("SimplerEnv | RoboCasa | RoboTwin 2.0 | LIBERO", "OpenVLA-family baselines"),
    12: (
        "WorldModelBench | DreamGen Bench | PAI-Bench | RoboTwin 2.0 | LIBERO-Plus",
        "Cosmos-Predict | Wan2.2 | LingBot",
    ),
    13: ("HM-World", "DFoT | Context-as-Memory | WorldPlay"),
    14: ("LIBERO", "OpenVLA-OFT | pi0 | GR00T"),
    15: ("EC-CATH | FoldBench | ProteinGym", "protein structure/function models"),
    16: (
        "PanoWorld panoramic-video benchmark",
        "panoramic and camera-control baselines",
    ),
    17: ("OmniWorld camera benchmark", "Matrix-Game | GameGen-X | WorldPlay"),
    18: ("WorldArena | embodied-transfer benchmark", "GPT-Image-2 | Cosmos | pi0.5"),
    19: (
        "RealEstate10K | UE Engine | MineDojo long-horizon prediction",
        "CameraCtrl | DFoT | Geometry Forcing",
    ),
    20: ("GigaWorld WMBench", "Cosmos 2.5 | robot video world models"),
    21: ("Olaf-World latent-action probes", "latent-action representation baselines"),
    22: (
        "Echo-Memory replay/loop-closure/open-domain protocol",
        "raw context | spatial memory | recurrence",
    ),
    23: ("WebWorld", "API/LLM web simulators"),
    24: ("Push-T", "DINO-WM | JEPA | stable-worldmodel"),
    25: ("Push-T | stable-worldmodel suite", "DINO-WM | planning ablations"),
    26: ("AgiBot G1 | DROID-Franka custom tasks", "GR00T N1.6 | pi0.5"),
    27: ("WorldScore on RE10K-Long", "WorldPlay | camera-conditioned generators"),
    28: (
        "PAIBench-G/C | RBench | Physics-IQ | DROID | RoboLab | LIBERO-10",
        "Wan | Qwen | Cosmos predecessors | Ctrl-World",
    ),
    29: ("survey tables only", "robot world-model literature"),
    30: ("WorldScore | RealEstate10K revisit protocol", "Spatia | memory baselines"),
    31: ("private PiPER robot tasks", "pi0.5 | Motus | Fast-WAM"),
    32: (
        "WorldScore-derived suite | Omni-WorldBench",
        "HY-WorldPlay 1.5 | LingBot-World",
    ),
    33: ("LongText-Bench and spatial image suites", "unified image/VLM generators"),
    34: ("RoboTwin 2.0 | PiPER tasks", "Motus | pi0.5 | Cosmos-Policy"),
    35: (
        "WorldScore-image | Tanks-and-Temples | MipNeRF360 | reconstruction suites",
        "HY-World 1.0 | WorldStereo | VGGT",
    ),
    36: ("LiveBench", "Matrix-Game 2.0 | Hunyuan-GameCraft | Spatia"),
    37: ("PAI-Bench/PBench | EZSbench", "Cosmos-Predict2.5 | GigaWorld | WoW"),
    38: (
        "Sketchy | BAIR | Mario | LanguageTable | Bridge | PandaPush | OGBench-Scene",
        "PlaySlot | Diffusion Policy | HIQL",
    ),
    39: ("NAVSIM v1/v2 | Bench2Drive", "LAW | World4Drive | Epona | DiffusionDrive"),
    40: ("WorldMem Minecraft protocol", "OASIS | MineWorld | WorldMem"),
    41: ("CLEVRER | PushT", "SlotFormer | DINO-WM | OC-DINO-WM"),
    42: ("private multi-reference video suite", "unnamed proprietary video systems"),
    43: ("BFCLv3 | tau2-bench | MCP-Universe", "Qwen3 | EnvScaler"),
    44: ("EgoDex-Test | private Robotic-Test", "CogVideoX | Wan | InterDyn"),
    45: ("Deform360", "PhysTwin | PGND | Cosmos-Predict2.5"),
    46: (
        "RoboTwin 2.0 | LIBERO | LIBERO-Plus",
        "LingBot-VA | Motus | Fast-WAM | WorldVLA",
    ),
    47: (
        "WorldArena | AgiBot-Challenge2026 | AgiBot-World",
        "GenieEnvisioner | NeoVerse | Cosmos-Predict2.5",
    ),
    48: ("EgoCS-400K dataset only", "dataset paper"),
    49: (
        "EWMBench | DreamGen Bench | WorldModelBench | PBench",
        "Cosmos | LTX-2 | GigaWorld",
    ),
    50: ("EgoTL-Bench", "Cosmos | Wan"),
    51: ("Edit3D-Bench | ImageNet-1K tokenizer", "Hunyuan3D | ShapeLLM-Omni | Cube3D"),
    52: ("EgoDex", "CoSHAND | Wan-I2V | Go-with-the-Flow"),
    53: ("VideoCUA preliminary analysis", "OpenCUA-7B/32B"),
    54: ("X-Ego", "EgoDreamer | Cosmos | HunyuanVideo | Wan2.2"),
    55: ("private HOT3D-derived protocol", "Wan | Cosmos | Uni3C"),
    56: ("StableToolBench agent planning", "RAW | DFSDT | BATS"),
    57: ("ARCTIC | HOT3D | HOI4D", "CosHand | InterDyn | Wan-Control"),
    58: ("RECON | SCAND | TartanDrive", "Navigation World Models"),
    59: ("MLE-bench subset and private preference corpus", "AIDE | AutoMind"),
    60: ("WildBench", "Wan2.2-Fun"),
    61: ("OS-Harm | WASP", "HarmonyGuard | GuardAgent"),
    62: ("Busan-City-Bench | Ann-Arbor-City-Bench", "Aether | Yume1.5 | HY-World1.5"),
    63: (
        "WorldScore-image | Tanks-and-Temples | MipNeRF360",
        "SEVA | Gen3C | WorldMirror",
    ),
    64: ("qualitative generation only", "camera/action-control systems"),
    65: ("SocialVideo-Bench", "JavisDiT++ | Ovi | LTX-2.3"),
    66: ("framework demonstrations only", "AI2-THOR | LIBERO integrations"),
    67: (
        "Infinite-World 100-scenario benchmark",
        "HY-World1.5 | GameCraft | Matrix-Game2.0",
    ),
    68: ("PushT quantized planning", "DINO-WM | AWQ | SmoothQuant | OmniQuant"),
    69: ("Solaris Minecraft benchmark", "Enigma Multiverse | frame concatenation"),
    70: ("RoboChallenge | private robot tasks", "pi0 | pi0.5 | GigaBrain-0"),
    71: ("private real-robot task suites", "pi0"),
    72: ("hardware-specific latency only", "Causal Forcing | bidirectional bases"),
    73: ("mechanistic analysis only", "video world-model literature"),
    74: (
        "WorldCam-50h custom camera trajectories",
        "Yume | Matrix-Game 2.0 | CameraCtrl",
    ),
    75: ("FlashInfer-Bench | GPUMODE TriMul", "OpenEvolve | ShinkaEvolve"),
    76: ("StEvo-Bench", "Veo 3 | Sora 2 Pro"),
    77: ("private PhysWorld suite", "PhysTwin | DreamPhysics"),
    78: ("VBench/VBench2.0 efficiency protocol", "Causal Forcing | Self Forcing"),
    79: ("RoboTwin 2.0", "contemporary VLA/WAM models"),
    80: (
        "NeoVerse 4D reconstruction and novel-view suite",
        "TrajectoryCrafter | ReCamMaster",
    ),
    81: ("MIND", "WorldScore | WorldModelBench | interactive video models"),
    82: ("LIBERO | SimplerEnv | CALVIN", "TLA | FlowVLA | UniVLA | CoT-VLA"),
    83: ("LIBERO | CALVIN", "VLA baselines"),
    84: ("TartanAir stereo/camera generation", "Voyager | camera-control baselines"),
    85: (
        "ImageNet-val | RoboNet | RECON | RoboMimic Lift",
        "tokenizer and planner baselines",
    ),
    86: ("VBench 2.0 | VideoPhy | WorldScore", "Wan2.1"),
    87: ("CoW-Bench", "unified multimodal/world models"),
    88: ("MuJoCo Playground humanoid control", "PPO | SAC | model-based finetuning"),
    89: ("EgoDex | EgoExo4D | BAIR | Physion", "V-JEPA | DINO-WM | BC/DDPM"),
    90: ("WorldScore image-to-world", "TeaCache | EasyCache"),
    91: ("custom Block Push and Pick-and-Place", "BC | Diffusion Policy | AIRL | RLPD"),
    92: ("RoboTwin 2.0", "RDT | pi0 | pi0.5"),
    93: ("DMLab Rooms | DeepMind Control Suite", "DreamerV3 | R2-Dreamer | DrQ-v2"),
    94: ("AndroidCode | AndroidWorld", "GPT-5 | Gemini-3-Pro-Image"),
    95: ("SAT-Real | MMSI | R2R", "MindJourney | GPT policy variants"),
    96: ("AndroidWorld | KApps", "GUI world-model baselines"),
    97: ("VisWorld-Eval", "BAGEL | interleaved visual/verbal CoT models"),
    98: ("EmbodiedBench Habitat | ALFRED", "ReAct | Synapse | SimuRA | AWM"),
    99: (
        "custom Embodied Video Generation | CO3Dv2 | private robot suites",
        "Wan | pi0.5 | DreamZero | LingBot-VA",
    ),
    100: ("WBench", "Wan 2.7 | Kling 3.0 | LingBot-World"),
}

NOT_RESULTS = {1, 9, 15, 29, 33, 48, 53, 56, 59, 64, 66, 73}
NOT_COMPARABLE = {7, 42, 71, 72, 75, 77, 91, 99}

SPECIAL_REASONS = {
    1: "Native tables evaluate unified image understanding/generation, not a world-model protocol.",
    9: "Survey paper; benchmark tables contain external models only.",
    15: "Protein biology results are outside the World Models task despite the title.",
    29: "Survey paper; no introduced model or paper-native evaluation row.",
    33: "Native results are image understanding/generation rather than world modeling.",
    48: "Dataset/resource paper; no introduced evaluated world model.",
    53: "Dataset paper with preliminary analysis of external OpenCUA models only.",
    56: "Evaluates costly tool-use planning rather than a world-model benchmark.",
    59: "Agent-selection study, not a reusable world-model evaluation.",
    64: "Qualitative demonstrations only; no paper-native quantitative score.",
    66: "Framework/position paper; no exact introduced-model leaderboard row.",
    73: "Mechanistic/position analysis; no introduced model or native results table.",
    7: "Only qualitative/capability comparisons; no reusable quantitative protocol.",
    42: "Private test set and unnamed comparators prevent independent comparison.",
    71: "Private paper-specific real-robot tasks do not define a reusable public board.",
    72: "Only hardware/configuration-specific latency is reported.",
    75: "Kernel-generation throughput is outside the World Models leaderboard scope.",
    77: "Core deformable-object scenes and protocols are private and paper-specific.",
    91: "Custom simulated/real hardware tasks are not a reusable public benchmark.",
    99: "Main robot protocol is private/custom; public CO3Dv2 needs a separate contract.",
}

# rank: (benchmarks imported, paper-native evidence location)
IMPORTED = {
    3: ("AgentWorldBench", "AgentWorldBench result table"),
    12: ("WorldModelBench | DreamGen Bench", "Kairos main result tables"),
    27: ("WorldScore", "InSpatio main result table"),
    30: ("WorldScore", "Mirage main result table"),
    49: ("WorldModelBench | DreamGen Bench", "Qwen-RobotWorld main result tables"),
    81: ("MIND", "MIND main result tables"),
    86: ("WorldScore", "DreamWorld main result table"),
    90: ("WorldScore", "WorldCache main result table"),
}

ROBOTICS_COVERED = {
    4: "Fast-WAM results are retained on the canonical LIBERO and RoboTwin 2.0 Robotics boards.",
    10: "LingBot-VA results are retained on the canonical LIBERO and RoboTwin 2.0 Robotics boards.",
    11: "StarVLA results are retained on Robotics; the generic VLA paper is not manually linked to World Models.",
    14: "VLA-JEPA results are retained on the canonical LIBERO Robotics boards.",
    24: "LeWorldModel results are retained on the canonical Push-T Robotics board.",
    41: "Causal-JEPA results are retained on the canonical Push-T Robotics board.",
    46: "ImageWAM results are retained on the canonical LIBERO and RoboTwin 2.0 Robotics boards.",
    82: "Chain-of-World results are retained on the canonical LIBERO and CALVIN Robotics boards.",
    83: "MMaDA-VLA results are retained on Robotics; the generic VLA paper is not manually linked to World Models.",
}

DEFER_OVERRIDES = {
    25: (
        "defer-not-paper-native",
        "The available Push-T number is a reproduction of DINO-WM, not an introduced stable-worldmodel result.",
    ),
    32: (
        "defer-not-comparable",
        "DreamX uses a custom WorldScore-derived suite rather than the configured public WorldScore protocol.",
    ),
    35: (
        "defer-not-comparable",
        "HY-World2 reports component/subset scores that are not a complete configured leaderboard protocol.",
    ),
    63: (
        "defer-not-comparable",
        "WorldStereo reports component/subset scores that are not a complete configured leaderboard protocol.",
    ),
    68: (
        "defer-not-comparable",
        "QuantWM's Push-T evaluation uses a paper-specific 50-step budget, not the official benchmark setup.",
    ),
    76: (
        "not-a-results-paper",
        "StEvo introduces the benchmark and reports external-system results, not an introduced model row.",
    ),
    100: (
        "not-a-results-paper",
        "WBench introduces the benchmark and reports external-system results, not an introduced model row.",
    ),
}


def main() -> None:
    with LEDGER.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])

    if len(rows) != 100:
        raise RuntimeError(f"expected 100 ledger rows, found {len(rows)}")

    paper_ids = [int(row["paper_id"]) for row in rows]
    with get_engine().connect() as connection:
        counts = connection.execute(
            text(
                """
                SELECT paper_id,
                       count(*) AS all_count,
                       count(*) FILTER (WHERE task_id = 26) AS world_models_count
                FROM evaluations
                WHERE paper_id = ANY(:paper_ids)
                GROUP BY paper_id
                """
            ),
            {"paper_ids": paper_ids},
        )
        eval_counts = {
            int(record.paper_id): (
                int(record.all_count),
                int(record.world_models_count),
            )
            for record in counts
        }

    for row in rows:
        rank = int(row["rank"])
        paper_id = int(row["paper_id"])
        terms, comparators = PAPER_EVIDENCE[rank]
        all_count, world_models_count = eval_counts.get(paper_id, (0, 0))
        row["all_task_eval_count"] = str(all_count)
        row["world_models_eval_count"] = str(world_models_count)
        row["benchmark_terms"] = terms
        row["comparator_papers"] = comparators
        if row["hf_models"]:
            row["open_evidence"] = (
                "official GitHub/project and linked HF artifact"
                if row["github_urls"]
                else "linked HF artifact"
            )
        elif row["github_urls"]:
            row["open_evidence"] = (
                "official GitHub/project; exact evaluated HF checkpoint not confirmed"
            )
        else:
            row["open_evidence"] = "no confident open checkpoint mapping found"

        if rank in NOT_RESULTS:
            row["decision"] = "not-a-results-paper"
        elif rank in NOT_COMPARABLE:
            row["decision"] = "defer-not-comparable"
        else:
            row["decision"] = "defer-missing-benchmark"
        row["reason"] = SPECIAL_REASONS.get(
            rank,
            f"Paper-native benchmark ({terms}) was not configured for World Models at inspection time.",
        )
        row["source_table"] = (
            "paper/official README or model card; see field-map worklist"
        )

        if rank in DEFER_OVERRIDES:
            row["decision"], row["reason"] = DEFER_OVERRIDES[rank]
        if rank in IMPORTED:
            benchmarks, source_table = IMPORTED[rank]
            row["decision"] = "imported"
            row["reason"] = (
                f"Imported {world_models_count} paper-native World Models evaluation row(s) "
                f"across {benchmarks}; independently verified."
            )
            row["source_table"] = source_table
        if rank in ROBOTICS_COVERED:
            row["decision"] = "already-covered"
            row["reason"] = ROBOTICS_COVERED[rank]
            row["source_table"] = "paper-native result retained on Robotics"

    with LEDGER.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
