# Plan: Improve paper-page SEO and discovery

Status: **proposed**
Last updated: 2026-07-28

## Decision

Make every public paper page a useful, crawlable HTML document before
JavaScript runs. Keep the React application as the interactive experience, but
serve the paper's title, authors, publication date, identifier, abstract, and
important resource links in the initial response. Add real XML sitemaps and
simple HTML browse pages so crawlers can discover new and historical papers
without entering Google's JavaScript rendering queue.

Treat metadata and structured data as supporting signals, not as substitutes
for visible content. A paper page should earn search visibility by combining
accurate bibliographic information with the information that makes Papers with
Code distinct: code, project pages, Hugging Face artifacts, tasks, methods,
benchmarks, evaluations, and related work.

The first qualification target is:

```text
https://paperswithcode.co/paper/2607.24653
```

for the queries `Kimi K3 technical report`, `Kimi K3 arxiv`, `Kimi K3 paper`,
and `Kimi K3 Open Frontier Intelligence`. No implementation can guarantee the
first Google result, especially for navigational queries where ArXiv or the
publisher is the expected destination. The goal is to make the PwC result
eligible, timely, accurate, compelling, and measurably competitive.

## Goals

- Put the paper's meaningful content and ordinary links in the initial HTML.
- Allow search engines to discover every canonical paper URL without executing
  JavaScript.
- Reduce the delay between paper ingestion and first Google crawl/indexing.
- Emit unique titles, descriptions, canonical URLs, bibliographic metadata,
  and valid structured data for every paper.
- Preserve one canonical URL per paper across ArXiv versions, merged rows,
  legacy routes, and the `www` hostname.
- Give high-value papers enough unique, accurate information to answer likely
  search intent rather than merely repeat the ArXiv abstract.
- Add automated checks so an empty app shell, invalid sitemap, soft 404, or
  conflicting canonical cannot silently return.
- Measure indexing coverage, discovery latency, click-through rate, and query
  position instead of treating deployment as proof of SEO success.

## Non-goals

- Do not promise or report a guaranteed Google position.
- Do not create crawler-only content, vary content by user agent, hide keyword
  blocks, buy links, or use other search-manipulation techniques.
- Do not change the canonical paper title stored in the database merely to add
  search phrases.
- Do not canonicalize PwC paper pages to ArXiv. PwC pages contain distinct
  resources and should remain their own canonical documents.
- Do not expose private, pending, superseded, merged-away, or otherwise
  non-public rows through sitemaps or browse pages.
- Do not add a new frontend rendering framework in the first phase.
- Do not require complete evaluation enrichment before a new paper can be
  indexed.
- Do not deploy to production or apply nginx changes without the separately
  required authorization.

## Current state

The production audit on 2026-07-28 found:

1. `GET /paper/2607.24653` returns a fast `200` response with a correct
   paper-specific title, description, canonical URL, Open Graph tags, and
   Twitter tags.
2. Its response body contains only `<div id="root"></div>`. The visible title,
   authors, abstract, identifiers, resources, tasks, methods, and internal links
   arrive after React and the paper API execute.
3. The homepage follows the same app-shell pattern, so the initial HTML exposes
   no paper links.
4. `GET /sitemap.xml` returns the generic SPA HTML with status `200`, rather
   than a sitemap. This is a false-success route caused by the static catch-all.
5. `robots.txt` permits search crawling, but does not advertise a sitemap.
6. `/paper/<id>` is canonical, `www` redirects to the apex host, and missing
   papers already receive a server-side `404`.
7. `HEAD /paper/<id>` currently receives `405`. Google indexes with `GET`, so
   this is not the primary issue, but supporting `HEAD` will make monitoring and
   crawler diagnostics consistent.
8. Paper pages do not emit Highwire Press `citation_*` tags or scholarly
   JSON-LD.
9. The Kimi K3 record has an abstract, date, tasks, methods, and a Hugging Face
   model link, but no TLDR in the paper response and incomplete visible
   official-resource coverage.

The existing implementation is concentrated in:

- `backend/routers/paper_pages.py`, which resolves a paper and returns the
  active Vite shell;
- `backend/services/social_meta_service.py`, which builds and injects the
  per-paper metadata;
- `backend/services/paper_service.py`, which resolves canonical paper rows and
  optionally loads resources;
- `frontend/src/views/PaperDetailView.tsx`, which renders the interactive page;
- `frontend/src/main.tsx`, which mounts React with `createRoot`;
- `deploy/nginx/paperswithcode.co.conf` and
  `deploy/nginx/staging.paperswithcode.co.conf`, which proxy paper routes but
  currently let sitemap and browse routes fall through to static HTML.

## Target architecture

```text
paper ingestion or curation
          |
          +--------------------------+
          |                          |
          v                          v
 canonical paper record       sitemap/browse query
          |                          |
          v                          v
 PaperSeoDocument             XML sitemap shards
          |                    HTML recent archive
          v                          |
 initial /paper/<id> HTML <-----------+
          |
          +-- visible bibliographic content and crawlable links
          +-- title, description, canonical, citation tags, JSON-LD
          +-- React/Vite scripts and styles
          |
          v
 React replaces/enhances the initial document with the interactive view
```

The backend remains the source of the first response because it already owns
paper resolution and sits in front of `/paper/<id>`. V1 will use progressive
initial HTML rather than introducing full React server-side rendering:

- inject a small, visibly styled paper document inside `#root`;
- load the existing application bundle normally;
- let `createRoot(...).render(...)` replace that equivalent initial content
  when the interactive page commits;
- do not hide the initial document or serve different content to crawlers;
- keep the initial layout close enough to the React header to avoid a large
  layout shift.

This is an incremental design. If replacement causes unacceptable Core Web
Vitals or maintenance duplication, a later phase can move the paper route to
true React SSR and `hydrateRoot`. That migration is not required to fix
discovery and initial-content indexing.

## Workstream 1: Server-render the paper document

### 1.1 Define a stable SEO view model

Add a small dataclass such as `PaperSeoDocument` in a new
`backend/services/paper_seo_service.py`. It should contain only fields needed
for the initial document:

```text
route_identifier
title
search_title
description
abstract
authors
published
arxiv_id
source
source_url
url_abs
url_pdf
thumbnail
tldr
conference
repositories
project_pages
hf_models
hf_datasets
hf_spaces
tasks
methods
organizations
introduced_benchmarks
```

Construct it from the canonical `Paper` API model returned by
`PaperService.get_paper_by_id_or_arxiv(..., include_resources=True)`. Keep
canonical resolution in `PaperService`; do not duplicate merge, version, or
external-resource resolution in the SEO service.

If loading the full resource projection makes the paper route materially
slower, add one bounded relation query in `paper_seo_service.py`. Do not issue
one query per author or resource. The target is a constant number of queries
per response and a warm p95 backend response below 250 ms.

The abstract is required visible content when present. Optional enrichment
must degrade independently: a missing TLDR, repository, thumbnail, or
evaluation must never make the paper page fail.

### 1.2 Render safe semantic HTML

Extend `social_meta_service.py`, or split its rendering responsibilities into
`paper_seo_service.py`, to produce:

```html
<main class="initial-paper" data-pwc-initial-document="paper">
  <nav aria-label="Breadcrumb">...</nav>
  <article>
    <header>
      <p>Paper · arXiv:2607.24653 · 27 July 2026</p>
      <h1>Kimi K3: Open Frontier Intelligence</h1>
      <p class="citation_author">Kimi Team, ...</p>
    </header>
    <section aria-labelledby="abstract-heading">
      <h2 id="abstract-heading">Abstract</h2>
      <p>...</p>
    </section>
    <nav aria-label="Paper resources">...</nav>
    <section aria-label="Tasks and methods">...</section>
  </article>
</main>
```

Requirements:

- escape every database-derived value with `html.escape(..., quote=True)`;
- convert supported LaTeX title text with the existing
  `latex_to_plain_text`;
- allow no database-derived raw HTML;
- use real `<a href>` elements for PwC, ArXiv, project, code, and artifact
  links;
