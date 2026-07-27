# Document Understanding verification ledger

This ledger is populated after the paper-native import workers finish. One audit
is run per changed or high-risk benchmark, with exact row IDs and source-backed
keep/fix/delete decisions.

## VisualMRC (`dataset_id=1630`, `task_id=308`, CIDEr)

Contract: test main setting with dataset-provided ground-truth ROIs and OCR
words, CIDEr via coco-caption. The two imported OCR-free models instead consume
the full raw page image and question without the benchmark's ROI/OCR inputs.

| Eval ID | Model | Score | Verdict | Action |
|---:|---|---:|---|---|
| 17972 | DocOwl 1.5 Chat | 246.4 | WRONG_SETUP | Delete |
| 17984 | mPLUG-DocOwl | 188.8 | WRONG_SETUP | Delete |

The scores, model identities, open/HF/parameter metadata, and rank order are
otherwise source-correct. Their methodologies incorrectly claimed the
ground-truth ROI/OCR main protocol, so relocation or a metadata-only fix is not
appropriate. No duplicates were found. The global CIDEr metric says scale
0–100 although this benchmark's official ×100 COCO convention can exceed 100;
that shared metric metadata was not changed.

## InfoVQA (`dataset_id=88`, `task_id=308`, ANLS)

Contract: official InfographicVQA test ANLS on a 0–100 presentation.

- PASS: 17964, 17983, 17991, 18011, 18047.
- WRONG_SPLIT / delete: 17996. OneVision-Encoder's 51.6 comes from the
  LMMs-Eval validation configuration; its test configuration only generates a
  submission and the source provides no official test ANLS.

All six rows have consistent harness/open/HF metadata and no unique-key,
variant, or exact cross-task duplicates. Dataset 88 is independently linked to
task 8 (44 historical rows) and task 308 (the new slice), which fragments the
display but is not a row-level duplicate.

## DocVQA (`dataset_id=29`, `task_id=308`, ANLS)

Contract: official hidden test ANLS, rendered 0–100. Audit: 79 rows; 49 PASS,
8 WRONG_SPLIT, 1 WRONG_METRIC, 21 UNVERIFIABLE. No duplicate, scale, harness,
rank, or confirmed open-tag errors.

- Delete WRONG_SPLIT: 4958, 5589, 1173, 6322, 1117, 7413, 8434, 17995.
- Delete WRONG_METRIC: 10559 (Qwen3-8B judged matching instead of ANLS).
- New rows PASS: 17963, 17969, 17977, 17982, 17989, 17990, 18000, 18010,
  18046.
- New row UNVERIFIABLE: 18040 (Oryx score/model/open artifact confirmed, but
  the source does not establish hidden-test/native-ANLS rather than the
  available validation scorer).

The 21 UNVERIFIABLE rows remain pending stronger author/server split evidence
and are not deletion candidates in this pass.

## FUNSD Entity Extraction (`dataset_id=560`, `task_id=308`, F1)

All 11 rows PASS under the standard 149/50 FUNSD test entity-labeling protocol.
New rows 17970, 17973, and 17978 are source-faithful. No alternate entity-linking
metrics, duplicates, harness values, scale/rank errors, or open/HF conflicts.

## CORD Entity Extraction (`dataset_id=563`, `task_id=308`, F1)

Contract: official 800/100/100 split, provided OCR/boxes, word-level semantic
entity labeling and entity-level F1.

- PASS: 9145, 6981, 5902, 17979, 17974, 7027, 5915.
- WRONG_SETUP / WRONG_METRIC_PROTOCOL; delete: 7166, 18009, 6113.

The rejected OmniParser/OmniParser V2/Donut rows are raw-image end-to-end
generation or text spotting with field-level exact-match F1, not official-OCR
entity labeling. No duplicate, rank, harness, or definite open-tag issues.

## RVL-CDIP (`dataset_id=571`, `task_id=308`, Accuracy)

All 9 rows PASS the canonical 320k train / 40k validation / 40k test,
16-class full-test Accuracy contract. New rows 17975 and 17981 are
source-faithful. No duplicate, rank, harness, split, scale, or open/HF issues.

## Kleister-NDA Entity Extraction (`dataset_id=570`, `task_id=308`, F1)

All 3 rows PASS. Contract is the 83-document validation split with entity-level
F1 via official GEval because test ground truth is private/unavailable.
Keep 17980, 17976, and 5918. Different PDF/OCR extraction pipelines are valid
end-to-end system choices here because all rows evaluate the same normalized
four-field outputs on the same validation documents. No duplicates or metadata
conflicts.

