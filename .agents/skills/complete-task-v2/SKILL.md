---
name: complete-task-v2
description: Holistic field-completion workflow for a Papers With Code task page: first build a broad map of the AI field/task from the live task page, local DB, legacy PwC dump, Semantic Scholar citation/recent searches, PapersWithCode trending papers, Hugging Face artifact signals, GitHub topic/repo popularity, and comparison tables in major papers; then add missing major benchmarks with add-benchmark, import paper-native evals with one add-evals worker per paper, and verify apples-to-apples comparability with one verify-evals worker per benchmark. Use when asked to complete, populate, audit, round out, or bring a task's benchmark/evaluation coverage up to date, especially when the goal is broad task coverage rather than a narrow single-benchmark import.
---

# Complete Task V2

Complete a Papers With Code task page by building a holistic view of the field first, then importing and verifying evaluation rows. This skill is for whole-task curation: it should identify the major benchmark families, impactful papers, current/recent papers, legacy PwC coverage, trending local papers, popular GitHub implementations, and Hugging Face artifact activity before deciding what to add.

It is an orchestrator. Use the existing repo skills for the write and audit work:

| Skill | Role |
|---|---|
| `add-benchmark` | One worker per missing or under-wired major benchmark; create/link datasets, source papers, and metrics before eval import. |
| `add-evals` | One worker per source paper; import only the model(s) introduced by that paper. |
| `verify-evals` | One worker per benchmark; audit all rows for apples-to-apples comparability. |
| `enrich-paper` | Optional follow-up when a source paper lacks repo/project/task/method metadata. |

Do not treat this as a blind bulk import or as a narrow "add the easiest current leaderboard" workflow. The main agent owns the field map, benchmark selection, paper worklist, subagent queue, verifier cleanup, and final report.

## Core Contract

Use this default scope unless the user narrows it:

- Preserve this user intent explicitly: **"I want you to get a thorough, holistic
  overview of this task: major benchmarks, major papers and papers they compare to,
  evals for those papers. Importantly, we want to cover the top 100 papers on this
  task and their benchmarks/evals."**
- Get a **thorough, holistic overview** of the task: major benchmarks, major papers,
  papers they compare to, and paper-native evaluations for those papers. Cover the
  **top 100 papers on the live task page and their benchmarks/evals** by default.
  Every paper in that top-100 slice must either have evaluation rows or a concrete,
  evidence-backed ledger decision explaining why it cannot or should not be imported.
- Build a **field map** before importing: major benchmarks, major papers, comparison-table baselines, recent 2025/2026 work, live task-page/trending papers, legacy PwC rows, popular GitHub repos, and relevant Hugging Face artifacts.
- Find the **major benchmarks** for the task, not every dataset ever used, but err toward breadth at the research stage. A broad task should usually produce tens of candidate papers and many candidate benchmarks before filtering.
- Prefer benchmarks where multiple papers report comparable numbers.
- Exclude low-impact one-off benchmarks unless they are clearly becoming field-standard or the user asks for them.
- Use legacy PwC as a required lead source, not an optional fallback. Mine it for historical benchmark families, important older papers, and missing source-paper links, then verify before importing.
- Follow comparison tables in major papers to discover what the field itself treats as important. Do not import comparator rows as evals by default, but do use them to identify papers/benchmarks that deserve their own workers.
- Use local PapersWithCode signals: live task-page papers, DB paper counts, GitHub star velocity/trending score, and linked Hugging Face artifacts. Do not rely only on citation counts.
- Treat source-availability metadata as part of curation, not a cosmetic afterthought. A paper can have open evaluation rows without a direct HF model link when the official GitHub/project page releases weights, links unindexed HF repos, or provides reproducible scripts/configs for the evaluated checkpoint.
- Treat 2025/2026 papers as a required explicit slice: search for them, list them, and decide whether they belong on existing benchmarks, require new benchmarks, or should be deferred.
- Add only **paper-native** evaluation results: the score must appear in the paper/official README/model card for the model that paper introduces.
- Do not add comparator/external eval rows from another paper's comparison table unless the user explicitly asks for external evals.
- Keep leaderboards apples-to-apples: same split, metric, degradation/protocol, input setup, and model mode.

If the user asks for only a benchmark/paper plan, stop after the research plan. If the user asks to complete/populate/import, continue through add-evals and verify-evals.

## Pre-flight

Run from the repo root:

```bash
uv run --env-file backend/keys.env ...
```

