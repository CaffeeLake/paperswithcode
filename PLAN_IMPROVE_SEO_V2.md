# Plan: Improve SEO V2 — Search Console and contextual discovery

Status: **proposed**
Last updated: 2026-07-28
Depends on: `IMPROVE_SEO.md` and deployed SEO V1

## Decision

Implement the next two SEO priorities:

1. activate and verify Google's discovery loop through a correct
   `robots.txt`, sitemap submission, URL Inspection, and measurable Search
   Console evidence; and
2. make the initial HTML for important public browse/entity pages contain
   useful, contextual links to papers before JavaScript runs.

V2 is not a keyword-placement exercise. It improves the paths by which a
crawler discovers, understands, prioritizes, and revisits canonical paper
pages. The implementation must expose the same content to users and crawlers,
must not vary by user agent, and must not create indexable filter combinations.

The first qualification target remains:

```text
https://paperswithcode.co/paper/2607.24653
```

for `Kimi K3 technical report` and `Kimi K3 arxiv`. Site-wide qualification
must also prove that a newly ingested eligible paper becomes discoverable from
the sitemap and at least one contextual HTML page without executing
JavaScript.

## Current state

SEO V1 established:

- crawlable initial HTML on canonical paper pages;
- paper-specific titles, descriptions, Highwire metadata, and scholarly
  JSON-LD;
- a valid XML sitemap index and paper shards;
- recent and historical HTML paper archives;
- canonical redirects and real `404` responses.

The 2026-07-28 production audit found two remaining discovery gaps:

1. `robots.txt` is not a clean origin document. Cloudflare's managed content
   signals are followed by the generic SPA HTML, and there is no
   `Sitemap: https://paperswithcode.co/sitemap.xml` directive.
2. The raw initial HTML for `/`, task pages, and method pages contains no paper
   links. `/papers/recent` contains links, but it is a flat archive rather than
   a semantically relevant recommendation from a task, method, benchmark,
   conference, organization, or author page.

## Goals

- Return a valid, plain-text `robots.txt` with the canonical sitemap declared
  exactly once.
- Preserve Cloudflare's managed search/content-use preferences while removing
  the accidental SPA document from `robots.txt`.
- Verify the `paperswithcode.co` Search Console domain property, submit the
  sitemap index, inspect Kimi K3, and record the result.
- Add ordinary `<a href="/paper/...">` links to the initial HTML of the
  homepage and public entity pages.
- Make each indexable entity page a useful standalone document with a unique
  heading, description/context, canonical URL, and a bounded list of relevant
  papers.
- Add entity pages to sitemaps only after they return `200`, are
  self-canonical, and have useful content.
- Keep filtered, sorted, paginated, and empty combinations out of the index.
- Add release smoke tests that catch regressions in robots, sitemap discovery,
  initial contextual links, canonical behavior, and soft 404s.
- Establish a repeatable Search Console measurement cadence for crawl,
  indexing, impressions, click-through rate, and target queries.

## Non-goals

- Do not promise first place or any specific Google position.
- Do not use the Google Indexing API for ordinary paper pages. Its supported
  use cases do not include general research-paper URLs.
- Do not add guessed DNS verification tokens or commit Search Console,
  Cloudflare, or service-account credentials.
- Do not request indexing for every paper manually.
- Do not serve crawler-only links, hidden keyword blocks, doorway pages, or
  user-agent-specific documents.
- Do not render every paper associated with an entity in one response.
- Do not make arbitrary search, sort, pagination, or filter query strings
  indexable.
- Do not add low-value author pages that cannot be disambiguated or have no
  eligible public papers.
- Do not replace React with a new rendering framework in V2.
- Do not apply an nginx change or deploy to production without explicit
  authorization.

## Success criteria

### Crawl-control and Search Console

- `GET` and `HEAD https://paperswithcode.co/robots.txt` return `200` with
  `Content-Type: text/plain`.
