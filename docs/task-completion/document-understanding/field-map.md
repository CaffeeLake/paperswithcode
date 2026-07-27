# Document Understanding field map

Research snapshot: 2026-07-23
Task: `document-understanding` (task ID 308)
Completion contract: reconcile the top 100 live/trending papers and cover their
paper-native benchmarks/evaluations or record an evidence-backed defer decision.

## Scope and current state

- The live task API contains 463 latest-version papers. The requested top-100
  slice is persisted in [top100-ledger.csv](top100-ledger.csv).
- Of those 100 papers, 43 had at least one evaluation row anywhere in the DB at
  stocktake and 57 had none. Only 26 had an evaluation on a task-308
  leaderboard.
- Task 308 currently links 20 datasets with 160 evaluation rows from 102
  distinct papers. The largest task-native leaderboard is DocVQA.
- The task tag is broad and noisy. It includes genuine document AI, sibling
  layout/OCR/retrieval work, and unrelated entity-linking, biomedical, RAG, and
  general NLP papers. The ledger distinguishes these rather than inventing
  document evaluations.

## Completion outcome

- All 100 frozen top-paper slots have a final decision: 43 already covered,
  13 imported, 11 deferred for a missing benchmark, 4 deferred as
  non-comparable, and 29 classified as not results papers.
- Final coverage is 56/100 papers with at least one evaluation anywhere and
  36/100 with a task-308 evaluation, up from 43/100 and 26/100 respectively.
- Paper-native import workers added 65 rows; strict benchmark verification
  retained 53 and removed 12 incompatible new rows.
- Four benchmark datasets were added (MP-DocVQA, MMLongBench-Doc, DUDE, and
  VisualMRC) and InfoVQA's source/task wiring was repaired.
- Twenty-one changed leaderboards were audited end-to-end. Central cleanup
  removed 59 incompatible rows in total (12 new and 47 pre-existing), corrected
  score/provenance/open-data metadata, and recalculated affected ranks.
- Task 308 finishes this pass with 175 evaluation rows from 106 distinct
  papers. The empty MP-DocVQA and VisualMRC pages are intentional: no eligible
  introduced-model row survived their strict full-document/provided-ROI
  contracts.

## Seven research surfaces

### 1. Live task page and local DB

The top of the live page is dominated by 2025/2026 OCR and document-parsing
releases (MonkeyOCRv2, Chandra OCR 2, GLM-OCR, HunyuanOCR, dots.ocr,
Qianfan-OCR, OvisOCR2, Infinity-Parser2-Pro), followed by classic LayoutLM-family
papers and broad multimodal models. Existing task-native coverage is strongest
for:

| Benchmark | Dataset ID | Metric(s) | Rows / papers | Notes |
|---|---:|---|---:|---|
| DocVQA | 29 | ANLS | 68 / 61 | Major single-page VQA contract; test ANLS only |
| MDPBench | 1199 | Latin, Non-Latin, Overall, Private | 25 / 23 | Keep public and private protocols explicit |
| ParseBench | 847 | Accuracy | 11 / 10 | Linked to both document-understanding and OCR |
| FUNSD Entity Extraction | 560 | F1 | 8 / 8 | Underfilled relative to historical field |
| CORD Entity Extraction | 563 | F1 | 7 / 7 | Underfilled |
| RVL-CDIP | 571 | Accuracy | 7 / 7 | Severely underfilled |
| ViDoRe | 583 | NDCG@5 | 11 / 2 | Retrieval-specific; not a generic DU score |
| PubTables-1M | 719 | AP, F1, GriTS | 2 / 1 | Detection/structure metrics must remain separate |
| PubTabNet | 720 | mAP, TEDS | 2 / 1 | Strongly underfilled; mixed-contract risk |
| ViDoRe v2 | 584 | NDCG@5 | 1 / 1 | Retrieval-specific |

Important sibling leaderboards already exist outside task 308: InfoVQA (ID 88,
ANLS, image-understanding), ChartQA (ID 30, Accuracy, image-understanding),
OCRBench/OCRBench v2 and versioned OmniDocBench pages under OCR, and PubLayNet /
DocLayNet under document-layout-analysis. Scores may be imported to those exact
configured pages without forcing every dataset onto task 308.

