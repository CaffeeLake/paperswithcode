# Plan: Organizations index and canonical organization pages

## Outcome

Add a curated overview at `https://paperswithcode.co/organizations` and make
organization pages canonical under:

- `https://paperswithcode.co/orgs/{organization-slug}`
- `https://paperswithcode.co/orgs/{organization-slug}/{task-slug}`

For example, NVIDIA moves from `/nvidia` to `/orgs/nvidia`. Existing public
organization URLs must continue to work through permanent redirects.

For the first release, an "organization paper" means only a paper present on
that organization's Hugging Face papers page. Do not supplement this coverage
with manual curation or inferred affiliations. A later AI extraction workflow
may add organization associations directly from paper content, including
multiple organizations for one paper, but that is outside this release.

The first release contains these 21 Hugging Face organizations, with public
Papers with Code slugs normalized to lowercase:

| Display order | HF handle | PwC slug |
| ---: | --- | --- |
| 1 | `microsoft` | `microsoft` |
| 2 | `google` | `google` |
| 3 | `nvidia` | `nvidia` |
| 4 | `Anthropic` | `anthropic` |
| 5 | `deepseek-ai` | `deepseek-ai` |
| 6 | `meta-llama` | `meta-llama` |
| 7 | `Qwen` | `qwen` |
| 8 | `black-forest-labs` | `black-forest-labs` |
| 9 | `stabilityai` | `stabilityai` |
| 10 | `moonshotai` | `moonshotai` |
| 11 | `facebook` | `facebook` |
| 12 | `zai-org` | `zai-org` |
| 13 | `ByteDance` | `bytedance` |
| 14 | `ByteDance-Seed` | `bytedance-seed` |
| 15 | `mistralai` | `mistralai` |
| 16 | `allenai` | `allenai` |
| 17 | `xai-org` | `xai-org` |
| 18 | `openai` | `openai` |
| 19 | `apple` | `apple` |
| 20 | `tencent` | `tencent` |
| 21 | `MiniMaxAI` | `minimaxai` |

## Current repository state

Much of the domain already exists and should be extended rather than rebuilt:

- `organizations` and `paper_organizations` are defined in
  `backend/models/database.py` and
  `backend/database/migrations/add_organizations.sql`.
- `backend/database/organizations_setup/import_hf_organization.py` can upsert
  one HF organization and link HF-attributed papers that already exist locally.
- `backend/services/organization_service.py` and
  `backend/routers/organizations.py` already expose list, detail, taxonomy, and
  paginated paper APIs under `/api/v1/organizations`.
- `frontend/src/views/OrganizationsIndexView.tsx`,
  `OrganizationDetailView.tsx`, and `OrganizationTaskView.tsx` already render
  the main page shapes.
- Organization links, discovery documents, Markdown representations, and
  sitemaps currently use top-level canonical paths such as `/nvidia`.
- Production currently has one organization, NVIDIA, with 125 linked papers.

The main gaps are:

1. only one organization is populated;
2. the one-org importer reports locally missing HF papers instead of importing
   them;
3. no bounded recurring sync keeps organization-paper links fresh;
4. canonical routes are top-level rather than `/orgs/{slug}`;
5. the existing index has no explicit featured/order metadata for a curated
   set;
6. ingestion, route migration, empty states, and frontend behavior need focused
   test coverage.

## HF source investigation

As checked on 2026-07-29:

- `hf papers search` and `HfApi.list_papers(query=...)` provide general paper
  search, not an organization membership filter.
- `hf papers list --submitter` filters daily-paper submitters, which is not the
  same as papers attributed to an organization.
- `GET /api/organizations/{slug}/overview` is useful for organization metadata
  and `numPapers`.
- The complete attributed paper list is rendered into the public
  `https://huggingface.co/{slug}/papers` response as `orgPapers`.
- No documented organization-papers REST or CLI operation was found. Candidate
  `/api/organizations/{slug}/papers` endpoints return 404, while generic
  `/api/papers` query parameters do not establish organization membership.
- `GET /api/papers/{arxiv_id}` can enrich an individual paper after its ID is
  discovered.