- The response contains no HTML and includes exactly:

  ```text
  Sitemap: https://paperswithcode.co/sitemap.xml
  ```

- The public response continues to allow search crawling. Cloudflare-managed
  content signals and configured AI-crawler rules remain intact.
- Staging returns a separate non-indexable policy:

  ```text
  User-agent: *
  Disallow: /
  ```

- Search Console reports that `/sitemap.xml` was fetched and processed without
  syntax errors.
- URL Inspection for `/paper/2607.24653` reports a successful live fetch,
  allows indexing, sees the intended canonical, and renders the paper title
  and abstract.
- The Search Console actions, dates, account owner, and screenshots/exported
  evidence are recorded in the release issue or operational log, not in source
  control if they contain account information.

### Contextual discovery

- The raw HTML from the default homepage contains at least 20 canonical paper
  links and at least 5 entity links.
- A representative task, method, benchmark, conference, organization, and
  author page contains a unique `<h1>` plus at least one relevant canonical
  paper link in raw HTML.
- Initial links and the first React-rendered result set agree on entity and
  default ordering semantics.
- All database-derived values are escaped; no database value is inserted as
  raw HTML.
- Missing entities return `404`; empty filter combinations do not soft-404 to
  the homepage.
- Default entity URLs are self-canonical. Non-indexable query variants emit
  `noindex,follow` and canonicalize to the unfiltered page.
- Representative discovery pages stay within the agreed response-time and
  query-count budgets. Initial target: warm backend p95 below 300 ms and no
  per-paper relation query.
- Entity sitemap URLs sampled in release smoke tests return indexable `200`
  documents with self-canonicals.

## Target architecture

```text
paper/entity database
        |
        +-----------------------+
        |                       |
        v                       v
discovery-page service     sitemap service
        |                       |
        v                       v
semantic initial HTML      canonical URL shards
        |                       |
        +-----------+-----------+
                    |
                    v
           crawler discovers paper
                    |
                    v
   robots.txt -> sitemap.xml -> Search Console
```

The existing backend-generated initial paper document is the model. V2 will
reuse the active Vite shell and inject an accessible entity document inside
`#root`. React will replace it when the application starts. Content must remain
visible and useful when JavaScript is unavailable.

## Workstream 1: Activate Search Console discovery

### 1.1 Serve a real origin `robots.txt`

Add an exact root route, preferably in
`backend/routers/search_discovery.py`, with `GET` and `HEAD` support.

Production origin response:

```text
User-agent: *
Allow: /
Sitemap: https://paperswithcode.co/sitemap.xml
```

Staging response:

```text
User-agent: *
Disallow: /
```

Requirements:

- return `PlainTextResponse`;
- set `X-Robots-Tag: noindex, nofollow` on staging responses and staging HTML;
- select behavior from the validated deployment environment, not the host
  header supplied by the client;
- include no Cloudflare-specific crawler list in application source;
- preserve a final newline;
- never fall through to the Vite SPA shell.

Use an application route rather than a shared Vite public file because
production and staging need different policies. Add exact nginx locations in
both checked-in templates that proxy `/robots.txt` to the corresponding
backend, before the static catch-all.

Cloudflare may prepend or merge managed robots content at the public edge.
Treat the final edge response—not only the origin response—as the acceptance
artifact. Confirm that its existing `search=yes, ai-train=no, use=reference`
policy and any managed AI crawler blocks remain present after deployment.

### 1.2 Add robots and sitemap release checks

Extend `deploy/smoke_test.py`, `deploy/nginx_validate.py`, and focused runtime
tests to assert:

- exact `/robots.txt` routing precedes the SPA catch-all;
- production origin policy allows crawling and advertises the sitemap;
- staging disallows all crawling and does not advertise the production
  sitemap;
- public robots is plain text and does not contain `<!doctype`, `<html`, or
  the application root;
- the canonical sitemap directive appears exactly once in the effective
  public response;