### 2. Semantic Scholar and citation coverage

Five broad queries plus five 2025/2026 queries produced 737 unique hits; 428
survived a broad relevance filter before manual screening. The historical
anchors are DocVQA, ChartQA, LayoutLM, LayoutLMv2/v3, PubLayNet, Donut, FUNSD,
InfographicVQA, Pix2Struct, RVL-CDIP, DocFormer, CORD, mPLUG-DocOwl, DiT,
DocLayNet, TILT, LiLT, UDOP, LayoutXLM, DUDE, MP-DocVQA, and MMLongBench-Doc.

High-signal 2025/2026 work shifts toward full-page parsing, retrieval,
multi-page QA, and physical/real-world robustness: Dolphin, MonkeyOCR,
VDocRAG/OpenDocVQA, dots.ocr, WildDoc, Infinity Parser, VisR-Bench,
Real5-OmniDocBench, Qianfan-OCR, Youtu-Parsing, Wild-OmniDocBench,
MonkeyOCRv2, and OvisOCR2.

### 3. Legacy Papers With Code dump

The exact legacy task label `document understanding` contains no datasets; old
coverage is fragmented across Visual Question Answering, Document Image
Classification, Document Layout Analysis, Semantic Entity Labeling, Key
Information Extraction, Table Recognition, and Chart Question Answering.

Legacy evidence shows the principal historical gaps:

| Family | Legacy rows | Current DB papers | Decision |
|---|---:|---:|---|
| DocVQA | 33 | 61 | Already broad; verify test-ANLS contract |
| InfographicVQA / InfoVQA | 21 | 37 on sibling page | Repair source/task visibility, not a duplicate dataset |
| RVL-CDIP | 31 | 7 | High-priority paper imports |
| FUNSD semantic entity labeling | 15 | 8 | High-priority paper imports |
| PubTabNet | 13 | 1 | High-priority, but split detection vs structure contracts |
| CORD | 9 | 7 | Moderate paper gap |
| SROIE | 5 | 4 | One clear historical gap plus OCR-source risk |
| Kleister NDA | 3 | 1 | Underfilled |
| VisualMRC | 1 | missing | Useful OCR-free suite benchmark, lower volume |

Legacy rows are leads only. They mix test/validation, component metrics, OCR
inputs, and old labels; every imported value must be checked in its source.

### 4. GitHub popularity

Popularity and reproducibility signals include PaddleOCR (86.1k stars), Docling
(63.7k), Microsoft UniLM/LayoutLM family (22.2k), Surya (21.1k), Chandra
(11.8k), dots.ocr (9.0k), Donut (6.9k), MonkeyOCR (6.6k), mPLUG-DocOwl
(2.4k), DocLayout-YOLO (2.2k), OmniDocBench (1.9k), HunyuanOCR (1.9k),
OCRBench (872), Pix2Struct (686), and ParseBench (533).

Repositories are source-availability evidence, not score authority. Important
lineage cautions:

- PaddleOCR-VL artifacts point to arXiv `2510.14528`, not the newer
  coarse-to-fine paper `2603.24326`.
- Infinity-Parser2-Pro points to `2607.07836`, not Infinity Parser
  `2506.03197`.
- Granite Docling evaluation artifacts point to `2503.11576`; do not attach
  them to the Docling toolkit paper `2501.17887`.
- PP-OCRv5 cards carry an unreliable historical arXiv tag; use the PaddleOCR
  3.0 report and official repository for attribution.

### 5. Hugging Face artifacts

Strong exact model signals include GLM-OCR, Chandra OCR 2, LayoutLMv3,
Surya OCR 2, LayoutLMv2, HunyuanOCR, dots.ocr, Qianfan-OCR, Granite Docling,
LayoutLM, PaddleOCR-VL, PP-DocLayoutV3, Donut-DocVQA, OvisOCR2, and
Infinity-Parser2-Pro. Official downloadable weights or reproducible official
code justify `is_open=true`; `hf_model_url` is set only for an exact evaluated
checkpoint.

Protocol warnings from cards:

- OCRBench appears on native 0–1000 and normalized 0–100 scales and may include
  post-processing variants.
