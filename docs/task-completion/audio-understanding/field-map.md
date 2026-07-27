# Audio Understanding field map

Research date: 2026-07-21. Task: `audio-understanding` (task id 10).

## Completion contract and live state

The requested contract is a thorough, holistic overview of major benchmarks, major papers and their comparison lineages, with paper-native evaluations for the live top 100 papers. Every paper in that slice must finish with an evaluation row or a concrete source-backed terminal decision in `top100-ledger.csv`.

The live trending API currently exposes 265 papers. The frozen top-100 slice contains 73 papers from 2025/2026. Before this pass, only 7 of the 100 had any task-10 evaluation rows and 93 had none; 69 of the 73 recent papers were zero-eval. The whole task had 58 rows from 20 papers on 19 linked datasets. The live snapshot and enriched DB inventory are preserved in `/tmp/audio-understanding/live-api.json` and `/tmp/audio-understanding/live-db.json`.

The task page mixes several adjacent fields. Its core is audio-language-model understanding and reasoning, but it also contains ASR-only, audio-generation, codec, TTS, video-generation, deepfake-detection, and sheet-music papers. Those papers are not forced onto generic Audio Understanding boards when their native protocol belongs to another task.

## Completion outcome

The final state has 111 task rows from 41 papers on 25 linked datasets, 23 of them non-empty. Seventy-one newly imported rows survived independent verification. The frozen top 100 is fully reconciled: 22 papers were imported, 5 remain already-covered, 22 defer for missing shared benchmarks, 2 for missing configured metrics, 25 for non-comparable/adjacent protocols, and 24 are benchmark/survey/dataset sources rather than model-result papers. Twenty-seven top-100 papers now have surviving task rows.

Verification removed 33 non-comparable rows across MMAU versioning, AIR-Bench partial aggregation, Clotho-AQA protocols, MuChoMusic variants, NSynth targets, IEMOCAP splits/setups, MusicAVQA modalities, LongAudioBench expansions, and constituent-board protocol mismatches. It also normalized AudioCaps/Clotho CIDEr to 0–100 and corrected open-weight metadata for cascaded or unreleased variants. Exact decisions and row IDs are in `verification-ledger.md` and `import-ledger.csv`.

## Benchmark families and comparability contracts

| Family | Canonical benchmarks | Metrics | Contract |
|---|---|---|---|
| Holistic audio-language understanding | MMAU, MMAR, MMSU, MMAU-Pro | Accuracy, with benchmark-defined aggregation | Keep MMAU releases/snapshots and full test vs test-mini separate. Keep MMAU-Pro multiple-choice and open-response protocols separate. |
| Broad LALM suites | AIR-Bench foundation/chat, AudioBench, AHELM, UltraEval-Audio, Dynamic-SUPERB Phase 2 | Dataset-specific; AIR foundation accuracy vs chat GPT judge | Do not collapse heterogeneous suites to one scalar unless the source defines a stable aggregate. AIR foundation and chat are separate boards. |
| Long-context and temporal audio | LongAudioBench, BLAB, GigaChat temporal QA, STAR-Bench, SpotSound-Bench | Judge score, accuracy, localization metric | Match duration bucket, judge/version, timestamp tolerance, and short/long split. One-off recent protocols remain deferred until adopted by multiple independent papers. |
| Audio QA and reasoning | Clotho-AQA, MusicAVQA, Audio Entailment, CompA-R-test, OpenAQA, Audiopedia, SAKURA | Accuracy or benchmark-native judge | Binary/unanimous and open-ended subsets are distinct. Audio-only and audio-visual MusicAVQA setups are distinct. |
| Captioning | AudioCaps, Clotho-v2, WavCaps/AudioSetCaps | CIDEr, SPIDEr, FENSE, METEOR | Keep zero-shot and fine-tuned captioning separate. Caption scores must never mix with retrieval or entailment scores on the same dataset. |
| Text-audio retrieval | AudioCaps, Clotho-v2, SoundDescs/Freesound | R@1/R@5/R@10, mAP@10 | Preserve text-to-audio vs audio-to-text direction, split, and candidate-pool size. |
| Audio classification/representations | AudioSet, FSD50K, ESC-50, VGGSound, CochlScene, NSynth, GTZAN | mAP or accuracy | AudioSet balanced/full training differs; ESC-50 supervised five-fold differs from zero-shot; VGGSound audio-only differs from audio-visual. |
| Paralinguistic understanding | IEMOCAP, MELD, RAVDESS, CREMA-D, MSP-Podcast | Accuracy/F1/CCC | Preserve label set, speaker split, cross-validation, and classifier-vs-generative-judge protocol. |
| Music understanding | MuChoMusic, MusicAVQA, NSynth, MARBLE tasks | Accuracy or task-specific metric | Keep perceptual MCQ, audio-visual QA, representation probes, and generative music QA separate. |
| Safety/trust | AudioTrust, JALMBench, Audio Jailbreak, AHELM safety, ALMGuard | Attack success/refusal/safety score | Current protocols are mostly benchmark-specific and comparator-only; do not merge until a stable shared contract exists. |
| Sound-event detection | DESED/WildDESED, L3DAS21 | PSDS1/PSDS2/event-F1 | Preserve DCASE edition, noise setting, strong/weak-label setup, and PSDS configuration. This is a legacy/core family rather than the main modern LALM wave. |

