# Legacy PwC Evaluation Expansion Plan

## Goal

Systematically backfill evaluation rows from legacy PapersWithCode leaderboards into the current database — without loading multi‑GB JSON dumps into RAM on the VPS.

The plan covers:

1. **Gap discovery** from legacy SOTA tables (OOM-safe streaming)
2. **Tiered work queues** (add-evals only → import paper → add-benchmark → unmapped)
3. **Metric compatibility gates** before posting rows
4. **Phased batches** with verification after each batch
5. **Refresh cadence** so the queue stays accurate as we import

Use the `add-benchmark` and `add-evals` skills when executing. Benchmark source papers must use native URLs (`https://paperswithcode.co/paper/{arxiv_id}` or `/paper/{id}` for external rows), not raw arXiv links.

---

## Current State (as of 2026-06-22)

Source: `data/legacy_top_ranked_missing_evals.csv` (top **3 ranks** per legacy leaderboard, streamed from `data/legacy_pwc_data/evaluation-tables.json` via `ijson`).

| Status | Rows | Meaning |
|--------|-----:|---------|
| **eval_missing** | 180 | Paper + `(task, dataset)` benchmark exist; no eval row yet |
| **paper_missing** | 202 | Benchmark wired; arXiv paper not indexed |
| **benchmark_missing** | 401 | Dataset exists but not linked to the matched task |
| **unmapped_leaderboard** | 19,087 | No task/dataset match in DB |
| **Total gap rows** | 19,870 | |

After live DB cross-check via `list_fresh_eval_missing.py` (rank-1 `eval_missing` only):

| Queue | Approx. count | Action |
|-------|--------------:|--------|
| **Ready for add-evals** | ~26 rank-1 rows | `/add-evals` only (mappable metrics) |
| **Metric-blocked (rank-1)** | ~32 rows | Fix leaderboard metrics or skip |
| **Import paper, then evals** | ~79 rank-1 papers / 202 rows | Index arXiv + add-evals |
| **Add benchmark, then evals** | ~173 rank-1 leaderboards / 401 rows | `/add-benchmark` + add-evals |
| **Unmapped** | ~8.9k rank-1 / ~19k total | Task/benchmark curation; defer bulk work |

**Recent batches:** Phase 1A (PASCAL VOC 2007), ImageNet 10% semi-supervised, Phase 1B scene text (5 evals), object detection (4 evals; GLIP/D-FINE skipped), image classification (10 evals; Task Arithmetic DTD + AIMv2 iNat 2021 skipped), **image super-resolution** (`import_phase1b_image_super_resolution_evals.py`, 7 evals; DRLN+ 8× skipped — no 8× benchmarks), **image generation** (`import_phase1b_image_generation_evals.py`, 3 evals: DiGIT, EDM2 autoguidance, SiT+MG), **depth estimation** (`import_phase1b_depth_estimation_evals.py`, 4 evals: ScaleDepth-NK ×3 AbsRel, PrimeDepth+DA delta1), **3D semantic segmentation** (`import_phase1b_3d_semantic_segmentation_evals.py`, 1 eval: PTv3 ArKitLabelmaker ScanNet200 test mIoU). R-CNN paper lineage wired (prior session).

---

## Data Sources (OOM Rules)

### Safe

| Asset | How to use |
|-------|------------|
| `data/legacy_top_ranked_missing_evals.csv` | Primary work queue; filter by `status`, `legacy_rank`, `db_task_slug`, `db_dataset_slug` |
| `backend/database/evaluations_setup/analyze_legacy_top_ranked_gaps.py` | Regenerate CSV by **streaming** `evaluation-tables.json` with `ijson` |
| Live DB via `get_engine()` / API | Confirm paper exists, leaderboard metrics configured, duplicate keys absent |
| Single arXiv PDF / HF card / README | Per-paper source fetch during add-evals |

### Unsafe on 4GB VPS

| Asset | Why |
|-------|-----|
| `data/legacy_pwc_data/evaluation-tables.json` (full load) | Multi‑GB; will OOM |
| `data/legacy_pwc_data/papers-with-abstracts.json` | Huge; not needed for gap analysis |
| `json.load()` on legacy dumps | Same |
| Spawning many parallel add-evals subagents each loading PDFs | RAM spikes; run **sequential batches** instead |

