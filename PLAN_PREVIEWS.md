# Plan: Paper previews for links across Papers With Code

Status: **proposed**
Last updated: 2026-07-27

## Decision

Turn every recognized internal paper link rendered from site-authored Markdown
into the same kind of hover preview currently used by staging chat citations.
Start with task descriptions and research trends, then inherit the behavior
automatically everywhere that uses the shared `MarkdownText` component:

- task descriptions, research trends, and image credits;
- method descriptions and image credits;
- conference descriptions, task copy, and image credits;
- organization descriptions.

Keep the ordinary link as the primary interaction. The preview is supplementary:
hovering or focusing the link may reveal metadata, while clicking it still opens
the paper page. Touch interaction must continue to navigate normally and must not
require dismissing a preview first.

Extract the existing chat presentation into a shared paper-preview component
instead of creating a second visual implementation. Chat may continue to pass
its persisted citation/search metadata for immediate rendering; links from
`MarkdownText` will fetch metadata lazily from the existing public paper-detail
API. No database, schema, or persisted-content change is needed for V1.

## Goals

- Give links such as `[UI-TARS](/paper/2501.12326)` in research trends an
  informative preview without changing stored Markdown.
- Use one preview UI and one metadata normalization path in chat and ordinary
  site content.
- Support both ArXiv-backed paper identifiers and numeric external-paper IDs.
- Avoid requests for links that the user never hovers or focuses.
- Deduplicate requests when the same paper is linked more than once on a page.
- Preserve link security, citation validation, keyboard behavior, and touch
  navigation.
- Degrade to a normal working link when metadata or thumbnails are unavailable.

## Non-goals for V1

- Do not unfurl arbitrary external URLs, fetch third-party Open Graph metadata,
  or introduce server-side URL fetching.
- Do not infer that an arXiv, DOI, Hugging Face, or GitHub URL refers to a local
  paper. Only canonical internal paper links are previewable.
- Do not add previews for tasks, methods, benchmarks, conferences, repositories,
  or Hugging Face artifacts yet.
- Do not rewrite existing Markdown or add preview metadata to task, method,
  conference, or organization records.
- Do not make preview metadata essential to understanding or following a link.
- Do not expose the chat-only `paper:` Markdown scheme to general site content.

## Current state

Two independent Markdown renderers exist:

1. `frontend/src/components/chat/ChatMarkdown.tsx` recognizes validated
   `[label](paper:<route_id>)` citations. `PaperCitation` renders a Radix
   `HoverCard` using metadata already captured in chat search results or
   persisted citation snapshots.
2. `frontend/src/components/MarkdownText.tsx` renders the site's stored Markdown.
   It turns recognized same-site paths into React Router links and opens external
   links in a new tab, but it does not preview papers.

The chat implementation already provides the desired visual language:

- thumbnail with a deterministic faux-paper fallback;
- title, authors, venue/date, ArXiv identifier, citation count, and task tags;
- 150 ms open delay and 100 ms close delay;
- a normal `/paper/<route_id>` link as the trigger.

It is not directly reusable yet. `PaperCitation` returns a plain link whenever
neither chat search metadata nor a citation snapshot is present. Its React Query
fallback is therefore only useful for partially populated chat metadata; it
cannot independently power an ordinary Markdown link.

The existing `GET /api/v1/papers/{paper_id}?include_resources=false` endpoint
already resolves modern ArXiv IDs and numeric IDs for external papers and
returns every field needed by the preview. Per-paper detail responses are
currently `Cache-Control: no-store`, so client-side TanStack Query caching is
the V1 deduplication and reuse layer.

## Proposed architecture

```text
stored Markdown                         chat answer
      |                                     |
      v                                     v
 MarkdownText                         ChatMarkdown
      |                                     |
      +-- recognize /paper/<id>             +-- validate paper:<id>
      |                                     |
      +------------------+------------------+
                         v
                PaperPreviewLink
                         |
             +-----------+-----------+
             |                       |
     supplied chat metadata     lazy getPaper(id, false)
             |                       |
             +-----------+-----------+
                         v
                PaperPreviewCard
```