## Seven evidence surfaces

### 1. Live task page and database

The task has 265 tagged papers and 19 linked datasets. The densest current boards are MMAU (14 rows/13 papers), MMSU (6/5), MMAR (5/4), and MuChoMusic (5/4); all other linked datasets have three or fewer rows. Only ranks 2, 5, 13, 31, 34, 44, and 45 in the frozen live top 100 had task evals at pre-flight.

High-priority zero-eval papers that name already configured boards include UAS-Audio (2604.12506: MMAU/MMAR/MMSU), Audio Flamingo 2 (2503.03983: LongAudioBench and the established audio suite), SLAM-AAC (2410.09503: AudioCaps/Clotho captioning), Mellow (2503.08540: MMAU), DIFFA (2507.18452: MMAU/MMSU), C2SER (2502.18186: IEMOCAP), AudioToolAgent (2510.02995: MMAU/MMAR), and AHA (2512.24052: MMAU/MMAR).

The current dataset wiring is also incomplete: 16 of 19 linked datasets use non-native external `paper_url` values, three lack an introducing-paper link, and MMAU points to unrelated arXiv 2407.18961 rather than the audio benchmark paper 2410.19168.

### 2. Semantic Scholar

Canonical, alias, benchmark, subarea, and recent-year queries produced 1,646 deduplicated records, including 946 dated 2025 or later. Citation counts were treated as one signal, not the selection rule. Historical/core leads include PANNs (1912.10211), AST (2104.01778), CLAP (2211.06687), BEATs (2212.09058), Pengi (2305.11834), Qwen-Audio (2311.07919), and Audio Flamingo (2402.01831). Major 2025 result papers include Audio Flamingo 2/3, Kimi-Audio, Audio-Reasoner, R1-AQA, Step-Audio 2, Baichuan-Audio, DeSTA2.5-Audio, MiDashengLM, and SAKURA.

### 3. Legacy Papers With Code dump

Streaming the legacy dump found 14 relevant task taxonomies, 68 candidate dataset leaderboards, 356 evaluation rows, and 42 matching dataset records. The dump confirms long-running families for AudioSet/FSD50K/ESC-50/VGGSound classification, AudioCaps/Clotho captioning and retrieval, Clotho-AQA/MusicAVQA, IEMOCAP and other emotion datasets, DESED event detection, and music representation. Legacy rows are lead evidence only because aliases, scales, folds, directions, DCASE editions, and training protocols are frequently mixed.

