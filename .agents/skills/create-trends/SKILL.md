---
name: create-trends
description: Research, write, and optionally publish exactly three field-direction bullets for a Papers With Code task page's `research_trends`, synthesizing recurring themes from recent major papers, current trending work, and widely reported benchmarks. Use this whenever the user asks where an AI/ML field is headed, wants key trends or techniques extracted from recent papers, asks to add/update the three bullets below a task description, or wants a concise AlphaXiv-style classic-versus-recent overview—even if they only provide a task-page URL or task name.
---

# Create Trends for a Task

Create three concise editorial bullets that explain where a Papers With Code task is headed. Ground the synthesis in the task page's recent major papers and current trending cohort, then use foundational work to explain how the field reached the present frontier.

The goal is not to summarize three papers. Cluster recurring mechanisms across several important recent papers, then name three durable movements: an architectural transition, a technique or systems frontier, a training/data/evaluation shift, or another grouping that better fits the field. The result should read like a sharp research briefing: plain-language direction first, concrete technical themes second, representative evidence third.

## Modes

Infer the mode from the request:

- **Draft mode:** Research and return proposed bullets without changing the database when the user asks to review, propose, research, or draft.
- **Apply mode:** Add/update `research_trends`, create a reproducible migration, apply it to the live database, and verify production when the user asks to add, create, update, publish, or fix the task-page trends.

If the request clearly authorizes an update, do not stop for confirmation after drafting.

## Evidence Hierarchy

Use this order so the copy describes the field represented on Papers With Code rather than a generic literature survey:

1. **Recent major and task-native papers.** Build a cohort from the latest two years using several importance signals together: task-page trending rank, citations normalized for age, repository or Hugging Face adoption, benchmark leadership, and visible follow-on work. A paper need not lead every signal, but it must materially advance the task rather than merely evaluate on it.
2. **Current task-page trending papers.** Query the same task endpoint the page uses with `order_by=trending`. GitHub star velocity and linked Hugging Face artifact signals reveal what is attracting current attention, including strong new work that raw citation counts underweight.
3. **Major, widely reported benchmarks.** Rank the task's benchmarks by evaluation or paper count, inspect the leading rows, and understand why researchers keep reporting them. Broad adoption is stronger evidence of a field-wide direction than a benchmark with only a few submissions.
4. **Recent benchmark leaders and task-native work.** Inspect the newest leaders, including compact or less-cited work with strong results on the major benchmarks.
5. **Major and highly cited papers.** Query by citation count to find established work that still defines the task.
6. **Foundational papers.** Use classics to date or explain a transition. Do not let them displace current techniques from the three-bullet summary.
7. **External primary sources.** Use arXiv, official repositories/project pages, and Hugging Face paper/model metadata to verify claims or fill gaps. External discovery is supporting evidence, not a substitute for the indexed PwC cohort.

Only link papers that have a working PwC paper page. An unindexed paper may inform the synthesis, but it should not be presented as indexed research. Prefer relative paper and benchmark links such as `[Paper](/paper/2606.23050)` and `[Benchmark](/benchmark/example-benchmark?task=example-task)`.

Some fields are led by products, open-source harnesses, datasets, or deployed systems before a conventional paper appears. When that artifact is genuinely pivotal and its influence is corroborated by the task's trending or benchmark evidence, link its official primary page and identify it as a project rather than inventing a paper citation. This is a narrow exception for product-led trends, not permission to replace the PwC evidence hierarchy with general web search.

## Workflow

### 1. Resolve the task and inspect the existing page

- Resolve the canonical slug and task ID from `GET /api/v1/tasks/<slug>/page`.
- Record the description, existing `research_trends`, benchmark list, paper count, and visible subtasks.
- For each benchmark, record its slug and `paper_count` or evaluation count. This distinguishes a benchmark that defines current reporting practice from a lightly used benchmark that merely has an interesting premise.
- If no exact task exists, stop and recommend `add-task`; do not attach trends to a loosely related task.

### 2. Build the paper and benchmark cohorts

Query at least these views with `include_resources=true`:

```text
GET /api/v1/tasks/<slug>/papers?page=1&page_size=30&order_by=trending&order_dir=desc&include_resources=true
GET /api/v1/tasks/<slug>/papers?page=1&page_size=30&order_by=citation_count&order_dir=desc&include_resources=true
GET /api/v1/tasks/<slug>/papers?page=1&page_size=30&order_by=date_published&order_dir=desc&include_resources=true
GET /api/v1/datasets/?task=<slug>&ordering=-paper_count&page=1&page_size=50
```

For each plausible anchor, capture:

- PwC identifier and whether its paper page resolves;
- publication date and citations;
- repository stars and current `trending_score`;
- linked Hugging Face models, datasets, and Spaces;
- benchmark placements;
- the paper's actual task contribution, core technique, claimed gain, and efficiency trade-off.

Select a working cohort of roughly 8–15 papers when the page has enough coverage. Include at least three recent major papers and enough adjacent recent work to tell whether a mechanism is recurring. Do not define “major” by lifetime citations alone: a new paper can qualify through strong trending, adoption, benchmark, or follow-on signals, while an old highly cited paper belongs mainly in the historical comparison.

Task tagging can be noisy. Exclude general-purpose papers that merely report the task as one benchmark unless they materially advance the task's methods, data, evaluation, or deployment.

Inspect the three to five most-reported meaningful benchmarks in more depth:

```text
GET /api/v1/datasets/<benchmark-slug>?include_paper=true
GET /api/v1/datasets/<benchmark-id>/evaluations/?page=1&page_size=30&ordering=best_rank
```

For each, determine:

- why it attracts reports: realistic environment, broad task coverage, reproducibility, executable grading, stable protocol, cost, or another concrete reason;
- whether the stored count represents genuinely comparable results rather than duplicate variants;
- which models or papers lead it and what harness, reasoning mode, context policy, training recipe, tool setup, or data advantage they use;
- which techniques recur across several top rows rather than appearing in one release.

Treat a technique as recurring only when the stored row metadata or primary sources establish it for multiple leaders. Do not infer a training recipe from a model-family label or generic model card; when methodology is missing, limit the claim to the techniques that are actually documented.

Do not promote a sparse benchmark as a major trend merely because its introducing paper is highly cited or conceptually appealing. A lightly reported benchmark can still support an emerging niche, but label it that way. Conversely, if a major benchmark is missing from the task's display association yet is clearly task-native and has substantial evaluation coverage, inspect it directly and note the data gap.

### 3. Verify the important claims

Read the primary source for every paper that will be named. Use the `hf-cli` skill (`hf papers info <arxiv-id>` or `hf papers read <arxiv-id>`) when Hugging Face metadata or artifacts are relevant, and use arXiv/official sources when more detail is needed.

Check concrete numbers and mechanisms rather than extrapolating from titles. Examples include native-resolution crops, constant KV cache, reward construction, model size, inference speedup, dataset scale, or a benchmark result.

### 4. Compare classic and recent work

Write a short internal field map before drafting. Start with a paper-to-theme matrix: rows are the recent major papers, columns are candidate mechanisms or directions, and each populated cell records explicit source evidence. This distinguishes a repeated pattern from a memorable feature of one paper.

Then answer:

- What did the classic pipeline or dominant paradigm look like?
- Which papers initiated the transition to the current paradigm?
- What do the most recent influential papers have in common?
- What changed to increase accuracy, efficiency, robustness, or coverage?
- Where do recent papers disagree or expose a trade-off?
- Which benchmarks are most widely reported, why did they become the field's common tests, and which techniques distinguish their leading rows?
- Which two to four technical phrases keep recurring across independent recent papers—for example a model family, memory mechanism, conditioning scheme, training recipe, systems optimization, or interaction mode?
- Do the three candidate trends share a higher-level direction, such as streaming, unification, test-time adaptation, smaller deployable models, or synthetic supervision? State it only if at least two trends independently support it.

Select a trend only when it is supported by multiple meaningful papers or by one pivotal transition paper plus several recent descendants. Avoid treating a single paper feature as a field-wide trend.

### 5. Write exactly three bullets

Use an AlphaXiv-style research-briefing voice: direct, current, technically specific, and easy to scan. Each bullet should normally be 45–80 words across one or two sentences:

1. Begin with a short bold direction label, such as `**Streaming replaces offline generation.**`
2. In the first sentence, say what is changing and why it matters.
3. In the second sentence, name two to four recurring technical themes and, where useful, two or three representative indexed papers or one major benchmark.