## MMLongBench-Doc (`dataset_id=1628`, `task_id=308`, Accuracy)

Row 18012 PASS. Nemotron Nano V2 VL reasoning-off 32.1 is the official revised
1,082-question full-set, zero-shot `overall_acc`, not F1 or a fine-grained
evidence/page/document subscore. Open BF16 artifact, exact parameter count,
scale, null harness, and rank are correct. No duplicates or actions.

## DUDE (`dataset_id=1629`, `task_id=308`, ANLS)

Row 18048 PASS. MACT's 72.5 is aggregate modified ANLS on the original blind
full multi-page test split, not a diagnostic/type score or oracle/retrieval
setup. The 24B four-agent identity, closed status, null HF/harness, and scale are
correct. No duplicates or actions.

## PubTabNet (`dataset_id=720`, `task_id=308`, TEDS + mAP)

Current wiring mixes three contracts. Keep 18007 OmniParser 88.96 as canonical
full-content validation TEDS. Delete 9085 from that leaderboard because its
96.75 is structure-only TEDS (future S-TEDS metric). Delete 9088 because its
86.8 mAP is TableFormer's derived/augmented content-cell box detection protocol
(future separate benchmark variant), not native end-to-end table recognition.
After cleanup, 18007 should rank first. All current rows use validation; the
issue is metric/target mixing, not split or source-score accuracy.

## OCRBench (`dataset_id=155`, `task_id=4`, Score)

Contract: original 1,000-item OCRBench native 0–1000 overall Score.

- All five new rows PASS: 17994, 17998, 18003, 18015, 18041.
- Fix 15077 from OCR-assisted PP-DocBee 835 to the base end-to-end 828 and
  normalize model name/methodology.
- Clear `num_parameters` on 15084 because 1.1B is only the GenLIP encoder, not
  the evaluated composite model; keep score 659.
- Keep the other 56 rows; no deletion, version mixing, percent-scale residue,
  duplicate, harness, rank, or confirmed open-tag issue.

## FinTabNet (`dataset_id=721`, `task_id=308`, TEDS)

Contract: standard 10,656-image cropped-table test split, end-to-end HTML
reconstruction with content-inclusive TEDS.

- Keep 18008 OmniParser 89.75 and 9248 SmolDocling 52.0.
- Delete 9086 TableFormer 96.8 because its source reports structure-only TEDS
  and no content-inclusive FinTabNet score.

No duplicates, harness, rank, or open-tag conflicts.

## ChartQA (`dataset_id=30`, `task_id=8`, Accuracy)

Contract: official test overall relaxed accuracy with 5% numeric tolerance.
Audit: 65 rows; keep 56, delete 7, leave 2 unverifiable.

- Delete: 10558 (LLM-judged matching), 8433 (augmented minival), 8425
  (augmented component only), 7412 (validation), 7810 (encoder probe),
  17997 (OneVision encoder probe), 15011 (MonkeyOCRv2 frozen-encoder probe).
- Unverifiable pending protocol evidence: 885, 5977.
- Fix metadata: rename 18001 to `InfiniteVL-4B` and correct table reference;
  set 6094 closed; set 6249 `uses_additional_data=true`; optionally canonicalize
  5588's redirected official HF URL.
- New rows 17967, 17985, 17992, 18001, and 18013 otherwise PASS.

No exact duplicate, harness, scale, rank, or same-variant open inconsistency.

## TextVQA (`dataset_id=62`, `task_id=8`, Accuracy)

Contract: official TextVQA validation split, using the native VQA accuracy
scorer on a 0–100 scale. This is distinct from the legacy plain TextVQA
test-standard surface.

- PASS: 31 rows, including new rows 17993, 18002, and 18014.
- WRONG_SPLIT; delete: 5873, 6271, 6591, 6968, 8422, 8534, 8549, 17968,
  and 17986.
- UNVERIFIABLE: 15 rows, including new row 18042; retain pending stronger
  primary-source split evidence.

No confirmed open-model, duplicate, harness, scale, or ranking issue remains
among the rows retained.

## TabFact (`dataset_id=729`, `task_id=331`, Accuracy)

Contract: official standard TabFact test-set classification accuracy through
the native exact-match evaluator, on a 0–100 scale. All 5 rows PASS, including
new rows 17966 and 17988; there are no deletion or unverifiable cases.

- Correct 9193's methodology from “denotation accuracy” to classification
  accuracy.
- Set `uses_additional_data=true` on 9193, 9153, and 12689 because each uses
  pretraining or multitask data beyond the TabFact training set.
- Optional enrichment: add UDOP's exact official HF URL; retain its
  paper-native 794M parameter count.

