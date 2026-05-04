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

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Add missing npm dependencies (router, react-query, TS, Tailwind, shadcn primitives, KaTeX, recharts, lucide, etc.) and a proper vite.config with /api proxy + tsconfig + eslint.

**Sub-tasks:**

- [ ] Install routing + data deps (`react-router-dom`, `@tanstack/react-query`)
- [ ] Install TypeScript toolchain (`typescript`, `@types/react`, `@types/react-dom`, `@types/node`, `eslint`, `typescript-eslint`)
- [ ] Install styling deps (`tailwindcss`, `tailwindcss-animate`, `@tailwindcss/typography`, `postcss`, `autoprefixer`, `class-variance-authority`, `clsx`, `tailwind-merge`)
- [ ] Install LaTeX deps (`katex`, `rehype-katex`, `remark-math`, `remark-gfm`)
- [ ] Install forms/dialog deps (`react-hook-form`, `@hookform/resolvers`, `zod`, required `@radix-ui/react-*` primitives)
- [ ] Install charts + icons/UX deps (`recharts`, `lucide-react`, `sonner`, `cmdk`, `date-fns`)
- [ ] Port 48 shadcn UI components from `frontend/src/components/ui/`
- [ ] Write `vite.config.ts` (host `::`, port 8080, `strictPort`, HMR config, `/api` → `127.0.0.1:8000` proxy, `@` → `./src` alias)
- [ ] Add staging Vite mode (port 8081, `allowedHosts: ['staging.paperswithcode.co']`, `hmr.host`/`hmr.protocol: 'wss'`/`hmr.clientPort: 443`)
- [ ] Add `tsconfig.json`, `tsconfig.node.json`, `eslint.config.js`

---

## ts (plan §2)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Convert frontend_v2's JSX to TypeScript and define props interfaces for App, Header, PaperCard, all View components, and shared components.

**Sub-tasks:**

- [ ] Convert `App.jsx`, `components.jsx`, `views.jsx`, `data.js`, `main.jsx` → `.tsx` / `.ts`
- [ ] Define props interfaces for `PaperCard`, `Header`, `TagChip`, `MethodChip`, `MethodFigure`, `BenchmarkChart`, `Sparkline`, `PdfThumbnail`, `SearchOverlay`
- [ ] Define props interfaces for the eight views (`FeedView`, `TagsIndexView`, `TagBrowseView`, `MethodsIndexView`, `MethodDetailView`, `BenchmarkDetailView`, `PaperDetailView`, plus the new `PapersListView`)
- [ ] Reuse API types from `lib/api.ts` (`Paper`, `Repository`, `Task`, `Method`, `Dataset`, `Evaluation`, `Metric`, `PaginatedResponse<T>`, `TrendingPaper`, …) rather than redefining

---

## router (plan §3)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Introduce react-router-dom and replace App.jsx's view-state machine with /, /papers, /paper/:arxivId, /tasks, /tasks/:taskSlug, /methods, /methods/:methodSlug, /benchmark/:datasetSlug, /cron-dashboard routes (the same paths as v1, no redirects required).

**Sub-tasks:**

- [ ] Wrap app in `<BrowserRouter>`; build the route table (`/`, `/papers`, `/paper/:arxivId`, `/tasks`, `/tasks/:taskSlug`, `/methods`, `/methods/:methodSlug`, `/benchmark/:datasetSlug`, `/cron-dashboard`, `*` → NotFound)
- [ ] Remove App-level state machine (`view`, `activeTag`, `activeMethod`, `activeBench`, `activePaper`)
- [ ] Replace `onNavigate` / `onClickTag` / `onOpenPaper` / `onClickMethod` / `onClickBench` with `<Link>` / `useNavigate()`
- [ ] Replace prop-drilled ids with `useParams()` inside each view
- [ ] Wire multi-version selector to `?version=` query param via `setSearchParams` (default: `is_latest_version=True`)
- [ ] Add redirect from `/papers/:arxivId` → `/paper/:arxivId` (v1 compatibility)
- [ ] Add a `NotFound` page for unmatched routes

---

## api (plan §5)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Port frontend/src/lib/api.ts, src/hooks/, src/lib/slug.ts and wrap the app in QueryClientProvider.

**Sub-tasks:**

