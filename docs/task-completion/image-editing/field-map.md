# Image editing field map

Research snapshot: 2026-07-22 UTC. Task: `image-editing` (task id 18).

User completion contract: get a thorough, holistic overview of the major
benchmarks, major papers and the papers they compare to, and paper-native
evaluations. Reconcile the top 100 papers on the live task page so every paper
has either a verified evaluation row or a concrete evidence-backed decision.

## Final verified snapshot

- The live task grew from 803 to 804 papers during the pass. The top-100 ledger was regenerated from the final live ordering rather than left at the initial snapshot.
- All 100 current papers have a terminal disposition: 27 retain verified paper-native configured evaluations, 39 were source-audited with no compatible configured result, two had unsupported existing rows removed, 18 are adjacent/off-task results, 12 are benchmark or dataset contributions without an eligible introduced-model row, and two are surveys.
- The task now has 42 verified evaluation rows from 29 papers across seven non-interchangeable benchmark datasets: GEdit 18, ImgEdit 12, PIE-Bench 4, RISEBench 3, KRIS-Bench 2, MagicBrush mask-free single-turn 2, and PICABench superficial-prompt 1.
- Thirty-eight of those rows belong to 27 papers in the current top 100. The four additional rows cover SenseNova-U1 and BAGEL, two important comparison-spine papers outside the current slice.
- Every final board was independently verified against primary sources. The task has no duplicate-paper leaderboard rows, harness leakage, or metric-label mismatch. The four remaining global validator warnings belong to unrelated ETH3D, FLORES, and LiveBench rows.

## Scope and protocol families

The live task label spans several protocols that must not be placed on one
leaderboard merely because they all alter images:

1. General instruction editing: an input image plus a natural-language edit;
   current shared suites include GEdit-Bench, ImgEdit-Bench, MagicBrush, Emu
   Edit, I2EBench, PICABench, KRIS-Bench, and RISEBench.
2. Real-image inversion and attention-based text editing: Prompt-to-Prompt,
   Null-text Inversion, Direct Inversion, Pix2Pix-Zero, MasaCtrl, PnP, and
   related methods, most consistently compared on PIE-Bench.
3. Mask-guided inpainting/object removal: Places2/Places365, CelebA-HQ, FFHQ,
   and ImageNet, where dataset, resolution, mask family, and text-guided versus
   unconditional setup are all part of the leaderboard contract.
4. Subject/identity/reference editing: DreamEditBench and newer identity or
   multi-reference suites. Identity similarity and reference preservation do
   not rank against general instruction-following scores.
5. Unified multimodal and reasoning-aware editing (2025-2026): Step1X, BAGEL,
   OmniGen2, Qwen-Image-Edit, FLUX Kontext, ImgEdit-E1, FireRed, and successors.
   These increasingly use versioned VLM judges, bilingual splits, multi-turn
   protocols, and reasoning-specific suites.

## Seven evidence surfaces

### 1. Live task page and database

- The task exists and is visible. The live task API contains 803 papers; the
  first 100 by the page's `trending` ordering were captured on 2026-07-22.
- The top-100 slice contains 62 likely result papers, 15 dataset/benchmark
  papers, 21 adjacent/off-task papers, and two surveys. Seventy-four papers are
  from 2025/2026 (56 from 2025, 18 from 2026).
- Only 10 of the top 100 currently have an image-editing evaluation row. Five
  have paper-native coverage (ranks 1, 7, 14, 49, 100); the other five (ranks
  11, 22, 73, 78, 79) only have PICABench comparator scores sourced from the
  PICABench paper, which do not satisfy the paper-native contract.
- Current linked benchmark stocktake before this pass:

| Dataset id | Benchmark | Configured metric | Rows | Papers |
|---:|---|---|---:|---:|
| 146 | PICABench | Accuracy | 13 | 12 |
| 339 | ImgEdit-Bench | ImgEdit Score | 7 | 7 |
| 346 | GEdit-Bench | G_O (Overall) | 4 | 4 |
| 348 | KRIS-Bench | Overall | 1 | 1 |
| 349 | RISEBench | Overall | 1 | 1 |

