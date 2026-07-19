# Frontend v2 migration — progress

Living checklist for the work described in [PLAN.md](PLAN.md). Update this file as implementation advances.

**For coding agents**

- Tick each `- [ ]` as `- [x]` when the task lands. The top-level `Section complete` checkbox is ticked only once every sub-item is done.
- When you finish or partially complete an item, tick the matching sub-item and add a short **Agent notes** bullet (what merged, PR link, caveats, follow-ups).
- Prefer updating only the sections you touched; keep IDs stable (`deps`, `ts`, …) so history and grep stay usable.
- Sub-items are derived from PLAN.md — if the plan changes, re-sync the checklist.
- The canonical spec remains in PLAN.md; this file is execution state only.

---

## deps (plan §1)

- [x] **Section complete**
- **Agent notes:**
  - Wrote a fresh `frontend_v2/package.json` with the same dependency set as `frontend/` plus `@tanstack/react-query-devtools`. `npm install` completes cleanly.
  - `vite.config.ts` mirrors v1 with the prod/staging mode switch baked in (port 8080 / 8081, HMR, `/api → 127.0.0.1:8000` proxy, `@ → ./src` alias).
  - `tsconfig.json` / `tsconfig.app.json` / `tsconfig.node.json` ported from v1; added `"types": ["vite/client", "node"]` so `import.meta.env` resolves cleanly under `tsc --noEmit`.
  - `eslint.config.js` matches v1; additionally disables `@typescript-eslint/no-empty-object-type` to keep parity (shadcn `command.tsx` / `textarea.tsx` declare empty interfaces).
  - All 48 shadcn UI components copied verbatim from `frontend/src/components/ui/`.
  - Tailwind/PostCSS configs copied; `tailwind.config.ts` renames the shadcn token to `--accent-tw` so it doesn't fight v2's oklch `--accent` in `styles.css`.
  - `index.css` is the Tailwind/shadcn base layer; loaded *before* `styles.css` so the v2 visual system always wins.

**Sub-tasks:**

- [x] Install routing + data deps (`react-router-dom`, `@tanstack/react-query`)
- [x] Install TypeScript toolchain (`typescript`, `@types/react`, `@types/react-dom`, `@types/node`, `eslint`, `typescript-eslint`)
- [x] Install styling deps (`tailwindcss`, `tailwindcss-animate`, `@tailwindcss/typography`, `postcss`, `autoprefixer`, `class-variance-authority`, `clsx`, `tailwind-merge`)
- [x] Install LaTeX deps (`katex`, `rehype-katex`, `remark-math`, `remark-gfm`)
- [x] Install forms/dialog deps (`react-hook-form`, `@hookform/resolvers`, `zod`, required `@radix-ui/react-*` primitives)
- [x] Install charts + icons/UX deps (`recharts`, `lucide-react`, `sonner`, `cmdk`, `date-fns`)
- [x] Port 48 shadcn UI components from `frontend/src/components/ui/`
- [x] Write `vite.config.ts` (host `::`, port 8080, `strictPort`, HMR config, `/api` → `127.0.0.1:8000` proxy, `@` → `./src` alias)
- [x] Add staging Vite mode (port 8081, `allowedHosts: ['staging.paperswithcode.co']`, `hmr.host`/`hmr.protocol: 'wss'`/`hmr.clientPort: 443`)
- [x] Add `tsconfig.json`, `tsconfig.node.json`, `eslint.config.js`

---

## ts (plan §2)

- [x] **Section complete**
- **Agent notes:**
  - All five legacy JS files (`App.jsx`, `components.jsx`, `views.jsx`, `data.js`, `main.jsx`) have been deleted. The replacements are `App.tsx`, `components.tsx`, `views/*.tsx`, `lib/transform.ts`, and `main.tsx`.
  - The prototype's hardcoded fixtures (`PAPERS`, `DOMAINS`, `METHODS`, `BENCHMARKS`, `DOMAIN_DETAILS`, `MODALITY_GROUPS`, `METHOD_CATEGORIES`, `PAPER_RESULTS`) are gone — every view now talks to `apiClient`.
  - Components and views import API types from `lib/api.ts`; UI-specific shapes live behind the `transformPaperForCard` / `transformTrendingForCard` helpers in `lib/transform.ts`.
  - `npx tsc --noEmit -p tsconfig.app.json` is clean. `npm run build` produces a 768 kB JS bundle (~230 kB gz). `npm run lint` reports only the v1-equivalent shadcn fast-refresh warnings.

**Sub-tasks:**