- [ ] Port `frontend/src/lib/api.ts` (set `API_BASE_URL = '/api/v1'`)
- [ ] Port `frontend/src/hooks/usePapers.ts` (`usePapers`, `usePaper`, `usePaperByArxivId`, `useInfinitePapers`, `useInfiniteTaskPapers`, `useTrendingPapers`)
- [ ] Port `useTasks`, `useMethods`, `useDatasets`, `useEvaluations`, `useMetrics`, `useHuggingFaceRepos`, `useIntersectionObserver`, `usePaperEditState`
- [ ] Port `src/lib/slug.ts`, `src/lib/imagePreloader.ts`, `src/lib/utils.ts`
- [ ] Wrap app in `<QueryClientProvider>` with matching defaults (3 retries, exponential backoff, 5-min staleTime, no refetch-on-focus)

---

## schema (plan §11)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Add backend schema for new fields (papers.tldr, papers.num_pages columns) via add_v2_schema.sql + run_add_v2_schema.py per existing backend/database/migrations/ convention (no Alembic). Plus insert_canonical_methods.sql for 3 missing Method rows (attention, vit, mixture-of-experts). Update SQLAlchemy + Pydantic models. Schema-only — no data ingestion in this migration; UI hides each surface gracefully when null/empty. Institutions and hf_upvotes are deferred entirely (no schema, no UI) — tracked as future work.

**Sub-tasks:**

- [ ] Write `backend/database/migrations/add_v2_schema.sql` (idempotent `ALTER TABLE` for `papers.tldr TEXT NULL` and `papers.num_pages INTEGER NULL`)
- [ ] Write `backend/database/migrations/run_add_v2_schema.py` runner (mirrors `run_add_trending_score.py`, with `information_schema.columns` verification)
- [ ] Write `backend/database/migrations/insert_canonical_methods.sql` for `attention`, `vit`, `mixture-of-experts` (fully-curated stubs, `image_url = NULL`, `ON CONFLICT DO NOTHING`)
- [ ] Update `backend/models/database.py` — add `tldr` / `num_pages` `Mapped` columns on `DBPaper`
- [ ] Update `backend/models/api.py` — add optional `tldr` / `num_pages` fields on `Paper`
- [ ] Update `docs/DATABASE_SCHEMA_UML.md` with the new columns
- [ ] Verify locally: run both migrations, confirm `SELECT` returns the 3 method rows and new columns exist

---

## transform (plan §4, §6)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Build transformPaperForUI / transformTaskForUI / transformMethodForUI / transformBenchmarkForUI helpers that map backend types into the props the v2 components expect, and drop the hardcoded fixtures in src/data.js. Drop submitter, comments, and the v2 upvote button outright (App.jsx upvotes state + onUpvote prop chain through FeedView/TagBrowseView/MethodDetailView/PaperDetailView/SearchOverlay all go away); derive nothing — just hide them.

**Sub-tasks:**

- [ ] Implement `transformPaperForUI` (maps `Paper` → PaperCard props; formats `published` via `date-fns`, sums official-repo stars, resolves `project_pages[0]?.url`, deterministic chip hue from `task.slug`)
- [ ] Implement `transformTaskForUI` (Task + sister tasks + datasets + methods)
- [ ] Implement `transformMethodForUI` (figure resolution inputs: slug, `image_url`)
- [ ] Implement `transformBenchmarkForUI` (Dataset + evaluations + metric direction → leaderboard + SOTA series)
- [ ] Delete hardcoded fixtures (`PAPERS`, `DOMAINS`, `METHODS`, `METHOD_CATEGORIES`, `BENCHMARKS`, `DOMAIN_DETAILS`, `MODALITY_GROUPS`) in `src/data.js`
- [ ] Remove `upvotes` state + `upvote(paperId)` handler from `App.jsx`
- [ ] Remove `onUpvote` / `upvotes` prop chain through `FeedView` / `TagBrowseView` / `MethodDetailView` / `PaperDetailView` / `SearchOverlay`
- [ ] Remove upvote button, upvote count chip, institution chip, submitter, comments count from `PaperCard`
- [ ] Hide `tldr` panel and PDF page-count affordance when their underlying fields are null

---

## papers (plan §4.6, §7)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Wire FeedView, TagBrowseView, MethodDetailView, and the new /papers list to real paper queries (incl. trending velocity from /papers/trending).

**Sub-tasks:**

