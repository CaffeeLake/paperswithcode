# Evaluation Source Attribution Plan

## Goal

Support evaluations of a paper/model whose score was reported by an independent source unrelated to the paper's own release materials.

Today, `evaluations.paper_id` effectively means both:

- the paper/model being evaluated
- the paper/source where the score was found

That works for self-reported results (which come from the paper or a related Github README, project page, blog post or HF model card), but it makes independent benchmark results ambiguous. A paper page should be able to show evaluations of the model introduced by that paper when the score came from another source, while making the source clear to users.

An evaluation should be marked `external` only when the source is independent of the paper/model's own release context. A Hugging Face model card, project page, GitHub repo, or blog post that is linked from the paper page (and is talking about the same thing) and represents the model/paper itself is not external. A separate benchmark leaderboard, unrelated paper, third-party analysis, or external comparison site is external.

For example, `paper/98456` should be able to show GLM-5.2 results from [FrontierSWE](https://www.frontierswe.com/) as external evaluations because FrontierSWE is an independent benchmark source, not GLM-5.2's own paper/model card.

It also does not make existing independent non-paper sources visible to readers. Today Open ASR Leaderboard results are already imported and shown on model paper pages such as `paper/2505.08699`, but the page does not clearly say that those rows were sourced from `https://paperswithcode.co/benchmark/open-asr-leaderboard` rather than from the model paper itself.

The same pattern applies to external leaderboards such as `https://arcprize.org/leaderboard`: if ARC-AGI evaluates GLM-5 and that score appears on `paper/2602.15763`, the row should remain attached to the GLM-5 paper/model but carry a subtle external marker so readers know the score was not reported by the GLM-5 paper.

The user-facing requirement is:

- self-reported and paper-related rows stay visually normal.
- externally sourced rows stay in the same evaluation results table at the bottom of paper pages.
- externally sourced rows get a subtle, small red `External` badge in that table.
- any evaluation with `source_url` populated should have a clickable source/result link.
- if `source_url` points to the evaluated paper itself, link to the paper's ArXiv PDF when available.
- otherwise, link directly to `source_url`.
- hovering or focusing the badge shows the source URL or a friendly source label.
- the source may be an internal benchmark page, another paper, a third-party leaderboard such as FrontierSWE or Open ASR, a benchmark site such as ARC Prize, or an unrelated external URL.
- a Hugging Face model card, project page, GitHub repo, or blog post linked to the paper/model itself should not be shown as `external`; those are related evidence for the paper/model.

## Current State

The database already has `evaluations.external_source_url`, and API responses expose it. The API also computes `is_external`, and the frontend can render an external badge, but the current semantics are narrower than this plan: only scores reported by another tracked paper are treated as external. Independent benchmark URLs, model cards, and unknown competition pages are not currently shown as external.

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

- keep `paper_id` as the paper/work/model attribution. It means the evaluation belongs on (and was introduced by) that paper's page.
- `source_url`: canonical source where the score was found. Populate this whenever the source is known, whether it is the paper itself, a linked model card, an official project page, or an independent benchmark source. Usually this is a URL, but for paper-sourced evals it can also be an internal paper reference encoded as `paper:<paper_id>` or as a canonical `/paper/...` URL.
- `external`: whether `source_url` is independent of the paper/model's own release context. This should be derived by backend logic from `paper_id`, `source_url`, and the paper's linked resources, then stored for fast filtering and display.

Classification rule:

- `external = false` for results reported in the paper itself.
- `external = false` for results reported in a linked Hugging Face model card, official project page, official GitHub repo, or official blog/release page for the same paper/model.
- `external = true` for results reported by an unrelated paper, third-party leaderboard, benchmark website, independent blog post, independent GitHub README, or other independent source.

The source classification should use existing SQL data rather than scraping pages. For `paper_id = X`, build a normalized related-source set from:

- the paper's own route and ArXiv URLs.
- `papers.source_url` for external/non-ArXiv paper rows.
- `papers.hf_models`, `papers.hf_datasets`, and `papers.hf_spaces`.
- `paper_hf_artifacts` joined to `hf_artifacts`.
- `paper_repositories` joined to `repositories.url`, especially official repos.
- `paper_project_pages` joined to `project_pages.url`.

If normalized `source_url` matches the paper itself or any linked/official resource for the evaluated paper/model, derive `external = false`. If it does not match and the source is a known independent source such as FrontierSWE, ARC Prize, Open ASR, or another paper, derive `external = true`.

Do not add `source_label`, `source_type`, `source_paper_id`, or `source_metadata` for now. The frontend can derive a readable tooltip label from `source_url`.

## Example

For a self-reported result in `paper/2605.09973`:

```text
paper_id = <2605.09973 paper row>
external = false
source_url = paper:<2605.09973 paper id>
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

For a Hugging Face model card result linked to a known paper/model, keep the source URL but derive `external = false` because that model card is already linked to the evaluated paper:

```text
paper_id = 82956
external = false
source_url = https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro
model_name = DeepSeek-V4-Pro <model name from card>
```

For a third-party benchmark result shown on `paper/98456`:

```text
paper_id = <98456 paper row>
external = true
source_url = https://www.frontierswe.com/
model_name = GLM-5.2
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
   - for normal self-reported rows, set `source_url` to the paper source when known and derive `external = false`.
   - for rows whose `external_source_url` is a linked/official paper or model source, copy it to `source_url` and derive `external = false`.
   - for rows whose `external_source_url` is an independent source, copy it to `source_url` and derive `external = true`.
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

`source_url` is the single source of truth for where the score came from. `external` is the derived/stored classification used for filtering and display. When `source_url` is present, the backend should compute `external` from the related-source check rather than relying on a hand-entered value.

`source_url` can be a normal URL or an internal paper reference. If we use paper ids, encode them consistently, for example `paper:<paper_id>`, and let the frontend turn that into a `/paper/...` link when it has enough paper metadata.

Result/source link behavior:

- if `source_url` points to the same paper as `paper_id`, expose `result_url` as the paper's ArXiv PDF URL when available, falling back to the paper route or `source_url`.
- if `source_url` points anywhere else, expose `result_url` as `source_url` after public URL normalization, such as ArXiv-to-`/paper/...` rewriting for indexed papers.
- if `source_url` is empty, keep the existing fallback behavior: paper ArXiv URL first, then the paper's `source_url` for external/non-ArXiv rows.

Keep `external_source_url` in the response during the transition, but prefer `source_url` in new frontend code.

Existing evaluation response display fields named `paper_*` should keep describing `evaluations.paper_id`, meaning the paper/model the row is attributed to.

Add filtering support:

```text
GET /api/v1/evaluations?paper_id=<id>
```

Returns evaluations attributed to a model/work introduced by that paper. This should become the default paper-page query and should include both normal rows and external rows.

```text
GET /api/v1/evaluations?external=true
```

Returns external evaluations only. This is useful for auditing rows that need source attribution.

For paper detail pages:

- query `paper_id=<id>` to load evaluations of this paper/model.
- show both normal and external rows in the same paper evaluation results table.
- render the external badge based only on `evaluation.external`.

## Frontend

On a paper page, keep the current evaluation table layout and include both normal and independent external evaluations in the same table. External rows are evaluations where:

```text
evaluation.external == true
AND evaluation.paper_id == currentPaper.id
```

Keep the row layout familiar and add row-level source attribution:

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
- for FrontierSWE rows, show `External` with tooltip/link `FrontierSWE` -> `https://www.frontierswe.com/`.
- if a legacy row is marked external but has no URL, still show `External` with fallback tooltip `Evaluation sourced outside this paper`; new writes should reject this state.

Keep the badge visually quiet: small text, muted red background/border, no large banner block. It should act as provenance metadata, not as a warning.

Do not show official linked resources as external. If the score came from a Hugging Face model card, official project page, official GitHub repo, or official release blog already associated with the paper/model, keep the row in the normal evaluation table with no `External` badge.

Clickable source behavior:

- every evaluation row with `source_url` should expose a clickable source/result link.
- when the source is the evaluated paper itself, the link should go to the ArXiv PDF if available.
- when the source is a linked model card, project page, official repo, external benchmark, or other paper, the link should go to the normalized `source_url`.
- this clickability is independent of the `External` badge; non-external HF model-card rows should still link to the HF model card as their source.

Later, for paper-sourced comparison rows, another section can be added:

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
source_url
```

The flow should compute `external` from `paper_id` and `source_url` before saving the row.

For the default self-reported or paper-related case, populate `paper_id`, populate `source_url` with the source where the score was found, and derive `external = false`. Use this when the score is listed in the paper itself or in an official/linked source for the paper/model.

For optional comparison rows, set `paper_id` to the paper/model being evaluated when known, set `source_url` to the source where the score was reported, and derive `external` from whether that source is related to the evaluated paper/model.

For independent evidence outside the paper/model's own release context, set `source_url` and `paper_id` when the evaluated paper/model is known, then derive `external = true`. This includes third-party benchmark sites such as FrontierSWE and ARC Prize, unrelated papers, and independent benchmark READMEs.

For related evidence outside the PDF, such as a Hugging Face model card linked from the paper page or an official project page for the model, set `source_url` to that evidence URL and derive `external = false`. These rows may still carry `result_url`, `hf_model_url`, or existing link metadata, but they should not show the `External` badge.

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

For FrontierSWE imports, use:

```text
source_url = https://www.frontierswe.com/
external = true
paper_id = <resolved model paper id, e.g. GLM-5.2 / 98456>
model_name = GLM-5.2
harness = Claude Code
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
2. Backfill existing evaluations with the new classification rule:
   - official/linked model or paper sources stay `external = false`.
   - independent benchmark/source rows become `external = true`.
   - Open ASR rows override to `source_url = 'https://paperswithcode.co/benchmark/open-asr-leaderboard'`.
3. Update API models and `EvaluationService` serialization with `external` and `source_url`.
4. Keep `paper_id` filtering as the default paper-page evaluation query.
5. Update paper-page evaluation rendering to keep normal and external rows in the same evaluation results table, rendering the red `External` badge/tooltip beside the model name for external rows.
6. Update manual evaluation creation to accept `source_url` and derive `external` from the evaluated paper's linked resources.
7. Update active ingestion scripts/tools, starting with the Open ASR importer.
8. Update duplicate checks to include source attribution.
9. Verify `paper/2505.08699` shows Open ASR rows with a subtle `External` badge linking to `https://paperswithcode.co/benchmark/open-asr-leaderboard`.
10. When ARC-AGI rows are imported, verify `paper/2602.15763` can show GLM-5 scores with a subtle `External` badge linking to `https://arcprize.org/leaderboard`.
11. Add or import a focused paper-to-paper example for `2605.09973` and verify the OpenAI model row uses `paper_id = 83213` while using `source_url = paper:<2605.09973 paper id>`.
12. Add or import a FrontierSWE example for `paper/98456` and verify the GLM-5.2 row appears in the paper's evaluation results table with an `External` badge and `source_url = https://www.frontierswe.com/`.

## Open Questions

- For paper sources, should `source_url` use `paper:<paper_id>`, our canonical paper page, the arXiv page, or the PDF? Prefer `paper:<paper_id>` or our paper page for internal navigation, but arXiv/PDF is closer to the primary evidence.
- Should we add `source_detail_url` later to preserve both a benchmark-level source and row-level evidence, such as an Open ASR leaderboard page plus a per-model HF model card?
- Should leaderboard pages visually distinguish self-reported vs independently sourced external results in the first pass, or only paper pages?
- How should ingestion determine whether a URL is related to the paper/model? Initial rule: treat URLs already linked from the paper page (`hf_models`, official repos, project pages, source URL) as related, and require explicit `external = true` for independent sources.