### Refresh the gap CSV

```bash
uv run --env-file backend/keys.env python \
  backend/database/evaluations_setup/analyze_legacy_top_ranked_gaps.py \
  --max-rank 3 \
  --path data/legacy_pwc_data/evaluation-tables.json \
  --csv-out data/legacy_top_ranked_missing_evals.csv
```

Re-run after each benchmark batch or large eval import so `eval_missing` / `unmapped_leaderboard` counts stay honest.

---

## Gap Taxonomy

Each CSV row is classified by `analyze_legacy_top_ranked_gaps.py`:

```
legacy SOTA row
    → match task (by name / sota slug prefix)
    → match dataset (by name / slug tail from sota slug)
    → check task_datasets link
    → check paper indexed by arxiv_id
    → check evaluations (paper_id, task_id, dataset_id)
```

| Status | Blocker | Skill |
|--------|---------|-------|
| `eval_missing` | None (infra ready) | `add-evals` |
| `paper_missing` | Paper row absent | arXiv import tooling, then `add-evals` |
| `benchmark_missing` | Dataset exists, not on task | `add-benchmark` |
| `unmapped_leaderboard` | Task or dataset not matched | `add-task` / `add-benchmark` / manual mapping |

**Do not** invent datasets, tasks, or metrics during add-evals. If the legacy metric label is not configured on the exact `(task_id, dataset_id)` leaderboard, skip and log — or fix the leaderboard in a separate add-benchmark pass.

---

## Metric Compatibility Gate

Before posting any row, assert:

1. `(task_id, dataset_id)` exists in `task_datasets`
2. Allowed metrics come from `task_dataset_metrics` for that pair
3. Legacy label maps to an **exact** configured metric name
4. `best_metric` and `metrics` keys ⊆ allowed set
5. Score scale matches existing leaderboard rows (e.g. OCRBench 0–1000 vs percent)

### Common legacy → DB mappings

| Legacy label (examples) | Configured metric |
|-------------------------|-------------------|
| `Top 1 Accuracy`, `Top-1 Accuracy`, `Accuracy (%)`, `Percentage correct` | `Accuracy` or `Top-1 Accuracy` (check leaderboard) |
| `Top 5 Accuracy` | `Top-5 Accuracy` |
| `MAP`, `Average mAP`, `box AP`, `box mAP` | `mAP` |
| `val mIoU`, `test mIoU`, `mIoU` | `mIoU` |
| `FID` | `FID` |
| `F1`, `Micro F1` | `F1` |
| `Exact Match Accuracy (in Dev)` | `Exact Match` (Spider — verify allowed list) |

### Frequent blockers (~129 eval_missing rows)

Legacy labels with no configured counterpart — skip unless add-benchmark adds the metric:

- `METEOR` on summarization leaderboards configured for `ROUGE-L` only
- `Delta < 1.25` variants where leaderboard uses `delta1` / `AbsRel`
- `Top 1 Accuracy` where only `Accuracy` exists (easy alias — map deliberately)
- Component scores (`MME-P`, subscores) where leaderboard allows canonical total only

---

## Default Import Scope (add-evals)

Per skill defaults, unless the user asks otherwise:

- Import **only models introduced by the source paper**, not comparator baselines (GPT, Claude, prior versions)
- Pick the **benchmark-wise best eligible** target row per configured metric — not every ablation
- One row per `(paper_id, task_id, dataset_id, model_name, harness, best_metric)`
- Set `is_open` from weight evidence; omit `num_parameters` / `hf_model_url` when not 100% confident
- Populate `methodology` with table, split, shot count, and any scale normalization

---

## Phase 0 — Infrastructure & Hygiene

**Effort:** ~2 hours once
**Priority:** Do before large batches.

1. Confirm backend reachable and `PWC_ADMIN_API_TOKEN` set.
2. Regenerate `legacy_top_ranked_missing_evals.csv` (command above).
3. List fresh work with `list_fresh_eval_missing.py` — filters stale CSV rows and flags metric blockers:

```bash
uv run --env-file backend/keys.env python \
  backend/database/evaluations_setup/list_fresh_eval_missing.py --rank 1
```

4. Document metric alias table in this plan (section above); extend as blockers appear.

