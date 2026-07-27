# Audio Understanding completion report

Completed: 2026-07-21. Live task: `audio-understanding` (task id 10).

## Result

This pass reconciled the requested frozen top 100 trending papers and rebuilt the task around exact, source-backed benchmark contracts.

- Top-100 adjudication: 100/100, with zero missing decisions.
- Top-100 decisions: 22 imported, 5 already covered and still valid, 22 deferred for a missing shared benchmark, 2 for a missing configured metric, 25 for incompatible/adjacent protocols, and 24 benchmark/survey/dataset sources that are not model-result papers.
- Top-100 papers with surviving task evaluations: 27, carrying 68 rows. Only 7 papers had task rows at preflight; verification later removed incompatible rows from two of those original papers while adding verified coverage for 22 previously zero-eval papers.
- Whole task: 58 → 111 evaluation rows, 20 → 41 evaluated papers, and 19 → 25 linked datasets.
- Added benchmark contracts: AIR-Bench Foundation, AIR-Bench Chat, and four MMAU-Pro views (overall, multiple choice, open-ended QA, instruction following).
- Repaired source/contract metadata for MMAU, MMAR, MMSU, LongAudioBench, AudioCaps, Clotho-AQA, and MuChoMusic.
- Surviving new rows: 71. Verification removed 33 mixed-version, mixed-target, mixed-modality, subset-only, or judge-incompatible rows.

## Field overview

The core field is modern large audio-language-model perception and reasoning. Its shared benchmark spine is MMAU/MMAR/MMSU/MMAU-Pro, with AIR-Bench for broad foundation/chat evaluation and LongAudioBench for long-context reasoning. Important constituent families include captioning/retrieval (AudioCaps, Clotho-v2), audio QA (Clotho-AQA, CompA-R, OpenAudioBench LlamaQuestions), classification/representation (CochlScene, NonSpeech7k, NSynth), music understanding (MuChoMusic, MusicAVQA), paralinguistics (IEMOCAP), and hallucination/safety analysis (CMM and newer one-off safety suites).

Repeated comparison lineage connects Qwen/Qwen2-Audio, SALMONN, LTU, Pengi, Audio Flamingo 1/2/3/Next, GAMA, Kimi-Audio, Audio-Reasoner, Step-Audio, Qwen2.5/3 Omni, MiMo-Audio, UAS-Audio, AudioToolAgent, MATS, AHA, and Covo-Audio. Comparator cells were used for discovery and protocol checking, never attached to a model paper as an external evaluation.

The field map combines the live task/database, the legacy Papers With Code dump, 1,646 deduplicated Semantic Scholar records, GitHub popularity/openness, Hugging Face artifacts, comparison-table expansion, and an explicit 2025/2026 slice. Seventy-three of the frozen top 100 papers are from 2025/2026, so recency was handled separately from citation rank.

## Highest-impact imports

- UAS-Audio: canonical MMAR and MMSU; its apparent MMAU row was removed as test-mini.
- Kimi-Audio: MMAU, CochlScene, NonSpeech7k, and OpenAudioBench; incompatible Clotho-AQA was removed.
- Audio Flamingo 1/2/Next: captioning, audio QA, long audio, music, and constituent classification results, normalized and protocol-filtered.
- Step-Audio-R1/R1.5: canonical MMSU and full MMAU where supported.
- AudioToolAgent: MMAR and the official MMAU-Pro overall/open-ended/instruction-following views.
- MATS: AudioCaps, Clotho-v2, and full MMAU.
- Covo-Audio: full MMAU, canonical MMSU, and full MMAR, with corrected closed/unreleased variant metadata.
- Audio-Omni, AudSemThinker, AHA, Mellow, DIFFA, Qwen2-Audio, Audio-Reasoner, Baichuan-Audio, ReCLAP, SLAM-AAC, Pengi, Qwen-Audio, SALMONN, GAMA, and Fun-Audio-Chat received source-native rows where their exact protocol survived verification.

## Important verifier decisions

- MMAU excludes test-mini and domain-only rows; five initial rows were removed.
- Clotho-AQA now contains only the official unanimous binary subset; six mixed judge/unfiltered/generated-answer rows were removed.
- MuChoMusic now contains only the original one-shot, three-randomization protocol; six perceptual/RUL/fixed-order rows were removed.
- NSynth is explicitly the three-class `instrument_source` target; pitch and 11-class instrument-family rows were removed.
- IEMOCAP uses the canonical SUPERB four-class five-fold classifier contract; generative fixed-split rows were removed.
- AIR-Bench Foundation is currently empty because the sole imported value covered only five of 19 tasks.
- AIR-Bench Chat's Audio-Reasoner score was corrected from the paper's arithmetically inconsistent 7.94 to 7.64.
- AudioCaps and Clotho-v2 CIDEr values are normalized to 0–100, while retrieval is text→audio only.

## Most important deferred top-page papers

- Step-Audio 2 and R1-AQA: paper-native MMAU results are test-mini, not the configured full board.
- Gemma 4: available source results are ASR and speech translation, not configured task-10 evaluation.
- SoundMind: results are exclusively on its own three-direction modality protocol.
- DeSTA2.5-Audio: MMAU test-mini and VoiceBench's different “MMSU” protocol.
- GigaChat Audio, STAR-Bench, SpotSound, SAKURA, Audiopedia, Audio Entailment, and several safety papers: meaningful but currently one-paper/unconfigured protocols.
- ASR, codec, TTS, audio/video generation, deepfake detection, and sheet-music papers remain tagged on the live task page but were not forced onto incompatible Audio Understanding boards.

## Durable artifacts

- `field-map.md`: holistic field and benchmark map.
- `top100-ledger.csv`: frozen top-100 reconciliation with current eval IDs and terminal decisions.
- `paper-worklist.csv`: major/recent/comparison-lineage paper worklist and outcomes.
- `import-ledger.csv`: surviving imports, deleted transient/bad rows, and inspected no-import papers.
- `verification-ledger.md`: benchmark contracts, cleanup decisions, and validation summary.

## Validation and remaining gaps

All Audio Understanding evaluation metric labels and `best_metric` fields pass validation. The global validator still reports four unrelated pre-existing mismatches on ETH3D relative, FLORES-101, FLORES-200 devtest, and Livebench.

Two newly created boards intentionally remain empty: AIR-Bench Foundation, because no imported paper reports the official 19-task aggregate, and MMAU-Pro Multiple Choice, because the source tables do not publish a standalone combined MCQ score that can be imported without synthesis. Future expansion should prioritize stable repeated adoption of SAKURA, SpotSound/temporal-audio, SoundMind, safety/trust, and long-audio protocols, plus target-specific NSynth and Clotho-AQA child boards rather than remixing them into the canonical pages.