- apply `rel="noopener noreferrer"` to new-tab external links;
- use an `<h1>` for the official title and ordinary text for repository/site
  branding;
- render the complete author-written abstract, not the 280-character social
  description;
- do not make unavailable sections or placeholder copy indexable;
- preserve a useful, readable page if JavaScript fails.

Add minimal initial-document CSS to `frontend/index.html` or a small,
fingerprinted stylesheet available before the application bundle. Prefer
matching existing typography and widths. The initial content must not be
`display:none`, visually off-screen, or removed based on user agent.

### 1.3 Insert the document into the shell

Replace the empty root during `inject_paper_meta` with the rendered document.
Use a narrowly matched root placeholder and fail closed in tests if the active
Vite shell no longer contains it. Continue to inject metadata immediately
before `</head>`.

Update `frontend/src/main.tsx` only as needed to make replacement explicit and
safe. The completed React paper page should contain materially the same title,
authors, date, abstract, and resource links as the initial document. Add a
development warning or test when these two representations diverge.

### 1.4 Preserve correct HTTP behavior

- Keep canonical paper routes at `200`.
- Return `404` for unknown or deleted identifiers with a minimal, index-safe
  error document; do not return the generic index shell.
- Return `301` from `/papers/<id>` and merged identifiers directly to the
  canonical `/paper/<route_identifier>` URL. Replace the current legacy
  `200 + Link rel=canonical` behavior.
- Normalize ArXiv version suffixes and merged internal IDs through the existing
  resolver before rendering.
- Continue the apex-host `301` from `www`.
- Add `HEAD` support with the same status, canonical `Link` header where
  useful, content type, and cache policy as `GET`, but no response body.
- Return `503`, not a generic `200`, when a database outage prevents resolving
  the document. This prevents an outage shell from being indexed as the paper.

### 1.5 Cache without making edits stale

Keep the initial implementation's bounded public cache:

```text
Cache-Control: public, max-age=300, stale-while-revalidate=3600
```

Use an ETag derived from the canonical paper ID and the record/resource update
timestamp if those timestamps can be obtained without another expensive query.
Otherwise defer ETag support. Curation writes should invalidate the relevant
edge/application cache when a supported invalidation mechanism exists; a
five-minute maximum age is acceptable for V1.

## Workstream 2: Titles, descriptions, and query intent

### 2.1 Separate official and search titles

The visible `<h1>` must remain the official paper title. Generate a concise
search title without mutating the database title:

```text
ArXiv paper:
{official title} (arXiv:{id}) | Papers with Code

External resource:
{official title} | Papers with Code
```

For recognized technical reports where the stored title does not contain the
phrase, allow an explicit, curated `document_type` or alternate title in a
later schema change. Do not infer “technical report” for every ArXiv paper.
Until that field exists, mention “technical report” naturally in a curated TLDR
or visible resource summary only when accurate.

For Kimi K3, qualify:

```text
Kimi K3 Technical Report (arXiv:2607.24653) | Papers with Code
```

as a targeted override only if the page accurately identifies itself that way
and the title remains concise. Prefer a general data field over a hard-coded
paper-ID conditional.

### 2.2 Generate unique descriptions

Use this priority:

1. curated TLDR;
2. the opening of the author-written abstract;
3. author/date fallback;
4. the existing generic site description only as the last resort.

Descriptions must be plain text, whitespace-normalized, unique per paper, and
roughly 150-180 characters for search snippets. Keep Open Graph descriptions
up to the existing 280-character limit if desired. Search and social
descriptions can share source text but should have separate length constants.

### 2.3 Avoid keyword templates

Do not add “paper,” “technical report,” “arxiv,” “code,” and “results” to every
title indiscriminately. The visible document should naturally express:

- the exact paper title;
- its identifier and type;
- what code, artifacts, data, or results PwC actually has.

Never describe absent code or evaluations as available.

## Workstream 3: Bibliographic and structured metadata

### 3.1 Add Highwire Press tags

Emit these server-side for all eligible papers:

```html
<meta name="citation_title" content="...">
<meta name="citation_author" content="First Author">
<meta name="citation_author" content="Second Author">
<meta name="citation_publication_date" content="2026/07/27">
<meta name="citation_arxiv_id" content="2607.24653">
```

Rules:

- one `citation_author` tag per actual author;
- no affiliations or organizations in author tags;
- use `YYYY/MM/DD`, or the year alone if only a year is known;
- emit conference/journal tags only from authoritative normalized fields;
- omit unknown values rather than invent them;
- do not emit `citation_pdf_url` for an external PDF unless the implementation
  satisfies Google Scholar's same-site/full-text requirements. Continue to
  provide the ordinary ArXiv PDF link visibly.

Google Scholar is not the same index as Google Search. These tags improve
bibliographic parsing and Scholar eligibility but do not guarantee general
web-search ranking.

### 3.2 Add JSON-LD

Render one escaped `<script type="application/ld+json">` object using
`json.dumps`, never string concatenation. Use `ScholarlyArticle` for semantic
specificity and include only supported, factual properties:

```json
{
  "@context": "https://schema.org",
  "@type": "ScholarlyArticle",
  "@id": "https://paperswithcode.co/paper/2607.24653#paper",
  "url": "https://paperswithcode.co/paper/2607.24653",
  "headline": "Kimi K3: Open Frontier Intelligence",
  "abstract": "...",
  "datePublished": "2026-07-27",
  "author": [{"@type": "Person", "name": "Kimi Team"}],
  "identifier": [
    {"@type": "PropertyValue", "propertyID": "arXiv", "value": "2607.24653"}
  ],
  "sameAs": ["https://arxiv.org/abs/2607.24653"],
  "image": "https://paperswithcode.co/api/thumbnails/...",
  "codeRepository": ["https://github.com/..."],
  "about": [{"@type": "Thing", "name": "Language Modeling"}],
  "isPartOf": {
    "@type": "WebSite",
    "name": "Papers with Code",
    "url": "https://paperswithcode.co/"
  }
}
```

Represent a team or organization as `Organization` only when the source data
supports that distinction; otherwise use a named author entry without guessing.
Validate Schema.org vocabulary independently from Google's Rich Results Test:
`ScholarlyArticle` helps machines understand the page but does not currently
promise an Article rich result.

### 3.3 Add breadcrumbs

Emit matching visible breadcrumbs and `BreadcrumbList` JSON-LD:

```text
Papers > 2026 > Kimi K3: Open Frontier Intelligence
```

Breadcrumb URLs must resolve to crawlable HTML archive pages introduced below.

## Workstream 4: Real sitemap infrastructure

### 4.1 Add canonical sitemap routes

Create `backend/routers/sitemaps.py` and domain logic in
`backend/services/sitemap_service.py`.

Routes:

```text
GET|HEAD /sitemap.xml
GET|HEAD /sitemaps/static.xml
GET|HEAD /sitemaps/papers-{shard}.xml
```

`/sitemap.xml` is a sitemap index. Paper shards contain at most 50,000 URLs and
stay below 50 MB uncompressed. Use deterministic, stable shards—prefer
publication year plus bounded numeric shard rather than page-number offsets
that shift whenever a new paper arrives.

Each paper entry contains:

```xml
<url>
  <loc>https://paperswithcode.co/paper/2607.24653</loc>
  <lastmod>2026-07-27T...</lastmod>
</url>
```

Eligibility:

- canonical latest ArXiv rows only, using `DBPaper.is_latest_version`;
- canonical external rows addressable through their internal route ID;
- non-empty title and enough content to avoid a thin/error document;
- exclude merge sources, invalid identifiers, private workflow rows, and URLs
  that return non-`200`;
- use the apex production origin regardless of request host.

`lastmod` should be the greatest meaningful public-content timestamp available,
not the time the sitemap was requested. Repository-star refreshes, citation
count refreshes, page views, and other ranking-only background writes must not
make every paper appear freshly edited.

### 4.2 Stream and cache sitemap responses

The catalog is large and the VPS has limited memory and disk:

- stream database rows in bounded batches;
- stream or incrementally generate XML;
- never materialize all paper URLs as Python objects;
- XML-escape every location;
- cache shard responses for at least one hour;
- support conditional responses if ETags are cheap;
- bound shard queries by indexed columns;
- add the necessary focused database index only after `EXPLAIN` demonstrates a
  need.

Avoid generating sitemap files into `frontend/dist` during every deployment:
that snapshot becomes stale as papers are ingested and consumes release disk.

### 4.3 Route sitemaps through nginx

Add exact proxy locations for `/sitemap.xml` and `/sitemaps/` to both checked-in
nginx templates. They must appear before the SPA catch-all. Extend
`deploy/nginx_validate.py` so a template cannot accidentally send these routes
back to `index.html`.

Applying the nginx template is a separate operational action:

```bash
sudo pwc-nginx staging --confirm APPLY_NGINX_STAGING
sudo pwc-nginx production --confirm APPLY_NGINX_PRODUCTION
```

The production command requires explicit production authorization. An
application deployment alone does not apply nginx changes.

### 4.4 Advertise the sitemap

Ensure the production `robots.txt` contains:

```text
Sitemap: https://paperswithcode.co/sitemap.xml
```

Cloudflare currently manages the public robots response. Determine whether the
line belongs in a checked-in static file or Cloudflare's managed robots
configuration before implementation. Do not remove the existing
`Content-Signal` policy or crawler restrictions as an incidental SEO change.
Verify specifically that `Googlebot` and Google Scholar can crawl paper,
archive, sitemap, JS, CSS, image, and API resources needed to render the page.

## Workstream 5: Crawlable HTML discovery

Sitemaps assist discovery but do not replace internal links. Add backend-served,
plain HTML archives:

```text
/papers/recent
/papers/archive
/papers/archive/2026
/papers/archive/2026/07
```

Requirements:

- list canonical paper URLs with descriptive anchor text;
- paginate with ordinary `rel="next"`/`rel="prev"` links where appropriate;
- default `/papers/recent` to papers added or published in the last fourteen
  days;
- provide stable year/month navigation;
- return useful HTML without JavaScript;
- use bounded page sizes such as 100 papers;
- add self-canonicals and unique titles/descriptions;
- exclude noncanonical and ineligible rows using the same eligibility function
  as the sitemap;
- link these archives from the server-rendered site shell or footer so they are
  reachable from the homepage through simple links.

Continue using the interactive React feed for normal users. The archive is a
real user-facing research index, not a crawler doorway. Style it simply and
make it usable for people browsing by date.

Add exact nginx proxy locations for the archive routes before the SPA catch-all.
Do not use a broad `/papers/` rule that would interfere with existing legacy
paper redirects.

In a later phase, server-render the first page of task, method, conference,
organization, and author listings. Those contextual internal links are more
valuable than a flat archive, but they should reuse the same safe HTML and
canonical helpers instead of becoming independent templates.

## Workstream 6: Paper completeness and unique value

### 6.1 Define an SEO completeness report

Add a read-only CLI/report that scores public papers on factual completeness,
not keyword density:

```text
required:
  canonical identifier
  title
  at least one author
  publication date or year
  full abstract or authoritative external summary

valuable:
  TLDR
  official repository
  project page
  Hugging Face artifacts
  task tags
  method tags
  benchmark/evaluation rows
  organization
  thumbnail
```

The report should accept one route ID, a publication window, or a bounded limit.
It must not edit records. Use the existing `pwc` commands and enrichment
workflows for changes rather than embedding curation logic in the SEO report.

### 6.2 Add a high-profile paper checklist

For newly trending or important papers:

1. verify the canonical record and title;
2. generate or curate a factual TLDR;
3. attach the official GitHub repository and project page;
4. attach explicit Hugging Face artifacts;
5. add existing task and method taxonomy tags;
6. add only paper-native, source-verifiable evaluation results;
7. verify related-paper links;
8. validate the initial HTML and metadata;
9. request indexing through Search Console after the sitemap contains the URL.

