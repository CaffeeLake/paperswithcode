# Frontend v2 migration — progress

Living checklist for the work described in [PLAN.md](PLAN.md). Update this file as implementation advances.

**For coding agents**

- Set **Status** to one of: `pending` | `in_progress` | `done`.
- When you finish or partially complete an item, change its status and add a short **Agent notes** bullet list (what merged, PR link, caveats, follow-ups).
- Prefer updating only the sections you touched; keep IDs stable (`deps`, `ts`, …) so history and grep stay usable.
- The canonical spec remains in PLAN.md; this file is execution state only.

---

## deps

- **Status:** pending
- **Agent notes:**
  - _None yet._

Add missing npm dependencies (router, react-query, TS, Tailwind, shadcn primitives, KaTeX, recharts, lucide, etc.) and a proper vite.config with /api proxy + tsconfig + eslint.

---

## ts

- **Status:** pending
- **Agent notes:**
  - _None yet._

Convert frontend_v2's JSX to TypeScript and define props interfaces for App, Header, PaperCard, all View components, and shared components.

---

## router

- **Status:** pending
- **Agent notes:**
  - _None yet._

Introduce react-router-dom and replace App.jsx's view-state machine with /, /papers, /paper/:arxivId, /tasks, /tasks/:taskSlug, /methods, /methods/:methodSlug, /benchmark/:datasetSlug, /cron-dashboard routes (the same paths as v1, no redirects required).

---

## api

- **Status:** pending
- **Agent notes:**
  - _None yet._

Port frontend/src/lib/api.ts, src/hooks/, src/lib/slug.ts and wrap the app in QueryClientProvider.

---

## schema

- **Status:** pending
- **Agent notes:**
  - _None yet._

Add backend schema for new fields (papers.tldr, papers.num_pages, papers.hf_upvotes columns + institutions table + paper_institutions junction) via add_v2_schema.sql + run_add_v2_schema.py per existing backend/database/migrations/ convention (no Alembic). Plus insert_canonical_methods.sql for 3 missing Method rows (attention, vit, mixture-of-experts). Update SQLAlchemy + Pydantic models. Schema-only — no data ingestion in this migration; UI hides each surface gracefully when null/empty.

---

## transform

- **Status:** pending
- **Agent notes:**
  - _None yet._

Build transformPaperForUI / transformTaskForUI / transformMethodForUI / transformBenchmarkForUI helpers that map backend types into the props the v2 components expect, and drop the hardcoded fixtures in src/data.js. Drop submitter, comments, and the v2 upvote button outright (App.jsx upvotes state + onUpvote prop chain through FeedView/TagBrowseView/MethodDetailView/PaperDetailView/SearchOverlay all go away); derive nothing — just hide them.

---

## papers

- **Status:** pending
- **Agent notes:**
  - _None yet._

Wire FeedView, TagBrowseView, MethodDetailView, and the new /papers list to real paper queries (incl. trending velocity from /papers/trending).

---

## paper_detail

- **Status:** pending
- **Agent notes:**
  - _None yet._

Rebuild PaperDetailView against /papers/arxiv/:arxivId?include_resources=true: real authors with toggle, repositories, project pages, evaluations table linking to Benchmark page, optional HF panel. Multi-version selector wires to ?version= query param via React Router setSearchParams (defaults to is_latest_version=True). Hide TL;DR / institution / upvote / pdf-pages surfaces when null.

---

## tasks

- **Status:** pending
- **Agent notes:**
  - _None yet._

Rebuild TagsIndexView from /areas + getAreaTasks rendering the 6 backend areas verbatim ("Computer Vision / Natural Language Processing / General / Audio / Time-series / Other"), and TagBrowseView (= task detail) from /tasks/:taskSlug with real datasets/benchmarks, sister tasks, common methods, and papers.

---

## methods

- **Status:** pending
- **Agent notes:**
  - _None yet._

Rebuild MethodsIndexView and MethodDetailView from /methods grouped by area_id, sorted by paper_count desc within each area. MethodDetailView figure resolution = dictionary first (canonical slugs) → method.image_url → GenericFig last. Insert missing canonical methods (attention, vit, mixture-of-experts) as Method rows.

---

## benchmark

- **Status:** pending
- **Agent notes:**
  - _None yet._

Rebuild BenchmarkDetailView from datasetSlug → dataset + tasks + evaluations + metric direction, computing the SOTA-progression series from evaluations sorted by paper.published.

---

## search

- **Status:** pending
- **Agent notes:**
  - _None yet._

Replace SearchOverlay's in-memory filter with debounced /papers/search?q calls only (papers-only, no tasks/methods/datasets). Keep v2's full-screen overlay layout. Preserve ⌘K shortcut.

---

## polish

- **Status:** pending
- **Agent notes:**
  - _None yet._

Add Skeleton / Loader2 / Alert states across views, KaTeX (LatexTitle) for paper titles and abstracts, long-author toggle, toast notifications, mobile hamburger nav, API status indicator, real PaperThumbnail with /api/thumbnails fallback, multi-version selector.

---

## auth

- **Status:** pending
- **Agent notes:**
  - _None yet._

Add GitHub OAuth backend (auth router, signed JWT in httpOnly cookie with per-environment Domain, OAuth state JWT for CSRF, allowlist via PWC_ADMIN_GITHUB_USERNAMES env var, require_admin middleware on write endpoints, /api/v1/auth/{login,callback,logout,me}). Register one GitHub OAuth App with two callback URLs (prod + staging). Extend CORS to include staging.paperswithcode.co. CRON jobs untouched — they call SQLAlchemy directly, never HTTP write endpoints.

---

## admin

- **Status:** pending
- **Agent notes:**
  - _None yet._

Port EditTasksDialog / EditMethodsDialog / EditRepositoriesDialog / EditEvaluationsDialog and indexPaperFromArxiv into v2. Add /admin/login route with "Log in with GitHub" button, auth Context, conditional rendering of edit UI, 401 handling.

---

## cron_dashboard

- **Status:** pending
- **Agent notes:**
  - _None yet._

Port /cron-dashboard route — render existing CronDashboard.tsx inside v2's Header chrome; body keeps raw shadcn (Card/Badge/progress bars). Zero re-skin work.

---

## staging

- **Status:** pending
- **Agent notes:**
  - _None yet._

Set up staging.paperswithcode.co — separate nginx server block proxying to port 8081 with WebSocket upgrade headers for Vite HMR, dedicated Let's Encrypt cert, Vite staging-mode config (allowedHosts + wss HMR), frontend_v2 dev server runs as systemd unit `frontend-staging.service` on 8081 throughout development for live preview against production backend.

---

## cutover

- **Status:** pending
- **Agent notes:**
  - _None yet._

Cutover sequence — atomic rename: stop services, git mv frontend frontend_legacy, git mv frontend_v2 frontend, restart, smoke-test. ~30s downtime. Keep frontend_legacy running on port 8081 behind nginx fallback for 1-week rollback window.