- `/sitemap.xml` remains XML and its referenced shards are fetchable;
- `GET` and `HEAD` agree on status and relevant headers.

Do not make deployment depend on the exact ordering of Cloudflare-managed
comments or its evolving list of AI user agents. Test stable outcomes.

### 1.3 Establish or verify Search Console ownership

This is an account-bound operator task:

1. Open the Google Search Console domain property for `paperswithcode.co`.
2. If it already exists, record the verified owner and current user access.
3. If it does not exist, request a domain-property verification token and add
   that exact TXT record through the authoritative DNS provider.
4. Wait for DNS propagation, verify ownership, and remove no unrelated TXT
   records.
5. Grant least-privilege access to the operator or service account that will
   read reports.

Never invent a verification token. Do not commit the token or credentials.
Although DNS verification tokens are publicly observable, they remain
environment configuration rather than application source.

### 1.4 Submit and validate the sitemap

After the robots release is public:

1. Submit `https://paperswithcode.co/sitemap.xml` in Search Console's Sitemaps
   report.
2. Confirm the fetched type is a sitemap index.
3. Confirm the discovered URL count is plausible relative to the eligible
   paper count.
4. Review each shard class for parse, fetch, canonical, redirect, or excluded
   URL errors.
5. Record submission time, first successful fetch, discovered count, and any
   error examples.

The sitemap is a discovery hint, not a ranking guarantee. Keep the root index
stable and update its shards automatically from the database.

Optional follow-up: if a Search Console API service account is available and
has property access, automate sitemap submission and read-only reporting.
Credentials must live in the protected environment. The browser workflow
remains the initial source of truth.

### 1.5 Inspect and request recrawl for Kimi K3

Use URL Inspection for:

```text
https://paperswithcode.co/paper/2607.24653
```

Record:

- URL availability to Google;
- last crawl and crawl user agent;
- declared and Google-selected canonical;
- indexing status and exclusions;
- rendered title, abstract, resource links, and structured data;
- referring sitemap;
- whether a live test differs from the indexed copy.

If the live test succeeds, use **Request indexing** once. Do not repeatedly
submit the same URL and do not use the Indexing API as a workaround.

Inspect one recent ordinary paper and one historical paper as controls. This
distinguishes a Kimi-specific issue from a site-wide discovery issue.

### 1.6 Create a measurement baseline

Export or record the previous 28 days and then review weekly:

- target queries: `Kimi K3 technical report`, `Kimi K3 arxiv`, `Kimi K3
  paper`, and title variants;
- page-level clicks, impressions, CTR, and average position for the Kimi URL;
- indexed/not-indexed counts by sitemap;
- crawl requests and response classes;
- Google-selected canonical mismatches;
- title-link rewrites;
- discovery lag from database publication to first Google crawl.

Compare 7-day and 28-day windows, annotate deployments, and avoid drawing
conclusions from one-day rank movement. Keep reports segmented by query,
country, device, and page when volume permits.

## Workstream 2: Server-render contextual paper links

### 2.1 Extract a shared SPA shell service

The paper route already loads the active release's Vite `index.html`. Move that
logic from `backend/routers/paper_pages.py` into a small shared service such as
`backend/services/spa_shell_service.py`.

It must:

- prefer the immutable active-release shell in deployment;
- retain the existing development fallback;
- cache by resolved path and modification time;
- provide safe head-metadata and root-document injection helpers;
- fail visibly if a deployed shell is unavailable;
- preserve the paper route's behavior and tests.

Do not duplicate shell-path resolution or HTML string replacement across
routers.

### 2.2 Define bounded discovery view models

Add `backend/services/discovery_page_service.py` with view models such as:

```text
DiscoveryPage
  kind
  canonical_url
  title
  description
  heading
  breadcrumbs
  entity_links
  paper_links
  robots

DiscoveryPaperLink
  route_identifier
  title
  authors
  published
  context_label
```