### 1. Extract a shared preview presentation

Create `frontend/src/components/paper-preview/PaperPreviewCard.tsx` and move the
following presentation-only pieces out of `ChatMarkdown.tsx`:

- `FauxPaperThumb`;
- the real-thumbnail wrapper and error fallback;
- the title/author/venue/citation/task layout;
- conversion from the public `Paper` API type into a compact preview view model.

Define a small frontend-only `PaperPreviewData` interface containing:

```text
routeId
title
arxivId
source
sourceUrl
thumbnailUrl
authors
published
conference
citationCount
tasks
```

Keep `authorsLine` and `venueLine` as the shared formatting functions. Avoid
making the new component depend on chat event types.

Rename generic CSS selectors from `chat-paper-pop`, `chat-thumb`, and related
names to `paper-preview-*`. During the refactor, aliases may temporarily keep
the old class names working, but the completed change should have one canonical
style definition.

### 2. Add a reusable `PaperPreviewLink`

Create `frontend/src/components/paper-preview/PaperPreviewLink.tsx`. It owns:

- the internal React Router `Link`;
- Radix `HoverCard` open state and delays;
- the lazy TanStack Query;
- loading, success, and unavailable preview states;
- the shared `PaperPreviewCard`.

Suggested props:

```ts
interface PaperPreviewLinkProps {
  routeId: string;
  to?: string;
  initialData?: PaperPreviewData;
  className?: string;
  children: React.ReactNode;
  target?: React.HTMLAttributeAnchorTarget;
}
```

Use a site-wide query key:

```ts
["paper-preview", normalizedRouteId]
```

and fetch with:

```ts
getPaper(normalizedRouteId, false)
```

Set `enabled` only after the card opens, `staleTime` to five minutes, a longer
garbage-collection window such as thirty minutes, and `retry: false`. A 404 or
network failure should render a compact “Preview unavailable” state for that
open card while leaving the link fully functional. Do not display raw API error
text.

Always render the `HoverCard` wrapper for a recognized paper link. This fixes
the current chat component's metadata prerequisite and permits the loading state
to appear while the lazy request is running.

When `initialData` comes from a chat search result or citation snapshot, render
it immediately. Do not fetch merely to replace a valid snapshot. Fetch only
when the supplied data lacks the minimum preview fields needed for the card.
The chat transcript remains authoritative for the historical citation snapshot;
opening an old chat must not silently rewrite persisted citation metadata.

### 3. Recognize paper links in `MarkdownText`

Move internal-URL parsing out of `MarkdownText.tsx` into a testable helper, for
example `frontend/src/lib/internalLinks.ts`. Keep the existing same-origin host
allowlist and allowed path prefixes.

Add:

```ts
extractPaperRouteId(internalPath: string): string | null
```

It should recognize:

- `/paper/2501.12326`;
- `/paper/104561` for an external paper;
- legacy `/papers/2501.12326`;
- equivalent absolute URLs on allowlisted Papers With Code hosts;
- an optional query string or fragment, which remains on the link destination
  but is excluded from the API identifier.

It should reject:

- empty identifiers;
- extra path segments;
- `/papers`, `/paper`, and unrelated internal routes;
- non-allowlisted hosts;
- encoded separators or malformed identifiers;
- arbitrary values that are neither a supported ArXiv route ID nor a positive
  numeric external-paper ID.

Normalize route IDs with the existing `normalizePaperRouteId` helper so
hyphenated modern ArXiv routes and version suffixes behave like paper detail
pages. Preserve the original normalized destination for navigation.

Update only the anchor renderer in `MarkdownText`:

1. recognized internal paper link -> `PaperPreviewLink`;
2. other recognized internal link -> existing React Router `Link`;
3. external link -> existing `_blank` anchor with
   `rel="noopener noreferrer"`.

