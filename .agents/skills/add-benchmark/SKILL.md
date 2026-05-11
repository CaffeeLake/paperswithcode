---
name: add-benchmark
description: Add or update benchmark datasets/leaderboards in the paperswithcode repo database. Use this whenever the user asks to add a benchmark, add a leaderboard, set default/featured benchmarks for a task, link benchmarks to tasks, add Accuracy or other metrics for a benchmark, or fix benchmark source links. This is repo-specific and should trigger even if the user only names benchmark titles and a task page.
---

# Add a benchmark

This skill adds benchmark metadata in the database so task pages and benchmark pages render correctly.

## Core rule

Benchmark source links must be native Papers with Code paper URLs:

```text
https://paperswithcode.co/paper/{arxiv_id}
```

Do not leave `datasets.paper_url` pointing to arXiv, OpenReview, a PDF, a project page, or a vendor blog when the benchmark has a source paper. First find or create the local `papers` row, set `datasets.introducing_paper_id`, then set `datasets.paper_url` to the native URL. If you cannot identify a source paper that can become a local paper page, stop and ask the user for the missing source details instead of inventing or storing an external source.

## Workflow

1. Identify the target task:
   - Prefer the URL slug the user gave, such as `/tasks/agents`.
   - Query `tasks` by `slug` and nearby names if needed.

2. Check whether each benchmark already exists:
   - Search `datasets` by exact name, slug, and fuzzy name variants.
   - Reuse an existing row when it clearly represents the requested benchmark/version.
   - Create a new `datasets` row only when no good match exists.

3. Normalize the source paper:
   - Resolve the source paper's arXiv ID from the user-provided source, benchmark homepage, or public paper page.
   - Find the local paper row in `papers` by `arxiv_id`.
   - If the paper is missing, index/import it using existing repo tooling before linking the dataset.
   - Update the dataset with:
     - `introducing_paper_id = papers.id`
     - `introducing_paper_title = papers.title`
     - `paper_url = 'https://paperswithcode.co/paper/' || papers.arxiv_id`

4. Link the benchmark to the task:
   - Ensure `(task_id, dataset_id)` exists in `task_datasets`.
   - If the user asked for default display order, set `featured_rank` in `task_datasets` and clear stale ranks for that task as appropriate.

5. Link metrics:
   - Use the requested metric, often `Accuracy`.
   - Ensure `(task_id, dataset_id, metric_id)` exists in `task_dataset_metrics`.
   - Do not duplicate metrics that are already present.

6. Verify:
   - Query the ranked task benchmarks from `task_datasets`.
   - Query the dataset rows and confirm `paper_url` starts with `https://paperswithcode.co/paper/`.
   - Hit the relevant API endpoint when the app is running, for example:

```bash
uv run --env-file backend/keys.env python - <<'PY'
import json
from urllib.request import urlopen

with urlopen("https://paperswithcode.co/api/v1/datasets/?task=agents&page_size=5&ordering=-paper_count") as resp:
    payload = json.load(resp)

for dataset in payload["results"]:
    print(dataset["featured_rank"], dataset["name"], dataset["paper_url"])
PY
```

## Database access

Run Python with the repo environment:

```bash
uv run --env-file backend/keys.env python ...
```

Use SQLAlchemy through `backend.database.connection.get_engine()` for idempotent updates. Prefer `INSERT ... ON CONFLICT DO NOTHING/UPDATE` for `task_datasets` and `task_dataset_metrics`.

## Reporting back

Report which benchmarks already existed, which were created, which metric was linked, and the final native source URL for each benchmark. If any source paper cannot be resolved to a native `paperswithcode.co/paper/{arxiv_id}` URL, clearly list what information is needed from the user.