**Verify:**

```bash
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py
```

---

## Phase 1 — Tier 1: add-evals only (~79 papers)

**Effort:** ~1–3 days sequential
**Risk:** Low (no schema changes)

Work from CSV where `status=eval_missing`, paper resolvable, metric maps to configured leaderboard. Prefer **rank 1** first.

### 1A — High-visibility classics (Object Detection / PASCAL VOC 2007)

| arXiv | Paper | Dataset | Metric |
|-------|-------|---------|--------|
| 1506.02640 | YOLO | PASCAL VOC 2007 | mAP |
| 1506.01497 | Faster R-CNN | PASCAL VOC 2007 | mAP |
| 2012.07177 | Copy-Paste | PASCAL VOC 2007 | mAP |

Four legacy rows on this leaderboard; strong anchor for detection task pages.

### 1B — Dense clusters (many rows per paper)

| Cluster | Ready rows (approx.) | Example papers |
|---------|---------------------:|----------------|
| Text-to-SQL / Spider | 6 | 2109.05093 PICARD |
| Scene Text Recognition | 9 | 2305.14014 CLIP4STR, 2307.12270 CPPD, 2308.15996 DTrOCR |
| Image Classification | 36 | 2203.02751 MetaFormer, 2401.15896 M2-Encoder, 2111.07991 LiT |
| Object Detection | 15 | 2112.03857 GLIP (RF100-VL), 2211.09807 M3I / COCO test-dev |
| Image generation | 8 | 2410.12490 DiGIT, 2406.02507 EDM2 autoguidance |
| 3D semantic seg | 4 | 2410.13924 ARKit LabelMaker / ScanNet200 |

Process **one paper at a time**: fetch Table → map metrics → POST → verify API → next paper.

### 1C — Easy metric-alias fixes (~10 rank-1 rows)

Same as 1B but blocked only by label naming (`box AP` → `mAP`, `Top 1 Accuracy` → `Accuracy`). Handle during import; do not add new metrics in the same pass unless user requests.

**Verify per paper:**

```bash
curl -s "http://localhost:8000/api/v1/evaluations/?paper_id=<id>&page_size=100" \
  | uv run python -c "import json,sys; d=json.load(sys.stdin); print(d['count']); [print(e['dataset_name'], e['best_metric'], e['metrics']) for e in d['results']]"
```

After each batch of ~10 papers, re-run gap analyzer and `validate_evaluation_metrics.py`.

---

## Phase 2 — Tier 2: import paper + add-evals (~127 papers)

**Effort:** ~2–4 days
**Risk:** Low–medium (paper indexing edge cases)

CSV `status=paper_missing` where `db_task_slug` and `db_dataset_slug` are populated and leaderboard has metrics.

### Priority sub-clusters

| Sub-cluster | Example arXiv | Notes |
|-------------|---------------|-------|
| Semi-supervised (non-ImageNet) | 1905.02249 MixMatch | CIFAR-10 benchmark likely exists under Image Classification |
| 3D / detection | 1902.04478 MASC, 2303.17895 EA-LSS | Paper import then eval on ScanNet / nuScenes |
| Super-resolution | 1904.05677 DBPN, 2411.18588 Hi-IR | Many rows; same paper spans Set5/Set14/Manga109 |
| Matting / medical / audio | 2312.05915 DiffMatte, 2204.02121 MetaAudio | One paper, multiple benchmarks |

Workflow per paper:

1. `ensure_arxiv_paper` (pattern in `add_tabular_learning_task.py` / `add_3d_segmentation_benchmarks.py`)
2. Tag `paper_tasks` with `source='manual'` when the paper clearly belongs on that task
3. Run add-evals with same scope rules as Phase 1
4. Verify no duplicate `(paper_id, task_id, dataset_id, model_name, harness, best_metric)`

---

## Phase 3 — Tier 3: add-benchmark + add-evals (~395 rows)

**Effort:** ongoing; batch by task
**Risk:** Medium (provenance, metric choice, task association)

CSV `status=benchmark_missing`: dataset row exists, `task_datasets` link missing.

### Suggested batch order (rank-1 density)