Because research trends already render through `MarkdownText`, no
`TagBrowseView.tsx` special case should be needed.

### 4. Refactor chat onto the shared component

Keep `ChatMarkdown` responsible for chat-specific policy:

- accept the `paper:` URL scheme;
- validate citations against search hits or resolved citation snapshots;
- render unknown citations as `chat-invalid-citation`;
- withhold half-typed citations while streaming.

Replace `PaperCitation`'s visual and query implementation with a thin adapter
around `PaperPreviewLink`. Convert `ChatPaperHit` and `ChatCitation` to
`PaperPreviewData` in one place. `RestrictedReasoning` and tool-result paper
titles should use the same adapter.

Do not weaken the authoritative backend resolution in
`backend/services/chat_citation_service.py`. A generic internal Markdown link
may fall back to “Preview unavailable,” but an unvalidated chat `paper:`
citation must remain visibly invalid rather than becoming convincing through a
client-side fetch.

## Interaction and accessibility

- Keep the trigger as a real anchor. Preview code must not call
  `preventDefault`, replace the link with a button, or require JavaScript to
  navigate.
- Support mouse hover and keyboard focus through Radix `HoverCard`. Escape and
  moving focus away should close the card.
- Treat preview content as supplementary. The link text remains the accessible
  name, the thumbnail remains decorative (`alt=""`), and no action is available
  only inside the card.
- On coarse-pointer/touch devices, do not intercept the first tap. Prefer no
  preview and immediate navigation over a two-tap hover emulation.
- Keep the open/close delay long enough to avoid accidental cards while reading
  citation-dense prose. Start with the chat values and tune only from staging
  feedback.
- Constrain the card to the viewport on narrow screens and long titles. Preserve
  wrapping in link text and avoid shifting the surrounding layout.
- Respect reduced-motion preferences through the existing Radix animation
  utilities.

## Performance and caching

V1 should use the existing paper detail endpoint rather than add a new backend
contract. Requests are lazy, metadata is small enough for initial rollout, and
React Query deduplicates repeated links by normalized route ID.

Instrument or inspect staging before introducing a dedicated preview endpoint.
Add `GET /api/v1/papers/{route_id}/preview` with a compact response only if one
of these becomes material:

- full paper responses have a p95 payload or query cost disproportionate to the
  card;
- hover traffic causes noticeable database load;
- median time from open to populated card is visibly poor;
- other preview consumers need a stable minimal contract.

If that endpoint is added later, it should return only `PaperPreviewData`,
resolve IDs through `PaperService`, remain read-only and public, and receive a
short public cache header. Do not solve preview performance with browser calls
to arXiv, Hugging Face, GitHub, or arbitrary paper URLs.

Thumbnail requests must continue through `assetUrl` and the existing
`/api/thumbnails/{filename}` path. Keep lazy image loading, decoding hints, and
the faux-paper fallback.

## Security and failure behavior

- Preview only links already classified as internal by the same-origin
  allowlist. Never fetch the URL found in Markdown.
- Pass only the extracted route ID to `getPaper`; do not concatenate query
  strings, fragments, or arbitrary paths into the API request.
- Continue relying on `react-markdown`'s URL transformation and React escaping.
  Do not enable raw HTML.
- Preserve `noopener noreferrer` for new-tab links.
- A missing paper, invalid identifier, request timeout, or thumbnail failure is
  non-fatal. The destination link remains usable.
- Keep API errors out of the card and logs free of stored Markdown content.
- Do not share authenticated chat citation state through a global cache.
  Only public paper metadata belongs under the shared `paper-preview` query key.

## Testing plan

### Pure helper tests

Add table-driven tests for internal-link resolution and paper-ID extraction:

- relative and absolute canonical paper URLs;
- ArXiv, external numeric, hyphenated, versioned, query, and fragment cases;
- legacy `/papers/` links;
- external hosts, malformed escapes, extra segments, and non-paper routes.

