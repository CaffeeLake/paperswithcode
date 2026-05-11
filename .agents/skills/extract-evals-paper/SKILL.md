---
name: extract-evals-paper
description: Run, debug, or extend the paperswithcode evaluation extraction pipeline that extracts leaderboard results from arXiv papers and adds datasets, metrics, leaderboards, and evaluations to the database. Use this whenever the user mentions extract_evaluation_results, parse.py, extracting evaluation results from a paper, adding paper evaluation results, resolving datasets from papers, Step 1-7 pipeline failures, cached evaluation outputs, or dataset enrichment for missing dataset metadata.
---

# Extract Evals From Paper

This skill helps coding agents operate the repo-specific `extract_evaluation_results/` pipeline. The pipeline converts an arXiv paper into structured leaderboard data, reconciles datasets and metrics with the database, and optionally writes new datasets, metrics, leaderboard triples, and evaluation rows.

## First Checks

Work from the repo root and use the project environment:

```bash
uv run --env-file backend/keys.env ...
```

Before running mutating steps, understand what the user wants:

- Use `--skip-addition` when the user wants extraction or inspection only. This skips dataset, metric, normalization, and evaluation database writes.
- Use `--skip-step-6` only for the legacy flag that now skips Step 7 evaluation insertion. The name is misleading.
- Use `--resume` when cached output exists and the user wants to continue after a failure.
- Warn before running the full pipeline if the user did not clearly ask to mutate the database.

Useful cache/output directory:

```text
backend/outputs/evaluation_results/{arxiv_id}/
```

Typical files include `markdown.md`, `step_1.json`, `step_2.json`, `step_3.json`, `step_4.json`, `step_5_metrics.json`, `step_6_normalized.json`, `step_7_aligned_results.json`, and `step_7_cli.json`.

## Main Pipeline

Prefer the orchestrator for normal use:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id <ARXIV_ID>
```

Common variants:

```bash
# Inspect extraction and dataset resolution without database additions.
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id <ARXIV_ID> --skip-addition

# Resume from cached step outputs.
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id <ARXIV_ID> --resume

# Run through normalization but skip evaluation insertion (legacy flag name).
uv run --env-file backend/keys.env extract_evaluation_results/parse.py --arxiv_id <ARXIV_ID> --skip-step-6
```

The orchestrator runs these steps:

1. `step_1.py`: Download the arXiv PDF, convert it to Markdown with Datalab, and extract leaderboard-table results plus dataset details. It should ignore ablations, appendix-only results, private/ad-hoc datasets, aggregate benchmark categories, ensembles, and results for models not introduced by the paper.
2. `step_2.py`: Resolve extracted datasets against the database using multiple search strategies. It must avoid duplicates, verify that task semantics match, and fetch task/metric context for found datasets.
3. `step_3.py`: For datasets not found in Step 2, gather web and Hugging Face metadata using Exa/HF MCP and select exactly one primary task ID.
4. `step_4.py`: Add newly discovered datasets only after duplicate checks. Datasets are not directly linked to tasks here; task/dataset/metric triples are created later.
5. `step_5.py`: Extract unique metric names, filter out dataset names accidentally extracted as metrics, add missing metrics with direction and scale.
6. `step_6.py`: Normalize dataset IDs, task IDs, metric names, and metric values using Step 2, Step 4, and Step 5 output. It filters unresolved entries and consolidates compatible metrics.
7. `step_7.py`: Add normalized evaluation rows, auto-create missing leaderboard triples, and skip duplicates for the same `(paper_id, task_id, dataset_id, model_name, best_metric)`.

## Verifying a Run

After a run, inspect the workflow summary and relevant output files. A successful full run usually shows:

- `Success: True`
- Step 1 extracted evaluation results and dataset details, or explicitly found none.
- Step 2 resolved some or all datasets.
- Step 5 mapped or added metrics.
- Step 6 reports mapped/unresolved counts.
- Step 7 reports evaluations added and duplicates skipped.

If the user asks for a concise status, report:

- arXiv ID
- whether the script succeeded
- number of evaluations extracted, normalized, added, and skipped as duplicates
- unresolved datasets or metrics
- cache/output path for review

If Step 7 reports skipped duplicates, that is expected when evaluations already exist.

## Debugging Failed Runs

Use cached step outputs to localize failures:

- Missing or empty `markdown.md`: Step 1 PDF download or Datalab conversion failed.
- Bad extraction in `step_1.json`: adjust extraction logic or rerun Step 1 after clearing only the affected cache file.
- Dataset false positive in `step_2.json`: check task semantics and split handling. Same dataset name can represent different tasks or splits.
- Missing dataset metadata in `step_3.json`: rerun Step 3 for that paper or gather the dataset manually.
- Unexpected dataset creation in `step_4.json`: check Step 2 and duplicate search before leaving the new row in place.
- Missing metrics in `step_5_metrics.json`: verify the metric is not actually a dataset name, then confirm direction and scale.
- Unresolved entries in `step_6_normalized.json`: inspect the `_reason` field. Usually this is dataset mapping, task selection, paper ID, or metric normalization.
- Failed `step_7_cli.json`: check duplicate detection, metric validity, and leaderboard triples.

Prefer rerunning the orchestrator with `--resume` after fixing transient issues. Run individual steps only when debugging a specific stage.

## Individual Step Commands

Use these when isolating a failure:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/step_1.py --arxiv_id <ARXIV_ID>
uv run --env-file backend/keys.env extract_evaluation_results/step_2.py --arxiv_id <ARXIV_ID>
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --arxiv_id <ARXIV_ID>
uv run --env-file backend/keys.env extract_evaluation_results/step_4.py --arxiv_id <ARXIV_ID>
uv run --env-file backend/keys.env extract_evaluation_results/step_5.py --arxiv_id <ARXIV_ID>
uv run --env-file backend/keys.env extract_evaluation_results/step_6.py --arxiv_id <ARXIV_ID>
uv run --env-file backend/keys.env extract_evaluation_results/step_7.py --arxiv_id <ARXIV_ID> --aligned_results_file backend/outputs/evaluation_results/<ARXIV_ID>/step_6_normalized.json
```