Confirm the backend and secrets:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/papers/recent?limit=1
grep -E '^(PWC_ADMIN_API_TOKEN|PWC_SEMANTIC_SCHOLAR_API_KEY|PWC_GITHUB_TOKEN)=' backend/keys.env | sed 's/=.*/=<redacted>/'
```

Resolve the task:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_database_session

task_slug = "<task-slug>"
db = next(get_database_session())
row = db.execute(text("""
    SELECT id, name, slug, is_visible
    FROM tasks
    WHERE slug = :slug OR name ILIKE :name
    ORDER BY id
    LIMIT 1
"""), {"slug": task_slug, "name": f"%{task_slug.replace('-', ' ')}%"}).mappings().first()
print(dict(row) if row else "TASK NOT FOUND")
db.close()
PY
```

If the task does not exist, use `add-task` first.

## Phase 1: Research the Field

Build evidence from at least seven surfaces. Browse when needed; these are current, changing sources. Do not proceed to imports until you have a written field map and candidate tables. If a surface is unavailable, record the reason and compensate with another source.

### 1. Live task page and DB

Open `https://paperswithcode.co/tasks/<task-slug>` and inspect:

- top/trending papers shown on the page;
- benchmarks already linked on the page;
- papers currently ranking on those benchmarks;
- missing-looking recent papers or thin leaderboards.
- any task-page sorting or trend signals that make a paper prominent despite low citations.

Build and persist a **live task-page paper ledger** before importing. Do not rely only on
benchmark-first discovery or citation search: the task page itself can surface current
high-signal papers whose evals are easy to miss.

- Page through the task papers API, for example
  `/api/v1/tasks/<task-slug>/papers?order_by=trending&page_size=100&page=<n>`,
  until all live task-page papers are inventoried, or until a user-specified scope is
  exhausted.
- For each prominent row, record rank, DB paper id, arXiv/source id, title, date,
  citations/trending score, linked artifacts, current eval count, benchmark terms found
  in the paper, and an import decision.
- At minimum, explicitly adjudicate the top 100 trending papers and their benchmark/eval
  coverage. Deep-inspect every zero-eval high-signal paper in that top 100. If the user asks for "all papers listed", inventory
  every API page and then deep-inspect the important zero-eval subset.
- If the user narrows the scope to a top-N slice (for example "stop at top 200"),
  treat that slice as the completion contract: every paper in the top N must either
  already have evaluation rows or have a ledger decision with a concrete reason. Do
  not report the broad task page as done until a reconciliation query shows
  `topN_missing_decision = 0`.
- The decision column must be one of: `imported`, `already-covered`, `defer-missing-benchmark`,
  `defer-missing-metric`, `defer-not-paper-native`, `defer-not-comparable`, or
  `not-a-results-paper`, with a short reason. For `imported`, include the benchmark(s)
  and source table/card.
- Do not finalize the task without reporting the ledger path/counts and naming the most
  important deferred top-page papers.

Query the DB too:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_database_session

task_slug = "<task-slug>"
db = next(get_database_session())
rows = db.execute(text("""
    SELECT d.id, d.name, d.slug, td.supports_harness,
           count(e.id) AS eval_rows,
           count(DISTINCT e.paper_id) AS papers,
           array_agg(DISTINCT m.name ORDER BY m.name) FILTER (WHERE m.name IS NOT NULL) AS metrics
    FROM tasks t
    JOIN task_datasets td ON td.task_id = t.id
    JOIN datasets d ON d.id = td.dataset_id
    LEFT JOIN task_dataset_metrics tdm ON tdm.task_id = t.id AND tdm.dataset_id = d.id
    LEFT JOIN metrics m ON m.id = tdm.metric_id
    LEFT JOIN evaluations e ON e.task_id = t.id AND e.dataset_id = d.id
    WHERE t.slug = :slug
    GROUP BY d.id, d.name, d.slug, td.supports_harness
    ORDER BY papers DESC, eval_rows DESC, d.name
"""), {"slug": task_slug}).mappings().all()
for row in rows:
    print(dict(row))
db.close()
PY
```

Also list the task's highest-signal local papers and artifacts. Prefer repo-native trend fields when present:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_database_session

task_slug = "<task-slug>"
db = next(get_database_session())
rows = db.execute(text("""
    SELECT p.id, p.arxiv_id, p.title, p.date_published, p.citation_count,
           p.trending_score, p.github_trending_component, p.hf_trending_component,
           p.hf_models, p.hf_datasets, p.hf_spaces
    FROM papers p
    JOIN paper_tasks pt ON pt.paper_id = p.id
    JOIN tasks t ON t.id = pt.task_id
    WHERE t.slug = :slug AND p.is_latest_version
    ORDER BY p.trending_score DESC NULLS LAST, p.date_published DESC NULLS LAST
    LIMIT 50
"""), {"slug": task_slug}).mappings().all()
for row in rows:
    print(dict(row))
db.close()
PY
```