- The HF daily-papers response and per-paper response currently include an
  `organization` object with the HF namespace name, full display name, and
  avatar. The existing PwC daily importer does not persist or link this field.

The existing HTML extraction is therefore acceptable for the initial bootstrap,
but it is an upstream-private contract and must be isolated, validated, and
monitored. The parser must fail closed when `orgPapers` is absent or malformed;
an upstream format change must never be interpreted as an authoritative empty
list.

Observed HF counts at planning time:

| Organization | HF papers | Organization | HF papers |
| --- | ---: | --- | ---: |
| Microsoft | 64 | Google | 82 |
| NVIDIA | 152 | Anthropic | 3 |
| DeepSeek | 27 | Meta Llama | 4 |
| Qwen | 48 | Black Forest Labs | 0 |
| Stability AI | 9 | Moonshot AI | 16 |
| AI at Meta (`facebook`) | 68 | Z.ai | 9 |
| ByteDance | 65 | ByteDance Seed | 104 |
| Mistral AI | 7 | Ai2 | 18 |
| xAI | 0 | OpenAI | 6 |
| Apple | 41 | Tencent | 97 |
| MiniMax | 4 |  |  |

This is 824 associations before deduplicating papers attributed to more than one
organization. Counts are discovery inputs, not hard-coded acceptance values.

## Data model and curated manifest

### 1. Add curation and sync metadata

Create an idempotent migration and update `Organization` in
`backend/models/database.py` with:

- `hf_slug VARCHAR(100)`: the HF namespace/handle used for synchronization;
- `is_featured BOOLEAN NOT NULL DEFAULT FALSE`: whether the organization appears
  on the curated index;
- `display_order INTEGER`: deterministic fallback order when trending signals
  tie or are absent;
- `last_hf_synced_at TIMESTAMPTZ`: last successful complete sync;
- `trending_score DOUBLE PRECISION`: persisted rolling 30-day organization
  momentum used by the logo grid;
- `trending_score_updated_at TIMESTAMPTZ`: when that monthly score was last
  refreshed;
- optionally `hf_paper_count INTEGER`: last complete upstream count, useful for
  drift diagnostics without making it the public count.

Keep `slug` as the lowercase, stable PwC URL identifier. Do not derive routing
from the mutable display name. Add a unique index on `hf_slug` when non-null and
indexes supporting `(is_featured, trending_score DESC)` and
`(is_featured, display_order)`.

Add a small `organization_trending_history` table with
`(organization_id, snapshot_date)` as its primary key and a `raw_score` column.
At one daily snapshot per featured organization, a rolling month requires only
about 630 active rows for the initial 21 organizations. Retain enough additional
history for diagnostics, with bounded cleanup documented in the cron.

Expose `is_featured`, `display_order`, and
`organization_trending_score` in the API `Organization` model without removing
or renaming existing fields. Add `featured_only: bool = false` to the list API
so its existing “all organizations” behavior remains compatible; the index view
requests `featured_only=true`.

Rank featured organizations by a consolidated organization trending score, not
by the manifest order, raw paper count, or the latest hourly spike. Reuse the
active paper trending mode already used by the homepage and organization paper
feed to calculate one raw daily organization snapshot:

- in composite mode, use each fresh `papers.trending_score`;
- in the GitHub rollback mode, use each paper's fresh best-official-repository
  EMA velocity;
- treat scores older than the existing 24-hour freshness window as zero;
- aggregate each distinct latest, eligible, HF-linked paper exactly once;
- sum those fresh paper scores into that day's raw organization score.

Factor the active per-paper score expression into a reusable service helper so
the organization aggregate and `PaperService.apply_scoped_trending_order` cannot
silently drift. Once per day, store the raw score snapshot and set the persisted
organization score to the arithmetic mean of the available daily raw snapshots
from the trailing 30 calendar days. Refresh the logo-grid ranking only after
that daily calculation, not on every hourly paper-score update. On first launch,
seed the score from the first raw snapshot and let it converge as daily history
accumulates.

Order by the rolling 30-day score descending, then the most recent daily raw
score, linked-paper count, and `display_order`. This makes ranking responsive to
sustained monthly momentum while keeping the page stable from hour to hour.

### 2. Add a version-controlled manifest

