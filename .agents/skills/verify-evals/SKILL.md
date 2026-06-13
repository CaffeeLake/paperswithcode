---
name: verify-evals
description: Audit and verify evaluation rows on a paperswithcode benchmark leaderboard for apples-to-apples comparability. Use this whenever the user asks to verify, audit, check, validate, or clean up evals on a benchmark page — e.g. "verify all evals on ScanNet", "are these leaderboard scores correct?", "check the benchmark page", "audit evals added with add-evals", or after bulk imports before trusting rankings. Also use proactively when reviewing a leaderboard that mixes splits, metrics, or evaluation setups. Cross-check each row against its cited paper, model card, or README using the hf-cli skill; compare against add-evals import rules to spot rows that should be deleted, corrected, or re-sourced.
---

# Verify Evaluations on a Benchmark

This skill audits **existing** evaluation rows on a configured benchmark leaderboard. It does not add new scores — use `add-evals` for that. The goal is to confirm every row on a benchmark page is **apples-to-apples**: the same metric, the same split, the same evaluation protocol, and a score faithful to the source paper or release.

Leaderboards rank models against each other. A row that uses validation AP50 next to hidden-test AP50, or a backbone ablation next to a full submission, misleads users even when the number itself is "correct" for some table in the paper.

## Related skills

| Skill | Role in verification |
|-------|----------------------|
| **`hf-cli`** | Read arXiv papers (`uv run hf papers read`), paper metadata, model cards (`uv run hf models card`), and model info JSON. Primary source for checking reported numbers. |
| **`add-evals`** | Defines how rows *should* have been imported — metric filter, split expectations, model naming, `methodology`, `is_open`, `num_parameters`. Verification is essentially running those rules in reverse on existing rows. |
| **`add-benchmark`** | Use only if the leaderboard itself is misconfigured (wrong metric linked, missing task association). Do not fix bad rows by changing the leaderboard definition during verification. |

## Pre-flight

Run from the repo root:

```bash
uv run --env-file backend/keys.env ...
```

Confirm the API is up (any dataset id works; 404 on missing id still means the server responded):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/datasets/276
```

Resolve the benchmark from the user URL or name. Example: `https://paperswithcode.co/benchmark/scannet?task=3d-instance-segmentation` → dataset slug `scannet`, task slug `3d-instance-segmentation`.

```python
from sqlalchemy import text
from backend.database.connection import get_engine

dataset_slug = "scannet"
task_slug = "3d-instance-segmentation"

with get_engine().connect() as conn:
    ds = conn.execute(text(
        "SELECT id, name, slug, introducing_paper_id, paper_url FROM datasets WHERE slug = :slug"
    ), {"slug": dataset_slug}).mappings().first()
    task = conn.execute(text(
        "SELECT id, name, slug FROM tasks WHERE slug = :slug"
    ), {"slug": task_slug}).mappings().first()
    metrics = conn.execute(text(
        "SELECT m.name, m.direction, td.supports_harness "
        "FROM task_dataset_metrics tdm "
        "JOIN metrics m ON m.id = tdm.metric_id "
        "JOIN task_datasets td ON td.task_id = tdm.task_id AND td.dataset_id = tdm.dataset_id "
        "WHERE tdm.task_id = :task_id AND tdm.dataset_id = :dataset_id"
    ), {"task_id": task.id, "dataset_id": ds.id}).mappings().all()
    print(dict(ds), dict(task), [dict(m) for m in metrics])
```

Record the **leaderboard contract** before reviewing rows:

- `dataset_id`, `task_id`
- Allowed metric name(s) — usually one primary metric (e.g. `AP50`)
- `supports_harness` — whether `evaluations.harness` should be populated
- Expected split and protocol for this benchmark (see Step 1 — do not assume hidden test without checking)

## Step 1: Define the apples-to-apples contract

Every row on a leaderboard must match the same contract. Infer it from the benchmark's official definition, existing rows, domain convention, and (for older CV/3D leaderboards) legacy PwC — then apply it uniformly.

