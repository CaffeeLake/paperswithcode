---
name: add-evals
description: Add evaluation results to the paperswithcode database from any source — Hugging Face model cards, arXiv/HF/PapersWithCode paper text, or GitHub repository READMEs — restricted to benchmarks that already exist with a task association and leaderboard metric. Use this whenever the user shares a Hugging Face model URL or repo id, an arXiv id / HF paper / PapersWithCode paper, a GitHub repository URL, or a model release page and asks to add evaluation results, benchmark scores, or leaderboard entries — even when phrased casually like "add scores from this model", "import benchmarks from <hf url>", "ingest the eval table from this paper into the DB", "grab the benchmarks from this repo's README", or "add evaluations for this release". This is the repo-specific workflow that uses `uv run hf`, `curl` against Hugging Face model search, `gh`, and the local backend API; trigger it instead of generic ingestion guidance whenever the user is trying to populate evaluation results from a model, paper, or repository source.
---

# Add Evaluations

This skill imports evaluation results into the paperswithcode database from any of the common sources that ship benchmark tables: Hugging Face model cards, the paper a model is linked to (arXiv or HF), and the GitHub repository associated with the model or paper. It is intentionally conservative: it only writes evaluation rows for benchmarks that already exist in the database with a task association and a configured leaderboard metric. It never invents new datasets, tasks, or metrics during the import.

## Why this exists

Model releases (especially flagship LLMs / VLMs / OCR models) advertise benchmark numbers across several surfaces — the HF model card, the technical report or arXiv paper, and the GitHub README. Any of them can be the only source where a particular table appears, so the import workflow has to be source-agnostic but consistent. The natural workflow is:

- Reuse existing benchmark datasets in the DB by matching names from the source.
- Skip source benchmarks that are not yet in the DB (curate those separately later, not as a side effect).
- Add evaluation rows for the model only on benchmarks that are fully wired up (dataset linked to a task with at least one leaderboard metric).
- Keep imports idempotent and easy to re-run.

This avoids polluting the schema with half-configured benchmarks, false-positive name matches, or duplicate evaluation rows.

## Pre-flight

Always run from the repo root using the project environment:

```bash
uv run --env-file backend/keys.env ...
```