The current 26 rows are not all trustworthy as one paper-native corpus:
PICABench ids 464-475 are external comparison-table rows except the benchmark
paper's own fine-tuned model (id 476). KRIS id 752 and RISE id 751 also require
scale/protocol verification against later papers that print values as percents.

### 2. Semantic Scholar citation and keyword searches

Six broad and recent searches covered `image editing`, instruction-based and
text-guided editing, inpainting, subject-driven editing, and editing benchmarks.
They surfaced historical anchors GLIDE (arXiv:2112.10741), InstructPix2Pix
(2211.09800), Prompt-to-Prompt (2208.01626), Imagic (2210.09276), DiffEdit
(2210.11427), MagicBrush (2306.10012), MasaCtrl (2304.08465), Emu Edit
(2311.10089), EditBench/Imagen Editor (2212.06909), and the major inpainting
lineage (contextual attention, gated convolution, LaMa/MAT/RePaint families).

The explicit 2025/2026 search produced Step1X-Edit, ImgEdit, Qwen-Image,
UniWorld-V2, FireRed, GEditBench v2, Edit-Compass, VIBE, Inline Critic,
Agent Banana, WeEdit, GRADE, Omni IIE Bench, PhyEditBench, and numerous new
specialized suites. Recency alone is not an import criterion; new one-paper
protocols are deferred until their metric and adoption are clear.

### 3. Legacy Papers With Code dump

- Legacy `Image Editing` has no datasets or rows.
- `Text-based Image Editing` contains PIE-Bench with 17 rows across 11 source
  paper groups and four metrics: Background PSNR, Background LPIPS, Structure
  Distance, and CLIPSIM. It is the strongest historical direct-editing board.
- Legacy `Image Inpainting` has 12 datasets and 51 rows across 27 titles. The
  largest are Places2 (14), CelebA-HQ (7), Places2 val (7), CelebA (6),
  ImageNet (5), and FFHQ-512 (4). They belong to the separate inpainting track.
- Comparator contamination is demonstrable: the DDNM paper group contains
  DDRM/RePaint/A+y rows, BRGM contains SN-PatchGAN, and LRS2 contains a
  Pix2PixHD-SIA comparator. No legacy row is imported without its own source
  paper inspection.
- PIE-Bench repeatedly compares Prompt-to-Prompt, Direct/DDIM/Virtual
  Inversion, MasaCtrl, Plug-and-Play, Pix2Pix-Zero, Null-text Inversion,
  Negative-prompt Inversion, StyleDiffusion, FireFlow, and ViMAEdit.

### 4. GitHub adoption and source availability

Popularity is used as a field signal, never as score evidence. Leading official
repositories include LaMa (10,128 stars), Qwen-Image (8,149), Inpaint Anything
(7,659), InstructPix2Pix (6,886), BAGEL (6,109), OmniGen2 (4,105),
Prompt-to-Prompt (3,456), InfiniteYou (2,683), Step1X (2,237), FireRed
(1,317), and Pix2Pix-Zero/MAT/MasaCtrl/EDICT/PowerPaint.

Official code/weights or exact reproducibility artifacts support open rows for
InstructPix2Pix, Step1X, BAGEL, OmniGen2, Qwen, FLUX Kontext dev, SmartEdit,
DreamEdit, FireRed, LaMa, MAT, and RePaint. A missing HF link does not make a
row closed when the official GitHub release provides the evaluated checkpoint
or complete reproduction path.

### 5. Hugging Face artifacts

Strong exact-weight or dataset signals include InstructPix2Pix, Step1X,
BAGEL-7B-MoT, OmniGen2, Qwen-Image-Edit variants, FLUX.1-Kontext-dev,
FireRed, MagicBrush, GEdit-Bench, ImgEdit, Emu Edit, PIE-Bench++, I2EBench,
DreamEditBench, ImagenHub's editing task set, OmniContext, KRIS-Bench,
REDEdit-Bench, and GEditBench v2.

Notable snapshot signals: Qwen-Image-Edit has tens to hundreds of thousands of
monthly downloads across versions; FLUX Kontext dev exceeds 200k; ImgEdit and
MagicBrush are the most visible dedicated dataset artifacts. Downloads can be
inflated by repackagings and are not evaluation provenance.