Build these models with bounded queries that reuse `PaperService`,
`TaskService`, `MethodService`, `DatasetService`, `ConferenceService`,
`OrganizationService`, and `AuthorService`. Add optimized service methods only
where existing API projections are substantially heavier than the initial
document needs.

Shared rules:

- use the canonical paper route identifier;
- apply the sitemap service's public paper eligibility predicate;
- use a constant number of relation queries;
- cap initial paper lists at 20–30 entries;
- render an explicit empty state but mark an entity with no useful content
  `noindex,follow`;
- sort deterministically, with a stable tie-breaker;
- never expose pending, merged-away, superseded, or private rows.

### 2.3 Render semantic, safe initial HTML

Add a renderer that emits:

```html
<main data-pwc-initial-document="discovery">
  <nav aria-label="Breadcrumb">...</nav>
  <header>
    <p>Task</p>
    <h1>Language Modeling</h1>
    <p>...</p>
  </header>
  <nav aria-label="Related research topics">...</nav>
  <section aria-labelledby="papers-heading">
    <h2 id="papers-heading">Relevant papers</h2>
    <ol>
      <li>
        <article>
          <h3><a href="/paper/...">...</a></h3>
          <p>Authors · date · relationship to this page</p>
        </article>
      </li>
    </ol>
  </section>
</main>
```

Requirements:

- escape all database-derived values with
  `html.escape(..., quote=True)`;
- never insert stored HTML;
- use one `<h1>` and a logical heading hierarchy;
- use ordinary crawlable anchors, not click handlers;
- link only canonical public paper URLs;
- include enough context to explain why the papers are on the page;
- do not hide or visually move the initial document off-screen;
- keep initial CSS in the existing shell small and consistent with the React
  layout;
- let React replace the document without a duplicate visible tree.

### 2.4 Homepage

Serve the default `/` route from the backend and inject:

- the current top/trending tasks;
- 20–30 papers using the same default ranking and time-window semantics as
  `FeedView`;
- canonical links to `/papers/recent`, `/papers/archive`, `/tasks`, and
  `/methods`.

Only the default homepage is indexable. Sort/time/filter query variants should
render the requested user experience but emit:

```html
<meta name="robots" content="noindex,follow">
<link rel="canonical" href="https://paperswithcode.co/">
```

Do not include query variants in a sitemap.

### 2.5 Task pages

For `/tasks/{task_slug}`, include:

- task name, description, research trends, and area;
- parent, child, and closely related task links where the taxonomy provides
  them;
- benchmark links;
- 20 relevant papers using the React page's default ordering.

The backend and `TagBrowseView` must use one documented default ordering.
Legacy `/task/{slug}` must remain a permanent redirect to the plural canonical
route.

### 2.6 Method pages

For `/methods/{method_slug}`, include:

- method name and description;
- source paper and project links when present;
- related methods/tasks;
- 20 papers associated with the method.

Avoid pages whose only visible content is the method name. Missing methods
return `404`; aliases redirect to the canonical slug.

### 2.7 Benchmark pages

For `/benchmark/{dataset_slug}`, include:

- benchmark/dataset name and description;
- associated tasks and configured metrics;
- a bounded set of top comparable leaderboard rows;
- paper links for those rows and recent benchmark papers.

Do not flatten incompatible metrics or evaluation setups into one ordered
claim. Each initial result must retain its metric and evaluation context.

Treat `?task=`, metric, split, and sort combinations as facets. Unless a
specific combination is deliberately promoted to a standalone canonical
route, emit `noindex,follow`, canonicalize to the base benchmark page, and omit
it from internal discovery lists and sitemaps.

### 2.8 Conference pages

For `/conferences/{conference_slug}`, include:

- conference name, edition, dates, venue, and description;
- task/category links;
- a bounded list of accepted, notable, or recent papers.

