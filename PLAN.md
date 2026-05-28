# Evaluation Source Attribution Plan

## Goal

Support evaluations whose score is reported by a source other than the paper/model that the evaluation belongs to.

Today, `evaluations.paper_id` effectively means both:

- the paper/model being evaluated
- the paper/source where the score was found

That works for self-reported results, but it makes external benchmark results ambiguous. A paper page should be able to show evaluations of the model introduced by that paper even when the score came from somewhere else, while making the source clear to users.

It also does not make existing non-paper sources visible to readers. Today Open ASR Leaderboard results are already imported and shown on model paper pages such as `paper/2505.08699`, but the page does not clearly say that those rows were sourced from `https://paperswithcode.co/benchmark/open-asr-leaderboard` rather than from the model paper itself.

The same pattern applies to external leaderboards such as `https://arcprize.org/leaderboard`: if ARC-AGI evaluates GLM-5 and that score appears on `paper/2602.15763`, the row should remain attached to the GLM-5 paper/model but carry a subtle external marker so readers know the score was not reported by the GLM-5 paper.

The user-facing requirement is:

- self-reported rows stay visually normal.
- externally sourced rows get a subtle, small red `External` badge in paper-page evaluation tables.
- hovering or focusing the badge shows the source URL or a friendly source label.
- the source may be an internal benchmark page, a Hugging Face model card linked from the paper page, a blog post, a GitHub README, or another paper.

## Current State

The database already has `evaluations.external_source_url`, and API responses expose it. Paper evaluation tables currently ignore it.

The Open ASR importer currently stores a per-model Hugging Face URL in `external_source_url`:

```text
https://huggingface.co/<model_id>
```

For the UI requested here, the canonical displayed source for those rows should be the benchmark page:

```text
https://paperswithcode.co/benchmark/open-asr-leaderboard
```

If we still want to preserve the per-model Hugging Face URL, keep it in `methodology` for now or add a later `source_detail_url`; do not overload the badge source with two meanings.

## Data Model

Keep the schema lean and avoid a separate source taxonomy.

Add these columns to `evaluations`:

```sql
external BOOLEAN NOT NULL DEFAULT FALSE;
source_url TEXT NULL;
```

Interpretation:

- keep `paper_id` as the paper/work/model attribution. It means the evaluation belongs on that paper's page.
- `external`: whether the score was sourced from anywhere other than the paper text itself. Defaults to false. A linked model card, benchmark page, blog post, GitHub README, or another paper is still external even when it describes the same model/paper.
- `source_url`: canonical source for the score. Required when `external = true`; null for normal self-reported rows. Usually this is a URL, but for paper-sourced external evals it can also be an internal paper reference encoded as `paper:<paper_id>` or as a canonical `/paper/...` URL.

Do not add `source_label`, `source_type`, `source_paper_id`, or `source_metadata` for now. The frontend can derive a readable tooltip label from `source_url`.

## Example

For a self-reported result in `paper/2605.09973`:

```text
paper_id = <2605.09973 paper row>
external = false
source_url = NULL
model_name = GLiNER2-PII
```

For an OpenAI model result reported in `paper/2605.09973`, where the OpenAI model is introduced by `paper/83213`:

```text
paper_id = <83213 paper row>
external = true
source_url = paper:<2605.09973 paper id>
model_name = <OpenAI model name>
```

For an Open ASR Leaderboard result shown on `paper/2505.08699`:

```text
paper_id = <2505.08699 paper row>
external = true
source_url = https://paperswithcode.co/benchmark/open-asr-leaderboard
model_name = Granite-speech-3.3-8b
```

For an ARC-AGI result for GLM-5 shown on `paper/2602.15763`:

```text
paper_id = <2602.15763 paper row>
external = true
source_url = https://arcprize.org/leaderboard
model_name = GLM-5
```

For a Hugging Face model card result linked to a known paper, mark it external because the score is listed on the model card rather than in the paper:

```text
paper_id = 82956
external = true
source_url = https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro
model_name = DeepSeek-V4-Pro <model name from card>
```

For a result where the evaluated model's paper is not known, do not create a paper-page evaluation row yet. Either first create/resolve a paper row for the model, or skip the row until attribution is known:

```text
paper_id = <resolved external/model paper row>
external = true
source_url = <source where score was found>
model_name = <model name>
```

## Migration

1. Keep the existing `evaluations.paper_id` column. It remains the paper/model this eval belongs to.
2. Add `external BOOLEAN NOT NULL DEFAULT FALSE` and `source_url TEXT NULL` to the `evaluations` table.
3. Backfill source attribution:
   - for normal self-reported rows, leave `external = false` and `source_url = NULL`.
   - for rows with `external_source_url`, set `external = true` and `source_url = external_source_url` by default.
   - for Open ASR rows, override the generic default:
     - identify rows by the Open ASR parent/sub-benchmark dataset slugs or `methodology LIKE 'Open ASR Leaderboard%'`.
     - set `source_url = 'https://paperswithcode.co/benchmark/open-asr-leaderboard'`.
     - set `external = true`.
4. Keep `external_source_url` temporarily as a read/write alias if existing code still depends on it.
5. Once API, frontend, and importers use `source_url`, remove or alias `external_source_url` in a later cleanup.

## Backend API

Extend the evaluation response model with:

```text
paper_id
external
source_url
```

`external` is stored on the row and should be the single source of truth for whether to show the badge. The backend should validate the invariant that `external = true` requires a non-empty `source_url`.

`source_url` can be a normal URL or an internal paper reference. If we use paper ids, encode them consistently, for example `paper:<paper_id>`, and let the frontend turn that into a `/paper/...` link when it has enough paper metadata.

Keep `external_source_url` in the response during the transition, but prefer `source_url` in new frontend code.

Existing evaluation response display fields named `paper_*` should keep describing `evaluations.paper_id`, meaning the paper/model the row is attributed to.

Add filtering support:

```text
GET /api/v1/evaluations?paper_id=<id>
```

Returns evaluations attributed to a model/work introduced by that paper. This should become the default paper-page query and should include both self-reported and external rows.

```text
GET /api/v1/evaluations?external=true
```

Returns external evaluations only. This is useful for auditing rows that need source attribution.

For paper detail pages:

- query `paper_id=<id>` to show evaluations of this paper/model, including Open ASR-style external rows.
- render the external badge based only on `evaluation.external`.

## Frontend

On a paper page, keep the current evaluation table layout and add row-level source attribution:

```text
Model name  [External]
```

Badge behavior:

- render a compact red or rose `External` badge next to the model name when `evaluation.external` is true.
- make the badge keyboard-focusable and hoverable.
- tooltip text should be derived from `source_url`.
- clicking the badge or tooltip link should open `source_url` when present.
- for Open ASR rows, show `External` with tooltip/link `Open ASR Leaderboard` -> `https://paperswithcode.co/benchmark/open-asr-leaderboard`.
- for ARC-AGI rows, show `External` with tooltip/link `ARC Prize Leaderboard` -> `https://arcprize.org/leaderboard`.
- if a legacy row is marked external but has no URL, still show `External` with fallback tooltip `Evaluation sourced outside this paper`; new writes should reject this state.

Keep the badge visually quiet: small text, muted red background/border, no large banner block, and no change to table grouping. It should act as provenance metadata, not as a warning.

Do not create a separate section just to satisfy the Open ASR or ARC-AGI cases. The immediate user need is a badge in the existing table at the bottom of the paper page.

Later, for paper-sourced comparison rows, a second section can be added:

```text
Other models evaluated in this paper
```

Rows:

```text
evaluation.external == true
AND evaluation.source_url == paper:<current_paper.id>
```

Those rows should display the attributed paper/model separately from the source:

```text
OpenAI privacy model
Score: ...
Model paper: paper/83213
Reported in: paper/2605.09973
```

## Ingestion

