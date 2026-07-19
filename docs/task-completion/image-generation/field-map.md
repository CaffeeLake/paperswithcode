# Image Generation Field Map

Research snapshot: 2026-07-19. Task: `image-generation` (`tasks.id=19`).

Scope: a holistic, metric-first completion pass over the live top 100 trending
papers, plus the major historical and current papers that define the field.
Subjective pairwise/Elo leaderboards are excluded. Preference predictors such
as HPSv3 are secondary; the primary focus is reproducible metrics such as
GenEval, DPG-Bench, and class-conditional ImageNet FID/IS.

## Evidence surfaces

1. Live task API: 3,210 tagged papers; the top-100 slice was captured from
   `/api/v1/tasks/image-generation/papers?order_by=trending&page_size=100&page=1`.
   It is dominated by 2025/2026 work and contains substantial false-positive
   task tagging (VLA, video, editing, restoration, and perception papers).
2. Local DB: 15 linked benchmark datasets and 169 existing evaluation rows.
   GenEval has 36 papers, ImageNet 256x256 has 17, and DPG-Bench has 18.
3. Semantic Scholar/current primary sources: citation and 2025/2026 searches
   surfaced the major historical line (ADM, LDM, DiT, Imagen, DALL-E 2) and
   current metric-native work (SANA 1.5, PixelFlow, MeanFlow, IMM, DDT,
   Improved MeanFlow, Drifting, Representation Frechet Loss, and newer AR
   tokenizers).
4. Legacy PwC dumps: streamed `evaluation-tables.json` and
   `jul-28-datasets.json`. Strong legacy coverage exists for ImageNet, CIFAR,
   FFHQ, LSUN, CelebA, CUB, STL-10, and MS-COCO; GenEval has metadata but no
   legacy leaderboard rows.
5. GitHub: high-signal official repositories include DiT, VAR, LlamaGen, MAR,
   SiT, LightningDiT, SANA, BAGEL, Infinity, HiDream-I1, PixelDiT, LPD, and
   the GenEval/ELLA benchmark repositories.
6. Hugging Face: exact official checkpoints were identified where the release
   ties them to the evaluated variant. GitHub/Dropbox/Azure checkpoint releases
   can still justify `is_open=true` when no exact HF model URL exists.
7. Comparison tables: GenEval, ELLA/DPG-Bench, SANA 1.5, PixelFlow, MeanFlow,
   RAE, SphereAR, and current top-page papers were expanded into source-paper
   leads. Comparator cells remain leads only; they are not imported as external
   evaluations.

## Benchmark families and contracts

| Family | Canonical contract | Evidence | Decision |
|---|---|---|---|
| GenEval | Original 553 prompts, four images/prompt, six task means macro-averaged into Overall on 0-1 scale; default inference without prompt rewriting/best-of-N | live DB, source paper 2310.11513, GitHub, recent comparison tables | Wave 1. Keep rewritten/CoT/best-of-N variants explicit and verify detector/protocol. |
| DPG-Bench | ELLA/2403.05135 protocol; 1,065 dense prompts, four images/prompt, mPLUG VQA/DSG overall score on 0-100 scale | live DB, ELLA paper/repo, recent tables | Wave 1. Do not mix component scores or evaluator/prompting variants. |
| ImageNet 256x256 | Class-conditional ImageNet-1k generation, normally 50k samples against canonical reference stats; FID lower is better, IS higher is better | live DB, 71 legacy rows/50 papers, many official repos | Wave 1. Record guidance, NFE/steps, sampler, label balance, FID implementation, and representation mode. Do not mix rFID/FD-DINO/10k-sample ablations. |
| ImageNet 512x512 | Same class-conditional contract at 512 resolution | live DB, 48 legacy rows/25 papers | Wave 1/2. Resolution-separated; same protocol cautions as 256. |
| ImageNet 64/128 | Resolution-specific class-conditional generation, FID/IS | legacy PwC (63 and 23 rows) | Wave 2 after separate benchmark rows and protocol review. |
| T2I-CompBench | Six dimensions, each with its own native evaluator/metric; no synthetic overall unless a source defines one | ELLA, GenEval-related literature, recent papers | Wave 2. Requires dimension-specific benchmark/metric wiring; never merge with CompBench++. |
| LongText-Bench | EN score currently stored as `Accuracy`; keep EN/ZH distinct | live DB/current papers | Wave 1 current-paper coverage; verify that rows consistently use EN or clearly named aggregate. |
| CVTG-2K | NED and Word Accuracy on the fixed 2K prompt suite | live DB/current papers | Wave 1 current-paper coverage. Store only configured metrics. |
| OneIG EN/ZH | Language-specific overall score | live DB/current papers | Wave 1 current-paper coverage. Keep EN/ZH separate. |
| PRISM-Bench EN/ZH | Fixed benchmark accuracy under its VLM-judge protocol | live DB/current papers | Wave 1/2. Metric-based but judge-dependent; keep language tracks separate. |
| HPSv3 | Fixed learned preference score on the benchmark suite | live DB/HF/current papers | Secondary only. It is metric-based but preference-derived, so it does not displace objective composition/FID leaderboards. |
| CIFAR-10 unconditional | Unconditional generation FID under a fixed sample/reference protocol | 69 legacy rows/63 papers | Wave 2. Must not reuse the classification `CIFAR-10` dataset row or merge with class-conditional CIFAR. |
| FFHQ 256/1024 | Resolution-specific face generation FID, fixed reference/sample protocol | 51 and 20 legacy rows | Wave 2. Standard FID, clean-FID, DINOv2 FD, precision/recall, and likelihood remain separate. |
| LSUN Bedroom/Churches | Category- and resolution-specific FID | 32 and 27 legacy rows | Wave 2. Split standard FID from clean-FID/trainfull and training-efficiency rows. |
| MS-COCO text-to-image | Fixed caption/prompt subset, resolution, sample count, and FID implementation; CLIP separately | 69 legacy rows/42 papers, PixArt sources | Defer until protocol-specific dataset rows exist. Legacy mixes zero-shot/fine-tuned, 10k/30k, resolution, and FID variants. |
| DrawBench/Elo arenas | Human pairwise preference, judge- and pool-dependent | Imagen/current release pages | Reject for this pass. Original DrawBench has no canonical scalar metric; Elo is explicitly out of scope. |

