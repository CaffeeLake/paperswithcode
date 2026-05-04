---
name: frontend v2 migration gaps
overview: Comprehensive gap analysis for replacing the current React/TypeScript frontend with the new design-first `frontend_v2/`. The new code is a pixel-perfect mock built on hardcoded data with no backend, no router, and no TypeScript — every layer between UI and the existing FastAPI / PostgreSQL data model has to be added before migration. Migration goal is **feature parity with v1 + redesign**: every existing route and capability ships under the v2 visual system.
progress: progress.md
isProject: false
---

# Frontend v2 Migration Gap Analysis

**Implementation checklist** (status + agent notes): [progress.md](progress.md).

## TL;DR

`frontend_v2/` is a **design prototype**, not an application. It is ~6 files of vanilla JSX rendering hardcoded fixtures (`PAPERS`, `DOMAINS`, `METHODS`, `BENCHMARKS`, `DOMAIN_DETAILS`, etc.) inside [src/data.js](frontend_v2/src/data.js). The visual system is excellent and worth keeping; the application plumbing all has to be built from scratch and reconciled with the existing backend's data model.

The migration bar is **feature parity with v1 + redesign + introduce real auth**: every existing route and capability must work under the v2 visual system before cutover, and the existing unauthenticated write endpoints are gated by GitHub OAuth as part of this migration. Admin dialogs are not in the v2 design at all and ship behind that auth gate; everything else (`/papers`, `/cron-dashboard`, multi-version UI, LaTeX rendering, long-author toggle, loading/error/empty states, toasts, mobile hamburger, API-status indicator, thumbnail generation) is a hard requirement for cutover.

The gaps fall into **13 sections**, listed below — the first 9 mirror the original analysis (build/tooling, TS, routing, data model, API client, search, parity-required pages, admin, UX), and the new §10–§13 capture decisions made during planning (styling system, schema additions, backend gaps, cutover plan).

---

## 1. Build / tooling / dependencies

`frontend_v2/package.json` only has `react`, `react-dom`, `vite`, and `@vitejs/plugin-react`. Compared with [frontend/package.json](frontend/package.json), all of the following are missing and need to be added:

- **Routing** — `react-router-dom` (frontend uses `BrowserRouter` + 9 routes in [frontend/src/App.tsx](frontend/src/App.tsx))
- **Data fetching / cache** — `@tanstack/react-query`
- **TypeScript** — `typescript`, `@types/react`, `@types/react-dom`, `@types/node`, `tsconfig.*`, `eslint`, `typescript-eslint`
- **Styling utilities** — `tailwindcss`, `tailwindcss-animate`, `@tailwindcss/typography`, `postcss`, `autoprefixer`, `class-variance-authority`, `clsx`, `tailwind-merge`
- **LaTeX** — `katex`, `rehype-katex`, `remark-math`, `remark-gfm` (paper titles routinely contain inline math; see [frontend/src/components/LatexTitle.tsx](frontend/src/components/LatexTitle.tsx))
- **Forms / dialogs** — `react-hook-form`, `@hookform/resolvers`, `zod`, plus the relevant `@radix-ui/react-*` primitives (dialog, select, popover, dropdown, toast, …)
- **Charts** — `recharts` (currently `Benchmark.tsx` renders leaderboard SVG with Recharts; v2's hand-rolled SVG chart in `views.jsx` is fine to keep but Recharts is needed for parity features like tooltips/legends)
- **Icons / UX** — `lucide-react`, `sonner`, `cmdk`, `date-fns`
- **Shadcn UI components** — the 48 files in [frontend/src/components/ui/](frontend/src/components/ui) are used pervasively (Button, Card, Badge, Skeleton, Alert, Select, Dialog, Toaster, …)
- **Lovable plugin** — `lovable-tagger` for dev-mode component tagging (optional)

**Vite config** ([frontend_v2/vite.config.js](frontend_v2/vite.config.js) is bare). Must mirror [frontend/vite.config.ts](frontend/vite.config.ts):

- `host: "::"`, `port: 8080`, `strictPort: true`
- `hmr.clientPort: 443`, `hmr.host: 'paperswithcode.co'` (production)
- Proxy `/api` → `http://127.0.0.1:8000`
- `@` alias → `./src`

Without the proxy, the frontend cannot talk to the FastAPI backend at all.

**Staging deploy mode** (used during development, see §13.1) overrides:

- `server.port: 8081`
- `server.allowedHosts: ['staging.paperswithcode.co']` (Vite ≥4 blocks unrecognized `Host` headers by default)
- `hmr.host: 'staging.paperswithcode.co'`, `hmr.protocol: 'wss'`, `hmr.clientPort: 443`

Switch via `vite --mode staging` reading `process.env.VITE_DEPLOY_TARGET` (or a sibling `vite.config.staging.ts`). The nginx server block for staging needs the WebSocket upgrade headers (see §13.1) or HMR silently falls back to long-polling.

## 2. TypeScript migration

V2 is plain JSX. The existing app is fully typed and the API client publishes ~12 interfaces from [frontend/src/lib/api.ts](frontend/src/lib/api.ts) (`Paper`, `Repository`, `ProjectPage`, `Author`, `Area`, `Task`, `Method`, `Dataset`, `Evaluation`, `Metric`, `PaginatedResponse<T>`, `TrendingPaper`).

- Convert `App.jsx`, `components.jsx`, `views.jsx`, `data.js`, `main.jsx` → `.tsx`/`.ts`.
- Define props interfaces for every component (`PaperCard`, `Header`, `TagChip`, `MethodChip`, `MethodFigure`, `BenchmarkChart`, `Sparkline`, `PdfThumbnail`, the eight views, `SearchOverlay`, …).
- Reuse the API types from `lib/api.ts` rather than re-defining (or split shared types into `src/types/`).

## 3. URL routing (currently zero)

`App.jsx` switches views via local React state (`view`, `activeTag`, `activeMethod`, `activeBench`, `activePaper`). Nothing is bookmarkable, the back button doesn't work, and no link can be shared.

Required routes (v2 *"tag"* pages are backend **task** pages; v2 *"modality groups"* are backend **areas** and only need a list page, since `TagsIndexView` already groups tasks by area in one screen):

```typescript
<Route path="/"                        element={<FeedView />} />          // 'feed'
<Route path="/papers"                  element={<PapersListView />} />    // paginated list with search (v1) — REQUIRED
<Route path="/papers/:arxivId"         element={<Navigate to=".../paper/:id" />} />
<Route path="/paper/:arxivId"          element={<PaperDetailView />} />   // v2 'detail' — version via ?version=v2 query param
<Route path="/tasks"                   element={<TagsIndexView />} />     // v2 'tags' — areas with their tasks
<Route path="/tasks/:taskSlug"         element={<TagBrowseView />} />     // v2 'tag'  — one task
<Route path="/methods"                 element={<MethodsIndexView />} />  // 'methods'
<Route path="/methods/:methodSlug"     element={<MethodDetailView />} />  // 'method'
<Route path="/benchmark/:datasetSlug"  element={<BenchmarkDetailView />} />
<Route path="/cron-dashboard"          element={<CronDashboard />} />     // REQUIRED — see Q-CRON for design fit
<Route path="/admin/login"             element={<AdminLogin />} />        // REQUIRED — see §8.1 for OAuth flow
<Route path="*"                        element={<NotFound />} />
```

These match the legacy v1 routes 1:1 — no redirects required, every existing inbound link keeps working.

**Multi-version paper URLs** use a `?version=` query parameter rather than a path segment: `/paper/2604.18221` always loads `is_latest_version=True`, and `/paper/2604.18221?version=v1` loads the explicit v1 row. This mirrors the backend `/papers/arxiv/:id?version=v2` API 1:1, keeps shareable links clean for the 99.98% single-version case, and avoids a server-side redirect on every paper-detail click. The version dropdown in `PaperDetailView` (§9) mutates `?version` via React Router's `setSearchParams`; browser back/forward navigates between versions.

`onNavigate('feed')`, `onClickTag(id)`, `onOpenPaper(id)`, `onClickMethod(id)`, `onClickBench(tag, slug, hi)` need to become `<Link>`s / `useNavigate()` calls. `useParams()` replaces the App-level state. Inside the components, the parameter currently called `tagId` is just a *task slug*.

## 4. Backend / data model reconciliation (the biggest gap)

V2 invents its own shape; the backend has a different one.

**Naming, per user clarification.** v2's source code uses misleading variable names — `DOMAINS` actually holds *tasks*, and `MODALITY_GROUPS` / `DOMAIN_DETAILS[*].parent` hold the *domains*. Once that's untangled the mapping is direct:

| v2 concept | v2 source (file:line) | Backend concept |
| --- | --- | --- |
| Domain (Language, Computer Vision, Multimodal & Generative, Audio, Embodied, Other) | `MODALITY_GROUPS` in [views.jsx#L308-L345](frontend_v2/src/views.jsx#L308); `DOMAIN_DETAILS[*].parent` in [data.js#L571](frontend_v2/src/data.js#L571) | `Area` |
| Task (language-modeling, image-classification, robotics, diffusion-models, …) | `DOMAINS` in [data.js#L2-L21](frontend_v2/src/data.js#L2); `tagId` in `App.jsx`, `views.jsx` | `Task` |
| Paper.tags (string[]) | `PAPERS[i].tags` in [data.js#L30](frontend_v2/src/data.js#L30) | `paper.tasks[*].slug` |
| Benchmark | `DOMAIN_DETAILS[domainId].benchmarks[]` in [data.js#L583](frontend_v2/src/data.js#L583) | `Dataset` + `Evaluation`s |
| Method | `METHODS` in [data.js#L212](frontend_v2/src/data.js#L212) | `Method` |
| Method category (architectures, normalization, …) | `METHOD_CATEGORIES` in [data.js#L256](frontend_v2/src/data.js#L256) | (no backend equivalent — dropped, see §4.3) |

### Live database snapshot (used to size every section below)

Verified directly against the running DB:

- **6 areas**: Computer Vision (15 tasks), Natural Language Processing (3), General (11), Audio (5), Time-series (2), Other (2).
- **38 tasks total** (35 with ≥1 paper).
- **191 methods** (29 CV, 18 NLP, 4 Audio, 139 General, 1 unassigned).
- **396 datasets**.

Curation problems the original plan worried about ("hundreds of tasks", "thousands of methods") don't exist at this scale — the entire taxonomy fits on one screen with room to spare.

### 4.1 Paper

V2 fixture (`PAPERS[i]`):

```javascript
{ id: "2604.18221",        // arxiv-style id used as primary key
  title, authors: string[],
  institution: "Stanford NLP Group",   // single string
  abstract,
  tags: ["language-modeling", ...],    // domain ids
  upvotes: 312, citations: 47,
  date: "Apr 26",                      // free-text day-month
  submitter: "wzhang",
  github: 4200,                        // single int = star count of one repo
  project: "https://...",              // single URL
  pdfPages: 24, year, venue, tldr }
```

Backend `Paper` (from [frontend/src/lib/api.ts](frontend/src/lib/api.ts) lines 30–52):

```typescript
{ id, arxiv_id,                              // separate DB id and arxiv id
  url_abs, url_pdf, thumbnail_url,
  title, abstract,
  authors: string[], published, conference, version, is_latest_version,
  citation_count, semantic_scholar_id,
  repositories?: Repository[],               // array, each with num_stars / is_official / source
  project_pages?: ProjectPage[],             // array
  tasks?: Task[],                            // array of Task objects, not strings
  methods?: Method[] }
```

**Resolved decisions for each v2 field that has no direct backend column:**

| v2 field | Decision | Mechanism |
| --- | --- | --- |
| `id` | Keep `arxiv_id` for URL/display, use DB `id` only for write APIs | transform helper |
| `tags` | `paper.tasks[*].slug` with deterministic-hash chip color | transform helper |
| `submitter` | **Drop entirely** — no UI affordance | remove from PaperCard / PaperDetailView |
| `comments` | **Drop entirely** — no UI affordance | remove count chip from PaperCard |
| `upvote button` (interactive toggle) | **Drop entirely** — v1 has no equivalent toggle, no backend support, out of migration scope. Future work could add it back as a real feature if needed. | remove `upvotes` state + `upvote(paperId)` handler from `App.jsx`; remove `onUpvote`/`upvotes` prop chain from `FeedView`/`TagBrowseView`/`MethodDetailView`/`PaperDetailView`/`SearchOverlay`; remove the upvote button from `PaperCard` |
| `institution` | **Schema added (M2M), no data ingestion this migration** | hide chip when `paper.institutions` is empty (= always, initially) |
| `tldr` | **Schema added (`papers.tldr TEXT NULL`), no generation pipeline this migration** | hide "TL;DR · AI-generated" panel when null |
| `upvotes` | **Schema added (`papers.hf_upvotes INTEGER NULL`), no ingestion this migration** | hide upvote count chip when null |
| `pdfPages` | **Schema added (`papers.num_pages INTEGER NULL`), no ingestion this migration** | replace v2's hand-drawn `PdfThumbnail` SVG with real `PaperThumbnail` regardless; don't surface page count |
| `github` | Sum of stars across `repositories.filter(is_official)` + most-starred link, mirroring [Papers.tsx](frontend/src/pages/Papers.tsx) | transform helper |
| `project` | `project_pages[0]?.url` | transform helper |
| `citations` | `citation_count` | direct |
| `date` | Format `published` (ISO) into v2 short form (`Apr 26`) via `date-fns` | transform helper |

The PaperCard layout in v2 needs to render gracefully when *every* schema-only field is null — that's the steady state for the next several months.

### 4.2 Tasks (= v2 "Domains") and Areas (= v2 "Domain parents / Modality groups")

**Resolved (Q6 = Path A):** render the **6 backend areas verbatim** in `TagsIndexView`. The Browse page reads:

> Computer Vision · Natural Language Processing · General · Audio · Time-series · Other

V2's curated label set ("Language / Multimodal & Generative / Embodied") is dropped; the backend area names take over. No frontend mapping layer, no DB restructure.

**`DOMAINS` replacement.** Backend has only 38 tasks total, so render every task in `TagsIndexView` — no curation needed. Hue per task is cosmetic, derived deterministically from `task.slug`. The v2 sidebar's "Top Domains" becomes `apiClient.getTasks({ ordering: '-paper_count', page_size: 8 })`.

**`DOMAIN_DETAILS`** ([frontend_v2/src/data.js#L571](frontend_v2/src/data.js#L571)) holds per-task metadata that the backend already covers:

| v2 field | Backend source |
| --- | --- |
| `parent` (e.g. "Language") | `task.area_id` → `area.name` |
| `explainer` (prose) | `task.description` |
| `sisters` (related tasks) | sibling tasks under the same `area_id` |
| `benchmarks` (datasets + leaderboards) | `getTaskDatasets(taskId)` + `getEvaluationsByDataset(datasetId)` |

So `TagBrowseView` is simply a task-detail view backed by `getTask(slug)` + four sub-queries.

### 4.3 Method ↔ Method

**Resolved (Q7):** group methods by `area_id` only — no `Method.category` column, no v2-style 7-bucket sub-grouping. `MethodsIndexView` renders 4 sections (Computer Vision · NLP · General · Audio), sorted by `paper_count` desc within each. The "General" bucket is large (~139 methods) but accurate; no further curation.

V2's `METHOD_CATEGORIES` constant (`architectures`, `normalization`, …) is discarded. Backend `Method` schema is unchanged.

**Other Method-shape mapping**:

- Replace v2's hardcoded `METHODS` array with `apiClient.getMethods({ page_size: 100 })` (paginated; current Methods.tsx fetches all pages in parallel — keep that pattern).
- `Method` already has `id`, `slug`, `name`, `full_name`, `description`, `area_id`, `introduced_year`, `source_url`, `source_title`, `image_url`, `paper_count` — all the fields the design needs.
**Resolved (Q-FIG):** figure resolution in `MethodDetailView` is a 3-tier fallback chain:

1. If `method.slug` is one of the canonical slugs (`transformer`, `attention`, `cnn`, `u-net`, `vit`, `mixture-of-experts`, `diffusion`, `gan`, `vae`, `rlhf`), render the matching v2 hand-drawn SVG from [components.jsx](frontend_v2/src/components.jsx#L572-L1168) (`TransformerFig`, `AttentionFig`, `CNNFig`, `UNetFig`, `ViTFig`, `MoEFig`, `DiffusionFig`, `GANFig`, `VAEFig`, `RLHFFig`).
2. Else, if `method.image_url` is non-empty, render that image (covers ~95% of methods).
3. Else, render `GenericFig`.

Live DB measurement: 95.3% of methods (182/191) have `image_url`, so tier 2 is the dominant case. Of the 10 canonical slugs, 3 (`attention`, `vit`, `mixture-of-experts`) are missing as `Method` rows in the DB and need to be inserted in this migration so tier 1 fires for them. The other 7 canonical methods exist; their hardcoded figures take precedence over their (heterogeneous third-party) `image_url` values, which is the explicit point of the dictionary.

### 4.4 Benchmark ↔ Dataset + Evaluation

V2 nests benchmarks inside `DOMAIN_DETAILS[domainId].benchmarks[]` ([frontend_v2/src/data.js](frontend_v2/src/data.js#L571-L860)) with `{name, metric, arrow, sota, sotaModel, series, seriesDates, leaderboard: [{model, value, paper, paperId, code, year, date}]}`. Backend separates this into:

- `Dataset` (`/datasets/`) — with `slug`, `name`, `description`, *task* associations (note: datasets are linked to **tasks**, not areas, so the area page must walk through tasks to enumerate benchmarks)
- `Evaluation` (`/evaluations/`) — links `paper_id × task_id × dataset_id`, has `metrics: Record<string, string>`, `best_metric`, `model_name`, `methodology`, `best_rank`
- `Metric` (`/metrics/`) — with `direction: 'higher_is_better' | 'lower_is_better'` (replaces v2's `arrow: '↑'/'↓'`)

The backend mapping work to render `BenchmarkDetailView`:

- Resolve `:datasetSlug` → `Dataset`. The `tagId` carried in app state (a *task* slug) is informational; v2's URL is `/benchmark/:datasetSlug` only.
- `apiClient.getEvaluationsByDataset(datasetId, bestMetric)` returns the leaderboard rows (already sorted by `best_rank`).
- Compute `series`/`seriesDates` (the SOTA progression chart) from evaluations sorted by `paper.published`, taking the running best — see [frontend/src/pages/Benchmark.tsx](frontend/src/pages/Benchmark.tsx) for the exact logic.
- Compute `sota` / `sotaModel` from the top-ranked evaluation.
- Get metric direction via `apiClient.getMetricDirections()` and map to `'↑'/'↓'`.
- The `[Compare →]` link on `PaperDetailView`'s results table needs `dataset.slug`, which means storing `dataset_id` (not just a name) in the backing data model — already done in `Evaluation.dataset_id`.

### 4.5 Author / Repository / Project page

These are unrepresented in v2. The current frontend renders an avatar list with colors, "show all authors" toggle (limit 30), per-repo `Github` cards with star counts and `Official` badges, and project page links. The new `PaperDetailView` sidebar shows hardcoded `paper.submitter/<id>-code` and `community/repro-<id>` rows — these need to be replaced with real `paper.repositories` and `paper.project_pages`.

The Hugging Face panel in v2's sidebar is also entirely fabricated (hardcoded `model-7b`, `curated`, `demo`). Either remove or wire to the existing `useHuggingFaceRepos` hook in [frontend/src/hooks/useHuggingFaceRepos.ts](frontend/src/hooks/useHuggingFaceRepos.ts).

### 4.6 Trending velocity

V2 computes `computeStarsPerHour(paper)` deterministically from `paper.upvotes / daysAgo + jitter` ([components.jsx#L479](frontend_v2/src/components.jsx#L479)). Backend exposes the real value via `/api/v1/papers/trending` returning `{ trending: { velocity_24h, trending_score, stars_gained_24h } }` per `TrendingPaper` ([api.ts#L172](frontend/src/lib/api.ts#L172)). When `sortBy === 'trending'`, the FeedView should call `getTrendingPapers()` and use `trending.velocity_24h` directly.

## 5. API client + data hooks (entirely missing in v2)

Port these wholesale from frontend/ — they already align with the backend and have no v2-specific design coupling:

- [frontend/src/lib/api.ts](frontend/src/lib/api.ts) (~787 lines) — single `ApiClient` class wrapping every endpoint. Update `API_BASE_URL` to `'/api/v1'` once the vite proxy is in place.
- [frontend/src/hooks/usePapers.ts](frontend/src/hooks/usePapers.ts) — `usePapers`, `usePaper`, `usePaperByArxivId`, `useInfinitePapers`, `useInfiniteTaskPapers`, `useTrendingPapers`.
- [frontend/src/hooks/useTasks.ts](frontend/src/hooks/useTasks.ts), `useMethods`, `useDatasets`, `useEvaluations`, `useMetrics`, `useHuggingFaceRepos`, `useIntersectionObserver`, `usePaperEditState`.
- `slug.ts` — `slugify()`, `getMethodSlug()` ([frontend/src/lib/slug.ts](frontend/src/lib/slug.ts)).
- `imagePreloader.ts`, `utils.ts`.

Wrap the app in `<QueryClientProvider>` with the same defaults as [frontend/src/App.tsx](frontend/src/App.tsx#L17-L27) (3 retries, exponential backoff, 5-min staleTime, no refetch-on-focus).

## 6. Search

**Resolved (Q9 = SR1, papers-only):**

Keep v2's full-screen `SearchOverlay` layout exactly. Replace its in-memory string-matching against the 12 hardcoded papers + 18 domains with a single live data source:

- 300ms debounced fetch to `/api/v1/papers/search?q=...&limit=8` (mirrors [PaperSearch.tsx](frontend/src/components/PaperSearch.tsx#L34-L56)).
- **No** parallel calls to tasks / methods / datasets endpoints. The "Domains" section in v2's overlay is removed; the layout collapses to papers-only.
- ⌘K shortcut binding is already in `App.jsx` — keep it.

The standalone `/papers?search=...` URL pattern is still supported via the `/papers` listing page (§7).

## 7. Pages required by feature parity

All three pages below are **hard requirements** for cutover (per migration philosophy: feature parity + redesign):

- **`/papers` (Q-PAPERS resolved).** Paginated full list with date filter, search, sort, and infinite scroll ([Papers.tsx](frontend/src/pages/Papers.tsx)). V2 has no equivalent design — `/papers` is built as a clone of `FeedView`'s two-column layout:
  - **Header**: title becomes "All Papers" (vs. FeedView's "Trending Research"). Date navigation arrows are dropped.
  - **Period switcher** (Today / This Week / This Month / All Time) doubles as the date filter, with semantics defined in §7.1.
  - **Sidebar**: "Top Domains" section identical to FeedView. The mock "Filters" section ("Has code", "Reproduced results", "From institution") is removed — none of those map to real backend filters at this stage.
  - **Inline search input** below the title, drives `?search=foo` URL state so searches are bookmarkable. (The full-screen search overlay from §6 is for global navigation; this inline input is /papers-specific.)
  - **Sort options** (trending / newest / most cited) mirror FeedView's `sort-bar`.
  - **Infinite scroll** via `useInfinitePapers` + `useIntersectionObserver` from v1.

  **Documented feature regression:** v1's conference filter dropdown is **dropped for this migration** and not part of cutover. Deferred to a follow-up — would re-introduce as a chip multi-select in the sidebar when added back.

### 7.1 Period switcher / date filter semantics (FeedView + /papers)

- **Reference field**: `papers.published` (arXiv submission date). Not `created_at` (would surface backfilled-from-PWC-archive papers as "trending today").
- **Timezone**: **visitor's browser local TZ**, computed client-side. Backend stays stateless and TZ-agnostic — frontend computes the cutoff in local time, converts to a UTC ISO string via `.toISOString()`, and passes as `published_after=` to `/api/v1/papers/`.
- **Boundary semantics**:
  - **Today** = midnight of the visitor's current local day (i.e. `startOfDay(now)` in local TZ → UTC).
  - **This Week** = ISO calendar week starting **Monday 00:00 local** (`startOfWeek(now, { weekStartsOn: 1 })`). Not rolling 7-day.
  - **This Month** = 1st of the visitor's current calendar month, 00:00 local (`startOfMonth(now)`). Not rolling 30-day.
  - **All Time** = no filter (omit `published_after`).
- All boundary computation uses `date-fns` (already in the §1 dep list); no `date-fns-tz` needed since `Date` objects respect local TZ by default.
- Backend index `idx_papers_date_published` on `papers.date_published` (per [backend/models/database.py:117](backend/models/database.py#L117)) already exists — the `published_after=` filter is fast at scale, no new index needed.
- TanStack Query cache key includes the cutoff timestamp; the key naturally changes only at local midnight / local Monday 00:00 / local 1st-of-month 00:00. No per-minute cache churn.
- Accepted trade-off: a visitor in Tokyo (UTC+9) loading at 9 AM JST sees "Today" containing what a UTC-tracker would call "yesterday's papers". This is the intended consequence of choosing visitor TZ; reflects the visitor's local mental model of "today".

- **`/cron-dashboard` (Q-CRON resolved).** Operations dashboard ([CronDashboard.tsx](frontend/src/pages/CronDashboard.tsx)). Ported as-is — the existing component is wrapped in v2's `<Header>` chrome but its body keeps using raw shadcn (`Card`, `Badge`, progress bars, status indicators). This matches the visual treatment of admin dialogs (§8): chrome is v2, content is shadcn, accepted operationally because it's not a user-facing surface. No re-skin work; no behavior changes. Zero rewrite risk.
- `404` page ("NotFound") for unmatched routes — small but required.

## 8. Admin / write features

Migration philosophy keeps these as a **hard requirement, but gated by real authentication** (they are not in the v2 design at all). Currently in [PaperDetail.tsx](frontend/src/pages/PaperDetail.tsx) and the [paper-detail/](frontend/src/components/paper-detail/) subfolder:

- `EditTasksDialog` — edit which tasks a paper belongs to (`PUT /papers/:id/tasks`).
- `EditMethodsDialog` — same for methods.
- `EditRepositoriesDialog` — add/remove official/unofficial GitHub repos.
- `EditEvaluationsDialog` — add / update / delete evaluation rows (`POST/PUT/DELETE /evaluations/`).
- `EvaluationResultsCard` — grouped-by-task result table.
- `indexPaperFromArxiv()` — `POST /papers/index/:arxivId` to ingest a missing paper from arXiv.

These ports use raw shadcn components (per Q8 = S1, hybrid styling), so they will look distinct from v2-styled surfaces — that visual gap is accepted to keep the migration scope narrow.

The same goes for the `Methodology`, `best_metric`, `Evaluated on (date)`, and `Methodology` fields in `Evaluation` — none of these surface in v2's leaderboard but they remain available via the admin dialogs.

### 8.1 Authentication (Q-ADMIN + Q-AUTH resolved)

This migration introduces real auth on the backend and admin-gate UI on the frontend. The current state is no auth on either side; this is the moment to formalize.

**Identity model: GitHub OAuth with a username allowlist** (option U4).

- New env vars in `backend/keys.env`:
  - `PWC_GITHUB_OAUTH_CLIENT_ID` — single OAuth App (see "GitHub OAuth App setup" below)
  - `PWC_GITHUB_OAUTH_CLIENT_SECRET`
  - `PWC_JWT_SECRET` — 32-byte random hex used to sign the session JWT and the OAuth `state` JWT
  - `PWC_ADMIN_GITHUB_USERNAMES` — comma-separated allowlist (e.g., `nielsrogge`)

**Backend changes (new `backend/routers/auth.py` and middleware):**

- `GET /api/v1/auth/github/login` — generates a short-lived (5 min) `state` JWT containing `{nonce, host}` where `host` is the originating request host (`paperswithcode.co` or `staging.paperswithcode.co`); redirects to GitHub OAuth `authorize` URL with `client_id` + `redirect_uri` (computed from the originating host) + `state` + `scope=read:user`.
- `GET /api/v1/auth/github/callback?code=...&state=...` — verifies the `state` JWT signature and confirms `state.host` matches the incoming request host (CSRF defense without a sessions table); exchanges code for GitHub access token; fetches `/user` to get the username; checks allowlist; issues a signed session JWT; sets it as an `httpOnly` + `Secure` + `SameSite=Lax` cookie named `pwc_admin_session` with `Domain` set to the **originating host** (i.e. `Domain=paperswithcode.co` for prod requests, `Domain=staging.paperswithcode.co` for staging requests — separate cookies per environment).
- `POST /api/v1/auth/logout` — clears the cookie (with the matching `Domain`).
- `GET /api/v1/auth/me` — returns `{username, is_admin: true}` if cookie valid; 401 otherwise.
- New auth dependency `require_admin(request)` injected into every write endpoint (`POST/PUT/DELETE` on papers/datasets/evaluations/etc.).

**Token mechanism**: signed JWT (HS256, secret in `PWC_JWT_SECRET` env var; generate once with `openssl rand -hex 32`). Stateless — no sessions table needed. Expiry: 30 days. No refresh token; user re-logs after expiry (rare event for a single operator). No rotation policy initially; rotating the secret invalidates all existing sessions, which is acceptable.

**CSRF protection**: relies on `SameSite=Lax` cookie behavior + the `state` JWT host check on the OAuth callback — sufficient for our threat model (single operator, no cross-site embeds). No explicit CSRF token header on write endpoints. If the threat model changes, add a CSRF token via `Set-Cookie: csrf-token=...; SameSite=Strict; HttpOnly=false` issued at login + required `X-CSRF-Token` header on writes.

**GitHub OAuth App setup** (one-time, manual):

- Create a single OAuth App in GitHub Developer Settings named "PapersWithCode Admin".
- Register **two callback URLs**: `https://paperswithcode.co/api/v1/auth/github/callback` and `https://staging.paperswithcode.co/api/v1/auth/github/callback`.
- Single `client_id` / `client_secret` pair shared by both environments. The backend chooses the correct `redirect_uri` based on the originating request host.

**Cookie scope rationale (separate per environment):** prod auth is rare and stable; staging auth is frequently broken during dev. A shared `Domain=.paperswithcode.co` cookie would mean every broken staging deploy could invalidate the operator's prod session, and a stale staging JWT could persist into prod after secret rotation. Separate cookies cost nothing and isolate failure modes.

**CORS update** (in `backend/config.py`):

- `Settings.cors_allowed_origins` must include `https://staging.paperswithcode.co` regardless of `is_production`. Recommended: introduce a `PWC_ENVIRONMENT=staging` mode that returns `["https://paperswithcode.co", "https://www.paperswithcode.co", "https://staging.paperswithcode.co"]`, and have the staging deploy set that env var. Simpler alternative: unconditionally include staging in the prod list — the only cost is that a leaked staging cert would be acceptable as a CORS origin in prod, which is not a meaningful threat for our setup.
- `allow_credentials=True` is already set in `backend/main.py` — no change needed.

**Frontend changes:**

- New auth context (React Context, not React Query — auth is global state) holding `{user: User | null, isLoading: boolean, logout: () => void}`. Initial state populated by calling `/api/v1/auth/me` on app mount.
- "Log in with GitHub" button: **only on `/admin/login` route, not in the main header** — admin UI is invisible to non-admin users browsing the site.
- 401 from any write request → clear auth context, redirect to `/admin/login`.
- Edit dialogs and admin-only buttons are conditionally rendered based on `user?.is_admin`.
- API client (`lib/api.ts`) sends `credentials: 'include'` on all fetches so the cookie travels.

**`/admin/login`** is a new route with the v2 header chrome, a centered "Log in with GitHub" button, and (after auth) an "Operator panel" listing the editing entry points. Admin tools elsewhere in the site (edit dialogs on PaperDetailView) are also unlocked by the same auth state.

**Single-operator allowlist (accepted risk).** `PWC_ADMIN_GITHUB_USERNAMES` will hold a single GitHub username for this migration; no second admin, no CLI escape hatch (the operator's GitHub account stability is treated as the source of truth). If that account is ever lost or GitHub OAuth itself breaks, recovery requires SSH-into-VPS + temporarily disabling `require_admin` in code or directly editing the database. Acceptable trade-off given a single-operator project. Multi-admin support / migration to a DB-backed users table is tracked as a deferred follow-up in §12.1.

**CRON jobs are unaffected by auth:** all current CRON jobs (`cron/hourly/*.py`, `cron/daily/import_hf_daily_papers.py`) call only external APIs (HuggingFace, GitHub, Semantic Scholar) and write to PostgreSQL **directly via SQLAlchemy** — they do not call our own `/api/v1/*` endpoints. Verified by `grep` over `cron/`. So no admin bypass key, no service token, no `Authorization` header is required for CRON. The only HTTP write paths gated by `require_admin` are UI-driven (edit dialogs + `indexPaperFromArxiv` from `PaperDetail.tsx`).

## 9. UX features visible in v1, missing or mocked in v2

Every item below is a **hard requirement** per the feature-parity philosophy:

- **LaTeX in titles / abstracts (Q-LATEX resolved).** Paper titles routinely contain `$\mathcal{L}$`, `$O(n^2)$`, etc. v2 renders titles as plain strings. Wrap with `<LatexTitle>` from [LatexTitle.tsx](frontend/src/components/LatexTitle.tsx). KaTeX's bundled math font is kept (typographic convention — fighting it produces worse-looking math). A small compatibility CSS layer (~10 lines, in a new `frontend_v2/src/katex-overrides.css`) ensures: (1) `.katex` inherits `currentColor` from surrounding text so math respects v2's `--ink` palette; (2) `.katex` uses `vertical-align: baseline` to fix any baseline drift in tight letter-spacing titles (`feed-title` has `-0.025em`); (3) optional small font-size adjustment if needed after visual review. No font-family override.
- **Long author lists** — backend papers commonly have 20+ authors. v2 hardcodes "+N authors" strings. Implement a `showAllAuthors` toggle (limit 30) like PaperDetail.tsx.
- **Multiple paper versions (Q-VERSION resolved).** Backend exposes `version`, `is_latest_version`, `/papers/arxiv/:id?version=v2`, `/papers/arxiv/:id/versions`. **Placement: inline in `PaperDetailView`'s meta line.** When `versions.length === 1` (the dominant case — see live data below), render just static text (e.g. `· v2 ·`). When `versions.length > 1`, that text becomes a small inline dropdown listing all versions with their dates. No always-visible chip, no sidebar widget.

  Live data (used to size this affordance): 57,826 paper rows; 25,644 have a `version != 'v1'`; only **9 arxiv_ids have multiple stored version rows**. So for 99.98% of papers the dropdown is a static label and never opens. Backfilling historical versions for the 25,644 updated papers is **out of scope for this migration** — it requires re-fetching from arXiv and a substantial ingestion pipeline. Tracked as a separate backend gap in §12.
- **Loading / error / empty states** — v2 has none. Use `Skeleton`, `Loader2`, and `Alert` shadcn components consistently. Standard pattern is in Tasks.tsx / Papers.tsx.
- **Toast notifications** — `Toaster` (shadcn) + `Sonner`, used after edits and on errors. v2 has neither.
- **Mobile responsive header** — v2 hides nav items at narrow widths (≤1100px) but does not have a mobile hamburger. v1's `<Menu>` button needs porting.
- **API status indicator** — [ApiStatus.tsx](frontend/src/components/ApiStatus.tsx) ping in the header.
- **Conference / date filters** — currently in `Papers.tsx` filter bar; required for the new `/papers` page. Date filter semantics (visitor TZ + ISO calendar week, Mon-Sun + calendar month + `published`): see §7.1. Conference filter is dropped per §7.
- **Thumbnail generation** — `POST /api/thumbnails/generate/:paperId` is wired in v1 to fall back when `thumbnail_url` is missing. v2's hand-drawn `PdfThumbnail` SVG is a placeholder — keep it as the *fallback* but prefer real thumbnails first.
- **`index.html` cleanup** — the existing [frontend/index.html](frontend/index.html) is a Lovable-generated stub with a UUID `og:title`, a Lovable OG image URL, and `meta name="author" content="Lovable"`. Replace with a real default `<title>Papers with Code</title>`, a real `og:image` (a `og-default.png` static asset in `frontend/public/`), real `og:title` / `og:description`, and drop or replace the `twitter:site` / `meta name="author"` lines. Per-route dynamic meta tags are deferred (see §12.1). This trivial cleanup is in scope for cutover.

## 10. Styling system

**Resolved (Q8 = S1):** keep v2's hand-rolled `frontend_v2/src/styles.css` (~1700 lines, with CSS variables `--ink`, `--bg`, `--accent`, `--serif`, `--mono`) verbatim. Layer raw Tailwind+shadcn for *new* surfaces only:

- Admin dialogs (§8)
- Loading / error / empty states (§9)
- Toast notifications (§9)
- Mobile hamburger sheet (§9)

The two systems coexist. Admin dialogs and toasts will look like default shadcn (different typography/border-radius/colors from v2-styled surfaces). That visual divergence is accepted to minimize migration risk.

No translation of `styles.css` tokens to `tailwind.config.ts`. No shared CSS-variable theming between the two systems.

## 11. Backend schema additions (this migration)

Pure schema work; **no data ingestion in this migration**. Each surface in the UI hides gracefully when null/empty — that's the steady state for the next several months.

### 11.0 Migration mechanism

Follows the existing convention in [backend/database/migrations/](backend/database/migrations/) (raw SQL file + per-migration Python runner script, e.g. [run_add_trending_score.py](backend/database/migrations/run_add_trending_score.py)). **No Alembic** — introducing it is a separate workstream and adds zero value for the 5 statements below.

Three new files in `backend/database/migrations/`:

1. `add_v2_schema.sql` — all five DDL statements (3 `papers` columns + `institutions` table + `paper_institutions` junction) in one idempotent file using `IF NOT EXISTS`.
2. `run_add_v2_schema.py` — wraps it like `run_add_trending_score.py`: opens a `db_manager.session_local()`, executes the file as one transaction, then runs verification queries against `information_schema.columns` for each new column/table.
3. `insert_canonical_methods.sql` — inserts the 3 missing `Method` rows (`attention`, `vit`, `mixture-of-experts`) needed by §4.3 figure resolution. Fully-curated stubs (not minimal placeholders) so the method-detail pages don't render half-empty on day one. `image_url` is `NULL` so §4.3 tier 1 dictionary figures (`AttentionFig`, `ViTFig`, `MoEFig`) win unimpeded. `paper_count` is left at 0; the existing keyword-matching CRON pipeline recomputes it once `keywords` are added later via the admin UI. `area_id` chosen via subquery on `areas.name` for robustness.

   ```sql
   INSERT INTO methods (slug, name, full_name, description, area_id, introduced_year, source_url, source_title, image_url, paper_count)
   VALUES
     ('attention',
      'Attention',
      'Attention Mechanism',
      'A mechanism that allows neural networks to focus on different parts of the input when producing each part of the output. Introduced for neural machine translation, attention computes a weighted sum of input representations where the weights are learned functions of a query.',
      (SELECT id FROM areas WHERE name = 'Natural Language Processing'),
      2014,
      'https://arxiv.org/abs/1409.0473',
      'Neural Machine Translation by Jointly Learning to Align and Translate',
      NULL,
      0)
   ON CONFLICT (slug) DO NOTHING;

   INSERT INTO methods (slug, name, full_name, description, area_id, introduced_year, source_url, source_title, image_url, paper_count)
   VALUES
     ('vit',
      'ViT',
      'Vision Transformer',
      'A pure transformer architecture applied directly to sequences of image patches for image classification, demonstrating that convolutional inductive biases are not strictly necessary at scale.',
      (SELECT id FROM areas WHERE name = 'Computer Vision'),
      2020,
      'https://arxiv.org/abs/2010.11929',
      'An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale',
      NULL,
      0)
   ON CONFLICT (slug) DO NOTHING;

   INSERT INTO methods (slug, name, full_name, description, area_id, introduced_year, source_url, source_title, image_url, paper_count)
   VALUES
     ('mixture-of-experts',
      'Mixture of Experts',
      'Mixture of Experts (MoE)',
      'An architecture where a sparse gating mechanism routes each input token to a small subset of expert subnetworks, dramatically increasing model capacity without proportional compute cost. Modern variants (e.g., Switch Transformer, GShard) are foundational to large-scale language model scaling.',
      (SELECT id FROM areas WHERE name = 'General'),
      2017,
      'https://arxiv.org/abs/1701.06538',
      'Outrageously Large Neural Networks: The Sparsely-Gated Mixture-of-Experts Layer',
      NULL,
      0)
   ON CONFLICT (slug) DO NOTHING;
   ```

Plus a code-side update in the same change:

4. `backend/models/database.py` — new SQLAlchemy `Mapped` columns on `DBPaper` (`tldr: Optional[str]`, `num_pages: Optional[int]`, `hf_upvotes: Optional[int]`); new `DBInstitution` and `DBPaperInstitution` ORM classes.
5. `backend/models/api.py` — new optional fields on the `Paper` Pydantic schema; new `Institution` schema; `Paper.institutions: Optional[List[Institution]] = None`.

### 11.1 New columns on `papers`

```sql
ALTER TABLE papers ADD COLUMN IF NOT EXISTS tldr TEXT NULL;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS num_pages INTEGER NULL;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS hf_upvotes INTEGER NULL;
```

- `tldr` — AI-generated summary surfaced in v2's `PaperDetailView` "TL;DR · AI-generated" panel. Generation pipeline (model choice, generation source, schedule, backfill) is a follow-up project.
- `num_pages` — page count of the source PDF. The v2 `PdfThumbnail` mock has a `pdfPages` field; we don't surface this number in the UI under feature parity, but the column exists for future use. Capture is trivial later from `extract_urls.py` (PyMuPDF already loaded).
- `hf_upvotes` — Hugging Face Daily Papers upvote count. Already returned by HF API during `import_hf_daily_papers.py` but currently discarded; wiring it up is a one-line follow-up for new papers, plus a backfill for the ~3K HF-Daily papers we already have. **Surfaced as a display-only count chip on `PaperCard` once populated; no interactive toggle (v2's upvote button is dropped — see §4.1).** Hidden when null.

### 11.2 New `institutions` table + `paper_institutions` junction

```sql
CREATE TABLE IF NOT EXISTS institutions (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    -- Future fields (not added now): slug, ror_id, country, url, logo_url
    UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS paper_institutions (
    paper_id        INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    institution_id  INTEGER NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
    -- Future field (not added now): position INTEGER -- ordering / primary affiliation
    PRIMARY KEY (paper_id, institution_id)
);
```

- Existing `backend/genai_steps/extract_orgs.py` LLM pipeline already returns lists like `["AI Centre, UCL", "Huawei Noah's Ark Lab, UK"]` — the future ingestion pipeline plugs into that.
- Open question for the future ingestion project: **canonicalization** (raw strings, fuzzy match, ROR API lookup, LLM judge, manual curation) and **primary-institution selection** for the v2 paper card. Not part of this migration.
- Until ingestion ships, `paper.institutions` is always empty; the v2 institution chip on `PaperCard` is hidden.

### 11.3 `docs/DATABASE_SCHEMA_UML.md` update

The schema doc is updated alongside the migration to reflect the new `papers` columns and the `institutions` / `paper_institutions` tables.

## Open questions

All previously-open questions are now resolved. The original Q1, Q1b, Q2, Q3, Q4 and the in-flight Q-FIG, Q-VERSION, Q-PAPERS, Q-CRON, Q-ADMIN, Q-AUTH, Q-LATEX, Q-CUTOVER are captured in §4.1, §4.2, §4.3, §6, §7, §8, §8.1, §9, §10, §11, §13.

If new ambiguities surface during implementation, they should be added back here.

## 12. Backend gaps surfaced by the new mapping

The corrected mapping (areas = v2 domains, tasks = v2 tasks) lines up almost perfectly with the existing backend. The remaining gaps are:

- **`Task.description` fill-in** — the `task-explainer` prose block in `TagBrowseView` reads `task.description`. The field exists, but coverage is sparse. Either fill in all 38 task descriptions (one-off data work, very small at this scale) or hide the block when missing. Recommended: hide-when-missing for the migration; fill in as separate content work.
- **Historical paper version backfill** — only 9 arxiv_ids currently have multiple stored versions, but 25,644 papers have a non-`v1` latest version (i.e. they were updated on arXiv after first publication). Surfacing meaningful version dropdowns for those papers requires re-fetching historical versions from arXiv. **Out of scope for this migration** — separate backend workstream.
- **Schema additions in §11** — covered above; schema-only this migration.

### 12.1 Deferred follow-ups (explicitly out of scope, tracked here so they aren't lost)

- **SEO + AI agent readiness.** Per-route `<title>` / `og:*` / `twitter:*` tags via `react-helmet-async`, generated `sitemap.xml` (CRON job over papers + tasks + methods + datasets), JSON-LD `ScholarlyArticle` / `Dataset` blocks on detail pages, structured `robots.txt` with AI bot rules, Markdown content negotiation, MCP server card, OAuth discovery, Agent Skills — see [isitagentready.com](https://isitagentready.com/) for the target compliance surface. Goal: high score on that scanner. Substantial workstream; deferred to a follow-up project.
- **`index.html` Lovable stub cleanup is *not* deferred** — see §9 (one-time cleanup as part of the v2 build setup; trivial, must ship at cutover).
- **Tests.** No automated test strategy is in scope for this migration (no frontend unit tests, no E2E, no Playwright). Manual smoke-test checklist in §13.4 is the only verification path. Adding tests is a separate workstream.
- **Analytics + error tracking.** No Sentry, no Plausible/GA, no logging integration for the frontend. The site currently has none either, so no regression. Worth adding later.
- **Accessibility audit.** No formal a11y pass. v2's hand-rolled custom components (segmented controls, custom dropdowns inside `views.jsx`) are likely keyboard-trap and screen-reader-poor. shadcn primitives used for new surfaces (admin dialogs, toasts) are accessible by default, so the *new* surfaces meet a baseline. Full audit deferred.
- **Hugging Face upvote button as a real feature.** v2's interactive `upvote(paperId)` is dropped (§4.1). If user voting is later desired, build it as a real workstream: anonymous voting via cookie or admin-only, `upvotes` table, rate-limiting, abuse mitigation.
- **Switch production frontend from `npm run dev` to a built `dist/`.** The current [start_services.sh](start_services.sh) script invokes `npm run dev` for prod ([line 211](start_services.sh#L211)) — i.e., production traffic is served by Vite's dev server with HMR enabled. This pre-dates the v2 migration and remains as-is post-cutover (§13.2 step 5). Long-term, edit `start_services.sh` to run `npm run build && npm run preview -- --port 8080` (or serve `dist/` via nginx directly, removing Vite from the prod path entirely). Out of scope for this migration to keep cutover risk minimal; tracked here as a deferred ops cleanup.
- **Multi-admin support / users table.** Current setup is single-operator via `PWC_ADMIN_GITHUB_USERNAMES` env var (§8.1). If admin count grows past ~5, or audit logging / role scopes / a UI to manage admins becomes desirable, migrate to a `users` DB table with `github_username`, `is_admin`, `created_at` columns. Out of scope for this migration.
- **Automated, off-host DB backups via Hugging Face Storage Buckets.** The VPS hosts the only copy of the production DB. This migration adds manual `pg_dump` checkpoints only (§13.0). Long-term plan: a daily CRON job `cron/daily/backup_database.py` that streams `pg_dump -F c paperswithcode_hf` directly to a private HF bucket via `hf buckets cp -` (stdin streaming — important on the 4 GB RAM VPS to avoid materializing the dump on disk). Date-stamped paths (`hf://buckets/<owner>/pwc-backups/YYYY-MM-DD.dump`) because [HF buckets are non-versioned/mutable](https://huggingface.co/docs/hub/storage-buckets) — overwriting one file would give a 1-deep restore window. Rolling retention: last 7 daily + last 4 weekly + last 12 monthly. Auth reuses `PWC_HF_TOKEN`. Off-host (geographically separate from Hetzner) provides real DR. Fits within HF free tier for a few-GB private bucket. Out of scope for this migration; tracked here so the manual `pg_dump` checkpoints aren't mistaken for a long-term solution.

## 13. Cutover plan (Q-CUTOVER resolved)

### 13.0 Backup checkpoints (manual, operator-driven)

The VPS hosts the only copy of the production DB. This migration adds three manual `pg_dump` checkpoints — automated/off-host backups are deferred to a follow-up (see §12.1).

Each checkpoint command (run from the VPS, results land in `/root/db_backups/`):

```bash
mkdir -p /root/db_backups
pg_dump -U paperswithcode_user -F c paperswithcode_hf \
  > /root/db_backups/<checkpoint_name>_$(date +%Y%m%d_%H%M).dump
pg_restore -l /root/db_backups/<checkpoint_name>_*.dump | head    # smoke verify
```

Three checkpoints required, in order:

1. **`pre_v2_schema`** — before running `run_add_v2_schema.py` in production.
2. **`pre_canonical_methods`** — before running `insert_canonical_methods.sql`.
3. **`pre_v2_cutover`** — before starting the §13.2 cutover window.

Restore command (only needed in a rollback): `pg_restore -U paperswithcode_user -d paperswithcode_hf -c <dump_path>` (`-c` drops/recreates objects).

The §13.2 cutover window must not start before the corresponding checkpoint file is confirmed present in `/root/db_backups/`.

### 13.0.5 Backend rollout commands (schema first, then code)

The §13.2 cutover prerequisites (#3 schema, #4 auth router) reference "deployed to production" without commands. Here's the literal sequence the operator runs on the VPS, in order. **Schema first, then code** — the new SQLAlchemy models in `backend/models/database.py` reference the new columns/tables, so deploying the code first against an unmigrated DB would crash on first query. A few seconds of read-API downtime per restart is acceptable (no users yet); zero-downtime backend restart is deferred per §12.1.

```bash
cd /root/python_projects/paperswithcode

# (1) Take the pre_v2_schema backup checkpoint per §13.0
mkdir -p /root/db_backups
pg_dump -U paperswithcode_user -F c paperswithcode_hf \
  > /root/db_backups/pre_v2_schema_$(date +%Y%m%d_%H%M).dump

# (2) Pull latest code (still on prod backend until restart)
git pull origin main
uv sync                                                              # install PyJWT, httpx if not already present

# (3) Run schema migrations (idempotent; safe to re-run)
uv run --env-file backend/keys.env python backend/database/migrations/run_add_v2_schema.py

# (4) Take the pre_canonical_methods checkpoint per §13.0
pg_dump -U paperswithcode_user -F c paperswithcode_hf \
  > /root/db_backups/pre_canonical_methods_$(date +%Y%m%d_%H%M).dump

# (5) Insert the 3 canonical method rows (ON CONFLICT DO NOTHING; idempotent)
psql -U paperswithcode_user -d paperswithcode_hf \
  -f backend/database/migrations/insert_canonical_methods.sql

# (6) Edit backend/keys.env — add the four new auth env vars:
#       PWC_JWT_SECRET            (generate via: openssl rand -hex 32)
#       PWC_GITHUB_OAUTH_CLIENT_ID
#       PWC_GITHUB_OAUTH_CLIENT_SECRET
#       PWC_ADMIN_GITHUB_USERNAMES

# (7) Restart backend so the new auth router and schema-aware models go live
./stop_services.sh && ./start_services.sh

# (8) Smoke test the auth router (read endpoints unaffected; auth /me returns 401 unauthenticated)
curl https://paperswithcode.co/api/v1/auth/me                        # → 401
curl https://paperswithcode.co/api/v1/papers/recent?limit=1          # → 200, schema fields tldr/num_pages/hf_upvotes appear as null
```

After step 8 succeeds, the backend prerequisites for cutover are met. The cutover window itself (§13.2) only touches the frontend folder — the backend keeps running uninterrupted through the rename.

### 13.1 Staging (CD2)

- New nginx server block at `staging.paperswithcode.co` proxying to `localhost:8081` (mirrors the production block at port 8080), with **WebSocket upgrade headers required for HMR**:

  ```nginx
  location / {
      proxy_pass http://127.0.0.1:8081;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
      proxy_read_timeout 86400;     # long-lived HMR ws
  }
  ```
  Without these headers, Vite's HMR silently falls back to long-polling and live-reload becomes unusable.
- New Let's Encrypt cert for `staging.paperswithcode.co`.
- `frontend_v2/` dev server runs on port 8081 throughout development. Vite staging mode config per §1 (`server.port: 8081`, `server.allowedHosts: ['staging.paperswithcode.co']`, `hmr.host: 'staging.paperswithcode.co'`, `hmr.protocol: 'wss'`, `hmr.clientPort: 443`).
- **Staging dev server runs as a systemd unit** `frontend-staging.service` (mirrors how the prod stack is managed, survives reboots and SSH disconnects). Unit file at `/etc/systemd/system/frontend-staging.service` invoking `npm run dev -- --port 8081 --mode staging` from `/root/python_projects/paperswithcode/frontend_v2`. Logs to `journalctl -u frontend-staging`. `start_services.sh` does *not* manage the staging dev server (stays scoped to prod).
- Same FastAPI backend at `localhost:8000` for both production and staging — single source of data truth.
- Staging URL is the live preview during development; visual review and integration bug-hunting happen here against real backend data.

### 13.2 Cutover sequence (CO1 atomic rename)

Pre-cutover (1-2 days before):
1. All items in [progress.md](progress.md) are marked `done`.
2. Smoke-test checklist (§13.4) passes on `staging.paperswithcode.co`.
3. Backend schema additions (§11) deployed to production via `backend/database/migrations/run_add_v2_schema.py` + `insert_canonical_methods.sql`. UI hides null fields gracefully — safe to deploy any time.
4. Backend auth router (§8.1) deployed to production. Public read endpoints unaffected. CRON jobs require no changes (they bypass HTTP entirely; verified in §8.1).
5. `start_services.sh` ports unchanged (frontend on 8080, backend on 8000) — no script edits needed.
6. Final operator checklist read, rollback steps rehearsed.
7. **(Day before cutover)** in the still-named `frontend_v2/` folder: `npm ci && npm run build`. Verify `frontend_v2/dist/` is non-empty and timestamped recent. This is the slow step (2-5 min); doing it ahead of time keeps the cutover window genuinely short.

Cutover window (~5 minutes total, ~30s actual downtime):
1. `cd /root/python_projects/paperswithcode`
2. `./stop_services.sh` (frontend stops; backend keeps running)
3. `git mv frontend frontend_legacy && git mv frontend_v2 frontend` (Git tracks renames; full history preserved on both folders)
4. `cd frontend && npm ci --prefer-offline --no-audit` (~5-15s on warm cache; explicitly verifies lockfile integrity post-rename without going to network if `node_modules/` is intact). **If this fails, abort cutover and rollback per §13.3 reverse-rename — do not paper over with `npm install`.**
5. `cd .. && ./start_services.sh` (auto-picks up new `frontend/`; continues to invoke `npm run dev` per the existing script — see §12.1 deferred follow-up about switching to a built `dist/`)
6. Run smoke-test checklist (§13.4) against `https://paperswithcode.co`
7. `git add -A && git commit -m "Cutover: frontend_v2 becomes frontend"`

The window must not begin before the `pre_v2_cutover` backup checkpoint from §13.0 is confirmed present in `/root/db_backups/`.

### 13.3 Rollback plan (R2 — 1-week parallel-run insurance)

After cutover, `frontend_legacy/` is **not deleted immediately**. For 1 week:

- A second nginx server block at `legacy.paperswithcode.co` (or alternatively a second upstream behind a query-string flag like `?legacy=1`) proxies to the legacy frontend running on port 8081.
- `frontend_legacy/` runs continuously on port 8081 alongside the new frontend on port 8080. Both are managed by `start_services.sh` extensions.
- If a critical regression is discovered in the new frontend, an instant nginx-level rollback is possible: edit `/etc/nginx/sites-available/paperswithcode.co`, change the `proxy_pass` from `localhost:8080` to `localhost:8081`, `nginx -s reload`. Zero downtime, ~30s operation.
- After 1 week of stability, `frontend_legacy/` and its nginx block are deleted and the rollback path is closed.

Manual reverse-rename rollback (if nginx flip is somehow not enough):
1. `./stop_services.sh`
2. `git mv frontend frontend_v2 && git mv frontend_legacy frontend`
3. `./start_services.sh`

### 13.4 Smoke-test checklist (manual, run pre and post cutover)

Run against staging pre-cutover, against production post-cutover:

1. `/` (FeedView) renders papers; sort by trending/newest/most-cited works; period switcher updates the list — verify "Today" returns rows where `published >= startOfDay(now)` in **visitor local TZ** (sanity-check via DevTools by changing system TZ and reloading)
2. `/papers` renders list; inline search updates URL `?search=`; infinite scroll fetches more; period switcher uses ISO Mon–Sun week boundary and calendar month boundary in visitor local TZ (per §7.1)
3. `/paper/:arxivId` renders detail; LaTeX in title/abstract renders correctly; multi-version selector shows static label when single-version, dropdown when multiple; selecting a version mutates `?version=` query param; navigating to `/paper/:arxivId?version=v1` directly loads v1; browser back/forward moves between versions
4. `/tasks` renders 6 backend areas (CV / NLP / General / Audio / Time-series / Other); clicking a task → task detail with sister tasks, common methods, papers
5. `/methods` renders 4 area sections; sorted by paper_count desc within each
6. `/methods/:slug` renders MethodFigure correctly: tier 1 dictionary for canonical slugs, tier 2 image_url for the rest, GenericFig fallback
7. `/benchmark/:datasetSlug` renders leaderboard (sorted by best_rank) + SOTA progression chart (running best by published date)
8. `/cron-dashboard` renders inside v2 chrome with raw shadcn body; admin-gated
9. ⌘K opens search overlay; debounced `/papers/search` calls work; results clickable
10. `/admin/login` renders "Log in with GitHub" button; OAuth round-trip succeeds; non-allowlisted users get rejected; allowlisted users land in operator panel
11. After login, edit dialogs visible on PaperDetailView; PUT/POST/DELETE writes succeed
12. Mobile width (<1100px) shows hamburger; nav drawer opens
13. Toast notifications appear on edit success/failure
14. API status indicator green when backend healthy
15. Thumbnails load from `/api/thumbnails/`; missing thumbnails fall back to `PdfThumbnail` SVG
16. On staging, edit a v2 source file → HMR updates the page over wss without a full reload (browser DevTools Network shows the `wss://staging.paperswithcode.co/...` connection live, no polling fallback)

## Suggested implementation order

The work below is roughly ordered so that each step unblocks the next without dead-end branches.

1. **Backend schema (§11)** — write `add_v2_schema.sql` + `run_add_v2_schema.py` (per existing convention; no Alembic) for `papers.tldr` / `papers.num_pages` / `papers.hf_upvotes` + `institutions` + `paper_institutions`. Write `insert_canonical_methods.sql` for the 3 missing `Method` rows (`attention`, `vit`, `mixture-of-experts`). Update SQLAlchemy + Pydantic models to expose nullable fields and the `Institution` schema. Update `docs/DATABASE_SCHEMA_UML.md`. No data ingestion.
2. **Backend auth (§8.1)** — register one GitHub OAuth App with two callback URLs (prod + staging). Generate `PWC_JWT_SECRET` via `openssl rand -hex 32`. Write `backend/routers/auth.py` with the `/login`, `/callback`, `/logout`, `/me` endpoints; `state` JWT for CSRF; per-environment cookie `Domain`. Add `require_admin` dependency to every write endpoint. Extend `Settings.cors_allowed_origins` to include staging. Test the full OAuth round-trip via browser against staging. CRON jobs require no changes — they bypass HTTP entirely.
3. **Foundation** — port dependencies into `frontend_v2/`, `vite.config.ts` proxy + port 8081 (for staging), `tsconfig`, `eslint`. Convert files to `.tsx`/`.ts`. App still renders mock data after this step.
4. **Staging URL** — set up `staging.paperswithcode.co` nginx block + Let's Encrypt cert (per §13.1). frontend_v2 dev server runs on port 8081 with HMR over wss to staging domain. Live preview is now available.
5. **Routing** — install `react-router-dom`, replace App-level state with the route table above. URL deep-linking works against mock data.
6. **API client + QueryClient** — port `lib/api.ts` and the `hooks/` directory. Verify against the running backend with `curl`.
7. **Replace `data.js` with hooks** — Papers / Tasks / Areas / Methods / Datasets / Evaluations. Drop `submitter` / `comments` / pdfPages-as-content from the UI; hide `tldr` / `institution` / `hf_upvotes` until backed by data.
8. **Detail pages** — `PaperDetailView`, `TagBrowseView` (= task detail), `MethodDetailView` (figure resolution = dictionary → image_url → GenericFig), `BenchmarkDetailView` swap to real data via `transformPaperForUI` and friends.
9. **Browse page** — `TagsIndexView` (areas → their tasks) wires to `getAreas()` + `getAreaTasks()`, rendering the 6 backend areas verbatim.
10. **Search** — replace overlay's in-memory filter with debounced `/papers/search` calls (papers-only); keep v2's full-screen overlay layout.
11. **Polish** — loading/error/empty states (raw shadcn Skeleton/Loader2/Alert), KaTeX with §9 compatibility CSS (`katex-overrides.css`), long-author handling, toast notifications, mobile hamburger, thumbnail fallback, multi-version selector inline in meta line, API-status indicator.
12. **`/papers`** — clone of FeedView with title swap, period switcher as date filter, inline search, infinite scroll. Conference filter dropped.
13. **`/cron-dashboard`** — port `CronDashboard.tsx` as-is inside v2's `<Header>` chrome, body keeps raw shadcn.
14. **Admin** — port edit dialogs from `paper-detail/` and `indexPaperFromArxiv`. New `/admin/login` route with "Log in with GitHub". Auth Context. 401 handling.
15. **Cutover (per §13.2)** — atomic folder rename, restart services, smoke-test, commit. Frontend_legacy stays running on port 8081 for 1-week rollback insurance (§13.3).
16. **Cleanup (1 week post-cutover)** — delete `frontend_legacy/` folder and the `legacy.paperswithcode.co` nginx block. Rollback path closed.