Prefer formulations like “Recent work is converging on…”, “The frontier is shifting from X to Y…”, or “Key themes are A, B, and C…”. Use energetic language only when the evidence warrants it; avoid unsupported claims that an area is “exploding,” “massive,” or universally converged.

Each bullet should:

- open with the field-level direction, not a paper title;
- explain the mechanism or reason the direction matters;
- name two or three representative indexed papers when useful;
- link a major benchmark when its adoption or evaluation design is itself evidence for the direction;
- connect classic work to recent work without making the bullet historical trivia;
- stay concise enough to scan below the task description;
- use relative PwC links and valid Markdown.

A strong default arc is:

1. **Paradigm shift:** where the field came from and what now dominates.
2. **Current technical frontier:** architecture, resolution, efficiency, robustness, deployment, or the recurring techniques used by leaders on the major benchmarks.
3. **How gains are produced:** data curation, pretraining/post-training, RL, distillation, synthetic data, or evaluation.

This is a default, not a forced taxonomy. Replace it when the evidence supports three different, clearer trends.

Do not write vague claims such as “models are becoming larger and more accurate.” Name the technical change and its consequence. Avoid promotional “SOTA” language unless the benchmark context materially supports the trend.

After the three bullets, include a one-sentence **Overall direction** in draft responses and final reports when a genuine cross-bullet convergence exists. This sentence is a synthesis of the same evidence, not a fourth database bullet, and should connect at least two of the three trends through one shared architectural, systems, data, or evaluation movement. Omit it when the field is moving along three unrelated axes.

### 6. Run the quality gate

Before presenting or applying the bullets, verify:

- there are exactly three non-empty strings;
- recent task-native papers drive the synthesis;
- each trend is supported by at least two meaningful recent papers, or by one pivotal transition paper plus multiple recent descendants;
- the named “key themes” recur across independent sources rather than being copied from one abstract;
- classic papers are used mainly to explain transitions;
- every linked internal `/paper/<id>` or `/benchmark/<slug>` page returns HTTP 200 on PwC;
- no linked paper came only from an external search without PwC indexing;
- any linked non-paper project is an official primary page, is clearly presented as a project, and is corroborated by indexed task or benchmark evidence;
- when the task has established leaderboards, benchmark adoption was ranked by reporting depth and any benchmark called major has substantial comparable coverage;
- claims about the frontier's techniques match the methodology or source evidence for multiple leading benchmark rows rather than one model's marketing copy;
- each bullet expresses one distinct trend supported by evidence;
- any **Overall direction** is supported by at least two bullets and is not persisted as a fourth item;
- the set covers both performance and efficiency/robustness when those are active research concerns;
- claims match primary sources and do not overgeneralize one release.

### 7. Persist in apply mode

Create an idempotent migration at:

```text
backend/database/migrations/update_<slug>_research_trends.sql
```

Use this shape, escaping SQL quotes correctly:

```sql
UPDATE tasks
SET research_trends = jsonb_build_array(
    '<bullet 1>',
    '<bullet 2>',
    '<bullet 3>'
),
updated_at = NOW()
WHERE slug = '<slug>';
```

The repository already constrains populated `research_trends` arrays to exactly three items. Apply the migration with the project database environment, using the normal application connection for content-only updates. If permissions require the table owner, run `psql` as the local `postgres` user with the migration passed on stdin.

Database-only editorial updates do not require a backend or frontend restart. If code or schema also changes, follow the repository deployment instructions.

### 8. Verify local and production output

- Fetch the local task-page API and assert the array has exactly three items.
- Check every internal paper and benchmark link locally and on production.
- Fetch the production API. The nginx task-page cache may serve the previous value for about 60 seconds; poll briefly until the normal, non-cache-busted endpoint returns the new copy.
- Open or request the production task page and confirm the bullets render below the description.

## Final Report

Lead with the outcome and link the task page. Include:

- the three final trends in compact form;
- a one-sentence **Overall direction** when the evidence supports cross-trend convergence;
- the principal recent and classic anchors used;
- whether the result was draft-only or applied and verified live;
- any evidence gap, noisy tagging issue, or important trade-off that affected the synthesis.

Do not dump the full research log unless the user asks for it.