### 2. Semantic Scholar: citations + keyword coverage

Use the API key from `backend/keys.env`. Search both the task name and task-specific keywords. Include `year` and `citationCount` in the fields. Run one broad search and one recent-year search.

```bash
source backend/keys.env
QUERY="<task name or keywords>"
curl -sG "https://api.semanticscholar.org/graph/v1/paper/search" \
  -H "x-api-key: $PWC_SEMANTIC_SCHOLAR_API_KEY" \
  --data-urlencode "query=$QUERY" \
  --data-urlencode "limit=100" \
  --data-urlencode "fields=title,year,citationCount,externalIds,abstract,url,authors" \
  > /tmp/s2-<task-slug>.json

curl -sG "https://api.semanticscholar.org/graph/v1/paper/search" \
  -H "x-api-key: $PWC_SEMANTIC_SCHOLAR_API_KEY" \
  --data-urlencode "query=$QUERY" \
  --data-urlencode "year=2025-2026" \
  --data-urlencode "limit=100" \
  --data-urlencode "fields=title,year,citationCount,externalIds,abstract,url,authors" \
  > /tmp/s2-<task-slug>-recent.json
```

Extract candidate arXiv IDs from `externalIds.ArXiv`. Keep papers that mention the task or close synonyms in title/abstract, especially high-citation classics and 2025/2026 papers.

Run multiple query variants for broad tasks:

- canonical task name;
- common abbreviations and aliases;
- benchmark names found in the DB/live page;
- domain-specific subareas the user calls out;
- recent terminology that may not match legacy names.

The output should include a top-cited list and a recent-paper list, not just one or the other.

### 3. Legacy PwC dump

Mine `data/legacy_pwc_data/evaluation-tables.json` and `jul-28-datasets.json`. Legacy PwC is often the best source for older benchmark families and historical leaderboards, even when the live page is thin.

Never load the full JSON files into memory on the VPS. Stream with `ijson` or use targeted `rg`.

```bash
uv run --env-file backend/keys.env python - <<'PY'
import ijson
from pathlib import Path

task_terms = ["<Task Name>", "<task alias>", "<important subarea>"]
path = Path("data/legacy_pwc_data/evaluation-tables.json")
with path.open("rb") as f:
    for item in ijson.items(f, "item"):
        task = item.get("task") or ""
        if not any(term.lower() in task.lower() for term in task_terms):
            continue
        print("\\nTASK:", task)
        for ds in item.get("datasets", []):
            rows = ds.get("sota", {}).get("rows", [])
            print("  DATASET:", ds.get("dataset"), "rows=", len(rows))
            for row in rows[:10]:
                print("    ", row.get("model_name"), row.get("metrics"), row.get("paper_title"), row.get("paper_url"))
PY
```

Use legacy results as leads. Before importing, verify the source paper, metric, split, and setup using `add-evals`/`verify-evals` rules. Legacy rows can mix splits or use stale metric labels.

### 4. GitHub repository popularity

Search GitHub topics and keywords. Use stars, recency, and README links as signals, not proof.

```bash
source backend/keys.env
gh search repos "topic:<task-slug> OR \"<task name>\"" \
  --limit 100 \
  --json fullName,description,stargazersCount,url,updatedAt,homepage,language \
  > /tmp/github-<task-slug>.json
```

If topic search is sparse, search likely synonyms, benchmark names, and model/dataset names found in papers. Map popular repos back to papers via README/arXiv links. Keep a "popular repo with no paper/eval table yet" follow-up list.

For every repo that maps to an in-scope paper, record source-availability evidence in the paper worklist:

- public weights or release assets in GitHub;
- scripts/configs/commands that reproduce the evaluated checkpoint from public artifacts;
- HF model or dataset URLs mentioned in README/docs/scripts, even if those HF repos lack cards, README metadata, or `arxiv:` tags and therefore are not linked from the HF paper page;
- whether the evidence supports `is_open = true`, and whether it is precise enough to set a row-level `hf_model_url`.

### 5. Hugging Face artifact coverage