The old extraction pipeline is out of scope because it is no longer used.

Update the active evaluation creation flow so every new evaluation can provide:

```text
paper_id
external
source_url
```

For the default self-reported case, populate `paper_id`, leave `external = false`, and leave `source_url` null. Use this only when the score is listed in the paper itself.

For optional comparison rows, set `paper_id` to the paper/model being evaluated when known, set `external = true`, and set `source_url` to the paper/source where the score was reported.

For any evidence outside the paper itself, set `source_url`, `external = true`, and `paper_id` when the evaluated paper/model is known. This includes a Hugging Face model card linked from the paper page; linked resources do not become self-reported just because they are associated with the paper.

For Open ASR, update `backend/database/evaluations_setup/import_open_asr_evaluations.py` so newly imported rows use:

```text
source_url = https://paperswithcode.co/benchmark/open-asr-leaderboard
external = true
paper_id = <resolved model paper id>
```

The per-model HF URL can remain in `methodology` until we add a dedicated `source_detail_url`.

For ARC-AGI imports, use the same shape:

```text
source_url = https://arcprize.org/leaderboard
external = true
paper_id = <resolved model paper id, e.g. GLM-5 / 2602.15763>
```

Only ingest comparison rows with `paper_id` when attribution is confident. If attribution is not known, first create/resolve a paper row for the evaluated model or skip the optional comparison row.

Update duplicate detection to include source attribution.

Recommended duplicate key:

```text
paper_id
external
source_url
task_id
dataset_id
model_name
best_metric
```

Because `paper_id` remains required, duplicate checks do not need special null handling for paper attribution.

This allows the same model score to appear from multiple sources when there is useful independent evidence, while still preventing repeated ingestion from the same source.

## Ranking Behavior

Leaderboards should primarily rank by model, dataset, metric, and score. `paper_id` is model-paper attribution; `external` and `source_url` are provenance.

If the same model has multiple scores for the same benchmark from different sources, keep them separate initially and display the source. Later, add canonical-source rules if duplicate evidence becomes noisy.

Benchmark detail pages should also be able to show the badge eventually, but the first implementation can limit the visible badge to paper-page evaluation tables.

## Implementation Order

1. Add database migration and ORM fields for `external BOOLEAN NOT NULL DEFAULT FALSE` and nullable `source_url`. Keep `evaluations.paper_id` unchanged.
2. Backfill existing evaluations, including the special Open ASR override to `https://paperswithcode.co/benchmark/open-asr-leaderboard`.
3. Update API models and `EvaluationService` serialization with `external` and `source_url`.
4. Keep `paper_id` filtering as the default paper-page evaluation query.
5. Update `EvaluationResultsCard` to render the red `External` badge and tooltip beside the model name.
6. Update manual evaluation creation to accept optional `external` and `source_url`.
7. Update active ingestion scripts/tools, starting with the Open ASR importer.
8. Update duplicate checks to include source attribution.
9. Verify `paper/2505.08699` shows Open ASR rows with a subtle `External` badge linking to `https://paperswithcode.co/benchmark/open-asr-leaderboard`.
10. When ARC-AGI rows are imported, verify `paper/2602.15763` can show GLM-5 scores with a subtle `External` badge linking to `https://arcprize.org/leaderboard`.
11. Add or import a focused paper-to-paper example for `2605.09973` and verify the OpenAI model row uses `paper_id = 83213` while using `source_url = paper:<2605.09973 paper id>`.

## Open Questions

- For paper sources, should `source_url` use `paper:<paper_id>`, our canonical paper page, the arXiv page, or the PDF? Prefer `paper:<paper_id>` or our paper page for internal navigation, but arXiv/PDF is closer to the primary evidence.
- Should we add `source_detail_url` later to preserve both a benchmark-level source and row-level evidence, such as an Open ASR leaderboard page plus a per-model HF model card?
- Should leaderboard pages visually distinguish self-reported vs externally reported results in the first pass, or only paper pages?