Confirm the backend is reachable and the admin token is set:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/datasets/1
grep -E '^PWC_ADMIN_API_TOKEN=' backend/keys.env | head -1 | sed 's/=.*/=<redacted>/'
```

If the server is not running, start it (or restart it without asking confirmation per AGENTS.md).

## Workflow

### 1. Identify and fetch the evaluation source

Different starting points should converge on the same triple — a model identity, an evaluation table, and a paper row to attach it to. Pick the first source below that the user actually gave you, and then follow the fallback chain until you have an evaluation table:

1. **HF model repo / card** — fetch the card and inspect the metadata. Always invoke `hf` via `uv run` so the venv-installed CLI is used:

   ```bash
   mkdir -p /tmp/<repo_slug>
   uv run hf models card <repo_id> --text > /tmp/<repo_slug>/card.md
   uv run hf models info <repo_id> > /tmp/<repo_slug>/info.json
   ```

   The model card is the primary surface. If it has evaluation tables, that is your source. If it does not, read the `info.json` metadata: the card's `arxiv` tag (e.g. `arxiv:2401.12345`) or `papers` field points at a linked paper, and the card body or repo description often contains a GitHub URL. Fall through to step 2 / 3 with those identifiers.

2. **Paper (arXiv, HF, or PapersWithCode paper with an arXiv ID)** — when the source is a paper directly, or the model card was missing evals, read the paper as markdown and inspect linked artifacts:

   ```bash
   uv run hf papers read <arxiv_id> > /tmp/<paper_slug>/paper.md
   uv run hf papers info <arxiv_id> > /tmp/<paper_slug>/paper-info.json
   ```

   Extract evaluation tables from the paper body first. If the paper itself has no usable table, look for official artifacts linked from the paper text and metadata.

   For papers with an arXiv ID, also look for HF models tagged with that paper. The current `uv run hf papers info <arxiv_id>` output does not reliably expose linked models, so use the Hugging Face model search page directly:

   ```bash
   curl -L "https://huggingface.co/models?other=arxiv:<arxiv_id>" > /tmp/<paper_slug>/hf-models.html
   ```

   Treat matching HF model cards as candidate sources only. A model can appear in this search simply because its README/model card mentions the arXiv ID, not because the paper introduced that model. Before parsing evals from any discovered model card, be 100% sure the model was introduced by the paper itself: the model card should clearly present the paper as the model's own technical report/release paper, share the same authors/organization/release context, and not merely cite the paper as related work, a base model, a benchmark source, or background. If this is not certain, do not use that model card as a source; ask the user or skip it.

   For each confirmed introduced model, fetch the model card and metadata as in step 1 and use its evaluation tables as candidate source rows. If the paper has no usable table but lists a GitHub repo, fall through to step 3.

3. **GitHub repository** — when the model card or paper points to a GitHub repo, or the user provided one directly, fetch the README via the `gh` CLI and use it as the source:

   ```bash
   gh repo view <owner>/<repo> --json description,url,homepageUrl > /tmp/<repo_slug>/repo.json
   gh api repos/<owner>/<repo>/readme -H "Accept: application/vnd.github.raw" > /tmp/<repo_slug>/README.md
   ```

   Repo READMEs often contain the most complete benchmark tables for new releases (especially for OCR/VLM models). Treat README tables exactly like card tables for the rest of the workflow.

You can combine sources when each one carries part of the picture (e.g. the card has the "main" table, the paper has an ablation, the README has the final leaderboard). Track per-row context — which source the score came from, model variant / mode / shot count / metric label / harness notes — so methodology lines you write later are accurate and traceable.

Do not extract Elo scores. Cards, papers, and READMEs increasingly include LLM-judged Elo rankings (e.g. Gemini-judged Elo over olmOCR-Bench / OmniDocBench / XDocParse / OCRArena). These are pairwise-comparison rankings, not the benchmark's native metric, and they are tied to the specific judge model and pool of comparators used at the time of publication. They do not map to any leaderboard metric in this database and they are not comparable across sources, so skip every Elo table outright and only ingest the underlying native-metric tables (Accuracy, Edit Distance, ANLS, Pass@1, Score, etc.). Mention the skipped Elo table in the final report so the user knows it was intentional.

Do not decide harness handling from benchmark names alone. The database marks each task-dataset leaderboard with `task_datasets.supports_harness`. Only populate `evaluations.harness` when the selected leaderboard has `supports_harness = TRUE`. For Terminal Bench 2.0 and SWE-Bench Verified, preserve named runtime/framework values such as `Terminus-2` when the flag is enabled. For non-supporting leaderboards, put runtime/framework/tool details in `methodology`, or use a concise `model_name` suffix for clearly distinct non-harness setups such as `(w/ tools)`, `(Agent Swarm)`, or `(w/ python)`.

### 2. Confirm import scope with the user

Sources typically contain several model variants and many comparator models. By default, import only the best target model configuration from the source, not every mode, size, compression setting, or comparator. This keeps benchmark pages focused on the strongest reported result for the source rather than filling them with ablation rows. Before importing anything, agree with the user on:

- Which model rows to ingest. Sensible defaults:
  - For multi-mode releases (e.g. Non-Think / High / Max / Thinking), import only the strongest/top-tier mode unless the user explicitly asks for all modes.
  - For multi-compression, decoding, or runtime settings, import only the source's best-performing target setting unless the user explicitly asks for the variants. If scores vary by benchmark and there is no single declared best setting, choose the setting that is presented as the main/default flagship result; ask once if that is ambiguous.
  - For multi-size product lines (e.g. Flash / Pro), import only the best overall target model by default. Include multiple sizes only when the user asks for family coverage or the source clearly treats them as separate released models worth comparing.
  - For frontier-comparison tables, exclude rows for non-target comparator models (Opus, GPT, Gemini, K2, GLM, etc.) unless the target model is one of them.
  - For base-model tables, exclude unless explicitly requested.
- Which benchmark tables to consider (base model, instruct, frontier comparison, modes-comparison) and which surface they come from (card / paper / README).

Ask the user once if anything is ambiguous; otherwise proceed with the defaults above and report exactly what was included and excluded at the end.

### 3. Resolve the source paper

Every evaluation row attaches to a `papers` row, regardless of which surface the numbers came from. Find or import the right source row before posting evaluations. Two common cases:

- ArXiv-backed: locate the paper row by `arxiv_id`. The release is usually already imported.
- External tech report / model release (HF model card, HF PDF, blog, vendor page, GitHub release page): the row often already exists with `source = 'external'` and the report URL as `source_url`.

**Always check HF model metadata `arxiv:` tags before falling back to an external row.** When the source is a HF model card (or a paper/README linked to a HF model), `uv run hf models info <repo_id>` returns a `tags` list that includes entries like `arxiv:2410.00037`. Each tag is the model's own declared canonical paper. Follow this resolution order:

1. Look up every `arxiv:` tag in the local `papers` table by `arxiv_id` (filtering on `is_latest_version`). If exactly one tag resolves to a local paper, use that paper as the source row and append the HF model URL (`https://huggingface.co/<repo_id>`) to its `hf_models` array for traceability. This is the common case — most flagship model cards list a single canonical paper — and it should be preferred over creating a new external row.
2. If multiple `arxiv:` tags resolve to local papers (ambiguous, e.g. a finetune that tags both its own paper and the base-model paper), pick the one the model card / README clearly identifies as the technical report for this release. If you cannot tell, stop and ask the user; do not guess.
3. If no `arxiv:` tag resolves to a local paper (none present, or all tags are unimported), fall back to the external-row path below. An ArXiv tag pointing at a paper we do not have is not, on its own, a reason to import a new ArXiv row in this skill — defer to the standard ingestion tooling and use an external row in the meantime if needed.