### 6. Comparison-table expansion

- Step1X/GEdit compares InstructPix2Pix, MagicBrush, AnyEdit, OmniGen, Gemini,
  Doubao, and GPT-4o. The benchmark-family table also names EditBench, EmuEdit,
  HIVE, HQ-Edit, ICE-Bench, and GEdit-Bench.
- ImgEdit compares GPT-4o-Image, Step1X, ImgEdit-E1, UltraEdit, AnySD,
  MagicBrush, and InstructPix2Pix; its benchmark survey adds EditVal, EmuEdit,
  AnyEdit, and I2EBench.
- Qwen's paper-native GEdit table compares InstructPix2Pix, AnyEdit,
  MagicBrush, UniWorld-v1, OmniGen/2, BAGEL, FLUX Kontext Pro, Step1X, GPT
  Image, and Gemini. Only Qwen's row can be imported from this source.
- KRIS compares GPT-4o, Gemini, Doubao, OmniGen, Emu2, BAGEL/Think, Step1X,
  AnyEdit, MagicBrush, and InstructPix2Pix.
- RISE compares GPT-4o-Image, Gemini, BAGEL, Step1X, OmniGen, Emu2,
  HiDream-Edit, and FLUX Canny.
- Inline Critic compares ReasonEdit, UniWorld-V2, Qwen-Image-Edit variants,
  BAGEL, FLUX Kontext, Step1X, and proprietary systems across GEdit, ImgEdit,
  KRIS, and RISE. These repetitions define the source-paper worker queue.

### 7. Explicit 2025/2026 checklist

The top-100 ledger contains every live-page 2025/2026 paper. High-signal
current result papers needing source inspection include Qwen-Image(-Layered),
JoyAI-Image, CARE-Edit, REASONEDIT, FireRed, VIBE, UniWorld-V2, LongCat,
ChronoEdit, Uni-Edit, Skywork UniPic, VAREdit, RePlan, EditThinker, FlashEdit,
FlowOpt, CannyEdit, LLM-I, OmniGen2, In-Context Edit, DreamOmni2, and DreamLite.

New benchmark papers include Edit-Compass, REDEdit-Bench, PBench-Edit,
ReShapeBench, UniREditBench, MotionEdit-Bench, WEAVEBench, SpotEdit, UnicBench,
GEditBench v2, VIBE-Bench, GRADE, DLEBench, Omni IIE Bench, and PhyEditBench.
Most remain wave 2/deferred until at least two independent paper-native result
sources use a stable public protocol.

## Candidate benchmark table

