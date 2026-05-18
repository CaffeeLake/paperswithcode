# Evaluation Source Attribution Plan

## Goal

Support evaluations whose score is reported by a source other than the paper/model that the evaluation belongs to.

Today, `evaluations.paper_id` effectively means both:

- the paper/model being evaluated
- the paper/source where the score was found

That works for self-reported results, but it cannot represent comparison rows. For example, a paper page such as `paper/2605.09973` can contain tables with results for external models, including a model introduced by `paper/83213`. Those rows should be attributed to the external model paper while still being discoverable as results reported in `paper/2605.09973`.

## Data Model

Keep the schema lean and avoid a separate source taxonomy.

Add these columns to `evaluations`:

```sql
introduced_paper_id BIGINT NULL REFERENCES papers(id) ON DELETE SET NULL;
source_url TEXT NULL;
source_paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE;
```

Interpretation:

- `source_paper_id`: the paper row whose evaluation section contains this result. This is always required because paper pages are the primary owner of evaluation rows.
- `source_url`: optional URL where this exact score was found. This can be the paper PDF, Hugging Face model card, blog post, GitHub README, benchmark page, or another public source.
- `introduced_paper_id`: optional paper/work/model attribution. Populate this when the evaluated model is known to have been introduced by a specific paper. For all existing self-reported rows, this should equal `source_paper_id`. The reason this gets added is to support evals from models introduced by other papers than the one reporting the eval.

Do not add `source_title`, `source_type`, or `source_metadata` for now.

## Example

For a self-reported result in `paper/2605.09973`:

```text
source_paper_id = <2605.09973 paper row>
source_url = https://arxiv.org/pdf/2605.09973
introduced_paper_id = <2605.09973 paper row>
model_name = 	GLiNER2-PII
```

For an OpenAI model result reported in `paper/2605.09973`, where the OpenAI model is introduced by `paper/83213`:

```text
source_paper_id = <2605.09973 paper row>
source_url = https://arxiv.org/pdf/2605.09973
introduced_paper_id = <83213 paper row>
model_name = <OpenAI model name>
```

For a Hugging Face model card result linked to a known paper:

```text
source_paper_id = <paper page that should show this eval>
source_url = https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro (example)
introduced_paper_id = 82956
model_name = DeepSeek-V4-Pro <model name from card>
```

For a result where the evaluated model's introducing paper is not known:

```text
source_paper_id = <paper page that should show this eval>
source_url = <optional evidence URL>
introduced_paper_id = NULL
model_name = <model name>
```

## Migration

1. Rename only `evaluations.paper_id` to `evaluations.introduced_paper_id`. Do not rename unrelated `paper_id` columns elsewhere in the schema.
2. Add `source_paper_id` and `source_url` to the `evaluations` table.
3. Backfill existing rows:
   - `introduced_paper_id = old paper_id`
   - `source_paper_id = introduced_paper_id`
   - `source_url = external_source_url` when present
   - otherwise use the paper URL derived from the paper row:
     - arXiv rows: `https://arxiv.org/abs/<arxiv_id>`
     - external rows: `papers.source_url`
4. Keep `external_source_url` temporarily if existing code still depends on it.
5. Once API and frontend use `source_url`, remove or alias `external_source_url` in a later cleanup.

## Backend API

Extend the evaluation response model with:

```text
introduced_paper_id
source_paper_id
source_url
```

Any existing evaluation response display fields named `paper_*` should be documented as describing `evaluations.source_paper_id`, meaning the paper page/source that owns this eval row. Do not rename unrelated paper fields across the rest of the API. Do not add extra source-paper display fields for now; the frontend can fetch paper details through the existing paper API when needed.

Add filtering support:

```text
GET /api/v1/evaluations?introduced_paper_id=<id>
```

Returns evaluations attributed to a model/work introduced by that paper. This is optional attribution and should not be the default paper-page query.

```text
GET /api/v1/evaluations?source_paper_id=<id>
```

Returns evaluations reported by that paper.

For paper detail pages, either:

- query `source_paper_id=<id>` to show all evals owned by that paper page, including optional external-model rows.
- optionally add a separate section elsewhere for `introduced_paper_id=<id> AND source_paper_id != id` if we want to show evaluations of this paper's model reported by other papers.

Prefer the explicit filters first. They are easier to reason about and make the new attribution semantics visible.

## Frontend

On a paper page, show two groups:

```text
Models introduced by this paper
```

Rows where:

```text
evaluation.source_paper_id == current_paper.id
AND (
  evaluation.introduced_paper_id IS NULL
  OR evaluation.introduced_paper_id == current_paper.id
)
```

```text
Other models evaluated in this paper
```

Rows where:

```text
evaluation.source_paper_id == current_paper.id
AND evaluation.introduced_paper_id IS NOT NULL
AND evaluation.introduced_paper_id != current_paper.id
```

For external rows, display the attributed paper/model separately from the source:

```text
OpenAI privacy model
Score: ...
Model paper: paper/83213
Reported in: paper/2605.09973
```

On the attributed paper page, external evaluations can appear in a small section:

```text
External evaluations of this paper's model
```

Rows where:

```text
evaluation.introduced_paper_id == current_paper.id
AND evaluation.source_paper_id != current_paper.id
```

## Ingestion

The old extraction pipeline is out of scope because it is no longer used.

Update the active evaluation creation flow so every new evaluation can provide:

```text
source_paper_id
source_url
introduced_paper_id
```

For the default case, only populate `source_paper_id`. These are the evals for models introduced by the paper itself. Set `introduced_paper_id = source_paper_id` when the importer can do so easily, especially for existing rows, but do not require this field for every new row.

For optional comparison rows, set `source_paper_id` to the paper where the score was reported and set `introduced_paper_id` to the paper/model being evaluated when known.

For non-paper evidence, such as a Hugging Face model card or blog post, set `source_url` and keep `source_paper_id` as the paper page that should show the eval.

Only ingest comparison rows with `introduced_paper_id` when attribution is confident. If attribution is not known, either leave `introduced_paper_id` null or skip the optional comparison row, depending on whether the row is still useful on the source paper page.

Update duplicate detection to include source attribution.

Recommended duplicate key:

```text
introduced_paper_id
source_paper_id
source_url
task_id
dataset_id
model_name
best_metric
```

For rows where `introduced_paper_id` is null, duplicate checks should treat nulls consistently so repeated ingestion of the same source/model/benchmark row is still skipped.

This allows the same model score to appear from multiple sources when there is useful independent evidence, while still preventing repeated ingestion from the same source.

## Ranking Behavior

Leaderboards should primarily rank by model, dataset, metric, and score. `source_paper_id` is the provenance/ownership anchor, and `introduced_paper_id` is optional model-paper attribution.

If the same model has multiple scores for the same benchmark from different sources, keep them separate initially and display the source. Later, add canonical-source rules if duplicate evidence becomes noisy.

## Implementation Order

1. Add database migration and ORM fields, including the scoped `evaluations.paper_id` to `evaluations.introduced_paper_id` rename.
2. Backfill existing evaluations with `source_paper_id` and `source_url`.
3. Update API models and `EvaluationService` serialization.
4. Add `source_paper_id` filtering as the default paper-page evaluation query.
5. Update frontend paper detail page grouping.
6. Update manual evaluation creation to require `source_paper_id` and accept optional `source_url` and `introduced_paper_id`.
7. Update active ingestion scripts/tools to pass required `source_paper_id` and optional `source_url` / `introduced_paper_id`.
8. Update duplicate checks to include source attribution.
9. Add or import a focused example for `2605.09973` and verify the OpenAI model row points to `83213` while using `2605.09973` as source.

## Open Questions

- Should `source_url` point to our canonical paper page, the arXiv page, or the PDF for paper sources when it is populated? Prefer our paper page for internal navigation, but arXiv is closer to the primary evidence.
- Should leaderboard pages visually distinguish self-reported vs externally reported results immediately, or only expose the source link in row details?