Add a small Python data module such as
`backend/database/organizations_setup/organizations.py` containing typed records
for the 21 HF handles, normalized PwC slugs, and display order. This becomes the
reviewable source of truth for the curated set and replaces ad hoc shell loops.

Treat this manifest as a strict launch allowlist, not merely a seed list. An HF
daily-paper payload naming any other organization must not create an
`organizations` row, create a `paper_organizations` link, or add a logo-grid
tile. Increment an `unknown_organizations_seen` diagnostic counter and log the
normalized HF handle for later review, without making it part of the initial
product.

Names, logos, websites, and HF paper counts remain fetched metadata. Apply small
explicit name overrides only when HF metadata is visibly unsuitable (for
example, trim the current `Mistral AI_` name) rather than maintaining a second
full metadata catalog.

Treat `facebook` and `meta-llama`, and `bytedance` and `bytedance-seed`, as
distinct organizations in the first release because they are distinct HF
namespaces in the requested list. The schema remains many-to-many, so the same
paper may legitimately appear under both.

Keep `paper_organizations.source` as explicit provenance. The launch source is
`hf_org_papers`. The future AI workflow can use a separate value such as
`ai_affiliation` and insert several organization links for one paper without a
schema change. If AI later rediscovers an existing HF association, retain the
higher-confidence HF provenance rather than overwriting it.

## Ingestion and synchronization

### 3. Separate HF fetching, paper ingestion, and linking

Refactor `import_hf_organization.py` into narrow reusable pieces:

- `backend/services/hf_organization_service.py`
  - fetch and validate `/api/organizations/{hf_slug}/overview`;
  - fetch the public papers page;
  - extract the balanced `orgPapers` payload;
  - return typed organization metadata and paper identifiers;
  - compare extracted count with `overview.numPapers`;
  - use bounded timeouts, the standard HF headers, and limited retries.
- `backend/services/paper_ingestion_service.py`
  - move/refactor the existing ArXiv fetch-and-persist logic currently private
    to `backend/routers/papers.py`;
  - return the existing or newly created latest paper row;
  - preserve authors and the established merge/deduplication behavior;
  - make router submission and organization sync share the same domain path.
- `backend/services/organization_sync_service.py`
  - upsert one organization;
  - resolve all local papers in one batched `arxiv_id` query;
  - import missing papers in bounded batches;
  - create idempotent `paper_organizations` links with
    `source='hf_org_papers'`;
  - update sync metadata only after a complete successful fetch and link pass.

Extend the shared HF paper-import path and
`.github/workflows/scripts/daily/import_hf_daily_papers.py` to consume the
paper payload's `organization` object immediately:

- normalize `organization.name` to the manifest's `hf_slug`;
- link only organizations in the curated manifest for this release;
- upsert the organization if necessary, while treating the organization
  overview endpoint as the authoritative metadata refresh;
- insert the idempotent paper link with `source='hf_org_papers'`;
- process the organization link for both newly created and already-existing
  papers.

The current daily importer returns early when an ArXiv paper already exists.
Refactor that branch so it still resolves the local paper ID and applies the
organization association before finishing. Otherwise an existing PwC paper
newly attributed by HF would never appear on its organization page.

Treat the organization value defensively as either one object or a future list,
even though current sampled payloads contain one object. The HF org-page sync
remains the historical and reconciliation backstop: it imports the full initial
catalog, catches papers never present in the rolling daily window, and can link
the same paper to several organizations when it appears on several org pages.

Avoid matching by title when HF supplies an ArXiv ID. Title matching can attach
an organization to the wrong version or an unrelated paper. Normalize versioned
IDs (`2501.12345v2` to the repository’s canonical ArXiv identifier) before
lookup.

Importing missing papers is required launch behavior, not an optional enrichment
pass. When an HF-attributed ArXiv ID has no local paper, run it through the
canonical ArXiv ingestion service, persist complete paper metadata and authors,
then create the organization link. If complete metadata cannot be retrieved, do
not create a partial paper or dangling association: record the paper-specific
failure, continue the bounded organization run, and retry it on the next sync.

### 4. Define reconciliation semantics safely

The bootstrap must be rerunnable and support:

- `--dry-run`: fetch and report intended org/paper/link changes without writes;
- `--organization SLUG`: sync one manifest entry;
- no filter: sync the full curated manifest;
- `--skip-missing-papers`: an explicit diagnostics-only override; normal
  bootstrap and scheduled runs always import missing papers;
- bounded batch size and per-organization transaction boundaries;
- a final summary with fetched, existing, imported, linked, already linked,
  failed, unknown-organization, and upstream/local count deltas.

HF organization associations are append-only. Once an HF papers page attributes
a paper to an organization, retain that `source='hf_org_papers'` link
indefinitely even if a later HF response omits the paper. Every sync may insert
new links or refresh organization metadata, but it must never reconcile, delete,
expire, or deactivate an existing paper-organization link. The local collection
therefore represents papers HF has attributed to the organization over time,
not an exact mutable mirror of the latest HF response.

Do not create launch associations from author names, email domains, repository
owners, organization mentions, acknowledgements, or model names. Those signals
belong to the later AI affiliation-extraction workflow.

Organizations with zero HF papers are still upserted and featured. Their detail
pages and logo-grid tiles show the explicit message "No papers indexed yet"
rather than a numeric zero without context. They remain clickable and
`noindex,follow` until they have eligible papers, and recurring imports populate
them without changing curated grid membership.

### 5. Keep the catalog current

After the bootstrap is proven idempotent, add a bounded scheduled job under
`.github/workflows/scripts/daily/` and register it in
`backend/services/cron_registry.py`. The existing hourly HF daily-paper importer
provides the fast path by linking the organization included in every new paper
payload. Run the full organization-page sync daily as a backstop after the
regular HF paper import so most papers already exist locally. Process only the
21 manifest entries, use per-org transactions, and continue to the next
organization after recording an isolated failure.

Run the daily organization-trending snapshot after the paper trending jobs and
organization sync. It writes one idempotent snapshot per organization per UTC
date, recomputes the rolling 30-day mean, and prunes history only according to a
bounded retention rule. A retry on the same day updates that day's snapshot
rather than inserting a duplicate.

Register both new scheduled jobs in `backend/services/cron_registry.py` so they
automatically appear in the existing `/admin-dashboard` daily supporting-jobs
section and in `pwc cron health`:

- `sync_hf_organizations` / "Sync HF Organizations";
- `calculate_organization_trending_scores` / "Calculate Organization Trending
  Scores".

Each registry definition must include its daily schedule, script and log names,
process pattern, dedicated production lock file, expected runtime,
`stale_after_minutes`, and workflow metadata. Mark both as noncritical because
stale data does not make the public site unavailable. Allow a successful
no-work run for the append-only HF sync, but not for the trend job, which should
write one snapshot per featured organization each day.

Add database freshness queries that let the dashboard detect silent failures:

- organization sync: newest `last_hf_synced_at`, featured organizations synced
  recently, and featured organizations beyond the stale threshold;
- organization trends: newest `trending_score_updated_at`, today's snapshot
  count, total featured count, and featured organizations missing today's
  snapshot.

Add both commands to `deploy/cron_launcher.py` so the installed immutable
`pwc-cron` interface can execute them. Add the corresponding scheduled GitHub
Actions workflows, invoke only `sudo /usr/local/sbin/pwc-cron <job>`, and order
the trend workflow after the relevant paper-trending and organization-sync
windows. Update `docs/operations.md`, `.github/workflows/scripts/README.md`, and
the registered-health-job inventory in `.agents/skills/pwc-cli/SKILL.md`.

The job should alert/log on:

- missing or unparseable `orgPapers`;
- extracted count differing from `overview.numPapers`;
- a sudden large upstream count drop, for diagnostics only and never deletion;
- unmatched/import-failed papers;
- stale `last_hf_synced_at`.

Do not make live page requests proxy HF. Public pages and APIs read only from
PostgreSQL, preserving latency and availability.

## Backend API and canonical URLs

### 6. Keep API routes stable

Retain these existing JSON contracts:

- `GET /api/v1/organizations/`
- `GET /api/v1/organizations/{slug}`
- `GET /api/v1/organizations/{slug}/areas-with-tasks`
- `GET /api/v1/organizations/{slug}/papers`