- [ ] `FeedView` — switch papers list + sidebar "Top Domains" to real queries; implement period switcher date filter per §7.1 (visitor local TZ, ISO Mon-Sun week, calendar month)
- [ ] `FeedView` — when `sortBy === 'trending'`, call `getTrendingPapers()` and use `trending.velocity_24h` directly (replace `computeStarsPerHour`)
- [ ] `TagBrowseView` — wire papers list to real queries via `useInfiniteTaskPapers(taskId)`
- [ ] `MethodDetailView` — wire papers list to real queries
- [ ] Build `/papers` (`PapersListView`) as a clone of FeedView: title "All Papers", period switcher as date filter, inline search driving `?search=`, sort options (trending / newest / most cited), infinite scroll via `useInfinitePapers` + `useIntersectionObserver`
- [ ] `/papers` sidebar: reuse "Top Domains"; drop the mock "Filters" section; drop conference filter (documented regression)

---

## paper_detail (plan §4.5, §9)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Rebuild PaperDetailView against /papers/arxiv/:arxivId?include_resources=true: real authors with toggle, repositories, project pages, evaluations table linking to Benchmark page, optional HF panel. Multi-version selector wires to ?version= query param via React Router setSearchParams (defaults to is_latest_version=True). Hide TL;DR / pdf-pages surfaces when null. Drop the institution chip and the upvote count chip outright (both deferred — see PLAN §11.2 / §11.1).

**Sub-tasks:**

- [ ] Fetch via `usePaperByArxivId(arxivId, { version, include_resources: true })`
- [ ] Render real author list with `showAllAuthors` toggle (limit 30)
- [ ] Render real `paper.repositories` with star counts, `Official` badge, source tag
- [ ] Render real `paper.project_pages` links
- [ ] Render evaluations table grouped by task; link each row to `/benchmark/:dataset.slug`
- [ ] Optional HF panel wired to `useHuggingFaceRepos` (or remove entirely if trimming scope)
- [ ] Multi-version selector inline in meta line: static text when `versions.length === 1`, dropdown when `> 1`; mutates `?version=` via `setSearchParams`
- [ ] Hide "TL;DR · AI-generated" panel when `tldr` is null
- [ ] Do not surface `num_pages` in UI (schema-only)
- [ ] Remove institution chip and upvote count chip

---

## tasks (plan §4.2)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Rebuild TagsIndexView from /areas + getAreaTasks rendering the 6 backend areas verbatim ("Computer Vision / Natural Language Processing / General / Audio / Time-series / Other"), and TagBrowseView (= task detail) from /tasks/:taskSlug with real datasets/benchmarks, sister tasks, common methods, and papers.

**Sub-tasks:**

- [ ] `TagsIndexView` — fetch `getAreas()` + `getAreaTasks(areaId)` for each of the 6 areas; render their names verbatim
- [ ] Sidebar "Top Domains" — `apiClient.getTasks({ ordering: '-paper_count', page_size: 8 })`
- [ ] `TagBrowseView` — resolve `:taskSlug` → `Task`; render `task.description` as the explainer (hide block when null)
- [ ] `TagBrowseView` — render sister tasks (sibling tasks under same `area_id`)
- [ ] `TagBrowseView` — render datasets/benchmarks via `getTaskDatasets(taskId)` + `getEvaluationsByDataset(datasetId)`
- [ ] `TagBrowseView` — render common methods section
- [ ] `TagBrowseView` — render papers list (paginated/infinite)

---

## methods (plan §4.3)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Rebuild MethodsIndexView and MethodDetailView from /methods grouped by area_id, sorted by paper_count desc within each area. MethodDetailView figure resolution = dictionary first (canonical slugs) → method.image_url → GenericFig last. Insert missing canonical methods (attention, vit, mixture-of-experts) as Method rows.

**Sub-tasks:**

- [ ] `MethodsIndexView` — fetch methods via paginated `apiClient.getMethods({ page_size: 100 })` (fetch all pages in parallel, like v1)
- [ ] Group into 4 sections (Computer Vision / NLP / General / Audio) by `area_id`; sort by `paper_count` desc within each
- [ ] Drop v2's `METHOD_CATEGORIES` 7-bucket sub-grouping
- [ ] `MethodDetailView` — implement 3-tier figure resolution: (1) dictionary match on canonical slugs (`transformer`, `attention`, `cnn`, `u-net`, `vit`, `mixture-of-experts`, `diffusion`, `gan`, `vae`, `rlhf`) → hand-drawn SVG from `components.jsx`; (2) `method.image_url`; (3) `GenericFig`
- [ ] Ensure canonical method rows (`attention`, `vit`, `mixture-of-experts`) exist via the schema migration (§schema)
- [ ] `MethodDetailView` — render papers list via real query