Search for models and datasets with task, benchmark, and subarea names. Use model cards and dataset cards to discover recent releases, benchmark tables, and source papers.

```bash
uv run hf models list --search "<task or subarea>" --limit 100 --format json > /tmp/hf-models-<task-slug>.json
uv run hf datasets list --search "<task or benchmark>" --limit 100 --format json > /tmp/hf-datasets-<task-slug>.json
```

For promising artifacts, inspect cards and metadata:

```bash
uv run hf models info <repo_id> > /tmp/<repo_slug>/info.json
uv run hf models card <repo_id> --text > /tmp/<repo_slug>/card.md
uv run hf datasets card <dataset_id> --text > /tmp/<dataset_slug>/card.md
```

Artifact popularity is not enough for import. It must resolve to a source paper/release and comparable benchmark scores.

HF paper linkage is incomplete in practice. Also discover HF artifacts through official GitHub/project pages and README links, then inspect those repos directly. A model repo can be official even when it has no model card or no `arxiv:` tag, but only use it for `hf_model_url` when the source ties it to the exact evaluated variant.

### 6. Comparison-table expansion

For each major paper found from citations, legacy PwC, live page, or trend signals, inspect its evaluation/comparison tables. Extract:

- benchmark names and splits;
- the paper's own introduced model(s);
- comparator model/paper names;
- cited benchmark source papers;
- recent papers that appear repeatedly as comparators.

Do not import comparator rows by default. Use them to add papers to the worklist and to identify missing benchmarks that need `add-benchmark`.

### 7. Recent papers check

Create an explicit recent-paper checklist:

- all 2025/2026 candidates from Semantic Scholar;
- 2025/2026 papers on the live task page;
- 2025/2026 papers in popular GitHub repos;
- 2025/2026 papers from Hugging Face model/dataset cards;
- 2025/2026 papers found by following comparison tables in major papers.

Do not add them just because they are recent; require source-reported scores on configured comparable benchmarks, or mark the missing benchmark/metric as follow-up.

### Field Map Gate

Before Phase 2, write a compact field map. It must include:

- benchmark families and their canonical metrics/splits;
- major historical papers and why they matter;
- major current/recent papers, especially 2025/2026;
- live/trending local papers and popular GitHub repos;
- legacy PwC benchmark rows found and whether they are candidates;
- missing benchmark/source-paper/metric wiring discovered;
- risks: mixed protocols, unclear splits, source-only metrics, or comparator-only evidence.

If the field map has only one or two benchmarks for a broad field, stop and search again unless the task is genuinely narrow or the user explicitly scoped it that way.

## Phase 2: Select Benchmarks and Papers

Make a candidate table before adding evals:

| Benchmark | Dataset slug/id | Task | Metrics | Evidence surfaces | Candidate papers | Open/HF Evidence | Decision |
|---|---:|---|---|---|---:|---|

Prefer a top 10 benchmark list for broad tasks, but do not cap discovery at 10. For very active fields, keep a larger candidate list and rank into waves: `wave1 import`, `wave2 follow-up`, `defer/split protocol`, `reject`. Rank benchmarks by:

1. number of independent papers reporting the same metric/setup;
2. field importance and citation/repo signal;
3. current/recent use, including 2025/2026 papers;
4. presence in legacy PwC;
5. live task-page/trending/HF/GitHub signal;
6. whether the DB already has a dataset, task link, and metric wiring;
7. apples-to-apples clarity.

Reject or defer:

- one-paper benchmarks with no adoption;
- benchmarks missing from the DB until an `add-benchmark` worker creates and wires them;
- metrics not configured in the DB until an `add-benchmark` worker links them;
- mixed protocols that need a new split leaderboard;
- benchmark names that hide incompatible setups.

Create a paper worklist: one row per source paper, with arXiv ID or external source, year, evidence source(s), candidate benchmarks, introduced model variants, comparator papers it points to, and source-availability notes (`is_open` evidence, exact HF repos when known, or why no row-level HF link should be set). For broad fields, expect this list to be much larger than the final eval import count.

## Phase 3: Stocktake DB State

For chosen benchmarks and papers, query current state before launching workers:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_database_session

task_slug = "<task-slug>"
dataset_slugs = ["<benchmark-slug>"]
arxiv_ids = ["<arxiv-id>"]