Step 3 also supports a targeted single-dataset investigation:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/step_3.py --dataset_details '{"dataset_name":"<NAME>","dataset_info":"<CONTEXT>","paper_arxiv_id":"<DATASET_PAPER_ARXIV_ID>"}'
```

## Data Quality Rules

Keep these rules in mind when reviewing outputs or changing prompts:

- Do not add duplicate datasets. Search by exact name, variants, introducing paper arXiv ID, and Hugging Face URL.
- Dataset name matching is not enough. The dataset must support the same task and, when split-specific rows exist, the same split.
- Do not add private, in-house, small ad-hoc, appendix-only, or aggregate-only evaluation sets.
- Prefer specific benchmark names over vague names like "overall", "combined", or "language benchmarks average".
- Do not add dataset names as metric names.
- Normalize object detection `AP` to `mAP` unless it is a specific variant such as `AP50`.
- For DocVQA, normalize `Accuracy`/`Acc` to `ANLS` when the leaderboard expects it.
- For coding benchmarks, normalize `Accuracy`/`Acc` to `pass@1` when appropriate.
- Strip confidence intervals from metric values before insertion.
- Normalize values to the metric scale stored in the database, for example percentage to `0-1` when required.
- Leaderboards are `(task, dataset, metric)` triples. Step 7 may create missing triples with `add_metric_to_leaderboard`.

## Dataset Enrichment

The enrichment sub-pipeline updates existing datasets that already have evaluations but are missing descriptions, paper URLs, or Hugging Face URLs. It is separate from adding new datasets from a paper.

Find missing metadata:

```bash
uv run --env-file backend/keys.env python extract_evaluation_results/enrich_datasets/find_datasets_missing_info.py
```

Dry-run enrichment first:

```bash
uv run --env-file backend/keys.env python extract_evaluation_results/enrich_datasets/enrich_datasets.py --limit 10
uv run --env-file backend/keys.env python extract_evaluation_results/enrich_datasets/enrich_datasets.py --dataset_ids 31 33 --batch-size 2
```

Apply only after reviewing the dry-run:

```bash
uv run --env-file backend/keys.env python extract_evaluation_results/enrich_datasets/enrich_datasets.py --limit 10 --batch-size 2 --apply
```

Memory guidance for the VPS:

- Use `--batch-size 1` on very constrained memory.
- Use `--batch-size 2-3` on the default 4GB VPS.
- Avoid large concurrent batches unless memory is known to be available.

## Reporting Back

When you finish, include the command you ran, the success/failure status, and the key counts. If any database write happened, mention what changed: datasets added or updated, metrics added, leaderboard triples created, evaluations added, and duplicates skipped. If you could not verify the result, say exactly which output file or database/API check is still needed.