| Task (DB slug) | Legacy datasets to link | Notes |
|----------------|---------------------------|-------|
| `pose-estimation` | COCO-WholeBody, COCO minival | Several rank-1 pose papers waiting |
| `object-detection` | PASCAL VOC 2012 | Distinct from VOC 2007 already wired |
| `retrieval` | Flickr30K I→T, ActivityNet Captions, COCO 2014 val | Respect I→T vs T→I dataset slugs |
| `image-generation` | CIFAR-10, CIFAR-100, Oxford Flowers-102 | Match FID / IS metrics |
| `question-answering` | GQA, HellaSwag, StoryCloze | Verify metric per leaderboard |

For each benchmark:

1. Resolve **introducing paper** (not a later model that merely evaluates on it)
2. `INSERT task_datasets`
3. Link metrics in `task_dataset_metrics`
4. Set `datasets.paper_url` to native PwC paper URL
5. Tag introducing paper on task via `paper_tasks`
6. Re-run gap analyzer for that `(task, dataset)` slice
7. Phase 1/2 add-evals for newly unlocked rows

---

## Phase 4 — Semi-supervised & fractional-label benchmarks

Legacy PwC treated many **label-fraction protocols** as separate leaderboards (not full Imagenet-1k).

### Done

| Benchmark | Task | Source paper |
|-----------|------|--------------|
| ImageNet - 10% labeled data | Semi-Supervised Image Classification | ILSVRC [1409.0575](https://paperswithcode.co/paper/1409.0575) |
| S4L evals | — | [1905.03670](https://paperswithcode.co/paper/1905.03670) |

### Next on ImageNet 10% (benchmark now exists; CSV still shows unmapped)

| Rank | arXiv | Action |
|------|-------|--------|
| 1 | 2311.18083 Meta Co-Training | add-evals (paper in DB) |
| 2 | 2301.07094 REACT | import paper + add-evals |
| 3 | 2208.05688 Semi-ViT | import paper + add-evals |

### Still need new benchmarks (legacy unmapped)

| Legacy leaderboard | Example papers | Skill |
|--------------------|----------------|-------|
| ImageNet - 1% labeled data | many semi-supervised papers | add-benchmark + add-evals |
| CIFAR-10 N labels / CIFAR-10 4000 labels | MixMatch, FixMatch, etc. | add-benchmark under semi-supervised or image-classification |
| COCO 10% labeled (detection / instance seg) | MixPL, Semi-DETR, Polite Teacher | add-benchmark on object-detection |
| Cityscapes 10% labeled (sem seg) | UniMatch, IM++ | add-benchmark on semantic segmentation |
| Open-world semi-supervised (CIFAR / ImageNet-100) | ORCA, OpenLDN, TRSSL | add-task or sub-benchmarks |

Mirror legacy naming where it aids discoverability: `ImageNet - 10% labeled data`, not a vague slug like `imagenet-10`.

---

## Phase 5 — Unmapped backlog (defer bulk)

**19,101 rows** — mostly missing task or dataset entities. Do not attempt bulk import.

Use the CSV to **prioritize**:

1. Rank-1 only
2. Rows where `db_task_slug` or `db_dataset_slug` is partially filled (closer to ready)
3. Tasks that already have strong coverage (image-classification, object-detection, reasoning)

Ignore long tail until Phases 1–4 materially reduce `eval_missing` and `benchmark_missing`.

---

## Execution Workflow (single paper)

```
1. Pick row from CSV (status, rank, task, dataset)
2. Confirm paper_id (import if paper_missing)
3. GET /api/v1/datasets/{id}/tasks/{task_id}/metrics
4. Fetch source (PDF table / HF card / README) — one paper only
5. Apply import filter + default scope (best introduced model per metric)
6. POST /api/v1/evaluations/ (or EvaluationService script)
7. validate_evaluation_metrics.py (dry run)
8. curl verify paper evals + benchmark rank
9. Mark row done mentally; refresh CSV weekly
```

Prefer **EvaluationService** in a `uv run --env-file backend/keys.env python` script when API auth is awkward; keep idempotent `existing` checks.

---

## Batching Strategy (OOM & throughput)

| Do | Don't |
|----|-------|
| Sequential papers within a batch | Parallel PDF extraction across 20 papers |
| Filter CSV in Python line-by-line | Load full evaluation-tables.json |
| Commit evals in small groups (~5–10 papers) | One giant transaction for 79 papers |
| Re-run gap analyzer after benchmark phase | Assume CSV is fresh after imports |
| Use `ijson` for any legacy JSON re-parse | `json.load` on legacy dumps |

Target throughput: **5–15 papers/day** for Tier 1 (manual source reading), faster for papers with clean HF model cards.

---

## Success Metrics

| Milestone | Target |
|-----------|--------|
| Phase 1 complete | ~100 new eval rows, 0 new metric validation errors |
| Phase 2 complete | +150–200 rows, 127 paper_missing rank-1 largely cleared |
| Phase 3 (first slice) | +50 rows from pose/retrieval/VOC2012 benchmark links |
| Semi-supervised 10% | Top-3 legacy papers on new leaderboard |
| CSV refresh | `eval_missing` rank-1 count drops by >50% from baseline |

Track weekly:

```bash
uv run --env-file backend/keys.env python - <<'PY'
import csv
from collections import Counter
from pathlib import Path
c = Counter()
with Path("data/legacy_top_ranked_missing_evals.csv").open() as f:
    for row in csv.DictReader(f):
        c[row["status"]] += 1
print(dict(c))
PY
```

---

## Related Docs & Skills

| Resource | Use |
|----------|-----|
| `.agents/skills/add-evals/SKILL.md` | Posting rows, scope, metric gates |
| `.agents/skills/add-benchmark/SKILL.md` | New datasets, task links, native paper URLs |
| `backend/database/evaluations_setup/analyze_legacy_top_ranked_gaps.py` | OOM-safe gap CSV regeneration |
| `backend/database/evaluations_setup/list_fresh_eval_missing.py` | Live DB cross-check of CSV `eval_missing` rows |
| `backend/database/validate_evaluation_metrics.py` | Post-import metric sanity check |
| `PLAN_ROBOTICS.md` | Parallel pattern for a task-specific seed list |
| `http://localhost:8000/docs` | Live evaluation and dataset metric endpoints |

---

## Open Questions

- **Rank depth:** Is top-3 enough, or regenerate with `--max-rank 5` for high-traffic leaderboards only (streaming still safe, but larger CSV)?
- **Metric aliasing:** Should we add a small `legacy_metric_aliases` table or keep alias logic in import scripts only?
- **Duplicate legacy rows:** Same paper appears twice on PASCAL VOC 2007 (FPS+MAP vs MAP only) — import best row once or both with distinct `model_name`?
- **Semi-supervised task tree:** One task vs subtasks for open-world / label-fraction variants?
- **Automation:** After Phase 1 manual pass, is a constrained auto-importer worth it for rows where HF model cards have clean tables and metrics already match?

---

## Immediate Next Steps

1. ~~Regenerate gap CSV (Phase 0).~~ Done 2026-06-22.
2. ~~Phase 1A — PASCAL VOC 2007.~~ Done (`import_pascal_voc_2007_phase1a_evals.py`).
3. ~~ImageNet 10% semi-supervised.~~ Done (REACT, Semi-ViT, SimCLRv2, SEER, PAWS, Meta Co-Training).
4. ~~Phase 1B — Scene Text Recognition cluster.~~ Done 2026-06-22 (`import_phase1b_scene_text_evals.py`, 5 evals).
5. ~~Phase 1B — Object Detection cluster (rank-1 ready rows).~~ Done 2026-06-22 (`import_phase1b_object_detection_evals.py`, 4 evals).
6. ~~Phase 1B — Image classification cluster (SAM, CCT, MetaFormer, …).~~ Done 2026-06-22 (`import_phase1b_image_classification_evals.py`, 10 evals).
7. **Phase 1B continued** — remaining rank-1 clusters (QA/summarization, audio, relation extraction, …) or metric-blocked rows (M2-Encoder, LiT, ObjectNet). ~~Image super-resolution~~, ~~image generation (ImageNet FID)~~, ~~depth estimation~~, and ~~3D seg (ScanNet200)~~ done 2026-06-22.
8. **Phase 3** — add-benchmark for PASCAL VOC 2012 detection, then Copy-Paste / Faster R-CNN follow-ups.
9. Re-run gap analyzer after each batch; refresh counts in this section.