No duplicate, harness, split, scale, judged-score, or open-status issue.

## WikiTableQuestions (`dataset_id=724`, `task_id=331`, Accuracy)

Contract: standard held-out test accuracy with the benchmark's normalized
answer evaluator. All 9 rows PASS, including new rows 17965 and 17987; no
required deletion or correction.

The leaderboard intentionally contains both structured-table systems and
rendered-document systems. The DUE document cohort retains the original
pristine-unseen test tables and normalized evaluator, so the setup difference
is recorded in methodology rather than treated as a split mismatch. Optional
enrichment: clarify 15010's Table 8 frozen-encoder setup and add exact official
HF links for TAPEX, TAPAS, and UDOP.

## AI2D (`dataset_id=33`, `task_id=8`, Accuracy)

Contract: standard fixed AI2D test split with opaque masked region labels
(`AI2D_TEST` / `lmms-lab/ai2d`), exact-match choice accuracy on a 0–100
scale. The transparent/no-mask protocol is a distinct, materially easier
benchmark and must not be mixed.

- PASS: 60 rows, including new 18016 and 18043.
- WRONG_SETUP; delete: 6321, 5078, 8351, 9521, 9532, 10353, and 18004.
- WRONG_SPLIT; delete: 7411 and 8432.

Clarify dataset 33's description as the opaque/masked-label test protocol.
Transparent/no-mask values may be preserved only on a separately configured
benchmark. No duplicate, metric, harness, rank, or confirmed open-status issue.

## MMBench-EN (`dataset_id=162`, `task_id=8`, Accuracy)

Contract: MMBench v1.0 English test, 1,784 multiple-choice questions,
CircularEval top-1 accuracy on a 0–100 scale. It is distinct from v1.1 and
from either version's development split.

- PASS: 544, 6885, 5001, 170, 171, 172, 5178, 6843, and 18005.
- WRONG_SPLIT or WRONG_VERSION; delete: 6318, 4731, 4730, 4962, 7724, 8545,
  18044, 7136, 1099, 18017, 8530, 6919, 7042, 6083, and 9463.
- UNVERIFIABLE; retain pending stronger version/split evidence: 9203, 5608,
  11382, 7966, 7113, 742, 10553, 10076, 7156, 6933, 8065, 6923, and 9461.

Rename retained row 18005 to `InfiniteVL-4B`. No exact duplicates, harness
issues, metric mismatch, or rank errors.

## WebSRC (`dataset_id=650`, `task_id=296`, F1)

Contract: official development split, extractive QA over HTML/web structure,
token-overlap F1 on a 0–100 scale. The test set was not released, so comparable
published results use development.

Both rows PASS: 7205 MarkupLM Large and new 17971 XDoc 1M. XDoc's official
configuration explicitly evaluates `websrc1.0_dev_.json`. No deletion,
duplicate, metric, split, setup, harness, rank, or open-status issue. Optional
enrichment: add MarkupLM Large's official HF URL.

## MMMU (`dataset_id=31`, `task_id=8`, Accuracy)

Contract: base MMMU validation, rule-based micro-averaged accuracy on a 0–100
scale. The development split is intended for few-shot examples, while the
hidden test split and MMMU-Pro are distinct contracts.

- PASS: 92 rows after the corrections below, including new 18018 and 18045.
- WRONG_SETUP; delete 18006 because its published aggregate uses Qwen3-4B as
  an evaluation model rather than MMMU's rule-based scorer.
- Correct 8067 from hidden-test 40.7 to the source's comparable validation
  result 46.7 and update its methodology.
- Set 7964 `is_open=false`: the valid 62.3 result is from the unreleased 32M
  in-house-data checkpoint, while only the lower-data checkpoint is public.

Nine retained canonical validation rows lack detailed methodology and are
listed as optional provenance enrichment in the worker report. There are no
exact duplicates, harness issues, metric mismatch, or rank errors.

## OCRBench v2 (`dataset_id=156`, `task_id=4`)

Three separate configured contracts are valid: official English Score
(eight-group macro average), official Chinese Score (five-group macro average),
and LMMs-Eval whole-dataset bilingual Accuracy. These aggregates are not
interchangeable.

All 15 rows PASS their respective score/protocol contracts, including new
17999. Required metadata fixes:

- Set 17999 `is_open=false` and clear `hf_model_url`; only its component vision
  encoder is public, not the evaluated aligned/instruction-tuned composite.
- Re-source 15082 to its OpenReview paper and correct the methodology table
  reference; the current arXiv version no longer contains its 59.09 result.

No deletion, duplicate, harness, scale, rank, or metric-label issue.