For `/conferences/{conference_slug}/{task_slug}`, use a self-canonical only
when the combination is a stable, curated browse page with multiple papers and
unique context. Otherwise mark it `noindex,follow` and canonicalize to the
conference page.

### 2.9 Organization pages

Canonical organization routes currently live at `/{organization_slug}` and
`/{organization_slug}/{task_slug}`. Preserve that public contract.

Add an organization resolver to the public-page backend gateway:

- reserve all application route prefixes before attempting organization
  lookup;
- resolve an exact organization slug;
- render the organization description, website, related tasks, and 20 papers;
- retain permanent redirects from `/organizations/{slug}` aliases;
- return `404` for an unknown top-level slug rather than a generic SPA `200`;
- self-canonicalize the top-level organization route.

Because this requires replacing nginx's generic SPA fallback with a backend
public-page fallback, roll it out after the explicit homepage/task/method/
benchmark/conference routes. The backend fallback must load the same immutable
SPA shell for known client-only routes and must never intercept `/api`,
fingerprinted assets, thumbnails, or deployment endpoints.

Before rollout, maintain and test a reserved-prefix registry shared by the
public router and route tests. Include at least all routes in `App.tsx`,
authentication callbacks, admin pages, API prefixes, sitemap/archive routes,
and static asset prefixes.

### 2.10 Author pages

There is an author API but no public frontend author route. Add:

```text
/authors/{author_id}
```

Use the stable database author ID initially; names are neither unique nor
stable enough to be the canonical key. Add a React `AuthorDetailView` for the
interactive state and a backend initial document containing:

- display name;
- verified Hugging Face identity or other public profile when present;
- organization links where known;
- 20 eligible papers.

Link paper bylines to author pages only when the paper-author relation resolves
to a stable author row. Do not generate ambiguous name-based URLs.

Author pages with zero eligible papers should return `404` or
`noindex,follow`; choose `404` when no public author entity exists and
`noindex,follow` when the entity is valid but temporarily empty.

### 2.11 Public-page routing

Add `backend/routers/discovery_pages.py` after API, sitemap, and paper routers.
Roll routing out in two stages:

1. exact nginx proxy locations for `/`, tasks, methods, benchmarks,
   conferences, and authors;
2. a named backend fallback for top-level organization resolution and known
   client-only SPA routes.

The final nginx order must be:

```text
exact operational/static routes
API and thumbnail routes
fingerprinted/static assets
robots, sitemap, archive, paper routes
explicit discovery routes
filesystem static files
named public-page backend fallback
```

The backend public router must be last and must distinguish:

- indexable discovery document;
- known client-only SPA document;
- legacy redirect;
- real unknown `404`.

This routing change requires focused nginx validation and explicit
environment-specific application through `pwc-nginx`; an application deploy
alone does not activate checked-in nginx changes.

### 2.12 Entity sitemaps

After each page class is live and qualified, extend the sitemap index with
separate entity sitemap classes:

```text
/sitemaps/tasks.xml
/sitemaps/methods.xml
/sitemaps/benchmarks.xml
/sitemaps/conferences.xml
/sitemaps/organizations.xml
/sitemaps/authors-<shard>.xml
```

Include only pages that:

- return `200`;
- are allowed to be indexed;
- declare themselves canonical;
- have a unique heading/description and at least one eligible public paper;
- use the production apex hostname.

Shard at 50,000 URLs and 50 MB uncompressed, using a lower operational target
where practical. Use `<lastmod>` only for significant content or relationship
changes. Do not update every entity timestamp because a background job ran.

### 2.13 Strengthen contextual cross-links

Use real relationships rather than site-wide keyword lists:

- paper → task, method, benchmark, conference, organization, author;
- task → benchmark, related task, relevant paper;
- method → source paper, related method/task, relevant paper;
- benchmark → task, metric-specific paper;
- conference → task and accepted paper;
- organization → task, author, and paper;
- author → organization and paper;
- homepage → current papers and high-value task pages.