Add only the compatible featured filter and metadata described above. Continue
sorting organization papers with the existing paginated `PaperService`
conversion path and `DBPaper.is_latest_version`.

For the first release, organization index counts, organization detail/task
queries, and organization badges returned on paper responses must include only
`paper_organizations.source='hf_org_papers'`. Define this launch-visible source
rule once in the service layer so the future AI rollout can deliberately extend
it to `ai_affiliation`; do not rely on the database merely happening to contain
only HF rows.

Review organization counts to ensure the index counts only eligible latest
papers, matching what a visitor can actually open. Avoid an index card count
that differs from the detail page because old/incomplete versions were counted.

### 7. Make `/orgs` canonical

Update `backend/routers/discovery_pages.py` and
`backend/services/discovery_page_service.py`:

- render organization documents at `/orgs/{slug}`;
- render scoped task documents at `/orgs/{slug}/{task_slug}`;
- reserve `orgs` as a top-level prefix;
- make `/organizations/{slug}` and `/organizations/{slug}/{task_slug}` return
  301 redirects to the corresponding `/orgs/...` URL;
- make legacy `/{slug}` and `/{slug}/{task_slug}` return 301 only when the
  organization exists;
- return a normal 404 for unknown legacy slugs;
- preserve query strings where relevant;
- use `/orgs/...` in canonical headers, HTML metadata, Markdown frontmatter,
  breadcrumbs, entity links, and structured data.

Update organization sitemap paths in `backend/services/sitemap_service.py` from
`/{slug}` to `/orgs/{slug}`. Sitemap output must contain only canonical URLs.

Update every internal organization link, including:

- organization links in `backend/services/discovery_page_service.py`;
- organization links in `backend/services/paper_seo_service.py`;
- paper detail organization buttons;
- index, detail, task, and breadcrumb links in the frontend.

The top-level catch-all currently makes every one- and two-segment client path
look like a possible organization. Once redirects are server-backed, remove the
organization detail views from the frontend catch-all routes. This reduces route
collisions and lets the normal `*` route handle unknown paths.

## Frontend experience

### 8. Organizations overview

Make a prominent logo grid the primary discovery surface in
`frontend/src/views/OrganizationsIndexView.tsx`. A visitor should be able to
scan recognizable labs and companies, click anywhere on a tile, and arrive
directly at `/orgs/{slug}`, where the organization's paper feed is already
visible without another navigation step.

Each grid tile contains:

- a large, centered organization logo in a fixed-ratio visual area;
- the organization display name below the logo so discovery does not depend on
  recognizing the mark;
- the linked-paper count as secondary text;
- one semantic link wrapping the complete tile, with an accessible label such
  as "Browse 152 NVIDIA papers";
- a clear hover treatment and keyboard-visible focus ring.

The grid should:

- show all 21 featured organizations without pagination;
- use a dense responsive layout (approximately two columns on narrow phones,
  three or four on tablets, and five or six on desktop);
- give logos consistent visual weight with `object-fit: contain`, internal
  padding, and a neutral tile background rather than stretching or cropping
  differently shaped marks;
- reserve logo dimensions to avoid layout shift;
- fall back to a styled organization initial or wordmark when `logo_url` is
  missing or fails to load;
- preserve a useful zero-paper tile that still links to the organization detail
  page and says "No papers indexed yet";
- rank by the backend-provided consolidated organization trending score by
  default, with client-side name search and optional “most papers” and
  alphabetical sorts;
- display loading skeletons in the same grid geometry and provide retryable
  error and no-search-results states.

Keep outbound website and Hugging Face links on the organization detail page so
each overview tile has one unambiguous click target. Treat the organization name
as visible text and the logo as decorative (`alt=""`) to avoid duplicate screen
reader announcements.

Use TanStack Query through `frontend/src/lib/api.ts`; do not fetch HF directly
from the browser.

### 9. Organization detail

Make `/orgs/{slug}` a paper-feed page rather than a taxonomy landing page. The
first viewport should establish the organization identity and begin its papers;
do not require visitors to click an intermediate "All papers" tile.