This is content curation, not a requirement to block paper publication.

### 6.3 Complete Kimi K3

Before requesting indexing for `2607.24653`:

- verify the technical-report classification from the official source;
- add a concise factual TLDR;
- attach the official `MoonshotAI/Kimi-K3` repository;
- attach the official Kimi K3 project/blog page;
- verify the existing `moonshotai/Kimi-K3` Hugging Face model link;
- remove any incorrect method tags found during curation;
- import only results directly supported by the report and compatible with
  existing leaderboards;
- ensure the visible lead naturally contains “Kimi K3 technical report” and
  `arXiv:2607.24653`;
- verify that every displayed claim has a source and that comparison language
  does not overstate vendor-reported evaluations.

These are data-only curation tasks and should use the repository's dedicated
paper-enrichment and evaluation workflows rather than being hidden inside the
SEO implementation.

## Workstream 7: Search Console and measurement

### 7.1 Establish ownership and baseline

Verify the apex-domain property in Google Search Console. Before production
changes, export or record:

- valid indexed pages;
- crawled/currently not indexed;
- discovered/currently not indexed;
- duplicate/canonicalized pages;
- soft 404s and server errors;
- sitemap status and discovered URL counts;
- paper-page clicks, impressions, CTR, and average position;
- Core Web Vitals for the paper route group.

Record baselines for a fixed cohort:

- Kimi K3;
- 20 papers from the last fourteen days;
- 20 established high-citation papers;
- 20 external-resource papers;
- 20 random canonical papers.

Do not use the approximate `site:` result count as the main success metric.

### 7.2 Request and monitor Kimi indexing

After production release:

1. run URL Inspection against the live Kimi URL;
2. confirm the fetched and rendered HTML contains the same title, authors,
   abstract, identifier, links, canonical, and JSON-LD;
3. request indexing;
4. submit the sitemap index;
5. confirm Google-selected canonical matches the declared canonical;
6. monitor the four target queries by country and device;
7. annotate the release date in the SEO dashboard.

Use Search Console data rather than automated scraping of Google result pages.
Automated rank checks, if added, must comply with the provider's terms and use
an approved search-data API.

### 7.3 Success metrics

Initial targets, to be revised after the baseline:

- 100% of sampled canonical paper routes expose an H1, author, date/identifier,
  and abstract in raw HTML.
- 100% of sitemap URLs return `200`, self-canonicalize, and are absent from
  merge redirects.
- Sitemap validation has zero XML errors and every shard remains within
  protocol limits.
- New-paper median discovery time falls below 24 hours.
- New-paper median indexing time falls below 72 hours.
- No increase in paper-page 5xx rate or p95 backend latency above 250 ms.
- No material regression in mobile LCP, INP, or CLS; specifically, initial
  document replacement should keep CLS below 0.1 at the 75th percentile.
- Kimi K3 becomes indexed under its exact title and gains impressions for all
  four target queries.
- Query CTR improves after titles/snippets stabilize, without measuring success
  solely by position one.

## Testing

### Backend unit tests

Extend `backend/tests/test_paper_social_meta.py` or split focused tests into
`test_paper_seo.py`:

- initial HTML contains semantic title, authors, date, identifier, complete
  abstract, tasks, and resource links;
- HTML metacharacters and hostile strings are escaped;
- LaTeX titles become readable plain text without corrupting stored content;
- search title and descriptions follow fallback rules;
- one `citation_author` tag appears per author;
- unknown bibliographic fields are omitted;
- JSON-LD parses as JSON and contains only factual values;
- canonical and `@id` use the resolved route identifier and production origin;
- legacy and merged routes redirect to the canonical URL;
- unknown routes return `404`;
- database failure returns `503`;
- `HEAD` matches `GET` status and headers without a body;
- the initial document injection fails clearly when the Vite root placeholder
  changes.

Add `backend/tests/test_sitemaps.py`:

- sitemap index and shard content types are XML;
- XML parses and escapes special characters;
- every URL is absolute, apex-hosted, and canonical;
- ineligible and superseded rows are excluded;
- shard boundaries are deterministic and limited to 50,000 URLs;
- `lastmod` comes from meaningful content timestamps;
- generation operates in bounded batches;
- `HEAD` returns correct headers and no body.