Keep the existing recent/archive links as coverage backstops. Contextual links
supplement the archive; they do not replace the sitemap.

## Canonical and indexing policy

| URL class | Status | Canonical | Robots |
| --- | --- | --- | --- |
| Default homepage | `200` | self | `index,follow` |
| Canonical entity with useful papers | `200` | self | `index,follow` |
| Supported query/filter variant | `200` | unfiltered base | `noindex,follow` |
| Empty filter combination | `404` | none | implicit |
| Legacy alias | `301` | destination | implicit |
| Unknown entity/slug | `404` | none | implicit |
| Valid but temporarily thin entity | `200` | self | `noindex,follow` |
| Staging page | auth boundary | none | `noindex,nofollow` |

Do not use `robots.txt` to hide query variants that need their HTML
`noindex` directive observed. Avoid generating crawlable anchors to arbitrary
facets in the first place.

## Test plan

### Unit tests

- environment-aware robots policy and final newline;
- sitemap directive uniqueness;
- discovery view-model eligibility and deterministic ordering;
- HTML escaping for headings, descriptions, authors, and paper titles;
- canonical identifier selection;
- facet canonical/noindex policy;
- reserved route-prefix classification;
- entity sitemap eligibility and sharding.

### Router tests

For each page class:

- `GET` and `HEAD`;
- successful semantic initial document;
- canonical and robots metadata;
- expected paper/entity anchors;
- alias redirect;
- real missing-entity `404`;
- empty/thin behavior;
- no accidental API or static-asset interception.

### Frontend tests

- add and exercise the author route;
- confirm initial markup is replaced once React commits;
- confirm default ordering and first-page entities match backend semantics;
- verify internal links navigate without full-page breakage;
- confirm query/filter views preserve user state while remaining non-indexable.

### Deployment and smoke tests

Extend release smoke coverage with:

- effective production/staging robots policy;
- sitemap directive and XML response types;
- raw homepage paper-link count;
- one representative task, method, benchmark, conference, organization, and
  author initial document;
- self-canonical entity URL sampled from every entity sitemap;
- legacy redirects and unknown-path `404`;
- staging auth/noindex boundary;
- query-count and response-time sampling.

Use an HTML parser rather than fragile substring matching for headings,
canonicals, robots directives, and anchor counts.

## Rollout

### Phase 0: Baseline

- Save current production robots, sitemap counts, raw HTML link counts, and
  Search Console reports.
- Select stable representative entities for all page classes.
- Record current Kimi URL Inspection and query performance.

### Phase 1: Robots and Search Console

- Add the environment-aware robots route and exact nginx locations.
- Validate locally and deploy the application commit to staging.
- Apply only the reviewed staging nginx change with explicit authorization.
- Verify staging disallow behavior.
- With explicit production authorization, deploy the exact commit and apply
  the production nginx template.
- Verify the final Cloudflare-edge robots response.
- Submit the sitemap and request Kimi recrawl.

### Phase 2: Shared renderer and exact discovery routes

- Extract the SPA shell loader.
- Implement the discovery service/renderer.
- Add homepage, task, method, benchmark, conference, and author initial
  documents.
- Validate parity, escaping, performance, and failure behavior.
- Deploy and qualify on staging before requesting production release.

### Phase 3: Organization/public fallback

- Add the reserved route registry and backend public-page fallback.
- Render canonical organization pages.
- Exhaustively test APIs, assets, auth, admin, chat feature boundaries, and
  unknown routes.
- Roll out staging first and monitor backend request volume/cache behavior.

### Phase 4: Entity sitemaps and cross-links

- Enable one qualified entity sitemap class at a time.
- Add cross-links from paper bylines/resources and entity documents.
- Check sampled URLs, shard sizes, and Search Console processing.

### Phase 5: Measure and iterate