Retain these useful parts of `OrganizationDetailView.tsx`:

- organization identity and outbound links;
- total linked papers;
- a compact task filter derived from the existing task/area data;
- sort controls for trending, newest, and most cited;
- the infinitely paginated `PaperCard` feed, defaulting to trending.

Change all generated paths to `/orgs/{slug}`. Reuse one shared organization-feed
component between `/orgs/{slug}` and the task-specific
`/orgs/{slug}/{task_slug}` route so pagination, sorting, empty states, and paper
cards cannot drift between two implementations. Task filters may navigate to
the task-specific canonical route, while an "All papers" filter returns to
`/orgs/{slug}`.

Ensure the zero-paper detail page still renders organization metadata and the
"No papers indexed yet" message rather than disappearing as a 404.

## Tests and validation

### 10. Unit and service tests

Add focused backend tests for:

- balanced-array extraction with nested arrays, escaped strings, HTML entities,
  missing keys, malformed JSON, and truncated HTML;
- overview/papers count validation;
- daily-paper organization payload parsing for one object and a future list;
- the daily importer linking organizations for both new and already-existing
  papers;
- the daily importer ignoring organizations outside the curated manifest;
- unknown HF organizations producing diagnostics without database rows, links,
  or visible tiles;
- handle normalization and manifest uniqueness;
- idempotent organization upsert and paper linking;
- importing a missing ArXiv paper before linking it;
- a paper linked to multiple organizations;
- launch queries excluding non-HF organization links while retaining those rows
  for future/manual workflows;
- preserving `hf_org_papers` provenance when another source rediscovers the same
  paper-organization pair;
- rerunning a sync without duplicate rows;
- zero-paper organizations;
- failed/incomplete fetches not updating `last_hf_synced_at` or deleting links;
- later successful syncs never deleting previously linked papers that are absent
  from the latest HF payload;
- featured filtering and stable display order;
- consolidated organization trending aggregation using the active composite and
  GitHub rollback modes, the 24-hour input freshness cutoff, distinct-paper
  counting, idempotent daily snapshots, a rolling 30-day mean, cold-start
  behavior, and deterministic tie-breakers;
- cron registry definitions, dedicated locks, launcher allowlist entries, and
  database freshness metrics for both new daily jobs;
- `/api/v1/cron/status` returning both jobs so the generic admin dashboard
  renders their cards without frontend hard-coding;
- healthy/degraded/broken evaluation for fresh, missing, and stale organization
  sync/trend writes, including the permitted no-work sync case;
- organization list/detail paper counts using latest eligible papers.

Mock HF and ArXiv responses; tests must not depend on live network access.

### 11. Route, SEO, and frontend tests

Extend `backend/tests/test_search_discovery.py`,
`backend/tests/test_sitemaps.py`, and `backend/tests/test_organizations_api.py`
to assert:

- `/orgs/nvidia` is a rendered canonical page;
- `/nvidia` and `/organizations/nvidia` return 301 to `/orgs/nvidia`;
- task subpaths redirect equivalently;
- unknown legacy slugs remain 404;
- canonical `Link` headers, HTML, Markdown, breadcrumbs, and sitemap locations
  use `/orgs/...`;
- query-string pages are noindexed consistently;
- organization APIs paginate and sort as documented.

Add React tests for:

- logo-grid geometry/classes, full-tile links, accessible labels, broken-logo
  fallbacks, loading, errors, searching, sorting, and zero-paper tiles on the
  index;
- `/orgs/:orgSlug` and `/orgs/:orgSlug/:taskSlug` routing;
- the canonical detail route immediately loading a trending paper feed without
  an intermediate "All papers" click;
- shared detail/task filtering, sorting, empty state, and paper pagination;
- paper-detail organization links;
- the old broad catch-all no longer swallowing unknown routes.

Run targeted validation:

```bash
uv run --env-file backend/keys.env pytest \
  backend/tests/test_organizations_api.py \
  backend/tests/test_search_discovery.py \
  backend/tests/test_sitemaps.py

cd frontend
npm run lint
npm test -- --run OrganizationsIndexView OrganizationDetailView OrganizationTaskView
```

Do not run `npm run build` as a routine check.

