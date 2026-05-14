# Handoff — Group paper evaluations by task: alignment + model column next steps

## User goal

On the paper detail page (e.g. `https://paperswithcode.co/paper/83018`), the evaluation results section should group rows by task with a per-task heading (e.g. `IMAGE UNDERSTANDING`, `OCR`), and each task's table should:

1. **Visually align** with the other task tables. Right now, every task table sizes its columns independently, so the `Accuracy` column for `Image Understanding` doesn't sit at the same x-position as the `Score` column for `OCR`. The user wants consistent column alignment across all task groups.
2. **Show the model name** as a column in each row.
3. **Make the benchmark name clickable**, linking to the benchmark detail page (in addition to the existing `Compare →` link, or replacing it).

## What changed in this session

- [`frontend/src/views/PaperDetailView.tsx`](frontend/src/views/PaperDetailView.tsx)
  - Added an `evaluationsByTask` `useMemo` (around lines 76–101) that groups `evaluations` by `task_id`, capturing `task_name` / `task_slug` from the first row of each group, and sorts groups by `rows.length` desc so the biggest task surfaces first.
  - Replaced the single flat `<table className="results-table">` (which had `Task` as the first column repeated on every row) with one rendered block per task group (around lines 555–598): a `section-rule` heading containing the task name (linked to `/tasks/{slug}` when available) and `<N> result(s)` accent on the right, followed by a `results-table` with columns `Benchmark | Metric | Value | (Compare →)`.
  - Loading skeleton and empty-state ("No benchmark results recorded yet.") are unchanged.

- [`frontend/src/styles.css`](frontend/src/styles.css)
  - Added a hover rule:

    ```css
    .section-rule a:hover { color: var(--accent-text); text-decoration: underline; text-underline-offset: 3px; }
    ```

    so the task heading link lights up on hover while looking consistent with the minimal mono headings otherwise.

- Rebuilt the frontend bundle via `cd frontend && npm run build` because nginx serves the static `frontend/dist` directory; the dev server was not running.

## Verified behavior

- DOM snapshot of [`https://paperswithcode.co/paper/83018`](https://paperswithcode.co/paper/83018) after rebuild shows:
  - One `Image Understanding` heading link + 12 `Compare →` links in its table.
  - One `OCR` heading link + 1 `Compare →` link in its table.
  - Total of 13 rows split across 2 task-scoped tables, matching the API payload (12 evals under `task_id=8`, 1 under `task_id=4`).

- `npm run lint` is clean (only pre-existing warnings unrelated to this change).

## User feedback / open issues

1. **Column misalignment between task tables.**
   - Cause: each `<table className="results-table">` is an independent HTML table, so column widths auto-size to its own row contents. With one OCR row whose `Benchmark` is `OCRBench` and `Metric` is `SCORE` (short), the columns shrink and shift the `Value` column left compared to the Image Understanding table that has longer values.
   - Possible fixes (any of these works; choose based on visual goal):
     - Set `table-layout: fixed;` on `.results-table` and define fixed/percent widths per column (e.g. via a shared `<colgroup>` inserted into each table).
     - Or wrap all task groups in a single CSS grid (5-column grid spanning all groups) and render headings as row spanners — heavier change.
     - Cleanest minimal change: add a `<colgroup>` with the same fixed percent widths inside each per-task table in [`PaperDetailView.tsx`](frontend/src/views/PaperDetailView.tsx) and set `table-layout: fixed` on `.results-table` in [`styles.css`](frontend/src/styles.css). Suggested widths after adding the Model column: `Model 22% | Benchmark 22% | Metric 14% | Value 12% | Compare 30%` (tweak to taste).

2. **Add `Model` column + clickable `Benchmark`.**
   - The `Evaluation` interface in [`frontend/src/lib/api.ts`](frontend/src/lib/api.ts) (lines 170–198) already exposes `model_name`, `dataset_name`, and `dataset_slug`, so no API change is needed.
   - In the per-task `<tbody>` block in [`PaperDetailView.tsx`](frontend/src/views/PaperDetailView.tsx) (~lines 583–594), update:
     - Add a `Model` `<th>` and a `<td>` rendering `{e.model_name || "—"}`. Probably the leftmost data column.
     - Replace the plain `Benchmark` cell with a `<Link to={\`/benchmark/${e.dataset_slug}\`}>{e.dataset_name || "—"}</Link>` when `dataset_slug` exists.
   - Decide whether to keep the `Compare →` action column once the Benchmark name itself is a link. Suggested: keep `Compare →` for affordance (it visually mirrors the OCR/Image rows now); ask the user if they want it removed.
   - Update the `<thead>` to match: `Model | Benchmark | Metric | Value | (Compare)`. Keep `Metric` and `Value` as the right-aligned pair so existing styles still work.

3. **Rebuild reminder.** Any further change must end with `cd frontend && npm run build` (or run a Vite dev server) because production-pointing nginx serves the static `dist/` bundle. There is no auto-reload on this host.

## Suggested next steps (concrete)

1. In [`frontend/src/views/PaperDetailView.tsx`](frontend/src/views/PaperDetailView.tsx) inside each per-task table:
   - Add a shared `<colgroup>` with explicit column widths.
   - Add a `Model` `<th>` and corresponding `<td>{e.model_name || "—"}</td>`.
   - Wrap the `Benchmark` cell content in `<Link to={\`/benchmark/${e.dataset_slug}\`}>…</Link>` when `dataset_slug` exists; fall back to plain text otherwise.
2. In [`frontend/src/styles.css`](frontend/src/styles.css):
   - Add `table-layout: fixed;` to `.results-table`.
   - Optionally add `.results-table .model { color: var(--ink); font-family: var(--serif); }` if the Model cell needs distinct styling from the existing `.benchmark` class.
   - Optionally add `.results-table .benchmark a { color: inherit; }` plus `.results-table .benchmark a:hover { color: var(--accent-text); text-decoration: underline; text-underline-offset: 3px; }` so the linkified benchmark name styles match the surrounding row.
3. Rebuild: `cd frontend && npm run build`.
4. Re-verify on [`paper/83018`](https://paperswithcode.co/paper/83018):
   - Image Understanding (12 rows) and OCR (1 row) tables should have their `Model`, `Benchmark`, `Metric`, and `Value` columns at identical x-positions.
   - Each Benchmark cell should be a link, e.g. `HallusionBench → /benchmark/hallusionbench`.
5. Optional polish:
   - Decide whether to truncate long model names (e.g. `MiniCPM-V 4.6-Thinking (16x)`) with ellipsis at table-column width.
   - Decide whether to keep the `Compare →` column once Benchmark is clickable.

## Out of scope (do not touch)

- No backend / API changes are needed.
- [`frontend/src/components/paper-detail/EvaluationResultsCard.tsx`](frontend/src/components/paper-detail/EvaluationResultsCard.tsx) is still unused on this route and should stay untouched.
- The edit-evaluations dialog (`EditEvaluationsDialog.tsx`) is also untouched and should remain so.

## Suggested skills for next session

- None of the workspace skills strictly apply; this is a small frontend tweak. Use the standard edit + `npm run build` loop. Only re-invoke `handoff` if another mid-conversation handoff becomes necessary.

## Working tree notes

`git status --short` at handoff time contained many unrelated in-progress changes (auth work, methods linking, subtasks, thumbnail work). The only files touched by this session are:

```text
 M frontend/src/views/PaperDetailView.tsx
 M frontend/src/styles.css
 M frontend/dist/...               (rebuilt bundle)
```

Do not revert or commit the unrelated paths.
