# Fix plan: `calculate_trending_scores` cron

**Status:** broken in production
**Impact:** GitHub velocity never reaches composite paper trending → homepage ranking ignores star growth for affected repos
**Discovered via:** [Unlimited OCR Works (`2606.23050`)](https://paperswithcode.co/paper/2606.23050) ranking #38 despite ~6.8k stars and strong HF signal

---

## Symptom

Hot new papers with fast-growing GitHub repos do not rise on the homepage trending feed, even though:

- `update_github_stars` is storing hourly snapshots correctly
- `repository_star_history` shows large star deltas (e.g. 772 → 6,799 over ~48 h for `baidu/Unlimited-OCR`)
- `papers.trending_score` composite runs hourly and looks healthy

The missing link is **`repositories.trending_score`** (EMA stars/hour). For Unlimited OCR the repo had:

| Field | Value before manual fix |
|-------|-------------------------|
| `num_stars` | 6,799 |
| `trending_score` | `0.0` |
| `trending_score_updated_at` | `NULL` |
| Star history snapshots | 39 (38 with growth) |

Manually running velocity calc for that single repo immediately produced **46.3 stars/hour**.

---

## Root cause

### Primary: batch SQL underflow kills the entire cron

`calculate_trending_scores.py` processes repos in batches of 500 via one SQL `UPDATE … FROM computed` statement. The EMA step reuses the stored previous score:

```sql
:alpha * raw_velocity + (1 - :alpha) * prev_score
```

~59k repos have decayed `trending_score` values at float subnormals (`1e-323`, `1e-120`, …) from years of zero star velocity with repeated EMA decay. When **any** repo in a batch has such a value, PostgreSQL raises:

```
psycopg2.errors.NumericValueOutOfRange: value out of range: underflow
```

The batch rolls back → **0 repos updated** → cron exits `SUCCESS` after ~20 s with `SUCCESS_NO_WORK` semantics.

Known poison repo: `https://github.com/hustvl/TBCM` (`id=160474`, `trending_score ≈ 1e-323`).

Because batches fail atomically, **new hot repos never get processed** even though they rank #2 in the “never calculated” queue (`trending_score_updated_at IS NULL`, sorted by `num_stars DESC`).

### Secondary: star-tracking cold start (lower priority)

The user hypothesis (“first snapshot already had a high count”) is **partially** true but not the main bug:

- GitHub repo created **2026-06-18**
- Paper/repo linked in PWC **2026-06-23**
- First snapshot: **772 stars** (not 6,799)
- Growth **after** link is tracked correctly

We still miss pre-discovery velocity (0 → ~772 over ~5 days). That caps how far back the EMA can look, but would not explain **zero** velocity if the cron were working.

### Tertiary: backlog + queue ordering

Even after fixing underflow, the job queue is large (~37k repos stale > 1 h). Hot repos are prioritized (`trending_score_updated_at NULLS FIRST`, then `num_stars DESC`), but only **500 × 100 batches/hour** max. Consider hot-paper-aware prioritization (see Phase 3).

---

## Pipeline (for context)

```
update_github_stars          hourly  → repository_star_history + repositories.num_stars
calculate_trending_scores    hourly  → repositories.trending_score   ← BROKEN
calculate_paper_trending_scores hourly → papers.trending_score (composite GitHub + HF)
homepage feed                reads papers.trending_score (composite mode)
```

Composite GitHub component requires fresh repo velocity:

```sql
r.trending_score IS NOT NULL
AND r.trending_score_updated_at >= NOW() - INTERVAL '24 hours'
```

(See `PaperService._TRENDING_SQL_COMPOSITE`.)

---

## Fix plan

### Phase 0 — Confirm (5 min)

Run on VPS:

```bash
cd .github/workflows
PYTHONPATH=. uv run --env-file ../backend/keys.env python -m scripts.hourly.calculate_trending_scores 2>&1 | rg "underflow|updated:"
```

Expect repeated `underflow` errors and `Trending scores updated: 0`.

Sanity query:

```sql
SELECT COUNT(*) FROM repositories
WHERE trending_score IS NOT NULL
  AND trending_score > 0
  AND trending_score < 0.0001;
-- expect tens of thousands
```

---

### Phase 1 — Code fix (required)

**File:** `.github/workflows/scripts/hourly/calculate_trending_scores.py`

**Goal:** Make batch SQL immune to subnormal / out-of-range `prev_score` and clamp stored output to `NUMERIC(10,4)` range.

#### 1a. Sanitize `prev_score` before EMA

In the `candidates` CTE (or `pivoted`), replace raw `prev_score` with a safe value:

```sql
CASE
  WHEN prev_score IS NULL THEN NULL
  WHEN prev_score != prev_score THEN NULL          -- NaN
  WHEN prev_score < 0 THEN 0
  WHEN prev_score < 1e-6 THEN 0                    -- treat subnormals as zero
  WHEN prev_score > 999999 THEN 999999
  ELSE prev_score
END AS prev_score
```

Use `prev_score::float8` only for intermediate math if needed; **store** result clamped back to numeric.

#### 1b. Clamp `new_score` before UPDATE

In `computed`:

```sql
LEAST(GREATEST(new_score, 0), 999999.9999) AS new_score
```

Also handle negative velocity (unstar events) explicitly — either clamp to 0 or allow small negatives; document the choice (recommend clamp to 0 for ranking purposes).

#### 1c. Fail loudly on batch error

Today `process_repository_batch` catches the exception, logs, returns `{updated: 0}`, and the outer loop continues — producing a false “success”. Change to:

- On batch failure: **bisect the batch** (binary search) to skip/isolate poison repos, **or**
- Re-run failed IDs individually (500 extra queries worst case, acceptable as fallback), **or**
- At minimum: increment an error counter and `sys.exit(1)` if `total_updated == 0` after processing a non-empty queue

Recommended: sanitize in SQL (1a/1b) **plus** exit non-zero when queue non-empty but zero writes.

#### 1d. Unit test

Add `backend/tests/test_calculate_trending_scores.py` (or under `.github/workflows/scripts/tests/` if that’s the convention for cron scripts):

- Insert repo with `trending_score = 1e-323`, two star-history rows 1 h apart (+10 stars)
- Call `process_repository_batch([repo_id])`
- Assert no exception, `trending_score_updated_at` set, score ≈ 7.5 (α=0.75 × 10 stars/h)

Add batch test: one poison repo + one healthy repo in same batch → both update.

---

### Phase 2 — One-time data cleanup (required)

Before or immediately after deploy, reset poisoned scores so the first cron run isn’t doing heavy float arithmetic on garbage:

```sql
-- Preview
SELECT COUNT(*) FROM repositories
WHERE trending_score IS NOT NULL
  AND (trending_score <= 0 OR trending_score < 0.0001 OR trending_score > 999999.9999);

-- Cleanup: zero out decayed/subnormal scores (keep NULL for never-calculated)
UPDATE repositories
SET trending_score = 0,
    trending_score_updated_at = COALESCE(trending_score_updated_at, NOW())
WHERE trending_score IS NOT NULL
  AND (trending_score < 0.0001 OR trending_score > 999999.9999);
```

Optional stricter variant: set to `NULL` instead of `0` so repos re-seed on next calc. Either works once SQL is fixed.

Run as a small migration script: `backend/database/migrations/fix_trending_score_subnormals.sql`.

---

### Phase 3 — Prioritize hot repos (recommended)

**File:** `get_repositories_needing_trending_update()` in the same script.

Current ordering:

```sql
ORDER BY trending_score_updated_at NULLS FIRST, num_stars DESC
```

Enhance to match `update_github_stars` hot-paper logic:

```sql
ORDER BY
  CASE WHEN MAX(p.date_published) >= NOW() - INTERVAL '30 days' THEN 0 ELSE 1 END,
  trending_score_updated_at NULLS FIRST,
  num_stars DESC
```

Requires joining `paper_repositories` + `papers` (official, latest version). Ensures repos like `baidu/Unlimited-OCR` are in **batch 1** even when 483 higher-star stale repos exist.

---

### Phase 4 — Cold-start baseline (optional, separate PR)

Problem: repo exists on GitHub days before PWC links it; first snapshot already reflects accumulated stars → early velocity is understated vs true launch curve.

Options (pick one):

1. **Backfill synthetic baseline** on first link: insert `repository_star_history` row at `min(paper.date_published, github_created_at)` with `num_stars = 0` (or fetch from first available snapshot if GitHub archive exists — unlikely).

2. **Seed velocity from first interval only** when `snap_count = 2` and `previous_at - repo.created_at > 24 h`: use raw velocity without EMA decay from subnormal prev (already mostly handled by Phase 1).

3. **Document as accepted limitation** — HF component carries HF-only launches; GitHub component kicks in after ~2 hourly snapshots.

Recommend (1) in `hf_paper_importer.py` / `update_github_stars.py` when creating a new repo row: if first fetch and repo `created_at` from GitHub API is within 30 days, also insert baseline snapshot at `created_at` with `num_stars = 0`.

---

### Phase 5 — Downstream refresh

After repo velocities are flowing:

```bash
# 1. Repo EMA (should now update >>0 repos)
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env \
  python -m scripts.hourly.calculate_trending_scores

# 2. Composite paper scores
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env \
  python -m scripts.hourly.calculate_paper_trending_scores
```

Verify Unlimited OCR:

```sql
SELECT r.url, r.trending_score, r.trending_score_updated_at,
       p.arxiv_id, p.trending_score, p.github_trending_component, p.hf_trending_component
FROM papers p
JOIN paper_repositories pr ON pr.paper_id = p.id AND pr.is_official
JOIN repositories r ON r.id = pr.repository_id
WHERE p.arxiv_id = '2606.23050';
```

Expect `r.trending_score > 0`, fresh `updated_at`, higher `p.trending_score` and `github_trending_component > 0`.

---

## Verification checklist

- [ ] `calculate_trending_scores` completes with **> 0** `Trending scores updated` (expect thousands on first run after cleanup)
- [ ] No `underflow` lines in cron log
- [ ] `baidu/Unlimited-OCR`: `trending_score_updated_at` within last hour, velocity > 0
- [ ] `2606.23050`: `github_trending_component > 0` after paper trending cron
- [ ] Homepage page 1 (trending, all time) includes Unlimited OCR or ranks it materially higher (exact rank depends on corpus quantiles)
- [ ] `manage_cron.py summary` shows `calculate_trending_scores` as healthy with non-zero work
- [ ] New unit tests pass

---

## Rollout order

1. Land Phase 1 (code) + Phase 2 (SQL cleanup migration)
2. Run `calculate_trending_scores` manually once; confirm non-zero updates
3. Run `calculate_paper_trending_scores` manually once
4. Deploy (cron picks up on next hourly run — no backend restart needed for cron-only changes)
5. Phase 3 hot-priority queue (follow-up PR if first run still slow to reach new repos)
6. Phase 4 cold-start (optional follow-up)

---

## Files to touch

| File | Change |
|------|--------|
| `.github/workflows/scripts/hourly/calculate_trending_scores.py` | Sanitize/clamp SQL; optional hot-priority queue; fail on zero-write |
| `backend/database/migrations/fix_trending_score_subnormals.sql` | One-time cleanup |
| `backend/tests/test_calculate_trending_scores.py` (new) | Underflow + batch regression tests |
| `.github/workflows/scripts/docs/TRENDING_EMA_GUIDE.md` | Note subnormal clamp + troubleshooting section |

---

## Not in scope (already working)

- `update_github_stars` — snapshots and star deltas are correct
- Composite formula in `backend/utils/trending.py` — working once repo velocity exists
- HF artifact trending (`update_hf_artifacts`) — separate signal; Unlimited OCR already had strong HF component