The frontend currently has no component-test runner. Add a minimal Vitest,
jsdom, and React Testing Library setup as part of the implementation rather than
embedding parsing logic that can only be tested manually.

### Component tests

Cover:

- a paper link renders as a normal anchor before interaction;
- opening without initial data shows a bounded loading state and issues one
  `getPaper(routeId, false)` request;
- two links to the same paper share the React Query result;
- supplied chat metadata renders immediately without a request;
- 404 and network failure leave the link working;
- thumbnail failure produces the faux-paper fallback;
- non-paper internal links and external links never call the paper API;
- keyboard focus can open and Escape can close the card;
- touch activation navigates without a preview-only first tap;
- invalid chat citations remain invalid and are never fetched.

### Focused repository validation

Run:

```bash
cd frontend
npm run lint
npm run test -- --run
```

Do not use `npm run build` as a routine local check. The immutable staging
deployment will perform the complete frontend build and release validation.

### Staging qualification

On the computer-use-agents task page:

1. expand **Key trends**;
2. hover and keyboard-focus each linked paper;
3. confirm title, authors, venue/date, citations, task tags, and thumbnail or
   fallback;
4. click through to each paper page;
5. confirm repeated hovers do not repeat API requests within the stale window;
6. verify ordinary benchmark links still behave as normal links;
7. verify a deliberately missing paper produces a harmless fallback;
8. repeat with a narrow viewport and touch emulation.

Also smoke one method, conference, and organization description containing an
internal paper link, plus a staging chat answer with both a valid and invalid
citation.

## Implementation sequence

### Phase 1: Shared component

1. Add the `PaperPreviewData` view model and metadata converters.
2. Extract thumbnail and card presentation from `ChatMarkdown`.
3. Add `PaperPreviewLink` with lazy React Query loading and failure states.
4. Refactor chat to use it without changing citation policy or stored events.
5. Add focused component tests for the shared behavior.

### Phase 2: Site Markdown integration

1. Extract and test internal-link parsing.
2. Add strict paper-route recognition.
3. Render recognized paper links through `PaperPreviewLink` in `MarkdownText`.
4. Verify task trends and every other current `MarkdownText` consumer.
5. Run frontend lint and component tests.

### Phase 3: Staging rollout

1. Commit and push the complete frontend change to `main`.
2. Deploy the exact commit to staging with `pwc-deploy`.
3. Run the staging qualification matrix above and normal release smoke checks.
4. Inspect browser requests and backend logs for request volume, latency, and
   unexpected errors.
5. Adjust only presentation delays or cache windows if staging evidence calls
   for it.

### Phase 4: Production rollout

Production requires a separate explicit release request. Deploy the exact
tested `origin/main` commit, verify the task page, a paper page, one API route,
and normal production feature boundaries, then report the immediately
recoverable previous release.

## Acceptance criteria

- Every valid internal `/paper/<route_id>` link rendered by `MarkdownText`
  receives the shared paper preview on hover/focus.
- Research-trend Markdown requires no per-task code or data changes.
- Chat previews retain their current appearance and citation-validation rules.
- A preview request is never sent before hover/focus unless metadata was already
  supplied.
- Repeated links share cached metadata.
- Invalid or unavailable previews never break navigation.
- External links are never fetched for previewing.
- Mouse, keyboard, and touch behaviors pass staging qualification.
- Frontend lint and focused tests pass.
- The implementation ships as one qualified immutable staging release before
  any separately authorized production rollout.

## Follow-ups after V1

- Evaluate compact previews for benchmarks, tasks, and methods using explicit
  typed components rather than generic Open Graph unfurling.
- Consider a compact cached paper-preview endpoint if measured traffic or
  payload cost justifies it.
- Consider deliberate previews for known external scholarly identifiers only
  after defining authoritative resolution, privacy, caching, and SSRF
  boundaries.
- Add preview analytics only if product decisions require them; do not add
  per-hover tracking by default.