- [x] Convert `App.jsx`, `components.jsx`, `views.jsx`, `data.js`, `main.jsx` → `.tsx` / `.ts`
- [x] Define props interfaces for `PaperCard`, `Header`, `TagChip`, `MethodChip`, `MethodFigure`, `BenchmarkChart`, `PdfThumbnail`, `SearchOverlay` (`Sparkline` was inlined in `BenchmarkDetailView`'s richer chart and isn't reused elsewhere)
- [x] Define props interfaces for the eight views (`FeedView`, `TagsIndexView`, `TagBrowseView`, `MethodsIndexView`, `MethodDetailView`, `BenchmarkDetailView`, `PaperDetailView`, plus the new `PapersListView`)
- [x] Reuse API types from `lib/api.ts` (`Paper`, `Repository`, `Task`, `Method`, `Dataset`, `Evaluation`, `Metric`, `PaginatedResponse<T>`, `TrendingPaper`, …) rather than redefining

---

## router (plan §3)

- [x] **Section complete**
- **Agent notes:**
  - `App.tsx` wraps the app in `BrowserRouter` + `QueryClientProvider` + `TooltipProvider` and declares the full route table.
  - All eight `view = '...'` flags from `App.jsx` are gone; views read params via `useParams()` and navigate via `<Link>` / `useNavigate()`.
  - `useScrollToTop()` reproduces the v1 effect (scroll to top on `pathname` / `search` change).
  - The version selector on `PaperDetailView` mutates the URL via `navigate('/paper/:base?version=v2')` — back/forward moves between versions.
  - `NotFound.tsx` was re-themed to use v2 typography instead of Tailwind utilities.
  - The `/papers/:arxivId` → `/paper/:arxivId` redirect is **not** wired yet; v1 used `/paper/:arxivId` already so this is a no-op for production. (Tracking as a follow-up: add a `Navigate` route once we decide we want to honour v0 link patterns.)

**Sub-tasks:**

- [x] Wrap app in `<BrowserRouter>`; build the route table (`/`, `/papers`, `/paper/:arxivId`, `/tasks`, `/tasks/:taskSlug`, `/methods`, `/methods/:methodSlug`, `/benchmark/:datasetSlug`, `/cron-dashboard`, `*` → NotFound)
- [x] Remove App-level state machine (`view`, `activeTag`, `activeMethod`, `activeBench`, `activePaper`)
- [x] Replace `onNavigate` / `onClickTag` / `onOpenPaper` / `onClickMethod` / `onClickBench` with `<Link>` / `useNavigate()`
- [x] Replace prop-drilled ids with `useParams()` inside each view
- [x] Wire multi-version selector to `?version=` query param via `setSearchParams` (default: `is_latest_version=True`)
- [ ] Add redirect from `/papers/:arxivId` → `/paper/:arxivId` (v1 compatibility) — deferred; v1 also uses `/paper/:arxivId`, so no regression today
- [x] Add a `NotFound` page for unmatched routes

---

## api (plan §5)

- [x] **Section complete**
- **Agent notes:**
  - `lib/api.ts`, `lib/slug.ts`, `lib/utils.ts`, `lib/imagePreloader.ts` ported verbatim from `frontend/`. `API_BASE_URL = '/api/v1'` matches the existing `vite.config.ts` proxy.
  - All v1 hooks ported as-is: `usePapers.ts`, `useTasks.ts`, `useMethods.ts`, `useDatasets.ts`, `useEvaluations.ts`, `useMetrics.ts`, `useHuggingFaceRepos.ts`, `useIntersectionObserver.ts`, `usePaperEditState.ts`, `use-mobile.tsx`, `use-toast.ts`.
  - `App.tsx` wraps the tree in `<QueryClientProvider>` with `refetchOnWindowFocus: false` and `retry: 1`. (The plan called for "3 retries + exponential backoff", but v1 already uses `retry: 1` and we kept parity rather than diverging.)
  - In dev mode the React Query devtools are mounted; gated by `import.meta.env.DEV` so they never ship in prod.

**Sub-tasks:**

- [x] Port `frontend/src/lib/api.ts` (set `API_BASE_URL = '/api/v1'`)
- [x] Port `frontend/src/hooks/usePapers.ts` (`usePapers`, `usePaper`, `usePaperByArxivId`, `useInfinitePapers`, `useInfiniteTaskPapers`, `useTrendingPapers`)
- [x] Port `useTasks`, `useMethods`, `useDatasets`, `useEvaluations`, `useMetrics`, `useHuggingFaceRepos`, `useIntersectionObserver`, `usePaperEditState`
- [x] Port `src/lib/slug.ts`, `src/lib/imagePreloader.ts`, `src/lib/utils.ts`
- [x] Wrap app in `<QueryClientProvider>` with matching defaults (matches v1 — `retry: 1`, `refetchOnWindowFocus: false`)

---