### Split (most common failure mode)

Check whether the leaderboard is meant to compare:

| Split | Typical use |
|-------|-------------|
| **Hidden test** | Official benchmark server results (ScanNet, many vision leaderboards) |
| **Public validation** | Ablation tables, development comparisons, papers that never submit to the server |
| **Train / other** | Almost never belongs on a public SOTA leaderboard |

**Rule:** Do not mix splits on one ranked leaderboard. Every row must use the **same** split (and the same score from that split).

Read the paper table caption carefully: "validation set", "test set", "hidden test", "leaderboard submission", "we report on val in the main paper and test in the appendix".

#### Resolving the split when convention is unclear

Do **not** jump straight to "hidden test because ScanNet has a benchmark server." Many curated pages — including legacy PwC — used **validation** for most papers and test only for benchmark submissions.

1. **Official source** — benchmark homepage / server docs (e.g. `kaldir.vc.in.tum.de/scannet_benchmark/`) → hidden test is the server leaderboard.
2. **Existing rows** — tag each row's split from `methodology` and flag mixing before per-row source checks:

```python
# Quick split-mixing audit
for r in rows:
    m = (r["methodology"] or "").lower()
    split = "test" if "hidden test" in m or " test " in m else (
        "val" if "validation" in m or " val " in m else "unclear"
    )
    print(r["model_name"], r["metrics"], split)
```

3. **Legacy PwC score-matching** — stream `evaluation-tables.json` (never load the full file on the VPS; use `ijson`). Match each legacy score to known val/test cells in papers or READMEs to infer which split legacy used. Legacy rows carry **no split label** — only score equality proves it.

```python
import ijson, re
from pathlib import Path

path = Path("data/legacy_pwc_data/evaluation-tables.json")
with open(path, "rb") as f:
    for item in ijson.items(f, "item"):
        if item.get("task") != "<Task Name>":
            continue
        for ds in item.get("datasets", []):
            if "<dataset slug fragment>" not in ds.get("dataset", "").lower():
                continue
            for row in ds.get("sota", {}).get("rows", []):
                print(row.get("model_name"), row.get("metrics"), row.get("paper_url"))
```

Legacy PwC was **not** split-consistent (e.g. ScanNet Mask3D mixed val mAP with test AP50 in one row; ScanNet200 used validation for ODIN/ISBNet/MSTA3D but test mAP for Mask3D). Treat legacy as **historical evidence**, not a mandate to keep mixing.

4. **User choice** — when official docs, legacy, and current rows disagree, report the options with evidence and let the user pick the contract (e.g. "validation for all rows except Mask3D on hidden test"). Document the chosen contract in the audit report and apply it to every row.

**Exception rows:** a contract like "validation except paper X on test" is valid when mirroring legacy or when only one method has an official test submission. List exceptions explicitly; every other row must still match the dominant split.

### Metric

The stored `best_metric` and the sole key in `metrics` must match a metric linked in `task_dataset_metrics` for this `(task_id, dataset_id)`.

Also verify the **source table column** maps to that metric:

- `AP50` / `mAP@50` / `mAP 50` → usually `AP50` when that is the configured metric
- Do not accept component subscores (e.g. MME-P on an `Score`-only leaderboard)
- Do not accept a different quantity (F1 imported as Accuracy, percent OCRBench score without scale normalization)

Cross-check `add-evals` Step 5 — the same exclusion rules apply in reverse.

### Evaluation setup / input modality

Many benchmarks allow only one input representation. Examples:

- ScanNet instance segmentation: mesh-sampled point cloud on hidden test (standard); sensor RGB-D with feature transfer is a **different setup** even on the same split
- Image-text retrieval: I→T vs T→I are separate leaderboards — never mix directions

If setups differ, rows are not comparable even when metric and split match. Prefer **delete** over keeping a row with a long methodology disclaimer unless the user explicitly wants a mixed setup page.

