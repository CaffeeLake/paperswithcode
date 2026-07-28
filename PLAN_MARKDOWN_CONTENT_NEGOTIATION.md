# Plan: Markdown Content Negotiation for Canonical Public Pages

## Goal

Return a concise, deterministic Markdown representation when a client requests a
canonical public page with `Accept: text/markdown`, while preserving HTML as the
default for browsers.

The implementation should:

- reuse the bounded database projections already used for server-rendered HTML;
- return `Content-Type: text/markdown; charset=utf-8`;
- send `Vary: Accept` on both Markdown and HTML variants;
- retain the existing canonical `Link` and cache headers;
- support `GET` and `HEAD`;
- avoid converting the React application shell or arbitrary HTML;
- make no changes to API, XML, authentication, asset, or client-only SPA routes.

## Decision

Implement content negotiation at the FastAPI origin instead of depending on
Cloudflare's HTML-to-Markdown converter.

Origin rendering is preferable because the existing page services already expose
the semantic content agents need. It avoids navigation, scripts, styles, and
duplicated structured data by construction, gives us explicit output bounds, and
is testable without Cloudflare. Cloudflare should pass through the origin's
`text/markdown` response.

Do not add a second `.md` URL for each page. The HTML and Markdown
representations should share the canonical URL and vary only by `Accept`.

## Initial route scope

Negotiate Markdown on canonical, server-rendered public pages:

| Page class | Routes |
| --- | --- |
| Homepage | `/` |
| Papers | `/paper/{canonical_id}` |
| Tasks | `/tasks/{slug}` |
| Methods | `/methods/{slug}` |
| Benchmarks | `/benchmark/{slug}` |
| Conferences | `/conferences/{slug}`, `/conferences/{slug}/{task_slug}` |
| Authors | `/authors/{id}` |
| Organizations | `/{organization_slug}`, `/{organization_slug}/{task_slug}` |
| Paper discovery | `/papers/recent`, `/papers/archive`, `/papers/archive/{year}`, `/papers/archive/{year}/{month}` |

Keep redirects such as `/papers/{id}`, `/task/{slug}`, and
`/organizations/{slug}` as redirects regardless of `Accept`. Keep client-only
routes such as `/tasks`, `/methods`, `/chat`, and `/saved` as HTML SPA routes.

Do not negotiate Markdown for:

- `/api/**`, `/openapi.json`, or `/.well-known/**`;
- `/sitemap.xml`, `/sitemaps/**`, or `/robots.txt`;
- images, thumbnails, JavaScript, CSS, fonts, and other assets;
- authenticated, administrative, mutation, or user-specific pages;
- error responses in the first release.

## HTTP contract

### Representation selection

Add a small, independently tested media-range parser in
`backend/services/content_negotiation_service.py`.

Rules:

1. Missing `Accept` keeps HTML.
2. `*/*` alone keeps HTML.
3. An explicit `text/markdown` with `q=0` is not acceptable.
4. Select Markdown when its effective quality is greater than HTML's quality.
5. On an explicit tie between `text/markdown` and `text/html`, select Markdown
   when `text/markdown` appears first.
6. Malformed ranges are ignored; if no valid Markdown preference remains, keep
   HTML rather than introducing new `406` responses.

Required test cases include:

| `Accept` | Result |
| --- | --- |
| absent | HTML |
| `*/*` | HTML |
| `text/html` | HTML |
| `text/markdown` | Markdown |
| `text/markdown, text/html;q=0.9` | Markdown |
| `text/html, text/markdown;q=0.5` | HTML |
| `text/markdown;q=0, text/html` | HTML |
| `application/json, text/markdown;q=0.8` | Markdown |

### Response headers

Every successful negotiable response must include:

```text
Content-Type: text/markdown; charset=utf-8  # Markdown variant only
Vary: Accept
Link: <https://paperswithcode.co/...>; rel="canonical"
Cache-Control: public, max-age=300, stale-while-revalidate=3600
```

Archive pages should retain their existing cache policy. `Vary: Accept` must be
merged with any existing `Vary` values rather than replacing them.