Add archive route tests:

- recent and year/month pages expose ordinary paper links;
- pagination and canonical links are correct;
- empty periods return a real empty archive, not a soft 404;
- invalid year/month paths return `404`.

### Frontend tests

- the application still mounts over an initial paper document;
- the interactive page preserves the same H1, abstract, and canonical resource
  URLs after mount;
- JavaScript-disabled markup remains readable;
- initial replacement does not duplicate landmarks in the final DOM;
- external links retain safe `rel` attributes;
- Kimi-specific text is data-driven rather than hard-coded in the component.

### Deployment and nginx tests

Extend `deploy/nginx_validate.py` and `deploy/smoke_test.py`:

- `/sitemap.xml` returns XML, never `text/html`;
- one sitemap shard parses successfully;
- `/papers/recent` returns HTML containing a canonical `/paper/` link;
- a known paper's raw response contains its H1 and abstract;
- a missing paper returns `404`;
- a legacy paper URL returns `301`;
- hashed assets still resolve from the selected immutable release;
- production and staging routes point only to their corresponding backends.

Use targeted tests and linters. Do not run a routine frontend production build
from the checkout; the immutable staging deploy performs the release build.

## Implementation sequence

### Phase 0: Baseline and contracts

1. Capture Search Console baselines and the fixed paper cohort.
2. Add failing raw-HTML, sitemap, status-code, and nginx validation tests.
3. Define the shared canonical eligibility and route-identifier helpers.
4. Record current response time and Core Web Vitals.

Exit criteria: the current empty-shell and false sitemap behavior are
reproducible in automated tests.

### Phase 1: Crawlable paper response

1. Add `PaperSeoDocument` and the bounded projection.
2. Render visible semantic HTML into `#root`.
3. Add search metadata, Highwire tags, and JSON-LD.
4. change legacy/merged aliases to direct `301` redirects;
5. add `HEAD` and correct outage behavior;
6. qualify raw and rendered Kimi output locally and on staging.

Exit criteria: a JavaScript-disabled request receives a useful Kimi paper page,
and React still provides the complete interactive view.

### Phase 2: Sitemaps and recent archive

1. Add streamed sitemap index/shards and HTML archive routes.
2. Add nginx template routes and validation.
3. Apply the staging nginx template only with explicit authorization.
4. Load-test bounded shard generation on staging.
5. Validate representative URLs and route isolation.

Exit criteria: staging returns valid XML and crawlable archive pages without
SPA fall-through or resource spikes.

### Phase 3: Production discovery

1. Deploy the exact validated commit to production with explicit authorization.
2. Apply the reviewed production nginx template with explicit authorization.
3. verify health, homepage, paper HTML, API, sitemap, archive, assets, and 404s;
4. publish the sitemap line through the correct robots-management surface;
5. submit the sitemap in Search Console and request Kimi indexing.

Exit criteria: Search Console accepts the sitemap and live inspection sees the
complete initial document.

### Phase 4: Unique content and internal-link expansion

1. Complete the Kimi paper record through existing curation workflows.
2. Add the read-only SEO completeness report.
3. Prioritize incomplete trending/recent papers.
4. Server-render first-page links for task, method, conference, organization,
   and author pages using shared components.

Exit criteria: high-opportunity pages contain verified PwC-specific value and
are linked from relevant taxonomy pages.

### Phase 5: Iterate from evidence

1. Compare cohort discovery and indexing latency after two and six weeks.
2. Review query/page CTR and Google title rewrites.
3. Adjust title and description templates only where Search Console evidence
   shows a systematic problem.
4. Evaluate true React SSR/hydration only if replacement causes measurable UX
   regression or template drift.

## Rollout and rollback

- Land each phase as a small, independently testable source change.
- Publish completed changes to `main` and stage the exact commit according to
  repository policy.
- Do not combine the first production SEO release with unrelated schema,
  frontend redesign, or crawler-policy changes.
