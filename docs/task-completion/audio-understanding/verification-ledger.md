# Audio Understanding verification ledger

Audit date: 2026-07-21. Task id: `10`. All score, split, setup, model, paper, openness, artifact, and rank checks used the `verify-evals` contract and primary paper/release evidence. Every changed benchmark received an independent post-import audit; MATS and Covo-Audio rows added after the first pass received focused follow-up verification.

## Final benchmark contracts and outcomes

| Dataset id | Benchmark | Final rows | Apples-to-apples contract | Audit outcome |
|---:|---|---:|---|---|
| 129 | MMAU | 21 | Full/main three-domain MMAU Accuracy; full v05.15.25 is eligible, test-mini and single-domain subsets are not. | Removed five initial mixed rows: Step-Audio 2 and MiMo/UAS test-mini, Music Flamingo music-only, and an AF3 sound-component/duplicate row. MATS `17621` and Covo `17618` passed focused follow-up. Seven older rows retain an explicit `UNVERIFIABLE` split/revision note because their primary source reports only the aggregate. |
| 128 | MMSU | 13 | Canonical 5,000-item, 47-task audio+text MCQ benchmark; not VoiceBench's spoken-MMLU-style “MMSU”. | Deleted VoiceBench LFM2-Audio and a lower AF3 duplicate. Covo `17619` passed focused follow-up. |
| 168 | MMAR | 9 | Full 1,000-question, seven-modality MMAR overall Accuracy. | Deleted lower AF3 duplicate and Music-only subset. Covo `17620` passed focused follow-up. |
| 1585 | MMAU-Pro | 4 | Official 5,305-item sample-weighted overall composite across MCQ, open-ended QA, and instruction following. | All four rows pass; AudioToolAgent transparently covers 5,304 successful items because one source item was broken. |
| 1586 | MMAU-Pro Multiple Choice | 0 | Official 4,593 MCQs with benchmark-native answer matching. | No paper-native combined MCQ aggregate was published by imported papers; no synthetic aggregate was created. |
| 1587 | MMAU-Pro Open-Ended QA | 1 | Official 625 questions, Qwen2.5-7B judge 1–5, normalized to 0–100. | AudioToolAgent `17558` passes. |
| 1588 | MMAU-Pro Instruction Following | 1 | Official 87 constraint items with deterministic success checks. | AudioToolAgent `17559` passes. |
| 1581 | AIR-Bench Foundation | 0 | All 19 foundation tasks; macro within Speech/Sound/Music, then equal category mean. | Deleted Audio-Reasoner `17542`: 65.2 averages only five selected tasks. |
| 1582 | AIR-Bench Chat | 2 | Full 2,000 items; `gpt-4-0125-preview`; two reversed reference/hypothesis passes; equal macro over Speech/Sound/Music/Mixed. | Corrected Audio-Reasoner `17543` from impossible printed 7.94 to reproducible 7.64; Qwen2-Audio 6.93 passes. |
| 131 | AudioCaps | 10 | Captioning CIDEr on official eval/test stored 0–100; retrieval is text→audio R@1/5/10 only. | Normalized five legacy/new CIDEr values from 0–1 to 0–100. MATS `17615` passed focused follow-up. No incompatible retrieval direction remains. |
| 177 | Clotho-v2 | 11 | Official held-out captioning CIDEr stored 0–100; retrieval is text→audio R@1/5/10 only. | Normalized six CIDEr rows. MATS `17616` passed focused follow-up. |
| 132 | Clotho-AQA | 3 | Official binary yes/no unanimous-answer test subset, Accuracy. | Deleted six unfiltered, generated-answer, or LLM-judge rows. Separate unfiltered, majority, 828-class, and open-ended boards remain possible future work. |
| 174 | MuChoMusic | 1 | Original 1,187-question/644-track one-shot protocol, output extraction, mean over three randomized option orders. | Deleted six RUL, perceptual, fixed-order zero-shot, or duplicate rows; only AF2 56.5 remains. |
| 176 | LongAudioBench | 3 | Original 2,429-item six-category base, GPT-4o-2024-05-13 judge, macro score on 0–100. | Deleted AF-Next `+Speech` `17601`; base AF2/AF3/AF-Next rows pass. |
| 172 | NSynth | 4 | Official test split, three-class `instrument_source` target, Accuracy. | Deleted four pitch, 11-class instrument-family, or zero-shot prompt-retrieval rows. Separate target-specific boards are recommended. |
| 171 | MusicAVQA | 5 | Official test `audio question` subset, audio-only input, Accuracy. | Deleted VideoLLaMA2.1 audio-video/open-ended row `9108`. |
| 178 | IEMOCAP | 2 | SUPERB four-class emotion recognition, speaker-independent five-fold CV, supervised classifier, mean Accuracy. | Deleted SALMONN fixed-Session-5 generative and AF3 generative/retrieval rows. BEATs and SSAST remain. |
| 179 | CochlScene | 4 | Official 13-class participant-disjoint test split, Accuracy. | Deleted MiDashengLM direct-capability protocol `12598`; four prompt-with-label rows pass. |
| 180 | NonSpeech7k | 5 | Official 725-item test split, seven closed-choice labels, Accuracy. | All five rows pass; metadata and exact checkpoint sizes were repaired. |
| 255 | OpenAudioBench LlamaQuestions | 4 | OpenAudioBench spoken LlamaQuestions, speech-to-text answers, GPT-4o binary correctness, percent Accuracy. | Deleted VoiceBench Audio-Interaction and Moshi's native zero-shot QA rows. |
| 170 | CompA-R-test | 3 | Audio-Flamingo-derived automated Accuracy protocol on CompA-R-test; do not mix with the original 1–5 human/GPT-4 ratings. | All AF2/AF3/AF-Next rows pass. The original source is open-ended QA, not pairwise evaluation. |
| 169 | CMM hallucination | 2 | Audio-Language spurious-correlation subset: 200 audios, 400 balanced yes/no probes, Accuracy = `(PA + HR) / 2`. | Audex and AF3 pass; methodology and parameter metadata repaired. |

## Cross-board corrections

- AF-Next's MMAU/MMAR/MMSU system is a captioner followed by proprietary GPT-5.2. Evals `17591`, `17592`, and `17593` are now named `AF-Next-Captioner + GPT-5.2`, closed, with captioner-only HF and parameter metadata removed.
- Covo-Audio's evaluated foundation model is distinct from the public `Covo-Audio-Chat` checkpoint. Evals `17618`, `17619`, and `17620` are now closed, have no mismatched HF link, and use the paper-reported 7B size.
- CIDEr is consistently stored on 0–100 for AudioCaps and Clotho-v2.
- Exact released-checkpoint parameter counts were added where the official artifact exposed reliable tensor totals; values remain null where shared/duplicated checkpoint serialization prevents a defensible whole-system count.

## Cleanup summary

- Preflight: 58 task rows, 20 papers, 19 linked datasets.
- Final: 111 task rows, 41 papers, 25 linked datasets; 23 datasets are non-empty.
- New surviving rows from this pass: 71.
- Non-comparable rows removed during verification: 33, plus one transient MATS row replaced by verified eval `17621`.
- Final duplicate-key and duplicate-paper checks passed on every audited board.
- Rank ordering was recalculated after each mutation and checked against metric direction.

## Validator

`validate_evaluation_metrics.py` reports 14,596 valid source labels, zero aliases, and all `best_metric` values populated. It still exits nonzero for four unrelated pre-existing mismatches outside Audio Understanding: ETH3D relative, FLORES-101, FLORES-200 devtest, and Livebench. No task-10 mismatch remains.