db = next(get_database_session())
print("== benchmark wiring ==")
for slug in dataset_slugs:
    rows = db.execute(text("""
        SELECT d.id, d.name, d.slug, t.id AS task_id, t.slug AS task_slug,
               td.supports_harness,
               array_agg(DISTINCT m.name ORDER BY m.name) FILTER (WHERE m.name IS NOT NULL) AS metrics,
               count(DISTINCT e.id) AS eval_rows,
               count(DISTINCT e.paper_id) AS eval_papers
        FROM datasets d
        LEFT JOIN task_datasets td ON td.dataset_id = d.id
        LEFT JOIN tasks t ON t.id = td.task_id
        LEFT JOIN task_dataset_metrics tdm ON tdm.task_id = t.id AND tdm.dataset_id = d.id
        LEFT JOIN metrics m ON m.id = tdm.metric_id
        LEFT JOIN evaluations e ON e.task_id = t.id AND e.dataset_id = d.id
        WHERE d.slug = :slug
        GROUP BY d.id, d.name, d.slug, t.id, t.slug, td.supports_harness
        ORDER BY t.slug
    """), {"slug": slug}).mappings().all()
    print(slug, [dict(r) for r in rows] or "MISSING")

print("== papers ==")
for aid in arxiv_ids:
    row = db.execute(text("""
        SELECT id, arxiv_id, title, date_published, urls_extracted, github_urls, project_page_url
        FROM papers
        WHERE arxiv_id = :aid
        ORDER BY is_latest_version DESC NULLS LAST
        LIMIT 1
    """), {"aid": aid}).mappings().first()
    print(aid, dict(row) if row else "MISSING")
db.close()
PY
```

If a major benchmark is missing or lacks metric wiring, launch `add-benchmark` before any paper worker that depends on it. If a source paper is missing or lacks links/tags, use `enrich-paper` or `add-external-paper` as appropriate.

## Phase 3.5: Launch Add-Benchmark Workers

Use one worker subagent per missing or under-wired major benchmark. Give each worker:

- path to `.agents/skills/add-benchmark/SKILL.md`;
- target task slug/id;
- benchmark name, source paper/homepage, expected split/protocol;
- metric names and directions to wire;
- evidence that this is a major benchmark from the field map;
- instruction to set native local `datasets.paper_url` and source-paper task tags.

Prompt template:

```text
Repo: /root/python_projects/paperswithcode. You are not alone in the DB; other workers may add benchmarks/evals. Do not revert or delete unrelated work. Use the add-benchmark skill at .agents/skills/add-benchmark/SKILL.md.

Task: Add or repair benchmark <benchmark name> for task <task-slug>.

Evidence and source:
<benchmark source paper/homepage, candidate source paper id/arxiv/external URL, expected split/protocol, metrics>

Rules: use the benchmark's introducing/descriptive source paper, not a later result paper. Ensure datasets.paper_url is a native paperswithcode.co/paper/... URL. Link the benchmark to task <task-slug> and wire only the requested comparable metrics. Leave featured_rank NULL unless explicitly told otherwise.

Final report: dataset id/slug, task id, metrics linked, source paper id/url, any blockers.
```

After these workers finish, rerun the benchmark stocktake and update the paper worklist's in-scope leaderboards.

## Phase 4: Launch Add-Evals Workers

Use one worker subagent per paper. Give each worker:

- path to `.agents/skills/add-evals/SKILL.md`;
- source paper ID/arXiv/year/title;
- exact candidate benchmark list with dataset IDs, task IDs, metric names, and comparability notes;
- instruction to skip comparator/external eval rows;
- instruction to report added/updated/skipped rows with eval IDs.

Prompt template:

```text
Repo: /root/python_projects/paperswithcode. You are not alone in the DB; other workers may add evals for other papers. Do not revert or delete unrelated work. Use the add-evals skill at .agents/skills/add-evals/SKILL.md.

Task: For paper <arxiv_id/year/title>, add missing evaluation rows reported by this paper itself for task <task-slug>.

In-scope leaderboards:
<dataset id/name/slug, task id/slug, configured metrics, supports_harness, comparability contract>

Rules: do not add external comparator rows; do not add scores for metrics that are not configured; do not put a score on a benchmark if the split/protocol/setup is not apples-to-apples. Use paper/official README/model card as the source. Set is_open, num_parameters, hf_model_url, and harness per add-evals. Do not mark a row closed merely because the paper page lacks a linked HF model: inspect official GitHub/project links for public weights, reproducibility scripts, and HF repos that may be unindexed or missing model cards. Recalculate ranks for affected leaderboards if you write directly.