- OmniDocBench v1.0, v1.5, v1.6, and Real5 are separate contracts.
- olmOCR-Bench versions and anchored/non-anchored settings differ.
- MDPBench public and withheld-private sets must not be mixed.
- DocVQA-2026 validation and private test use format-sensitive ANLS and must be
  split explicitly.

### 6. Comparison-table expansion

The field's own comparison tables define the worker queue:

- LayoutLMv2/v3 compare LayoutLM, BERT/UniLM, BROS, PICK, TRIE, SPADE,
  StructuralLM, FormNet, TILT, DocFormer, LiLT, SelfDoc, UDoc/UniDoc, and DiT
  across FUNSD, CORD, SROIE, Kleister-NDA, RVL-CDIP, DocVQA, and PubLayNet.
- UDOP is the central DUE comparison hub: Donut, BROS, StructuralLM, LiLT,
  FormNet, LayoutLM-family, SelfDoc, UniDoc, DocFormer, and TILT, plus seven
  heterogeneous DUE datasets.
- DocOwl/DocOwl2 compare Donut, Pix2Struct, CogAgent, InternVL, TokenPacker,
  DocPedia, Monkey, UReader, TextMonkey, Qwen-VL, and Vary across a recurring
  ten-task OCR-free suite.
- Modern parsing tables compare MinerU, Marker, Mistral OCR, Qwen2.5-VL,
  InternVL, Gemini, Nougat, Dolphin, dots.ocr, PaddleOCR-VL, GLM-OCR,
  Qianfan-OCR, and MonkeyOCR-family systems.
- ViDoRe/VDocRAG tables compare BM25, Contriever, E5/GTE/NV-Embed, CLIP,
  ColPali/ColQwen, DSE, and VisRAG-style retrievers. Retrieval-pool protocols
  stay separate from answer-generation leaderboards.

Comparator cells are discovery evidence only. They are not imported as
external evaluations.

### 7. Explicit 2025/2026 checklist

Priority source-paper workers: dots.ocr, Dolphin, MonkeyOCR, Qianfan-OCR,
PP-DocBee, Infinity Parser, Youtu-Parsing, MonkeyOCRv2, OvisOCR2, GLM-OCR,
HunyuanOCR, and Nemotron Nano V2 VL.

Priority benchmark/source follow-ups: MMLongBench-Doc, MP-DocVQA, DUDE,
OpenDocVQA, WildDoc, VisR-Bench, Real5/Wild-OmniDocBench, DocVQA-2026, and
ViDoRe v3. Very new one-paper benchmarks (SynthDocBench, DocSplit) remain
deferred until their metric contracts and adoption justify leaderboard
creation.

## Benchmark families and contracts

| Family | Canonical benchmark(s) | Comparable contract | Main risks |
|---|---|---|---|
| Single-page VQA | DocVQA, InfoVQA, ChartQA | Dataset-native test metric (ANLS or relaxed accuracy) | zero-shot vs fine-tuned, val vs test |
| Forms/KIE | FUNSD, CORD, SROIE, Kleister, XFUND | Entity extraction/linking/relation F1 on named split | OCR source, task mixing, label granularity |
| Classification | RVL-CDIP | Test Accuracy | augmentation/pretraining differences are okay; split mixing is not |
| Layout | PubLayNet, DocLayNet, D4LA | COCO-style mAP on named split | per-class vs overall, detection vs segmentation |
| Table structure | PubTabNet, PubTables-1M, FinTabNet, TableBank | TEDS/GriTS/AP on exact structure/detection task | metrics and task types are not interchangeable |
| Multi-page QA | MP-DocVQA, DUDE, MMLongBench-Doc | answer metric plus page/evidence protocol | page retrieval, oracle context, long-context setup |
| Full-page parsing | OmniDocBench versions, olmOCR-Bench, ParseBench, MDPBench | versioned native aggregate and split | version, language subset, post-processing |
| Retrieval/RAG | ViDoRe versions, OpenDocVQA, VisR-Bench | NDCG/Recall on exact corpus/pool | retrieval vs downstream QA; corpus pooling |
| Real-world robustness | WildDoc, Real5/Wild-OmniDocBench | separate physical/capture protocol | must not merge with digital/scanned source page |