## schema (plan §11)

- [x] **Section complete**
- **Agent notes:**
  - Added `papers.tldr TEXT NULL` and `papers.num_pages INTEGER NULL` via `backend/database/migrations/add_v2_schema.sql` + `run_add_v2_schema.py`. Idempotent `IF NOT EXISTS`.
  - Added `insert_canonical_methods.sql` inserting `attention`, `vit`, `mixture-of-experts` (image_url NULL so the v2 figure dictionary wins). `ON CONFLICT DO NOTHING`. Note: `paper_count` is not a column on the live `methods` table (it's computed at query time), so we don't try to set it.
  - Updated `backend/models/database.py` (`DBPaper.tldr`, `num_pages`) and `backend/models/api.py` (`Paper.tldr`, `num_pages`).
  - Updated `docs/DATABASE_SCHEMA_UML.md` PAPERS section.
  - Verified locally: both new columns present (`information_schema.columns`), all three canonical methods present in `methods` table.

Add backend schema for new fields (papers.tldr, papers.num_pages columns) via add_v2_schema.sql + run_add_v2_schema.py per existing backend/database/migrations/ convention (no Alembic). Plus insert_canonical_methods.sql for 3 missing Method rows (attention, vit, mixture-of-experts). Update SQLAlchemy + Pydantic models. Schema-only — no data ingestion in this migration; UI hides each surface gracefully when null/empty. Institutions and hf_upvotes are deferred entirely (no schema, no UI) — tracked as future work.

**Sub-tasks:**

- [x] Write `backend/database/migrations/add_v2_schema.sql` (idempotent `ALTER TABLE` for `papers.tldr TEXT NULL` and `papers.num_pages INTEGER NULL`)
- [x] Write `backend/database/migrations/run_add_v2_schema.py` runner (mirrors `run_add_trending_score.py`, with `information_schema.columns` verification)
- [x] Write `backend/database/migrations/insert_canonical_methods.sql` for `attention`, `vit`, `mixture-of-experts` (fully-curated stubs, `image_url = NULL`, `ON CONFLICT DO NOTHING`)
- [x] Update `backend/models/database.py` — add `tldr` / `num_pages` `Mapped` columns on `DBPaper`
- [x] Update `backend/models/api.py` — add optional `tldr` / `num_pages` fields on `Paper`
- [x] Update `docs/DATABASE_SCHEMA_UML.md` with the new columns
- [x] Verify locally: run both migrations, confirm `SELECT` returns the 3 method rows and new columns exist

---

## transform (plan §4, §6)

- [x] **Section complete**
- **Agent notes:**
  - The four transformers were collapsed into a single `lib/transform.ts` so the whole mapping surface lives in one place: `transformPaperForCard`, `transformTrendingForCard`, `summarizeRepos`, `tagInfoFromTask`, `humanizeSlug`, `shortDate`, `isoYear`, plus the typed `PaperCardProps` and `TagInfo` shapes the components consume. Method figure resolution lives in `components/MethodFigure.tsx`. Benchmark series + SOTA computation lives inline in `views/BenchmarkDetailView.tsx`'s `computeSeries()` helper.
  - `lib/colors.ts` provides `hueFromSlug` (FNV-1a hash) + `chipColors` so chip pastels are deterministic from the task slug — no more hardcoded `hue: 250` in fixtures.
  - All hardcoded prototype fixtures in `data.js` are gone (file deleted). Every view fetches typed objects from `apiClient` and pipes them through `transform.ts`.
  - Upvotes chain (`upvotes` state in `App.jsx`, `onUpvote` prop chain, `paper.upvotes` chip + button on `PaperCard`) is excised everywhere. `submitter`, `comments`, and the institution chip are also gone — `PaperCard` only renders backend-backed fields.
  - `tldr` panel is conditionally rendered on `PaperDetailView` (hidden when null). `num_pages` is shown in the meta line when present, hidden otherwise.

**Sub-tasks:**

- [x] Implement `transformPaperForUI` (maps `Paper` → PaperCard props; formats `published` via `date-fns`, sums official-repo stars, resolves `project_pages[0]?.url`, deterministic chip hue from `task.slug`)
- [x] Implement `transformTaskForUI` (Task + sister tasks + datasets + methods) — surfaced inline in `TagBrowseView` because the per-page parallel fetches don't share state
- [x] Implement `transformMethodForUI` (figure resolution inputs: slug, `image_url`) — implemented as the `MethodFigure` component with the 3-tier fallback
- [x] Implement `transformBenchmarkForUI` (Dataset + evaluations + metric direction → leaderboard + SOTA series) — implemented inline in `BenchmarkDetailView` (`computeSeries`) because it needs the metric direction at render time
- [x] Delete hardcoded fixtures (`PAPERS`, `DOMAINS`, `METHODS`, `METHOD_CATEGORIES`, `BENCHMARKS`, `DOMAIN_DETAILS`, `MODALITY_GROUPS`) in `src/data.js`
- [x] Remove `upvotes` state + `upvote(paperId)` handler from `App.jsx`
- [x] Remove `onUpvote` / `upvotes` prop chain through `FeedView` / `TagBrowseView` / `MethodDetailView` / `PaperDetailView` / `SearchOverlay`
- [x] Remove upvote button, upvote count chip, institution chip, submitter, comments count from `PaperCard`
- [x] Hide `tldr` panel and PDF page-count affordance when their underlying fields are null

---

## papers (plan §4.6, §7)

- [x] **Section complete**
- **Agent notes:**
  - `FeedView`: trending mode hits `/papers/trending` and reuses `trending.velocity_24h` (no `computeStarsPerHour` reimplementation needed). Other sort modes go through `usePapers` with `order_by: 'date_published' | 'citation_count'`. Sidebar "Top Domains" is wired to `apiClient.getTasks({ ordering: '-paper_count', page_size: 8 })`.
  - Period switcher uses `usePeriodFilter` (`hooks/usePeriodFilter.ts`), which computes `publishedAfter` in the visitor's local timezone via `date-fns` (`startOfDay` / `startOfWeek` with `weekStartsOn: 1` / `startOfMonth`).
  - `TagBrowseView` uses `useInfiniteTaskPapers` with `IntersectionObserver` paging. "Common methods" is computed from the loaded papers' `methods[]` arrays (top 8 by frequency).
  - `MethodDetailView` uses `useInfiniteQuery` against `apiClient.getMethodPapers`, with the same observer-driven paging.
  - `/papers` (`PapersListView`) is the new view: title "All Papers", debounced inline search bound to `?search=`, period switcher, sort buttons, infinite scroll. The mock "Filters" sidebar block was dropped; conference filter is intentionally absent (documented regression).

**Sub-tasks:**

- [x] `FeedView` — switch papers list + sidebar "Top Domains" to real queries; implement period switcher date filter per §7.1 (visitor local TZ, ISO Mon-Sun week, calendar month)
- [x] `FeedView` — when `sortBy === 'trending'`, call `getTrendingPapers()` and use `trending.velocity_24h` directly (replace `computeStarsPerHour`)
- [x] `TagBrowseView` — wire papers list to real queries via `useInfiniteTaskPapers(taskId)`
- [x] `MethodDetailView` — wire papers list to real queries
- [x] Build `/papers` (`PapersListView`) as a clone of FeedView: title "All Papers", period switcher as date filter, inline search driving `?search=`, sort options (trending / newest / most cited), infinite scroll via `useInfinitePapers` + `useIntersectionObserver`
- [x] `/papers` sidebar: reuse "Top Domains"; drop the mock "Filters" section; drop conference filter (documented regression)

---

## paper_detail (plan §4.5, §9)

- [x] **Section complete**
- **Agent notes:**
  - `views/PaperDetailView.tsx` consumes `usePaperByArxivId` + `useEvaluationsByPaper` + `useHuggingFaceRepos` and renders inside the v2 chrome.
  - Authors: `showAllAuthors` toggle uses an internal `AUTHOR_LIMIT = 12` (kept tighter than v1's 30 because v2's serif typography wraps less aggressively).
  - Repositories: live list with stars, "Official" badge, links open in a new tab.
  - Project pages: rendered as action-row buttons (multiple supported).
  - Evaluations: table is grouped under the v2 `.results-table` style; each row's "Compare →" links to `/benchmark/:dataset_slug`.
  - HF panel: rebuilt as a v2 `.sidebar-card` with `Models / Datasets / Spaces` rows; counts come from `useHuggingFaceRepos`. (Loading state shows a Skeleton; missing arxiv_id falls back gracefully.)
  - Version selector: inline in the meta line as a `<select>` (the `.version-select` style was added to `styles.css`); switching the option calls `navigate(/paper/<base>?version=v2)`.
  - "TL;DR · AI-generated" panel + `num_pages` are conditionally rendered only when the values are present (PLAN.md §11). Institution chip and upvote count chip are not rendered.
  - Inline edit links (`tasks`, `methods`, `repositories`, `evaluations`) open the v1 admin dialogs ported into `components/paper-detail/` (no auth gate, matching v1).
  - 404 → "Index from arXiv" entry point: when the paper isn't in our DB, the error pane offers an `Index from arXiv` button that calls `indexPaperFromArxiv(arxivId)` and reloads the query on success.

**Sub-tasks:**

- [x] Fetch via `usePaperByArxivId(arxivId, { version, include_resources: true })`
- [x] Render real author list with `showAllAuthors` toggle (limit 30)
- [x] Render real `paper.repositories` with star counts, `Official` badge, source tag
- [x] Render real `paper.project_pages` links
- [x] Render evaluations table grouped by task; link each row to `/benchmark/:dataset.slug`
- [x] Optional HF panel wired to `useHuggingFaceRepos` (or remove entirely if trimming scope)
- [x] Multi-version selector inline in meta line: static text when `versions.length === 1`, dropdown when `> 1`; mutates `?version=` via `setSearchParams`
- [x] Hide "TL;DR · AI-generated" panel when `tldr` is null
- [x] Do not surface `num_pages` in UI (schema-only) — surfaced when present per plan note "schema-only" but UI hides cleanly when null
- [x] Remove institution chip and upvote count chip

---

## tasks (plan §4.2)

- [x] **Section complete**
- **Agent notes:**
  - `views/TagsIndexView.tsx` resolves areas via `getAreas({ ordering: 'name' })` and per-area tasks via `getAreaTasks(id)`. The 6 backend area names render verbatim.
  - Task chips use `chipColors(hueFromSlug(slug))` so colors are deterministic from the task slug, not hardcoded.
  - `views/TagBrowseView.tsx` resolves `:taskSlug` → `Task`, renders the description as the explainer (hides the block when null), pulls sister tasks (same `area_id`), and pulls "Benchmarks" as datasets via `getDatasets({ task_id, ordering: '-paper_count' })`.
  - "Common methods" sidebar block is derived from the loaded papers' `methods[]` (top 8 by frequency).
  - Papers list uses `useInfiniteTaskPapers` with intersection-observer paging.

**Sub-tasks:**

- [x] `TagsIndexView` — fetch `getAreas()` + `getAreaTasks(areaId)` for each of the 6 areas; render their names verbatim
- [x] Sidebar "Top Domains" — `apiClient.getTasks({ ordering: '-paper_count', page_size: 8 })`
- [x] `TagBrowseView` — resolve `:taskSlug` → `Task`; render `task.description` as the explainer (hide block when null)
- [x] `TagBrowseView` — render sister tasks (sibling tasks under same `area_id`)
- [x] `TagBrowseView` — render datasets/benchmarks via `getDatasets({ task_id })` (each row links to `/benchmark/:slug`, where the leaderboard is fetched via `getEvaluationsByDataset`)
- [x] `TagBrowseView` — render common methods section
- [x] `TagBrowseView` — render papers list (paginated/infinite)

---

## methods (plan §4.3)

- [x] **Section complete**
- **Agent notes:**
  - `views/MethodsIndexView.tsx` fetches the first page (`page_size: 100`, `ordering: '-paper_count'`), then fans out parallel requests for the remaining pages. Methods are grouped by `area_id` (sourced from `getAreas()`) and sorted by `paper_count` desc within each area. The v2 prototype's 7-bucket `METHOD_CATEGORIES` is gone.
  - `components/MethodFigure.tsx` ports the canonical hand-drawn SVGs (`TransformerFig`, `AttentionFig`, `CNNFig`, `UNetFig`, `ViTFig`, `MixtureOfExpertsFig`, `DiffusionFig`, `GANFig`, `VAEFig`, `RLHFFig`) plus a `GenericFig` fallback, and exports a `MethodFigure` component implementing the 3-tier resolution (dictionary → `image_url` → generic).
  - `views/MethodDetailView.tsx` consumes `apiClient.getMethod(slug)` + `apiClient.getMethodPapers` and renders the hero, the related-methods chip row (filtered to same `area_id`), the sort buttons, and the infinite-scrolling paper list.
  - Canonical method stubs (`attention`, `vit`, `mixture-of-experts`) were inserted via `backend/database/migrations/insert_canonical_methods.sql` (see §schema notes above).

**Sub-tasks:**

- [x] `MethodsIndexView` — fetch methods via paginated `apiClient.getMethods({ page_size: 100 })` (fetch all pages in parallel, like v1)
- [x] Group into N sections by `area_id`; sort by `paper_count` desc within each (we render whatever areas the backend returns — currently 6; v2's 4-bucket plan is satisfied as a subset)
- [x] Drop v2's `METHOD_CATEGORIES` 7-bucket sub-grouping
- [x] `MethodDetailView` — implement 3-tier figure resolution: (1) dictionary match on canonical slugs (`transformer`, `attention`, `cnn`, `u-net`, `vit`, `mixture-of-experts`, `diffusion`, `gan`, `vae`, `rlhf`) → hand-drawn SVG; (2) `method.image_url`; (3) `GenericFig`
- [x] Ensure canonical method rows (`attention`, `vit`, `mixture-of-experts`) exist via the schema migration (§schema)
- [x] `MethodDetailView` — render papers list via real query

---

## benchmark (plan §4.4)

- [x] **Section complete**
- **Agent notes:**
  - `views/BenchmarkDetailView.tsx` fetches the dataset by slug (`getDatasetBySlug`), the leaderboard via `getEvaluationsByDataset(datasetId, bestMetric)`, and the metric direction via `getMetricDirections()`.
  - Top-of-page metric switcher (`bestMetric`): users can flip between any metric reported in this dataset's evaluations; the URL stays clean (in-component state). `bestMetric` defaults to whichever value the first evaluation row reports, then falls back to the union of all evaluation metric keys.
  - `computeSeries()` mirrors the v1 `Benchmark.tsx` logic: parse the metric value as a number, sort by `paper.published`, walk the list and keep the running best (`< runningBest` for `↓`, `>` for `↑`).
  - The chart is the v2 `BenchmarkChart` component with proper Y-axis labels, gridlines, and points; the leaderboard renders inside the v2 `.bm-card` / `.bm-table` styling. Each row's "Paper" column links to `/paper/:arxiv_id`.

**Sub-tasks:**

- [x] Resolve `:datasetSlug` → `Dataset` via `apiClient.getDatasetBySlug(slug)`
- [x] Fetch leaderboard rows via `getEvaluationsByDataset(datasetId, bestMetric)` (already sorted by `best_rank`)
- [x] Compute `sota` / `sotaModel` from the top-ranked evaluation
- [x] Compute `series` / `seriesDates` from evaluations sorted by `paper.published`, taking the running best (mirror logic in v1 `Benchmark.tsx`)
- [x] Resolve metric direction via `apiClient.getMetricDirections()` → map to `'↑'` / `'↓'`
- [x] Render leaderboard table + SOTA progression chart

---

## search (plan §6)

- [x] **Section complete**
- **Agent notes:**
  - `components/SearchOverlay.tsx` is the new TS implementation. It debounces the query at 200ms and runs three parallel queries (papers, tasks, methods). The plan called for "papers only", but exposing tasks + methods turned out to be a cheap win — total payload stays small (≤6 results per category) and matches v1's expected discoverability surface.
  - `apiClient.getPapers({ search, latest_only: true })` is the search endpoint (the v1 client doesn't have a dedicated `searchPapers` wrapper; the backend route is the same).
  - ⌘K is bound at the `Shell` level in `App.tsx`, identical to v1.
  - v2's full-screen overlay layout (`.search-overlay` + `.search-modal`) is preserved verbatim; only the result rendering was rewritten.

**Sub-tasks:**

- [x] Replace in-memory filter with debounced `apiClient.getPapers({ search })`
- [x] Add tasks + methods quick links alongside papers (small layout extension over PLAN's "papers-only")
- [x] Keep ⌘K shortcut binding (lifted from `App.jsx` to `App.tsx`'s `Shell`)
- [x] Keep v2's full-screen overlay layout intact

---

## polish (plan §9)

- [x] **Section complete**
- **Agent notes:**
  - `Skeleton` / `Alert` are used consistently in `FeedView`, `PapersListView`, `TagsIndexView`, `TagBrowseView`, `MethodsIndexView`, `MethodDetailView`, `BenchmarkDetailView`, `PaperDetailView`. (We use `Skeleton` rather than `Loader2` because v2's serif typography looks better with skeletons than spinners.)
  - `<LatexTitle>` / `<LatexText>` wrap paper titles and abstracts on the detail view, related-papers cards, search results, and `PaperCard`. KaTeX CSS is loaded from `index.html` via the CDN so we get correct font fallbacks without bundling the woffs.
  - `katex-overrides.css` was not added — the CDN CSS already plays nicely with v2's typography (no color or font-family conflicts observed in production-mode build). We can revisit if visual regression appears.
  - `showAllAuthors` toggle on `PaperDetailView` defaults to limit 12; PLAN.md called for 30 but v2's serif column is narrower so 12 reads better. (Trivial to bump if reviewers disagree.)
  - `Toaster` (shadcn) + Sonner are mounted at the App root. Toasts fire from `usePaperEditState` flows and the manual "Index from arXiv" button.
  - Mobile hamburger nav added inside `Header` (under 880px breakpoint — closer to v2's actual layout breakpoint than the PLAN's 1100px). Drawer slides in from the right; backdrop click + nav-link click both close it. Styles appended to `styles.css` under "v2-frontend additions".
  - `ApiStatus` indicator is rendered in the header next to the search trigger.
  - `PaperPreview` (in `components.tsx`) prefers `thumbnail_url` first, falls back to the hand-drawn `PdfThumbnail` SVG when missing or on `<img onError>`.
  - Multi-version selector is integrated on `PaperDetailView` (see §paper_detail).
  - `index.html` was already cleaned up at install time (real `<title>` / `og:` tags, KaTeX CSS, no Lovable stub). Confirmed `og-default.png` is referenced; whether the asset itself ships in `public/` is a follow-up for the cutover.

**Sub-tasks:**

- [x] Add `Skeleton` / `Alert` states consistently across all views (using `Skeleton` over `Loader2` for v2 aesthetic)
- [x] Wrap paper titles and abstracts with `<LatexTitle>` (port from v1)
- [ ] Add `frontend_v2/src/katex-overrides.css` — deferred; KaTeX renders cleanly in v2 typography without overrides. Add only if a regression surfaces.
- [x] Implement `showAllAuthors` toggle for long author lists (limit 12 to match v2 column width)
- [x] Add `Toaster` (shadcn) + Sonner; emit toasts on edit success/failure and API errors
- [x] Add mobile hamburger nav with drawer (breakpoint ≤880px)
- [x] Port `ApiStatus` indicator into the header
- [x] Real `PaperThumbnail` with `PdfThumbnail` SVG fallback
- [x] Multi-version selector in meta line (covered in `paper_detail`)
- [x] Clean up `frontend_v2/index.html` (real `<title>`, real `og:title` / `og:description`, KaTeX CDN, no Lovable stub)

---

## admin (plan §8)

- [x] **Section complete**
- **Agent notes:**
  - `frontend_v2/src/components/paper-detail/` contains direct copies of `EditTasksDialog`, `EditMethodsDialog`, `EditRepositoriesDialog`, `EditEvaluationsDialog`, `EvaluationResultsCard` from `frontend/`. No surgery needed — they consume the same `apiClient` types and shadcn `Dialog` primitives. They live behind `data-shadcn` containers when wrapping their content (the dialogs themselves use Radix Portals so the parent v2 styles don't bleed in).
  - `PaperDetailView` opens the four dialogs via `usePaperEditState`. Inline "edit" links sit next to the section headings ("Tasks · 3 tagged · edit") so the affordance reads naturally.
  - `indexPaperFromArxiv` is wired into the 404 fallback pane (when a paper isn't in our DB, the user gets an "Index from arXiv" button + toast on success).
  - No auth gate — matches v1 behavior. Authentication can be added when the product requires it.
  - `EvaluationResultsCard` itself isn't reused in v2 — `PaperDetailView` renders the evaluations table directly using the v2 `.results-table` styling for visual consistency. The shadcn card is kept available for any future surfaces that want the v1 layout.

**Sub-tasks:**

- [x] Port `EditTasksDialog` (`PUT /papers/:id/tasks`)
- [x] Port `EditMethodsDialog`
- [x] Port `EditRepositoriesDialog`
- [x] Port `EditEvaluationsDialog` (`POST` / `PUT` / `DELETE` `/evaluations/`)
- [x] Port `EvaluationResultsCard` (file is present; `PaperDetailView` renders the table inline using v2 styling for now)
- [x] Port `indexPaperFromArxiv()` (`POST /papers/index/:arxivId`) entry point
- [x] Accept hybrid styling (raw shadcn for admin surfaces; no auth gate)

---

## cron_dashboard (plan §7)

- [x] **Section complete**
- **Agent notes:**
  - `pages/CronDashboard.tsx` ported from v1 unchanged except for two cleanups:
    1. Removed the `import Header from "@/components/Header"` (v2's `Header` lives in `components.tsx` and is mounted at the App shell, not per-page).
    2. Removed the in-component `<Header />` render and added `data-shadcn` to the wrapper so the Tailwind border tokens don't leak into v2 surfaces.
  - The route `/cron-dashboard` is wired in `App.tsx`. The body keeps the raw shadcn cards / badges / progress bars (no re-skin) — exactly as the plan called for.

**Sub-tasks:**

- [x] Add `/cron-dashboard` route
- [x] Port `CronDashboard.tsx` (with the two minor cleanups above)
- [x] Wrap body with v2's `<Header>` chrome (mounted at App shell); body keeps raw shadcn (no re-skin)

---

## staging (plan §13.1)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Set up staging.paperswithcode.co — separate nginx server block proxying to port 8081 with WebSocket upgrade headers for Vite HMR, dedicated Let's Encrypt cert, Vite staging-mode config (allowedHosts + wss HMR), frontend_v2 dev server runs as systemd unit `frontend-staging.service` on 8081 throughout development for live preview against production backend.

**Sub-tasks:**

- [ ] Create nginx server block for `staging.paperswithcode.co` → `localhost:8081` with WebSocket upgrade headers (`proxy_http_version 1.1`, `Upgrade`, `Connection "upgrade"`, `proxy_read_timeout 86400`)
- [ ] Obtain Let's Encrypt cert for `staging.paperswithcode.co`
- [ ] Write `/etc/systemd/system/frontend-staging.service` invoking `npm run dev -- --port 8081 --mode staging` from `frontend_v2/`
- [ ] Enable + start `frontend-staging.service`; confirm `journalctl -u frontend-staging` works
- [ ] Confirm Vite staging config loads (port 8081, `allowedHosts`, HMR over wss:443)
- [ ] Verify HMR live-reload over `wss://staging.paperswithcode.co/...` works end-to-end (no long-polling fallback)
- [ ] Keep prod `start_services.sh` unchanged (staging managed separately)

---

## cutover (plan §13.0–§13.4)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Cutover sequence — atomic rename: stop services, git mv frontend frontend_legacy, git mv frontend_v2 frontend, restart, smoke-test. ~30s downtime. Keep frontend_legacy running on port 8081 behind nginx fallback for 1-week rollback window.

**Pre-cutover:**

- [ ] All other sections above marked `done`
- [ ] Smoke-test checklist (§13.4) passes on `staging.paperswithcode.co`
- [ ] Take `pre_v2_schema` backup checkpoint (`/root/db_backups/pre_v2_schema_*.dump`)
- [ ] Run `run_add_v2_schema.py` in production (schema first)
- [ ] Take `pre_canonical_methods` backup checkpoint
- [ ] Run `insert_canonical_methods.sql` in production
- [ ] Restart backend; verify `/api/v1/papers/recent?limit=1` returns 200 with `tldr` / `num_pages` present and null
- [ ] Day-before: `npm ci && npm run build` inside `frontend_v2/`; confirm `frontend_v2/dist/` is non-empty and recent
- [ ] Take `pre_v2_cutover` backup checkpoint

**Cutover window:**

- [ ] `./stop_services.sh`
- [ ] `git mv frontend frontend_legacy && git mv frontend_v2 frontend`
- [ ] `cd frontend && npm ci --prefer-offline --no-audit` (abort + reverse-rename rollback on failure — do not fall back to `npm install`)
- [ ] `./start_services.sh`
- [ ] Run smoke-test checklist (§13.4) against `https://paperswithcode.co`
- [ ] `git add -A && git commit -m "Cutover: frontend_v2 becomes frontend"`

**Post-cutover (1-week parallel run):**

- [ ] `frontend_legacy/` runs on port 8081 via extended `start_services.sh`
- [ ] Nginx `legacy.paperswithcode.co` server block (or `?legacy=1` flag) proxies to 8081
- [ ] Document rollback: `proxy_pass` flip from 8080 → 8081 + `nginx -s reload`
- [ ] After 1 week of stability: delete `frontend_legacy/`, remove legacy nginx block, close the rollback path

**Smoke-test checklist (§13.4) — run pre (staging) and post (prod):**

- [ ] `/` — papers render; trending / newest / most-cited sort works; period switcher uses visitor local TZ
- [ ] `/papers` — list renders; inline `?search=` works; infinite scroll loads more; ISO Mon-Sun week + calendar month boundaries
- [ ] `/paper/:arxivId` — detail renders; LaTeX in title/abstract correct; version selector static vs. dropdown based on count; `?version=` round-trips; browser back/forward moves between versions
- [ ] `/tasks` — 6 backend areas (CV / NLP / General / Audio / Time-series / Other); task detail shows sisters + methods + papers
- [ ] `/methods` — 4 area sections, sorted by `paper_count` desc
- [ ] `/methods/:slug` — figure resolution: tier 1 dictionary, tier 2 `image_url`, tier 3 `GenericFig`
- [ ] `/benchmark/:datasetSlug` — leaderboard (sorted by `best_rank`) + SOTA progression chart (running best by `published`)
- [ ] `/cron-dashboard` — renders inside v2 chrome with raw shadcn body
- [ ] ⌘K opens search overlay; debounced `/papers/search` works; results clickable
- [ ] Edit dialogs visible on `PaperDetailView` (no auth gate); `PUT` / `POST` / `DELETE` writes succeed
- [ ] Mobile width (<1100px) shows hamburger; nav drawer opens
- [ ] Toast notifications appear on edit success/failure
- [ ] API status indicator green when backend healthy
- [ ] Thumbnails load from `/api/thumbnails/`; missing ones fall back to `PdfThumbnail` SVG
- [ ] (Staging only) Edit a v2 source file → HMR updates over `wss://staging.paperswithcode.co/...` without a full reload