## Rollout

### Phase 1: code and dry run

1. Add the migration, manifest, services, routes, UI updates, and tests.
2. Run the full-manifest sync with `--dry-run`.
3. Compare per-org extracted counts with HF overview counts.
4. Review import failures and duplicate/cross-org associations.

### Phase 2: staging data and application

1. Apply the migration to staging.
2. Run the real manifest sync in bounded batches.
3. Deploy the exact pushed commit to staging.
4. Verify `/organizations`, representative `/orgs/...` pages, a zero-paper org,
   task filtering, API pagination, old redirects, canonical metadata, Markdown,
   the organizations sitemap, and both new daily jobs on `/admin-dashboard`.
5. Confirm that no existing static route is intercepted by an organization
   alias.

### Phase 3: production

1. Apply the migration and run the idempotent bootstrap.
2. Deploy only with explicit production-release approval.
3. Smoke-test `/health`, `/`, `/organizations`, `/orgs/nvidia`,
   `/orgs/moonshotai`, `/orgs/black-forest-labs`, one organization API, and the
   legacy redirects.
4. Enable the recurring sync after one successful manual production run.
5. Monitor import failures, count drift, 404s, redirect volume, and sync
   freshness.

The application deploy and data bootstrap are independently rerunnable. If the
new application must be rolled back, legacy top-level URLs still redirect safely
only after confirming the active release understands `/orgs/...`; sequence the
route deployment before changing sitemap/canonical discovery in production.

## Acceptance criteria

- `/organizations` lists all 21 requested organizations ranked by their
  consolidated rolling 30-day paper-trending score, refreshed daily with
  deterministic tie-breakers rather than reshuffling hourly; the two that
  currently have zero HF papers remain clickable and say "No papers indexed
  yet".
- The 21-entry manifest is a strict allowlist: unknown HF organizations never
  create rows, links, or tiles during the initial release.
- `/organizations` presents them as a responsive logo grid whose complete tiles
  link to the corresponding `/orgs/{slug}` paper-discovery page.
- `/orgs/{slug}` immediately renders that organization's trending-first paper
  feed with compact task and sort controls; no second "All papers" click is
  required.
- Organization counts, pages, task filters, and paper badges use only
  HF-attributed (`source='hf_org_papers'`) associations at launch.
- The many-to-many model permits one paper to link to several organizations and
  reserves distinct provenance for a future AI affiliation extractor.
- HF organization links are append-only: syncs add newly attributed papers and
  never remove previously attributed papers.
- `/admin-dashboard` and `pwc cron health` expose health, last-run, lock,
  workflow, and database-freshness status for both the HF organization sync and
  rolling organization-trending jobs.
- Every nonzero HF-attributed paper is either linked locally or reported with a
  specific import failure; the run produces a reconciliation summary.
- Every missing valid ArXiv paper is imported with complete canonical metadata
  before its organization link is created; partial paper rows and dangling
  associations are never created.
- The existing HF daily-paper cron links its payload's curated organization for
  both new and pre-existing local papers, so new papers appear on organization
  pages without waiting for the full daily org-page backfill.
- Repeating the sync creates no duplicate organizations, papers, or links.
- `/orgs/{slug}` and `/orgs/{slug}/{task}` are the only canonical public
  organization URL shapes.
- `/nvidia`, `/nvidia/{task}`, `/organizations/nvidia`, and
  `/organizations/nvidia/{task}` permanently redirect to `/orgs/...`.
- All internal links, metadata, Markdown, and sitemaps use `/orgs/...`.
- Organization pages remain database-backed when HF is unavailable.
- API contracts remain backward compatible.
- Focused backend/frontend tests pass, and staging smoke tests cover normal,
  zero-paper, and legacy-route cases.

## References

- HF organization papers example:
  <https://huggingface.co/moonshotai/papers>
- HF organization overview example:
  <https://huggingface.co/api/organizations/moonshotai/overview>
- HF paper pages documentation:
  <https://huggingface.co/docs/hub/paper-pages>
- `huggingface_hub` API reference:
  <https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api>
- HF OpenAPI explorer:
  <https://huggingface.co/spaces/huggingface/openapi>