---

## benchmark (plan §4.4)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Rebuild BenchmarkDetailView from datasetSlug → dataset + tasks + evaluations + metric direction, computing the SOTA-progression series from evaluations sorted by paper.published.

**Sub-tasks:**

- [ ] Resolve `:datasetSlug` → `Dataset` via `apiClient.getDataset(slug)`
- [ ] Fetch leaderboard rows via `getEvaluationsByDataset(datasetId, bestMetric)` (already sorted by `best_rank`)
- [ ] Compute `sota` / `sotaModel` from the top-ranked evaluation
- [ ] Compute `series` / `seriesDates` from evaluations sorted by `paper.published`, taking the running best (mirror logic in v1 `Benchmark.tsx`)
- [ ] Resolve metric direction via `apiClient.getMetricDirections()` → map to `'↑'` / `'↓'`
- [ ] Render leaderboard table + SOTA progression chart

---

## search (plan §6)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Replace SearchOverlay's in-memory filter with debounced /papers/search?q calls only (papers-only, no tasks/methods/datasets). Keep v2's full-screen overlay layout. Preserve ⌘K shortcut.

**Sub-tasks:**

- [ ] Replace in-memory filter with 300ms-debounced `apiClient.searchPapers(q, { limit: 8 })`
- [ ] Remove the "Domains" section from overlay (papers-only); collapse layout
- [ ] Keep ⌘K shortcut binding in `App.jsx`
- [ ] Keep v2's full-screen overlay layout intact

---

## polish (plan §9)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Add Skeleton / Loader2 / Alert states across views, KaTeX (LatexTitle) for paper titles and abstracts, long-author toggle, toast notifications, mobile hamburger nav, API status indicator, real PaperThumbnail with /api/thumbnails fallback, multi-version selector.

**Sub-tasks:**

- [ ] Add `Skeleton` / `Loader2` / `Alert` states consistently across all views
- [ ] Wrap paper titles and abstracts with `<LatexTitle>` (port from v1)
- [ ] Add `frontend_v2/src/katex-overrides.css` (inherit `currentColor`, `vertical-align: baseline`, optional font-size tweak; no font-family override)
- [ ] Implement `showAllAuthors` toggle (limit 30) for long author lists
- [ ] Add `Toaster` (shadcn) + Sonner; emit toasts on edit success/failure and API errors
- [ ] Add mobile hamburger nav (breakpoint ≤1100px) with drawer
- [ ] Port `ApiStatus` indicator into the header
- [ ] Replace hand-drawn `PdfThumbnail` with real `PaperThumbnail` (prefer `thumbnail_url`, fall back to `/api/thumbnails/`, last-resort `PdfThumbnail` SVG)
- [ ] Multi-version selector in meta line (covered in `paper_detail`; verify integration)
- [ ] Clean up `frontend/index.html` (real `<title>`, real `og:title` / `og:description`, `og-default.png` in `public/`, drop Lovable `author` / `twitter:site`)

---

## admin (plan §8)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Port EditTasksDialog / EditMethodsDialog / EditRepositoriesDialog / EditEvaluationsDialog and indexPaperFromArxiv into v2. No auth gate this migration (matches v1 behavior — admin UI is visible to everyone). Real auth is tracked as a separate workstream in [AUTH.md](AUTH.md).

**Sub-tasks:**

- [ ] Port `EditTasksDialog` (`PUT /papers/:id/tasks`)
- [ ] Port `EditMethodsDialog`
- [ ] Port `EditRepositoriesDialog`
- [ ] Port `EditEvaluationsDialog` (`POST` / `PUT` / `DELETE` `/evaluations/`)
- [ ] Port `EvaluationResultsCard` (grouped-by-task result table) into `PaperDetailView`
- [ ] Port `indexPaperFromArxiv()` (`POST /papers/index/:arxivId`) entry point
- [ ] Accept hybrid styling (raw shadcn for admin surfaces; no auth gate)

---

## cron_dashboard (plan §7)

- [ ] **Section complete**
- **Agent notes:**
  - _None yet._

Port /cron-dashboard route — render existing CronDashboard.tsx inside v2's Header chrome; body keeps raw shadcn (Card/Badge/progress bars). Zero re-skin work.

**Sub-tasks:**

- [ ] Add `/cron-dashboard` route
- [ ] Port `CronDashboard.tsx` unchanged
- [ ] Wrap body with v2's `<Header>` chrome; body keeps raw shadcn (no re-skin)

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