## Ranked benchmark candidate table

| Benchmark | Dataset ID / slug | Metrics | Evidence surfaces | Candidate papers | Decision |
|---|---|---|---|---:|---|
| DocVQA | 29 / docvqa | ANLS | live, DB, legacy, S2, comparison, HF | 60+ | Wave 1 paper imports + verification |
| InfoVQA (InfographicVQA) | 88 / infovqa | ANLS | legacy, S2, comparison, HF | 35+ | Repaired: native source + task-308 ANLS link |
| RVL-CDIP | 571 / rvl-cdip | Accuracy | DB, legacy, S2, comparison | 30+ | Wave 1 paper imports |
| FUNSD Entity Extraction | 560 | F1 | DB, legacy, S2, comparison | 15+ | Wave 1 paper imports |
| CORD Entity Extraction | 563 | F1 | DB, legacy, S2, comparison | 9+ | Wave 1 paper imports |
| SROIE Entity Extraction | 562 | F1 | DB, legacy, comparison | 5+ | Wave 1 paper imports; OCR-source audit |
| Kleister-NDA | 570 | F1 | DB, legacy, S2, comparison | 3+ | Wave 1 paper imports |
| PubTabNet | 720 | TEDS / mAP | DB, legacy, S2, comparison | 13+ | Wave 1 repair/audit; split task types |
| MP-DocVQA | 1627 / mp-docvqa | ANLS | S2, comparison, HF, live | 10+ | Added: full-document non-oracle test ANLS |
| MMLongBench-Doc | 1628 / mmlongbench-doc | Accuracy | S2, live, GitHub/HF | 10+ | Added: official revised full-set zero-shot overall ACC |
| DUDE | 1629 / dude | ANLS | S2, comparison | 8+ | Added: blind full-test modified ANLS_all |
| VisualMRC | 1630 / visualmrc | CIDEr | legacy, S2, comparison | 10+ mentions | Added: test main setting with provided ROIs/OCR |
| OmniDocBench versioned | 139/140/684 | version-specific | live, S2, GitHub/HF, comparison | 20+ | Use existing OCR leaderboards; verify versions |
| olmOCR-Bench | 141 | Accuracy | live, GitHub/HF, comparison | 15+ | Use existing OCR leaderboard; verify setup |
| PubLayNet / DocLayNet | 846 / 845 | mAP | legacy, S2, GitHub, comparison | 10+ | Use sibling layout task; verify split |
| ViDoRe / v2 | 583 / 584 | NDCG@5 | live, S2, HF | retrieval papers | Keep retrieval-specific |
| OpenDocVQA / VisR-Bench | missing | retrieval + QA metrics | 2025 S2, GitHub, comparison | emerging | Wave 2 if contracts/adoption verified |
| SynthDocBench / DocSplit | missing | new benchmark-native metrics | top-100 live page | one paper each | Defer: too new/one-off for now |

## Paper selection policy

The detailed queue is in [paper-worklist.csv](paper-worklist.csv). It includes:

1. every zero-eval, high-signal paper in the live top 100;
2. classic comparison-table models needed to fill RVL-CDIP/KIE/table gaps;
3. current 2025/2026 parsing and multi-page work;
4. benchmark-source papers needed for missing wiring.

Only a paper's introduced model(s) are eligible. Benchmark papers and comparator
columns remain discovery evidence. The benchmark-wise best eligible introduced
variant is selected after split, metric, model identity, source availability,
and scale checks.

## Primary risks to enforce during import

- Never mix validation/test/private splits.
- Never mix entity extraction, linking, and relation extraction.
- Never collapse TEDS, GriTS, AP/mAP, edit distance, ANLS, and aggregate parser
  scores.
- Preserve document page count, oracle-retrieval, retrieved-context, and
  zero-shot/fine-tuned protocols.
- Preserve benchmark versions and OCR/post-processing settings.
- Do not back-attribute release-card scores to an older paper in the model
  family.
- Treat official GitHub weights/reproduction code as open evidence even without
  a row-level HF link; set an HF URL only for the exact checkpoint.