## Major paper map

Historical anchors: BigGAN (1809.11096), PGGAN (1710.10196), StyleGAN
(1812.04948), StyleGAN2 (1912.04958), StyleGAN3 (2106.12423), DDPM
(2006.11239), Improved DDPM (2102.09672), ADM (2105.05233), VQGAN
(2012.09841), Latent Diffusion (2112.10752), DiT (2212.09748), EDM
(2206.00364), SiT (2401.08740), VAR (2404.02905), MAR (2406.11838),
LlamaGen (2406.06525), EDM2/autoguidance (2312.02696/2406.02507), and
Consistency Models (2303.01469).

Text-to-image benchmark anchors: GenEval (2310.11513), ELLA/DPG-Bench
(2403.05135), T2I-CompBench (2307.06350), Imagen (2205.11487), SDXL
(2307.01952), PixArt-alpha (2310.00426), SANA 1.5 (2501.18427), PixelFlow
(2504.07963), Infinity (2412.04431), BAGEL (2505.14683), HiDream-I1
(2505.22705), and Qwen-Image (2508.02324).

Current 2025/2026 objective leads include RAE (2510.11690), PixelDiT
(2511.20645), MeanFlow and Improved MeanFlow, IMM (2503.07565), DDT
(2504.05741), Drifting (2602.04770), Representation Frechet Loss
(2604.28190), Internal Guidance (2512.24176), SRA/SRA2, SoFlow
(2512.15657), pMF (2601.22158), LPD (2507.01957), SphereAR
(2509.24335), MF-RAE (2511.13019), AsymFlow (2605.12964), and the
metric-bearing top-100 papers recorded in the ledger.

## Top-100 and recent-paper observations

- The live top 100 are all 2025/2026 releases. Every row is tracked in
  `top100-ledger.csv`.
- Papers already covered include Boogu-Image, HiDream-O1-Image, GLM-Image,
  Qwen-Image, Z-Image, Lens, i1, Emu3.5, PixNerd, DeCo, X-Omni, RAE,
  MiniT2I, AsymFlow, and several multimodal releases.
- High-priority zero-eval candidates with paper-native rows on configured
  benchmarks include JoyAI-Image, GenClaw, Decoupled DMD, HunyuanImage 3.0,
  Multi-Resolution Flow Matching, NextStep-1, LongCat-Image, MixGRPO,
  Pref-GRPO, Reconstruction Alignment, Skywork UniPic, URSA, StageVAR,
  PPCL, GRN, MF-RAE, Adv-GRPO, SphereAR, BitDance, Nucleus-Image, and WEAVE.
- Many apparent zero-eval gaps are correct deferrals: VLA/video/restoration/
  editing papers, benchmark-only papers, one-off personalized/controlled
  generation suites, and results that use incompatible ImageNet/COCO sample
  protocols.

## Risks and curation rules

- GenEval prompt rewriting, CoT, best-of-N, reward optimization, and detector
  versions can materially change the score. Base/default and test-time-scaling
  variants must not be silently collapsed.
- DPG-Bench evaluator/version and four-image grid protocol must be documented.
- ImageNet leaderboards currently do not encode all protocol axes in schema.
  Methodology and model-name suffixes must make CFG/guidance, NFE, sampler,
  label balance, sample count, and FID implementation explicit; incompatible
  variants are deferred to separate dataset rows.
- Current ImageNet dataset source links point at the GAN paper or ImageNet
  homepage rather than a native local source page. Metadata repair must not
  pretend the GAN paper introduced ImageNet; the dataset source remains
  ImageNet while the leaderboard protocol is documented in the dataset text.
- Source-paper comparator rows are discovery signals only. Every imported row
  must be native to the model's own paper/release.
- Open status is variant-specific. Official non-HF checkpoints/reproduction
  code can justify `is_open=true`; `hf_model_url` is set only for an exact,
  official evaluated checkpoint.

## Import waves

1. Repair source metadata for the existing high-priority benchmark rows where
   a local source paper exists (GenEval, DPG-Bench, current benchmark suites).
2. Import missing paper-native top-100 rows on configured leaderboards.
3. Fill iconic and recent ImageNet/GenEval/DPG gaps outside the top 100.
4. Verify GenEval, DPG-Bench, ImageNet 256/512, and every changed secondary
   leaderboard; remove or split non-comparable rows.
5. Add Wave-2 historical benchmark rows only with explicit protocols, then
   import their source-native historical papers.