Do not add `x-markdown-tokens` initially. There is no tokenizer dependency in
the backend, and an invented byte-to-token estimate would be misleading. This
header can be added later if a real tokenizer is already available for another
feature.

## Markdown format

All documents should:

- use UTF-8 and end with one newline;
- use absolute `https://paperswithcode.co/...` links for internal resources;
- contain no raw HTML, scripts, style, navigation chrome, or JSON-LD duplicate;
- use JSON-quoted YAML scalars in frontmatter to prevent malformed metadata;
- normalize database text to plain text and escape Markdown control characters;
- reject CR/LF characters in link destinations and safely encode destinations;
- preserve stable ordering from the existing view models.

Use this frontmatter:

```markdown
---
title: "Page title"
description: "One concise description"
canonical: "https://paperswithcode.co/canonical/path"
type: "task"
---
```

### Discovery pages

Render `DiscoveryPage` directly:

```markdown
# Image Classification

Research papers, benchmarks, and methods for image classification.

## Related research

- [ImageNet](https://paperswithcode.co/benchmark/imagenet)

## Relevant papers

1. [Paper title](https://paperswithcode.co/paper/1234.56789) — Tagged with Image Classification · 2026-07-28
```

Keep the existing bounds: at most 20 papers and the already bounded related
links. Omit empty sections instead of emitting placeholder prose.

### Paper pages

Render `PaperSeoDocument` directly, after canonical-ID resolution:

1. title;
2. identifier, publication date, conference, and authors;
3. TL;DR when present;
4. abstract;
5. tasks, methods, organizations, and introduced benchmarks;
6. code repositories, project pages, Hugging Face artifacts, source, and PDF.

For concision:

- include the complete abstract once;
- show at most 20 authors, followed by `… and N more authors`;
- cap each resource group at 20 links;
- omit absent fields and empty headings;
- do not repeat the title or description in the body;
- do not include citation meta tags or JSON-LD because the same facts are
  already present in readable Markdown.

### Archive pages

Refactor the current archive renderer so HTML and Markdown consume the same
title, description, canonical path, papers, period navigation, page number, and
pagination state.

Include every paper returned by the existing archive page query. The query is
already bounded to 100 rows, and slicing it further would make papers
unreachable because pagination advances by 100. Render dates in ISO 8601 and
include explicit newer/older page links.

The archive index should list years and counts. Year and month pages should
include period navigation without reproducing the site's global navigation.

## Implementation steps

### 1. Add negotiation and response helpers

Create `backend/services/content_negotiation_service.py` with:

- `prefers_markdown(accept_header: str | None) -> bool`;
- `merge_vary(headers, "Accept")`;
- a helper for the shared canonical/cache headers if that removes duplication
  without obscuring route behavior.

Keep parsing pure and dependency-free.

### 2. Add safe Markdown renderers

Create `backend/services/public_page_markdown_service.py` with:

- `render_discovery_markdown(page: DiscoveryPage) -> str`;
- `render_paper_markdown(document: PaperSeoDocument) -> str`;
- `render_archive_markdown(document: ArchivePage) -> str`;
- private helpers for frontmatter, plain text, labels, and safe links.

Do not reuse `backend/services/paper_markdown_service.py`; that service reads
full paper Markdown from Hugging Face storage and has a different contract.

Introduce an `ArchivePage` dataclass in the archive/sitemap service layer so
both HTML and Markdown renderers consume one projection instead of passing
loosely related arguments.

### 3. Integrate the discovery routes

In `backend/routers/discovery_pages.py`:

1. resolve the `DiscoveryPage` exactly as today;
2. apply staging/query robots policy;
3. if Markdown is preferred, render and return a plain `Response` immediately;
4. otherwise load and render the SPA shell as today.

The Markdown branch must run before `load_index_html()`. A Markdown request
should remain available even if the frontend bundle is missing.

### 4. Integrate paper pages

In `backend/routers/paper_pages.py`:

1. accept `Request` (or the `Accept` header) in both paper route handlers;
2. preserve not-found, database-error, and canonical redirect behavior;
3. build `PaperSeoDocument` once;
4. return Markdown before loading the SPA shell when requested;
5. leave the existing social metadata and HTML rendering path unchanged.

### 5. Integrate archive pages

In `backend/routers/sitemaps.py`:

- add `Request` to the archive handlers;
- construct one `ArchivePage` projection;
- select the HTML or Markdown renderer from that projection;
- add `Vary: Accept` to both successful variants.

XML sitemap handlers remain unchanged.

### 6. Verify proxy and cache behavior

The checked-in nginx templates already proxy the canonical page classes to
FastAPI. Confirm that:

- nginx forwards `Accept` unchanged;
- no canonical route falls through to static `index.html`;
- origin `Content-Type`, `Vary`, `Link`, and cache headers survive nginx and
  Cloudflare;
- requesting HTML then Markdown, and Markdown then HTML, never returns a cached
  representation of the wrong type.

Do not enable Cloudflare Markdown for Agents as part of this change. It can be
evaluated separately for pages outside the explicit origin-rendered scope.

## Tests

### Unit tests

- media-range quality, wildcard, ordering, malformed input, and `q=0`;
- Markdown escaping for headings, descriptions, labels, and URLs;
- frontmatter quoting for quotes, newlines, colons, and Unicode;
- stable final newline and deterministic ordering;
- author/resource limits and empty-section omission;
- archive pagination links and 100-row bound.

### Router tests

For discovery, paper, and archive routes:

- no `Accept` returns the existing HTML unchanged;
- `Accept: text/markdown` returns Markdown with the expected content type;
- both variants contain `Vary: Accept`, canonical `Link`, and cache headers;
- `HEAD` matches GET headers and has an empty body;
- aliases still redirect;
- missing pages retain the current status and error representation;
- Markdown works when `load_index_html()` is unavailable;
- dangerous database strings cannot create Markdown headings, links, YAML
  fields, or raw HTML.

Extend:

- `backend/tests/test_search_discovery.py`;
- `backend/tests/test_paper_social_meta.py`;
- `backend/tests/test_sitemaps.py`;
- `backend/tests/test_deployment_runtime.py` for nginx route invariants.

### Release smoke tests

Extend `deploy/smoke_test.py` to request Markdown for:

- `/`;
- one canonical paper;
- one task;
- `/papers/recent`.

For each response assert:

- HTTP 200;
- `Content-Type` starts with `text/markdown`;
- `Vary` contains `Accept`;
- canonical `Link` is correct;
- body starts with frontmatter and contains one `#` heading;
- body contains no `<html`, `<script`, or frontend asset reference;
- body stays below a conservative byte limit appropriate to its page class.

Retain the existing HTML, SPA asset, API, and production chat-boundary smoke
checks.

## Rollout

1. Implement the shared parser, projections, renderers, and targeted tests.
2. Run focused backend tests, formatting hooks, nginx validation, and release
   smoke tests.
3. Commit and push the exact implementation SHA.
4. Deploy that SHA to staging.
5. Exercise the Accept matrix through staging's public origin and verify both
   request orders for cache separation.
6. Inspect representative paper, task, benchmark, author, organization, and
   archive output for usefulness and bounds.
7. Deploy to production only with explicit production authorization.
8. Re-run the external agent-readiness scan and compare the Markdown check.

## Acceptance criteria

- Browsers and clients without an explicit Markdown preference see the same
  HTML behavior as before.
- Every in-scope canonical page returns concise Markdown for
  `Accept: text/markdown`.
- HTML and Markdown variants cannot poison each other's caches.
- Markdown is rendered from bounded semantic projections without parsing HTML.
- Canonical redirects, 404s, APIs, XML, authentication, and assets retain their
  existing contracts.
- Staging and production release smoke suites cover the negotiated
  representation.

## References

- [Cloudflare: Markdown for Agents](https://developers.cloudflare.com/fundamentals/reference/markdown-for-agents/)
- [RFC 9110: Accept](https://www.rfc-editor.org/rfc/rfc9110.html#name-accept)
