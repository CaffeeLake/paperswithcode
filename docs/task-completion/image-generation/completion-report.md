# Image Generation Task Completion Report

Snapshot: 2026-07-19. Task: `image-generation` (`tasks.id=19`).

## Outcome

- Audited the live top 100 trending papers one by one and recorded a terminal decision for every paper.
- Added 100 surviving paper-native evaluation rows during this completion wave.
- Final task coverage is 252 evaluation rows across 17 benchmark datasets.
- Forty-three of the live top 100 now have comparable task evaluations: 24 were newly imported and 19 had existing coverage that was audited or augmented.
- The other 57 papers have explicit outcomes: 18 are not image-generation results papers, 33 require an unconfigured benchmark/protocol, and 6 report only non-comparable setups.
- Elo, arena, Bradley-Terry, and human side-by-side rankings were excluded.

## Final leaderboard coverage

| Benchmark | Rows | Source papers | Verification result |
|---|---:|---:|---|
| GenEval | 52 | 50 | Full audit; custom test prompts, LLM rewriting, and Self-CoT rows removed or replaced with raw-prompt scores. |
| ImageNet 256x256 | 52 | 30 | Full audit; strict class-conditional 50k protocol, FID/IS rows normalized and historical combined rows split. |
| DPG-Bench | 33 | 32 | Full audit; rewritten-prompt i1 row removed and exact-checkpoint openness corrected. |
| ImageNet 512x512 | 21 | 12 | Full audit; one misplaced 256 result removed and JiT FID/IS split. |
| CVTG-2K | 18 | 10 | Full audit; adjacent-column errors/comparator ownership fixed. |
| LongText-Bench EN | 13 | 12 | Full audit; bilingual averages replaced by EN-only scores. |
| OneIG-EN | 13 | 13 | Full audit; language and Overall-score contract verified. |
| T2I-CompBench | 10 | 2 | Full audit; six dimensions remain separate and no synthetic overall exists. |
| OneIG-ZH | 9 | 9 | Full audit; ZH-only Overall scores verified. |
| TIIF-Bench mini | 9 | 9 | Full audit; short/testmini Overall contract enforced. |
| LongText-Bench ZH | 7 | 6 | Full audit; ZH-only percentage scale verified. |
| PRISM-Bench EN/ZH | 7 | 7 | Existing coverage retained; no component-only values imported. |
| HPSv3 | 5 | 4 | Full audit; MJHQ/RealBench/HPDv2 prompt subsets excluded from canonical HPDv3 ranking. |
| ICE-Bench Task 1-31 Overall | 1 | 1 | Existing Emu3.5 paper-native coverage retained and audited. |
| ImageNet 1024x1024 | 1 | 1 | Resolution-separated row retained. |
| OmniContext | 1 | 1 | Full audit; partial aggregate excluding SINGLE removed. |

## Major benchmark and paper spine

The metric-first field map covers the historical ImageNet lineage (BigGAN/StyleGAN context, DDPM/ADM/LDM, DiT, SiT, VAR, MAR, MaskGIT, LlamaGen, RAE/REPA, and current pixel/AR systems) and the modern text-to-image suites (GenEval, ELLA/DPG-Bench, T2I-CompBench, LongText, CVTG, OneIG, PRISM, TIIF, and HPSv3).

High-value top-100 imports include BitDance, SphereAR, MF-RAE, GRN, ViT3, Nucleus-Image, StageVAR, URSA, Skywork UniPic, Echo-4o, FIBO, IRG, PPCL, Pref-GRPO, RecA, LongCat, MrFlow, NextStep, GenClaw, JoyAI, WEAVE, and Few-Step Distillation. Existing rows for Boogu, HiDream-O1, Qwen-Image, Z-Image, Lens, GLM-Image, Emu3.5, X-Omni, and SenseNova were audited and corrected where needed.

## Protocol decisions

- GenEval uses the original 553 prompts and excludes external prompt rewriting, Self-CoT, task-specific replacement test prompts, and best-of-N unless separately configured.
- DPG-Bench uses the original 1,065 dense prompts, four images per prompt, mPLUG/DSG overall score on 0-100.
- ImageNet leaderboards remain resolution-specific and require class-conditional ImageNet-1K generation, normally 50k samples against canonical reference statistics. Guidance, rejection sampling, NFE, and sampler details are preserved in model names/methodology.
- LongText and OneIG keep English and Chinese tracks separate. No bilingual mean is stored as a language-track score.
- T2I-CompBench stores Color, Shape, Texture, Spatial, Non-Spatial, and Complex independently; no invented aggregate is used.
- HPSv3 is retained as a secondary learned-preference metric only when evaluated on the canonical HPDv3 benchmark prompt set.
- COCO FID/CLIP results remain deferred because current sources mix 5k/10k/30k samples, COCO-2014/2017, resolutions, fine-tuned/zero-shot settings, and FID implementations.

## Integrity checks

- No duplicate task/dataset/model/metric keys.
- No null `best_metric` or `best_rank` values on task 19.
- Metric validator reports zero image-generation mismatches. Its four global warnings are unrelated pre-existing rows on ETH3D relative, FLORES-101, FLORES-200, and LiveBench.
- The task API returns HTTP 200 after all mutations.

## Artifacts

- `field-map.md`: seven-surface research map and benchmark contracts.
- `top100-ledger.csv`: terminal decision and final coverage for all 100 live papers.
- `import-ledger.csv`: every surviving evaluation row created during this wave.