- Release application code before applying matching nginx routes so the backend
  endpoints exist when nginx begins proxying them.
- Keep the prior immutable release as the application rollback target.
- Keep the prior checked-in nginx template as the nginx rollback source.
- If paper response latency, error rate, or Core Web Vitals regress, roll back
  the complete application release rather than mixing frontend and backend
  versions.
- If sitemap generation is the only failing surface, remove or revert its exact
  nginx locations through `pwc-nginx`; do not reload nginx manually.
- Search indexing changes are not instantly reversible. Preserve stable
  canonical URLs and use redirects rather than deleting published paper paths.

## Risks and mitigations

### Template drift between initial HTML and React

Keep the initial document deliberately small and semantic. Share URL,
plain-text, date, author, and title-formatting helpers where practical, and add
parity tests for representative papers.

### Layout shift during React replacement

Match the initial header's width, typography, thumbnail aspect ratio, and
section order to the React view. Measure CLS on staging before production.
Escalate to `hydrateRoot` only if data shows replacement cannot meet the target.

### Increased database load

Use bounded relation queries, short public caching, stable sitemap shards, and
streamed batches. Measure query counts and `EXPLAIN` sitemap/archive queries
before adding indexes.

### Large author lists

Render all `citation_author` tags for bibliographic accuracy, but visually
collapse very long author lists behind an accessible summary while retaining
the complete author data in the document. Cap neither metadata correctness nor
response size without measuring representative consortium papers.

### Thin or inaccurate pages

Exclude structurally invalid rows from sitemaps, but do not fabricate content.
Use the completeness report to route important papers into established
curation workflows.

### Duplicate content and route aliases

Centralize eligibility and canonical resolution. Use direct `301` redirects,
self-canonicals, and only canonical URLs in sitemaps and archives.

### Structured-data expectations

Validate syntax and semantic correctness, but do not advertise rich-result
features Google does not support for scholarly pages. Treat structured data as
machine-readable context, not a ranking lever.

### Cloudflare robots ownership

Do not assume a repository `robots.txt` controls production. Identify and
document the authoritative Cloudflare configuration before changing it, and
preserve existing AI-training restrictions.

## Completion checklist

- [ ] Raw paper HTML contains visible bibliographic content and abstract.
- [ ] React replacement preserves equivalent user-visible information.
- [ ] Titles, descriptions, canonicals, citation tags, and JSON-LD validate.
- [ ] Legacy, merged, missing, and outage responses use correct status codes.
- [ ] `/sitemap.xml` is a valid sitemap index, not SPA HTML.
- [ ] Shards are bounded, stable, streamed, and canonical-only.
- [ ] Recent and archive pages expose simple HTML paper links.
- [ ] Nginx templates and validators route SEO endpoints correctly.
- [ ] Production robots advertises the sitemap without changing unrelated
      crawler policy.
- [ ] Targeted backend, frontend, deployment, and smoke tests pass.
- [ ] Staging latency, resource usage, and Core Web Vitals meet targets.
- [ ] Kimi K3 data is complete and its raw HTML passes the paper checklist.
- [ ] Search Console accepts the sitemap and live URL inspection.
- [ ] The baseline cohort is monitored for at least six weeks.

## References

- Google Search Central, JavaScript SEO basics:
  <https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics>
- Google Search Central, SEO Starter Guide:
  <https://developers.google.com/search/docs/fundamentals/seo-starter-guide>
- Google Search Central, sitemap construction:
  <https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap>
- Google Search Central, canonicalization:
  <https://developers.google.com/search/docs/crawling-indexing/canonicalization>
- Google Search Central, title links:
  <https://developers.google.com/search/docs/appearance/title-link>
- Google Search Central, Article structured data:
  <https://developers.google.com/search/docs/appearance/structured-data/article>
- Google Search Central, breadcrumb structured data:
  <https://developers.google.com/search/docs/appearance/structured-data/breadcrumb>
- Google Scholar, inclusion guidelines:
  <https://scholar.google.com/intl/en/scholar/inclusion.html>