| Benchmark/family | DB state | Canonical contract | Evidence | Decision |
|---|---|---|---|---|
| GEdit-Bench EN | id 346; metric `G_O (Overall)` | English full set, named VLM judge/version, 0-10 overall; do not mix CN/intersection | Live, GitHub/HF, Step1X/Qwen/BAGEL/FireRed/current papers | Wave 1; repair native source link and import paper-native rows |
| ImgEdit-Bench | id 339; `ImgEdit Score` | Explicit basic/full subset and evaluator; 0-5 overall | Live, HF, ImgEdit, FireRed, Qwen, Mage-Flow | Wave 1; preserve subset/judge in methodology |
| PICABench | id 146; `Accuracy` | PICABench-Superficial overall accuracy, GPT-5 judge | Live, source paper, many external comparators | Verify now; remove/relocate non-paper-native external rows |
| KRIS-Bench | id 348; `Overall` | Knowledge reasoning suite; exact hint/no-hint protocol and native scale | Live, HF/GitHub, KRIS/Inline Critic | Wave 1 high-risk; resolve scale before additions |
| RISEBench | id 349; `Overall` | Reasoning-informed editing overall; raw vs rewritten instruction and percent scale explicit | Live, source paper, Inline Critic | Wave 1 high-risk; resolve scale/setup before additions |
| PIE-Bench | missing for task | 700-image inversion/text-editing suite; four separately directed metrics | Legacy, GitHub/HF, 11 paper groups | Add as historical wave 1, with exact metric directions/scales |
| MagicBrush | missing for task | Separate single-turn/multi-turn and mask/no-mask; L1/L2/CLIP-I/DINO/CLIP-T | Citations, GitHub/HF, repeated comparison tables | Add as historical instruction-editing wave 1; split contracts |
| Emu Edit test set | missing | Seven editing tasks; exact aggregate and metric definition required | HF, Step1X/ImgEdit comparisons | Wave 2 pending canonical scalar selection |
| I2EBench | missing | 16-dimensional comprehensive benchmark; do not collapse components without defined total | Citation/HF/GitHub, ImgEdit table | Wave 2; metric contract needed |
| EditBench | missing | Text-guided inpainting; human preference/CLIP protocol | Citations, Step1X/ImgEdit tables | Keep in inpainting/text-guided track; defer generic board |
| ICE-Bench | id 403 under image generation | 31-task combined creation/editing overall | Current comparison tables | Do not relabel combined score as generic image editing |
| GEditBench v2 | missing | 1,200 prompts, 23 tasks, pairwise ELO and new judge | Current paper/HF | Separate v2 only; defer ELO because pool/judge dependence |
| REDEdit-Bench | missing | 1,673 bilingual pairs, 15 categories, reported EN/CN totals | FireRed paper/repo/HF | Wave 2; emerging one-source board |
| Places2/CelebA-HQ/FFHQ/ImageNet inpainting | mostly under `image-inpainting` | Dataset + resolution + mask family + metric | Legacy, major repos | Retain on separate task; do not merge with general editing |
| DreamEditBench/reference suites | missing for this task | Subject/reference identity and prompt fidelity | GitHub/HF | Separate subject-driven track; not general score |

## Major papers and historical/current structure

- Foundational diffusion editing: GLIDE, Prompt-to-Prompt, Imagic, DiffEdit,
  Null-text Inversion, EDICT, Pix2Pix-Zero, MasaCtrl, Direct Inversion.
- Instruction editing and data: InstructPix2Pix, MagicBrush, HIVE, SmartEdit,
  Emu Edit, UltraEdit, AnyEdit, HQ-Edit, OmniEdit.
- Inpainting: contextual attention/gated convolution, RePaint, LaMa, MAT,
  PowerPaint, BrushNet, HD-Painter. These remain a separate protocol family.
- Unified/current editors: OmniGen/2, Step1X, BAGEL, ImgEdit-E1, Qwen-Image-Edit,
  FLUX Kontext, UniWorld-V2, FireRed, ReasonEdit, VIBE, Mage-Flow, Inline Critic.
- Evaluation advances: EditBench, PIE-Bench, MagicBrush, I2EBench, GEdit,
  ImgEdit, PICABench, KRIS, RISE, REDEdit, GEditBench v2, Edit-Compass.

## Risks and import policy

- Add only scores reported by the source paper/release for the model it
  introduces. Comparison-table baselines are discovery leads, not imports.
- Judge-based results are comparable only when split, prompt pool, judge model
  and version, rubric, and aggregation match. GEdit EN/CN and full/intersection
  are distinct; ImgEdit basic/full/multi-turn are distinct.
- KRIS/RISE currently show likely 0-1 versus 0-100 scale inconsistencies; do not
  rank new rows until verifiers establish the canonical stored scale.
- PIE mixes higher- and lower-is-better metrics and may contain scaled LPIPS.
- Inpainting requires dataset/resolution/mask-family separation. Places2-val in
  the legacy dump already mixes free-form and center-mask protocols.
- Proprietary APIs require dated/versioned labels and `is_open=false`. Official
  GitHub weights or reproducible checkpoints can justify `is_open=true` without
  an HF URL.
- Training datasets are not benchmarks unless they define a held-out suite and
  a configured comparable metric.

## Durable work products

- [`top100-ledger.csv`](top100-ledger.csv): required live-page reconciliation.
- [`paper-worklist.csv`](paper-worklist.csv): source-paper worker queue and
  comparison expansion.
- [`import-ledger.csv`](import-ledger.csv): surviving evaluation ids and worker
  outcomes.
- [`verification-ledger.md`](verification-ledger.md): benchmark audit decisions.
- [`completion-report.md`](completion-report.md): final reconciled report.