### 4. GitHub popularity and openness

High-signal repositories include SenseVoice (8.9k stars), Kimi-Audio (4.7k), Qwen2.5-Omni (4.0k), LAION-CLAP (2.2k), Qwen2-Audio (2.1k), Step-Audio 2 (1.5k), Audio Flamingo (1.2k), MiMo-Audio (1.1k), MOSS-Audio, LTU, Pengi, and AudioBench. Official public weights exist for many exact model families, but licenses range from Apache/MIT/CC0 to noncommercial or custom. `is_open` and `hf_model_url` therefore require row-level variant evidence, not paper-level inference.

### 5. Hugging Face artifacts

Strong current signals include Kimi-Audio-7B-Instruct, Qwen2/2.5 Omni audio models, Step-Audio-2-mini, Audio Flamingo variants, MiMo-Audio, MOSS-Audio, and the official CLAP fused checkpoint. Dataset activity confirms AudioSet, VGGSound, ESC-50, AudioCaps, Clotho, WavCaps, AIR-Bench, MMAU, and MMAU-Pro as important discovery surfaces. AudioSkills and WavCaps are primarily training resources and are not automatically treated as test leaderboards.

### 6. Comparison-table expansion

MMAU, AIR-Bench, AudioBench, Audio Flamingo 2/3, and MMAR comparison tables repeatedly identify Qwen/Qwen2-Audio, SALMONN, LTU/LTU-AS, Audio Flamingo 1/2/3, GAMA, Pengi, MusiLingo, MU-LLaMA, Audio-CoT/Audio-Reasoner, Baichuan-Audio, Qwen2.5-Omni, Step-Audio, Gemini, and GPT-4o Audio as the main lineage. Comparator cells are not imported under those source papers; each model paper must supply its own native score.

### 7. Explicit 2025/2026 slice

The frozen top 100 contains 73 recent papers. Additional high-signal recent papers outside that slice include MMAU-Pro (2508.13992), MiMo-Audio (2512.23808), Audio Flamingo Next (2604.10905), AudioChat (2602.17097), AQUA-Bench (2601.12248), RSA-Bench (2601.10384), LVOmniBench (2603.19217), MOSS-Audio (2606.01802), and Audio-Visual Flamingo (2607.16107). They are included in the paper worklist when they report on recurring contracts; one-paper protocols are recorded as follow-up rather than forced into an existing board.

## Candidate benchmark decision table