Use an ArXiv row only when it is actually the source for the evaluated model and scores. Do not attach a model-card / README evaluation table to a related technique paper just because the source cites it. If the source is the primary surface for an unreleased or not-yet-paper-backed model, create or reuse an external paper row for the release title and canonical URL (HF model page, GitHub repo, or blog) instead.

Always populate `papers.date_published` for the source row. Scatter plots use this date to place benchmark progress over time, so do not leave external source rows undated. For ArXiv rows, use the paper's publication date. For external reports/blogs/model cards/README releases, use the source publication date from the page metadata, visible page date, release notes, or trusted source metadata; if you cannot determine it confidently, stop and ask the user instead of importing undated evaluations.

Look up the paper id with a read-only query, e.g.:

```python
from sqlalchemy import text
from backend.database.connection import get_engine
with get_engine().connect() as conn:
    rows = conn.execute(text(
        "SELECT id, arxiv_id, source, source_url, title FROM papers "
        "WHERE arxiv_id = ANY(:arxiv_ids) OR title ILIKE :t "
        "ORDER BY date_published DESC NULLS LAST LIMIT 5"
    ), {
        "arxiv_ids": ["<arxiv id from HF tags>", "..."],
        "t": "%<model family>%",
    }).fetchall()
    for r in rows:
        print(dict(r._mapping))
```

If no paper row exists, stop and ask the user how to proceed (import via the standard tooling, create/import an external source row, or use a related paper). Do not invent a paper. If the user chooses an external source row, create it with `source = 'external'`, `source_url`, title/abstract when available, any relevant HF/GitHub artifact links, and `date_published`. Store HF artifacts as absolute URLs in `hf_models`, `hf_datasets`, and `hf_spaces` (for example, `https://huggingface.co/org/model`), not bare repo ids, because the frontend uses these fields directly as links.

