# Document Understanding completion report

Completed: 2026-07-23
Task: <https://paperswithcode.co/tasks/document-understanding>

## Outcome

The requested top-100 slice is fully reconciled. Every paper has a final,
evidence-backed decision in [top100-ledger.csv](top100-ledger.csv):

| Decision | Papers |
|---|---:|
| Already covered | 43 |
| Imported in this pass | 13 |
| Deferred: missing benchmark | 11 |
| Deferred: not comparable | 4 |
| Not a results paper | 29 |
| **Total** | **100** |

Coverage among those 100 papers increased from 43 to 56 papers with any
evaluation and from 26 to 36 papers with a Document Understanding task
evaluation.

## Field overview

The completed [field map](field-map.md) synthesizes the live task page and
database, 737 unique Semantic Scholar hits (428 screened), the legacy
Papers With Code dump, GitHub popularity, Hugging Face artifact evidence,
comparison tables in major papers, and an explicit 2025/2026 scan.

The task spans nine distinct benchmark families that should not be collapsed:

1. single-page document VQA;
2. forms and key-information extraction;
3. document classification;
4. layout analysis;
5. table recognition and structure;
6. multi-page and long-document QA;
7. full-page OCR/parsing;
8. document retrieval/RAG;
9. real-world capture robustness.

Comparison-table expansion covered the LayoutLM, DUE/UDOP, DocOwl, modern
parsing/OCR, and ViDoRe/VDocRAG lineages. Comparator cells were used for
discovery only; no comparator was attributed to a paper that did not introduce
the evaluated model.

## Benchmarks added or repaired

| Benchmark | Dataset ID | Contract | Result |
|---|---:|---|---|
| InfoVQA | 88 | test ANLS | Native source repaired and linked to task 308 |
| [MP-DocVQA](https://paperswithcode.co/benchmark/mp-docvqa?task=document-understanding) | 1627 | full-document, non-oracle test ANLS | Added; no eligible row survived this pass |
| [MMLongBench-Doc](https://paperswithcode.co/benchmark/mmlongbench-doc?task=document-understanding) | 1628 | revised 1,082-question full-set zero-shot overall Accuracy | Added; 1 verified row |
| [DUDE](https://paperswithcode.co/benchmark/dude?task=document-understanding) | 1629 | blind full-test modified ANLS_all | Added; 1 verified row |
| [VisualMRC](https://paperswithcode.co/benchmark/visualmrc?task=document-understanding) | 1630 | test CIDEr with provided ROI/OCR | Added; raw-image rows removed as incompatible |

MP-DocVQA and VisualMRC remain intentionally empty rather than displaying
oracle, raw-image, wrong-split, or otherwise incompatible results.

## Paper-native evaluation imports

The import wave added 65 rows across 13 top-100 papers. Verification retained
53:

- OneVision-Encoder;
- InfiniteVL;
- MACT;
- XDoc;
- ERNIE-Layout;
- mPLUG-DocOwl 1.5;
- mPLUG-DocOwl;
- Mini-Monkey;
- LayoutLLM;
- OmniParser;
- NVIDIA Nemotron Nano V2 VL;
- Oryx MLLM;
- DocFormer.

The exact row IDs, source surfaces, model variants, openness evidence, skipped
metrics, outreach issues, and post-verification dispositions are recorded in
[import-ledger.csv](import-ledger.csv).

Four investigated top-100 papers correctly produced no rows:

- PP-DocLayout uses a private relabeled mixed layout protocol;
- SDMG-R's official SROIE result does not match the configured SROIE* split;
- Logics-Parsing v1 reports only the unconfigured LogicsParsingBench;
- OmniLayout reports layout-generation metrics that are not detection mAP.

## Verification and cleanup

Twenty-one changed leaderboards received full row-level audits. Their resolved
contracts and exact decisions are in
[verification-ledger.md](verification-ledger.md).

The consolidated cleanup:

- deleted 59 incompatible rows: 12 from the new import wave and 47
  pre-existing rows;
- removed validation/minival, wrong-version, wrong-metric, component-only,
  judge-based, raw-image, no-mask, and structure-only results from incompatible
  pages;
- corrected one MMMU row from its hidden-test score to the paper's exact
  validation score;
- corrected OCRBench, OCRBench v2, ChartQA, TabFact, and open-model provenance
  metadata;
- added explicit protocol warnings to AI2D and MMBench-EN;
- recalculated 423 rank fields across 13 affected leaderboard/metric triples.

Unverifiable rows were retained rather than guessed. Notable pending cases are
source tables that do not state DocVQA/TextVQA split details and older generic
MMBench labels that do not identify version or split.

## Final state and validation

- Task 308: 175 evaluation rows from 106 distinct papers.
- New paper-native rows retained: 53.
- Top-100 decisions: 100/100 complete, with no blank or invalid decision.
- Deleted-row readback: 0 of the 59 targeted IDs remain.
- Metric validator: no new mismatch. It still reports four unrelated
  pre-existing issues on ETH3D relative, FLORES-101, FLORES-200 devtest, and
  Livebench.

The task-specific disposable research clones and scratch directory were
removed after a temporary disk-pressure event; all durable evidence and
ledgers are preserved in this directory. No production service, frontend,
nginx configuration, or release snapshot was restarted or changed.