| Benchmark | Current DB state | Evidence surfaces | Candidate paper families | Decision |
|---|---|---|---|---|
| MMAU (versioned full test) | id 129, Accuracy, 14 rows; wrong source URL | live, DB, comparison tables, GitHub/HF, recent | AF2/3/Next, Kimi, Qwen Omni, Step, UAS, Mellow, DIFFA, AudioToolAgent, AHA, MiMo, MOSS | Wave 1 repair and fill; split incompatible snapshots/test-mini. |
| MMAR | id 168, Accuracy, 5 rows | live, comparison tables, recent, HF | AF3/Next, Qwen Omni, Kimi, UAS, AudioToolAgent, AHA, MiMo, MOSS | Wave 1 repair and fill. |
| MMSU | id 128, Accuracy, 6 rows | live, recent, HF | Qwen Omni, UAS, DIFFA, AF Next, MiMo, MOSS | Wave 1 repair and fill. |
| MMAU-Pro | missing | recent, GitHub/HF, repeated 2025/26 tables | AF Next, MiMo, MOSS, AudioToolAgent/TAC | Wave 1 create only with explicit MCQ/open-response contract. |
| LongAudioBench | id 176, GPT4o, 1 row | live, AF2/3/Next tables | AF2, AF3/Next, long-audio models | Wave 1 repair; lock judge/version and duration setup. |
| AudioCaps captioning | id 131 also has retrieval metrics | legacy, CLAP, AF2/3, caption papers | AF family, SLAM-AAC, Pengi | Repair/split caption contract from retrieval; wave 1 imports. |
| Clotho-v2 captioning | id 177 also has retrieval metrics | legacy, CLAP, AF2/3, caption papers | AF family, SLAM-AAC, Pengi | Repair/split caption contract from retrieval; wave 1 imports. |
| AudioCaps/Clotho retrieval | same dataset IDs, R@K configured | legacy, CLAP, WavCaps | CLAP and representation papers | Keep direction and pool explicit; wave 1/2. |
| Clotho-AQA | id 132, Accuracy, 2 rows | live, AF lineage, VideoLLaMA | AF family, Kimi, Qwen Audio, Pengi | Wave 1 fill only for matching AQA subset. |
| MuChoMusic | id 174, Accuracy, 5 rows | live, MMAR/AF tables, music signals | AF family, Kimi, MiDasheng, Music Flamingo | Wave 1 fill; repair source name/URL. |
| AudioSet/FSD50K/ESC-50/VGGSound | exist under audio-classification, not task 10 | legacy, citations, GitHub/HF, comparison tables | PANNs, AST, CLAP, BEATs, AudioMAE, WavCaps, MiDasheng | Wave 2 link/import only under explicit protocol; reuse datasets without duplicating them. |
| AIR-Bench foundation/chat | missing | live, citations, GitHub/HF, comparison tables | Qwen2-Audio, Audio-Reasoner, SALMONN, Step/Kimi | Wave 1 create as two separate contracts. |
| AudioBench | id 133, unlinked/no metrics | live, legacy-like component signals, GitHub/HF | Qwen2-Audio, SALMONN, WavLLM | Do not create one aggregate scalar; represent stable constituent datasets. |
| AHELM / safety / temporal one-off boards | mostly missing | live, recent, GitHub/HF | benchmark-specific models | Wave 2/defer until independently adopted and exact protocol is stable. |

## Major paper work waves

- Wave 1 existing contracts: UAS-Audio, Audio Flamingo 2, SLAM-AAC, Mellow, DIFFA, C2SER, AudioToolAgent, AHA, Kimi-Audio, Qwen2/2.5/3 Omni, Step-Audio 2, Audio-Reasoner, Audio Flamingo Next, MiMo-Audio, and MOSS-Audio.
- Wave 1 historical/core: CLAP, BEATs, Audio Flamingo, Pengi, Qwen-Audio, Qwen2-Audio, SALMONN, LTU/LTU-AS, PANNs, AST, and AudioMAE where their source-native result matches a selected contract.
- Benchmark/source papers: MMAU, MMAR, MMSU, MMAU-Pro, AIR-Bench, AudioBench, AHELM, MuChoMusic, Clotho/Clotho-AQA, AudioCaps, and LongAudioBench. Their comparator tables expand the worklist but do not create model rows for the benchmark paper unless it introduces its own evaluated model.
- Defer/adjacent-task examples: Qwen3-ASR and Mega-ASR (ASR/WER), LiveTalk/TalkingMachines (video generation), EnCodec/high-fidelity codec work, EzAudio/ETTA (audio generation), TTS benchmark papers, and Codecfake (deepfake detection).

## Principal risks

- MMAU version/snapshot and test/test-mini mixing is the largest current ranking risk.
- Dataset names such as AudioCaps and Clotho currently hide captioning, retrieval, QA, and entailment protocols; metric presence alone does not make rows comparable.
- Judge-based scores depend on prompt and judge model/version.
- Suite-level averages can conceal different task subsets and weights.
- Legacy values often mix 0–1 and percentage scales.
- Open weights must be matched to the exact evaluated checkpoint; a public family does not prove every reported API/model variant is open.
- Benchmark-source comparison rows are external evidence and must not be attached to comparator papers.

Scratch evidence is under `/tmp/audio-understanding/`; durable reconciliation artifacts live beside this file.