### 4. Inventory existing benchmarks

For each benchmark name from the source, check the DB for an existing dataset, an existing task association, and existing leaderboard metrics. Use a single read-only query:

```python
from sqlalchemy import text
from backend.database.connection import get_engine

source_benchmarks = ["MMLU-Pro", "GPQA Diamond", "HLE", ...]  # exact labels from the source

with get_engine().connect() as conn:
    for name in source_benchmarks:
        pattern = "%" + name.replace("-", "%").replace(" ", "%") + "%"
        slug    = "%" + name.lower().replace(" ", "-").replace("_", "-") + "%"
        rows = conn.execute(text(
            "SELECT d.id, d.name, d.slug, "
            "       array_agg(t.name ORDER BY t.name) FILTER (WHERE t.id IS NOT NULL) AS tasks, "
            "       bool_or(COALESCE(td.supports_harness, FALSE)) AS any_supports_harness "
            "FROM datasets d "
            "LEFT JOIN task_datasets td ON td.dataset_id = d.id "
            "LEFT JOIN tasks t ON t.id = td.task_id "
            "WHERE d.name ILIKE :exact OR d.name ILIKE :pattern OR d.slug ILIKE :slug "
            "GROUP BY d.id, d.name, d.slug ORDER BY d.name LIMIT 5"
        ), {"exact": name, "pattern": pattern, "slug": slug}).fetchall()
        print(name, "=>", [dict(r._mapping) for r in rows] or "MISSING")
```

Then for each in-scope dataset id, list the leaderboard metrics that already exist:

```python
rows = conn.execute(text(
    "SELECT t.id AS task_id, t.name AS task_name, "
    "       td.supports_harness, m.name AS metric_name, m.direction "
    "FROM task_dataset_metrics tdm "
    "JOIN tasks t ON t.id = tdm.task_id "
    "JOIN task_datasets td ON td.task_id = tdm.task_id AND td.dataset_id = tdm.dataset_id "
    "JOIN metrics m ON m.id = tdm.metric_id "
    "WHERE tdm.dataset_id = :id"
), {"id": dataset_id}).fetchall()
```

Or via the API: `GET /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics`.

### 5. Apply the import filter

Apply the exclusion rules in this order:

1. Drop any benchmark with no matching dataset row in the DB.
2. Drop any matched benchmark with no task association.
3. Drop any matched benchmark whose required metric is not already in `task_dataset_metrics`.
4. For each remaining benchmark, pick a `best_metric` that is already linked to that leaderboard. Prefer the source's metric label (`Pass@1`, `Accuracy`, etc.) when it is already linked; otherwise fall back to the canonical metric the leaderboard uses (most often `Accuracy`).
5. Record `supports_harness` for the exact selected `(task_id, dataset_id)` row. This flag decides whether the API payload may include `harness`.

Keep an explicit "skipped" list of names + reasons to report at the end. Do not change task associations or leaderboard metrics in this pass; if the user explicitly wants to add tasks or metrics, defer to the `add-benchmark` skill instead.

### 6. Optional: minimal benchmark metadata enrichment

For matched benchmarks, normalize `paper_url` to the native `https://paperswithcode.co/paper/{arxiv_id}` form whenever a local paper row exists for the benchmark's introducing paper. Do this through the dataset PUT endpoint:

```bash
curl -s -X PUT "http://localhost:8000/api/v1/datasets/<id>" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"paper_url": "https://paperswithcode.co/paper/<arxiv_id>"}'
```

The `DatasetUpdateRequest` does not expose `introducing_paper_id` / `introducing_paper_title`. If the benchmark is missing those fields and you can confidently identify the source paper row, set them with a single direct SQL update — that is the only acceptable direct-DB write in this skill, and it is consistent with the `add-benchmark` skill:

```python
with get_engine().begin() as conn:
    conn.execute(text(
        "UPDATE datasets SET introducing_paper_id = :pid, "
        "introducing_paper_title = :title, "
        "introduced_year = COALESCE(introduced_year, :year) "
        "WHERE id = :did"
    ), {"pid": paper_id, "title": paper_title, "year": year, "did": dataset_id})
```

If the source paper cannot be confidently identified, leave the dataset alone and report it as a metadata gap.

### 7. Post evaluations via the API

Use `POST /api/v1/evaluations/` with `X-Admin-Token`. Build one row per (selected best target model configuration × benchmark). Include `harness` only when the selected leaderboard's `supports_harness` flag is true. The unique key is `(paper_id, task_id, dataset_id, model_name, harness, best_metric)`, so:

- Distinguish variants from the same release with `model_name`, e.g. `DeepSeek-V4-Pro Max` vs `DeepSeek-V4-Flash Max`. Do NOT bake harness names, parameter counts, or modes into `model_name` — keep `model_name` clean (e.g. `GLM-5.1`, not `GLM-5.1 (Terminus-2)` or `GLM-4.5 (355B)`).
- Since the default import scope is the best target model only, model-name suffixes for ablations like `(4x)`, `(16x)`, `(Non-Think)`, or `(w/ tools)` should appear only when the user explicitly requested those variants or when they are needed to identify the single selected best setup.
- Set `harness` only for leaderboards where `supports_harness = TRUE` and the source attributes the score to a specific runtime (`Terminus`, `Terminus-2`, etc.). If a harness-supporting row clearly requires a runtime but the source omits it, use `harness = "unknown"` and mention the missing attribution in the final report.
- Leave `harness` unset (null) on every leaderboard where `supports_harness = FALSE`, even when the setup is agentic or tool-augmented. Capture those details in `methodology`, or in a concise `model_name` suffix only when the setup represents a distinct non-harness condition.
- Two harness variants of the same model on a harness-supporting leaderboard (e.g. `GLM-5.1` with `Claude Code` and `GLM-5.1` with `Terminus-2`) become two separate rows that differ only in `harness`. They are not duplicates.
- Distinguish setups on the same benchmark that are NOT about harness (e.g. `HLE` vs `HLE w/ tools`) via a `model_name` suffix like `(w/ tools)` plus a clear `methodology` description, since the metric is shared. Only do this if the metric/methodology can clearly distinguish the rows — otherwise skip and report.
- Always include `methodology` summarizing the source's note for that row (shot count, metric label, mode, harness version, source surface — card/paper/README — etc.) so the row is traceable back to where the number came from.

Skeleton:

```python
import json, os, urllib.request, urllib.error
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
BASE = "http://localhost:8000/api/v1"

def post_eval(
    paper_id, task_id, dataset_id, model_name, metric, score, methodology,
    harness=None,
):
    body = {
        "paper_id": paper_id,
        "task_id": task_id,
        "dataset_id": dataset_id,
        "model_name": model_name,
        "methodology": methodology,
        "metrics": {metric: f"{score}"},
        "best_metric": metric,
    }
    if harness:
        body["harness"] = harness
    req = urllib.request.Request(
        f"{BASE}/evaluations/",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Admin-Token": ADMIN_TOKEN},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
```

Common error responses:

- `400 Failed to create evaluation: No leaderboard defined ...` — the dataset has no metric linked for that task. The benchmark should have been filtered out in step 5; recheck the inventory.
- `400 Metric '<X>' is not allowed ...` — pick a `best_metric` already in the leaderboard's allowed list, often `Accuracy`.
- `401 Unauthorized` — `X-Admin-Token` is missing or wrong; reload `backend/keys.env`.

### 8. Validate and verify

Run the standard validation script (it is a dry-run by default, pass `--fix` only if you really want to mutate):

```bash
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py
```

Then verify the imported rows:

```bash
curl -s "http://localhost:8000/api/v1/evaluations/?paper_id=<paper_id>&page_size=200" \
  | uv run python -c "import json,sys; d=json.load(sys.stdin); print(d['count']); [print(e['model_name'], '/', e.get('harness') or '-', e['dataset_name'], e['best_metric'], e['metrics'].get(e['best_metric']), 'rank=', e.get('best_rank')) for e in d['results']]"
```

And confirm there are no duplicate `(paper_id, task_id, dataset_id, model_name, harness, best_metric)` rows for the imported paper.

## Reporting back

End by giving the user a concise report:

- The PapersWithCode paper URL for the source row, as the final line of the response. Use `https://paperswithcode.co/paper/{arxiv_id}` for ArXiv rows and `https://paperswithcode.co/paper/{paper_id}` for external rows without an ArXiv ID. Do not use the HF repo id, GitHub URL, or `source_url` path as the local paper route, because repo ids such as `Hcompany/Holo2-235B-A22B` contain slashes and do not resolve as paper identifiers.
- Which source(s) the evaluation table actually came from — model card, paper body, GitHub README, or a combination — so the user can audit the provenance quickly.
- Which model variants were imported and how many rows were posted per variant. For harness-supporting leaderboards, list each `(model, harness)` combination explicitly.
- The list of in-scope benchmarks, with `dataset_id`, `task`, `best_metric`, and `supports_harness`.
- The list of skipped benchmarks with the reason for each (no DB match / no task / no metric / missing source paper / could not distinguish setup).
- Any benchmark metadata gaps left for follow-up (e.g. missing `introducing_paper_id`, no arXiv source paper, missing source publication date, missing harness attribution for a harness-supporting leaderboard).
- Any harness details from the source that were downgraded into `methodology` or `model_name` because `supports_harness = FALSE`.

## When NOT to use this skill

- The user wants to add a brand-new benchmark to the database, link it to a task, or set leaderboard metrics. Use `add-benchmark` for that.
- The user wants to extract evaluation tables from an arXiv paper through the cached extraction pipeline (parse.py / Step 1–7), rather than ingesting a handful of rows from a known source. Use `extract-evals-paper` for that automated pipeline; this skill is for the manual / source-driven path.
- The user only wants the model card / README / paper summarized, with no intent to populate evaluation rows. Hand off to general tooling instead.

## Quick reference

- Source fetch:
  - Card: `uv run hf models card <repo_id> --text`
  - Model metadata (incl. arXiv tag, linked papers): `uv run hf models info <repo_id>`
  - Paper text: `uv run hf papers read <arxiv_id>`
  - Paper metadata (incl. GitHub repo link): `uv run hf papers info <arxiv_id>`
  - HF models tagged with a paper: `curl -L "https://huggingface.co/models?other=arxiv:<arxiv_id>"` (candidate sources only; verify the paper introduced the model)
  - GitHub README: `gh api repos/<owner>/<repo>/readme -H "Accept: application/vnd.github.raw"`
- API base: `http://localhost:8000/api/v1/`.
- Admin token: `PWC_ADMIN_API_TOKEN` in `backend/keys.env`, header `X-Admin-Token`.
- Endpoints used: `PUT /datasets/{id}`, `GET /datasets/{id}/tasks/{task_id}/metrics`, `POST /evaluations/`, `GET /evaluations/?paper_id=...`.
- Uniqueness for evaluations: `(paper_id, task_id, dataset_id, model_name, harness, best_metric)`.
- Source rows must have `papers.date_published` populated from the source publication date so benchmark scatter plots can place results over time.
- Harness column: optional `evaluations.harness` (VARCHAR(255)) — populate it only when the selected `(task_id, dataset_id)` row has `task_datasets.supports_harness = TRUE`; use the named runtime verbatim (for example `Terminus-2`) or `unknown` only when the harness-supporting leaderboard requires a runtime but the source omits it. Leave null for non-supporting leaderboards and report any downgraded harness-like details.
- Native benchmark source URL form: `https://paperswithcode.co/paper/{arxiv_id}`.
