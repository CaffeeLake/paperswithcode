# Method Source Link Plan

How to make method source links reliable long-term.

## Goal

Method pages should link to the canonical paper page on `paperswithcode.co` whenever the source is an indexed paper. Stored URLs should never leak internal preview hosts such as `167.235.148.241`, and arbitrary external source pages should remain external.

The durable invariant:

1. `methods.source_paper_id` is the source of truth when a method was introduced by a paper in our database.
2. `methods.source_url` is optional display/external metadata, not the canonical internal route.
3. API/frontend code should prefer `source_paper_id` for internal paper links and fall back to `source_url` only when no source paper exists.

## Current Problem

Some method rows have source links saved as local website URLs:

```text
http://167.235.148.241:8080/paper/2212.04356
https://paperswithcode.co/paper/2212.04356
/paper/2212.04356
```

These are all references to papers indexed by the site, but if the API returns the stored URL directly, the UI can send users to the wrong host.

There is already a short-term API normalization that rewrites known local paper URLs into app-relative `/paper/{id}` links. That prevents the visible leak, but the cleaner long-term fix is to populate and use `source_paper_id`.

## Data Model

Keep the existing columns:

- `methods.source_paper_id`: foreign key to `papers.id`; canonical internal source when available.
- `methods.source_url`: external source URL or legacy display URL.
- `methods.source_title`: display title for the source.

No new column is needed.

## Backfill Strategy

Create an idempotent script or migration that scans `methods.source_url` and fills `methods.source_paper_id` only when the source URL shape is trusted and resolves unambiguously to exactly one paper row.

Trusted URL shapes:

- Local paper routes: `/paper/{ref}`, `/abs/{ref}`, `/pdf/{ref}.pdf`
- Production website routes: `https://paperswithcode.co/paper/{ref}`
- Legacy/internal hosts: `localhost`, `127.0.0.1`, `167.235.148.241`
- ArXiv canonical routes: `https://arxiv.org/abs/{ref}`, `https://arxiv.org/pdf/{ref}.pdf`

`{ref}` may be either:

- Base arXiv ID, e.g. `2212.04356`
- Versioned arXiv ID, e.g. `2212.04356v2`
- Legacy arXiv ID, e.g. `cs.CL/0101001`

Resolution rules:

1. If `{ref}` includes a version suffix, match `papers.arxiv_id` plus `papers.version`.
2. If `{ref}` has no version suffix, match the latest row with `papers.is_latest_version`.
3. If no paper matches, leave `source_paper_id` null and report the method.
4. If multiple papers match, leave `source_paper_id` null and report the conflict.
5. Do not parse arbitrary external URLs just because they contain an arXiv-looking string.

Also insert missing `paper_methods` rows for `(source_paper_id, method_id)` so the source paper is explicitly associated with the introduced method.

## API Behavior

Update method serialization so responses expose an internal route derived from `source_paper_id` whenever possible:

```text
if method.source_paper_id resolves to paper with arxiv_id:
    source_url = /paper/{paper.arxiv_id}
else:
    source_url = normalize_local_paper_source_url(method.source_url)
```

This should be applied consistently in:

- `GET /api/v1/methods/`
- `GET /api/v1/methods/{id-or-slug}`
- `GET /api/v1/papers/{paper}/methods`
- Paper detail responses that embed method summaries
- Any collection/year/search method response paths

External URLs remain unchanged.

## Frontend Behavior

The frontend can keep rendering `m.source_url` for now after the API guarantees canonical output. A later cleanup can make the contract more explicit by returning separate fields:

- `source_paper_id`
- `source_paper_url`
- `external_source_url`

That split is cleaner, but it is not required for the first durable fix.

## Verification

Before writing:

1. Count methods with non-null `source_url`.
2. Count trusted local/arXiv URL matches.
3. Count resolvable, unresolved, and conflicting rows.
4. Print a sample of unresolved/conflicting rows.

After writing:

1. `methods.source_paper_id` is populated for every trusted URL that resolves to one paper.
2. Every populated `source_paper_id` points to an existing paper.
3. Every populated `source_paper_id` has a matching `paper_methods` row.
4. `GET /api/v1/methods/whisper` returns `/paper/2212.04356`, not an IP address.
5. External source URLs, such as OpenAI blog pages or GitHub URLs, are unchanged.

Run:

```bash
uv run --env-file backend/keys.env python backend/database/methods_setup/check_method_source_links.py
uv run --with pytest --env-file backend/keys.env python -m pytest backend/tests/test_method_source_links.py
```

## Rollout

1. Add a dry-run backfill script under `backend/database/methods_setup/`.
2. Review the dry-run counts and unresolved/conflicting samples.
3. Run the write mode against production DB.
4. Restart the backend so API serialization changes are live.
5. Verify the Whisper API and page source link.
6. Keep the local-host URL normalizer as defense in depth for old or manually-entered rows.

## Non-Goals

- Do not rewrite arbitrary external URLs that merely contain an arXiv ID.
- Do not remove `source_url`; it is still useful for non-paper source pages.
- Do not require a frontend migration before fixing the backend/data contract.