- Review Search Console weekly for at least four weeks.
- Compare discovery/indexing lag and impressions against the Phase 0 baseline.
- Fix canonical/exclusion clusters before expanding page volume.
- Adjust snippets and visible content only when query/page evidence supports
  the change.

## Release and rollback gates

Every repository implementation change must:

1. run focused backend, frontend, nginx-validation, and deployment smoke tests;
2. preserve unrelated work in the checkout;
3. be committed and pushed as one exact `main` commit;
4. deploy that exact commit to staging;
5. report staging `current`, `previous`, and smoke results.

Production deployment and nginx application remain separate explicit
authorizations. For each production phase:

- record the exact commit and current rollback release;
- qualify the candidate;
- deploy backend and frontend with `pwc-deploy`;
- apply nginx only if the phase includes a reviewed nginx diff;
- smoke robots, sitemap, homepage, paper, entity, API, and asset routes;
- roll back the complete release if application validation fails;
- use the supported nginx rollback/application path for nginx failures.

## Operational ownership

| Item | Suggested owner | Evidence |
| --- | --- | --- |
| Robots/application implementation | Repository engineer | Tests and release smoke |
| Cloudflare managed robots policy | DNS/edge administrator | Effective public response |
| Search Console ownership | Search/operations owner | Verified property access |
| Sitemap submission | Search/operations owner | Sitemaps report |
| URL Inspection/request indexing | Search/operations owner | Inspection record |
| Initial HTML discovery pages | Backend/frontend engineer | Raw HTML and parity tests |
| Entity sitemap quality | Data/platform engineer | Eligibility report |
| Weekly SEO review | Product/search owner | Annotated Search Console report |

## Risks and mitigations

### Cloudflare overwrites or duplicates robots directives

Validate the final public response. Keep origin robots minimal and test stable
policy outcomes rather than Cloudflare's generated comment text.

### The public-page fallback breaks SPA routes

Roll out explicit routes first. Add a complete reserved-prefix registry,
backend fallback tests, staging traffic observation, and an immediate immutable
release/nginx rollback path before organization routing.

### Contextual rendering adds database load

Use bounded projections, set hard result limits, eager-load relations, measure
query counts, cache stable entity documents briefly, and never query once per
paper.

### Backend and React show different papers

Share ordering/filter constants and service semantics. Test the first page from
both paths using stable fixtures.

### Entity sitemaps create many thin pages

Gate inclusion on useful content and eligible papers. Launch sitemap classes
only after their HTML pages are qualified.

### Faceted URLs consume crawl budget

Do not emit arbitrary facet links. Apply `noindex,follow` plus base canonicals
to supported query variants and return `404` for invalid/empty combinations.

### Search performance does not improve immediately

Sitemap submission and recrawl are hints. Use four-week annotated trends,
control pages, and indexing evidence before changing strategy.

## Definition of done

V2 is complete when:

- effective production `robots.txt` is valid plain text, preserves the intended
  Cloudflare content-use policy, and advertises `/sitemap.xml`;
- Search Console ownership, sitemap processing, and Kimi URL Inspection have
  recorded successful evidence;
- the homepage and all six entity classes expose bounded, relevant paper links
  in raw initial HTML;
- entity pages have correct status, canonical, robots, and thin-page behavior;
- qualified entity pages are represented in valid sitemap shards;
- focused tests and release smoke checks prevent regressions;
- production rollout was separately authorized and retains a verified
  rollback target;
- weekly measurement has an owner, baseline, and first post-release review.

## Primary references

- [Google: Build and submit a sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Google: Consolidate duplicate URLs](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
- [Google: Managing crawling of faceted navigation URLs](https://developers.google.com/crawling/docs/faceted-navigation)
- [Google: Article structured data](https://developers.google.com/search/docs/appearance/structured-data/article)
- [Cloudflare: Managed robots.txt](https://developers.cloudflare.com/bots/additional-configurations/managed-robots-txt/)