### Model identity

The score must be for the model named in `evaluations.model_name`, using the setup that row claims:

- Primary method vs backbone-only ablation (e.g. `PTv3 + PointGroup` backbone table vs `Mask3D` end-to-end method)
- Correct variant (size, mode, decoder/head suffix when the score is for a downstream system)
- Not a comparator/baseline row unless the leaderboard intentionally tracks comparators (default: paper's **own** best eligible result only, per `add-evals`)

### Paper attachment

Each row's `paper_id` must be the paper that **introduced or released** the evaluated model, not a survey or unrelated technique paper. The score must appear in that paper (or its official README/model card linked from it).

## Step 2: Inventory all rows on the leaderboard

```python
from sqlalchemy import text
from backend.database.connection import get_engine

task_id = 327
dataset_id = 276

with get_engine().connect() as conn:
    rows = conn.execute(text("""
        SELECT e.id, e.model_name, e.best_metric, e.metrics, e.methodology,
               e.paper_id, e.harness, e.is_open, e.num_parameters,
               e.external_source_url, e.best_rank,
               p.arxiv_id, p.title, p.source
        FROM evaluations e
        JOIN papers p ON p.id = e.paper_id
        WHERE e.task_id = :task_id AND e.dataset_id = :dataset_id
        ORDER BY (e.metrics->>e.best_metric)::float DESC NULLS LAST, e.model_name
    """), {"task_id": task_id, "dataset_id": dataset_id}).mappings().all()
    for r in rows:
        print(r["id"], r["best_rank"], r["model_name"], r["metrics"], r["arxiv_id"])
```

Also fetch via API for rank sanity:

```bash
curl -s "http://localhost:8000/api/v1/evaluations/?dataset_id=<dataset_id>&task_id=<task_id>&page_size=100"
```

Flag duplicates on the unique key `(paper_id, task_id, dataset_id, model_name, harness, best_metric)`.

## Step 3: Verify each row against its source

For each row, trace: **stored value → cited source → table row/cell**.

Priority order for sources (same as `add-evals`):

1. **`external_source_url`** on the evaluation row, if set
2. arXiv paper via **`hf-cli`**
3. GitHub README (`gh api repos/<owner>/<repo>/readme …`)
4. HF model card (`uv run hf models card <repo_id> --text`)
5. Legacy corroboration: `data/legacy_pwc_data/evaluation-tables.json` via `ijson` streaming (see Step 1; helpful for split inference on older 3D/CV benchmarks; not authoritative alone)

**VPS / memory:** On the Hetzner VPS (~4GB RAM), never load `papers-with-abstracts.json` or full `evaluation-tables.json` into memory. Stream with `ijson`, fetch individual PDFs to `/tmp`, use `pdftotext` + `rg`. Prefer `gh api …/readme` and targeted SQL queries over bulk dumps.

### Reading papers with hf-cli

Always use the project venv:

```bash
mkdir -p /tmp/verify-<slug>
uv run hf papers read <arxiv_id> > /tmp/verify-<slug>/paper.md
uv run hf papers info <arxiv_id> > /tmp/verify-<slug>/paper-info.json
```

Search the paper for the model name, benchmark name, split, and metric:

```bash
rg -i "AP50|mAP.?50|test|validation|hidden|<model_name>|<benchmark>" /tmp/verify-<slug>/paper.md
```

For PDF-only tables that render poorly in markdown, fetch the PDF and extract text:

```bash
curl -sL "https://arxiv.org/pdf/<arxiv_id>.pdf" -o /tmp/verify-<slug>/paper.pdf
pdftotext /tmp/verify-<slug>/paper.pdf - | rg -i "Table|AP50|test|validation|<model>"
```

### Reading model cards

When the row traces to a HF release:

```bash
uv run hf models card <repo_id> --text > /tmp/verify-<slug>/card.md
uv run hf models info <repo_id> > /tmp/verify-<slug>/info.json
```

Confirm the card's eval table matches the row and that the linked `arxiv:` tag matches `paper_id`.

### What to record per row

| Check | Pass criteria |
|-------|---------------|
| **Score** | Stored value equals the source cell for the claimed setup (allow minor rounding, e.g. 71.2 vs 71.0 only if same split and you document rounding) |
| **Split** | Matches leaderboard contract (test vs val) |
| **Metric** | Source column is the configured leaderboard metric, not a alias or subscore |
| **Setup** | Input modality, framework/head, shot count, pretrain recipe match `model_name` + `methodology` |
| **Paper** | `paper_id` is the introducing/release paper for that model |
| **Provenance** | `methodology` accurately states split, table, and source surface; does not contradict the source |
| **`is_open`** | Consistent with evidence of public weights (see `add-evals`) |
| **`num_parameters`** | If set, matches source for that exact variant; if unset, source didn't state it — OK |
| **`harness`** | Null when `supports_harness=false`; populated only when the leaderboard supports it and the source names a runtime |

## Step 4: Classify issues

Use explicit verdicts:

| Verdict | Meaning | Typical action |
|---------|---------|----------------|
| **PASS** | Score, split, metric, setup, and paper all match the contract | Keep |
| **WRONG_SCORE** | Right row identity but incorrect number or typo | Fix via API PUT or delete + re-import with `add-evals` |
| **WRONG_SPLIT** | Score is from a different split than the leaderboard contract | **Update** to the correct split's score via PUT when that cell exists in the source; **delete** only when no comparable score exists for the contract split or the row should not be on this page |
| **WRONG_SETUP** | Different input modality, framework ablation, or non-comparable protocol | **Delete** unless user wants mixed page |
| **WRONG_METRIC** | Component/subscore or different quantity | **Delete** |
| **WRONG_PAPER** | Score belongs on a different paper row | Move scoped rows per `add-evals` misattribution workflow |
| **DUPLICATE** | Same unique key twice | Delete the duplicate |
| **UNVERifiable** | Source missing, table ambiguous, cannot confirm split | Report blocker; do not delete without user confirmation |

**Important:** An honest `methodology` field that says "validation" does not make a validation row OK on a test leaderboard — it confirms the row should be removed or relocated.

### Red flags from 3D instance segmentation audits (ScanNet / ScanNet200)

These patterns recur across benchmarks:

1. **Mixed splits on one page** — e.g. ScanNet200 with Volt/Mask3D on test and ODIN/OneFormer3D/PTv3/ISBNet on validation. Methodology may label the split correctly; the row is still **WRONG_SPLIT** until the whole page uses one contract.
2. **Same paper, two splits** — ODIN Table 1(c) validation AP50 45.3 vs Table 6 test AP50 39.4. Pick one split for the contract; do not rank both on the same leaderboard.
3. **Best-score import vs split contract** — `add-evals` may pick test when it is higher (Mask3D test 38.8 > val 37.0) or test when the paper headlines it (Volt test 47.5), even when other rows use validation. Verification must normalize all rows to the chosen contract.
4. **Backbone ablation rows** — e.g. `Point Transformer V3 + PointGroup + PPT` from a backbone comparison table, not the paper's primary instance method
5. **Legacy PwC imports** — legacy ScanNet200 stored validation for most papers but test mAP for Mask3D; legacy also mixed metrics across splits on ScanNet(v2). Re-verify every score against the paper; use legacy only to infer split policy.
6. **Comparator tables in newer papers** — Volt/Mask3D papers list SPFormer AP50 as a baseline; verify the score belongs to the paper attached to the row
7. **Scale mismatches** — OCRBench `Score` stored as percent instead of native 0–1000 scale (see `add-evals` normalization rules)

**Worked fix (ScanNet200, contract: validation except Mask3D on test):** Volt WRONG_SPLIT — stored 47.5 (test), validation cell is 48.4 (Table 3). PUT `metrics` + `methodology`; other rows already matched or were already validation; Mask3D 38.8 test unchanged.

## Step 5: Run automated checks

```bash
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py
```

This catches metric label mismatches (`best_metric` vs allowed leaderboard metrics). It will not catch wrong splits or setup mixing — that remains manual/source-driven in this skill.

Optionally check rank order matches stored scores for the configured metric direction.

## Step 6: Remediate

Get user confirmation before bulk deletes unless they already asked to "clean up" or "delete wrong rows".

### Delete a row

```bash
source backend/keys.env
curl -s -o /dev/null -w "%{http_code}\n" \
  -X DELETE "http://localhost:8000/api/v1/evaluations/<id>" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN"
```

Ranks recalculate automatically.

### Fix a score or metadata

Prefer delete + `add-evals` re-import when multiple fields are wrong. For a **WRONG_SPLIT** where the correct split's score exists in the source, PUT the row (score + methodology) rather than delete — same `paper_id` / `model_name`, different table cell.

```bash
source backend/keys.env
curl -s -X PUT "http://localhost:8000/api/v1/evaluations/<id>" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{
    "metrics": {"AP50": "<correct_value>"},
    "best_metric": "AP50",
    "methodology": "<split, table, source surface — must match the new score>"
  }'
```

Ranks recalculate automatically. For a single numeric typo with correct split/setup, PUT is enough. Delete when the row should not exist on this leaderboard at all.

### Do not fix during verification

- Do not add new metrics or task-dataset links (`add-benchmark`)
- Do not bulk-import replacement rows unless the user asks — **report first**, then remediate when the user confirms the contract or asks to fix/clean up

## Reporting back

Structure the audit report like this:

### Leaderboard contract

- Benchmark URL, `dataset_id`, `task_id`, configured metric(s), expected split/setup

### Summary

- Total rows, PASS count, issues by verdict

### Row-by-row table

For each evaluation: id, rank, model, stored score, verdict, one-line evidence (source table + split)

### Recommended actions

- Rows to delete (with reason)
- Rows to fix (with correct value and source)
- Rows to re-source (wrong paper)
- Metadata gaps (dataset description, missing introducing paper, etc.)

### Skipped / inconclusive

- Rows that could not be verified and what evidence is missing

End with the benchmark URL, e.g. `https://paperswithcode.co/benchmark/scannet?task=3d-instance-segmentation`.

## Quick verification checklist

Copy and use per row:

```
[ ] metric matches task_dataset_metrics for this leaderboard
[ ] split matches leaderboard contract (test vs val)
[ ] setup matches other rows (input, framework, shots)
[ ] score matches source table cell for this model+setup
[ ] paper_id is the releasing paper for this model
[ ] methodology accurately describes split/table/source
[ ] is_open / num_parameters / harness consistent with add-evals rules
[ ] not a duplicate unique key
```

## When NOT to use this skill

- **Adding** new evaluation rows → `add-evals`
- **Creating** benchmarks or wiring metrics → `add-benchmark`
- **Bulk extracting** evals from a paper via the automated pipeline → `extract-evals-paper`
- **Moving paper lineage** → `link-paper-lineage`

## Quick reference

```bash
# Leaderboard metrics
curl -s "http://localhost:8000/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics"

# All evals on a leaderboard
curl -s "http://localhost:8000/api/v1/evaluations/?dataset_id={dataset_id}&task_id={task_id}&page_size=100"

# Read paper
uv run hf papers read <arxiv_id>

# Read model card
uv run hf models card <repo_id> --text

# Validate metric wiring
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py

# Fix split/score on existing row
curl -X PUT "http://localhost:8000/api/v1/evaluations/{id}" \
  -H "Content-Type: application/json" -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{"metrics": {"AP50": "48.4"}, "best_metric": "AP50", "methodology": "..."}'

# Delete bad row
curl -X DELETE "http://localhost:8000/api/v1/evaluations/{id}" -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN"
```