Final report: rows added/updated/skipped with eval IDs, benchmark, metric, score, model_name, and reasons for skips.
```

Track every worker result in a ledger:

- rows added and eval IDs;
- transient rows deleted by the worker;
- rows updated;
- benchmarks skipped and why;
- comparator/external rows deliberately skipped;
- source papers with no native scores after inspection;
- source-availability evidence used for each imported variant, including open GitHub-only rows where `hf_model_url` remains unset;
- suspected verifier risks.

## Phase 5: Launch Verify-Evals Workers

After add-evals workers finish, launch one verifier worker per changed benchmark, plus any high-risk existing benchmark. Use `.agents/skills/verify-evals/SKILL.md`.

Prompt template:

```text
Repo: /root/python_projects/paperswithcode. Use the verify-evals skill at .agents/skills/verify-evals/SKILL.md.

Audit benchmark leaderboard: <benchmark URL>. dataset_id=<id>, task_id=<id>, configured metrics=<metrics>, supports_harness=<bool>.

Leaderboard contract: <expected split/protocol/metric/setup>. New rows to especially verify: <eval IDs>. Also audit existing rows for duplicates and obvious apples-to-apples issues.

Do not add evals. Report exact row IDs to keep/fix/delete, evidence, and whether any open/hf_model_url/num_parameters metadata is wrong. When checking `is_open`, inspect official GitHub/project links as well as HF model links; a reproducible open GitHub release can justify `is_open = true` without `hf_model_url`. Mutate only if the correction is trivial and fully certain; otherwise report it.
```

Verifier findings override add-worker optimism. If a verifier finds wrong setup, mixed metric scale, streaming vs offline protocol, reference-guided vs blind setup, validation vs test split, or comparator rows, clean them up.

## Phase 6: Apply Cleanup Centrally

Apply fixes in one scoped transaction after all verifier reports:

- delete rows that belong to a different benchmark/protocol;
- update score/model/methodology when the row identity is correct but a comparable source cell should replace it;
- fix `is_open`, `hf_model_url`, `num_parameters`, or methodology metadata when evidence is clear;
- recalculate ranks for every affected `(task_id, dataset_id, metric)`.

Use `EvaluationService.recalculate_ranks` after direct SQL writes.

```bash
uv run --env-file backend/keys.env python - <<'PY'
from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService

db = next(get_database_session())
try:
    # apply scoped deletes/updates here
    db.commit()
    svc = EvaluationService(db)
    for task_id, dataset_id, metric in [
        # (task_id, dataset_id, "Metric")
    ]:
        print(task_id, dataset_id, metric, svc.recalculate_ranks(task_id, dataset_id, metric_name=metric))
finally:
    db.close()
PY
```

Run validation:

```bash
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py
```

If it reports unrelated pre-existing mismatches, say so. Do not hide them, and do not imply they came from this pass.

## Phase 7: Final Report

Report:

- benchmark/paper scope used, including how 2025/2026 coverage was handled;
- field map summary: major benchmark families, major papers, trend/GitHub/HF/legacy signals considered;
- candidate papers/benchmarks that were found but not imported and why;
- benchmark rows created or repaired by `add-benchmark`;
- net eval rows added after verification, grouped by benchmark;
- rows updated or deleted by verifier cleanup;
- source-availability corrections made by verifier cleanup, especially rows changed from closed to open because official GitHub code/weights/reproduction scripts or unindexed HF repos were found;
- benchmarks that passed verification;
- remaining follow-ups, especially missing benchmark/metric wiring or deliberately split protocols;
- validation status and any unrelated existing validator failures.

Use exact eval IDs when possible. Be clear about intermediate rows that were added then removed; only count verified rows as net additions.

## Practical Heuristics

- Prefer adding fewer, verified rows over importing many questionable rows.
- But do not confuse "verified fewer rows" with "researched a narrow slice." The research phase should be broad enough that a broad field produces a broad worklist, even if many items are deferred after verification.
- Treat legacy PwC, GitHub READMEs, Hugging Face cards, and comparison tables as leads, not authoritative proof.
- Recent papers often introduce new protocols. Do not force them onto older leaderboards when a new benchmark should exist.
- If a metric has incompatible scales across papers, remove or split the leaderboard rather than ranking it.
- If a model has reference-guided and no-reference variants, keep them on separate leaderboards or keep only the variant matching the page contract.
- Use subagents for bounded paper/benchmark work, but the main agent must reconcile results, enforce consistency, and prevent a narrow/easy subset from being reported as complete.
