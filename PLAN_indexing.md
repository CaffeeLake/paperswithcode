# Paper Indexing Plan

## Goal

Make manual and submit-page arXiv indexing feel fast, predictable, and honest when upstream arXiv is slow or rate-limiting us.

The current behavior leaves the user staring at `Indexing...` while a single blocking request retries `export.arxiv.org`. The backend eventually turns upstream `429` responses into a misleading "paper not found" style error. We should preserve the simple one-click workflow, but make upstream throttling visible and avoid compounding it.

## Current Behavior

Paper detail indexing is a synchronous request:

```text
Click "Index from arXiv"
  -> POST /api/v1/papers/index/{arxiv_id}
  -> fetch metadata from https://export.arxiv.org/api/query
  -> insert paper
  -> insert authors
  -> return full Paper
```

The submit form's arXiv path uses the same backend persistence helper through `POST /api/v1/papers/submit`.

Important current constraints:

- There is no job queue, status endpoint, or polling.
- The frontend has no explicit client-side timeout.
- `ArxivService` has per-instance rate limiting, so it does not coordinate requests across users or endpoint calls.
- `ArxivService` retries all HTTP errors up to 3 times with a 30s request timeout.
- Upstream arXiv `429` responses are collapsed into a `404` from the indexing endpoint.

## Principles

Make rate limits explicit. A throttled upstream is not "paper not found"; it should be reported as temporary indexing unavailability.

Avoid retry storms. When arXiv says "rate exceeded", do not immediately fan more requests into the same upstream from concurrent users or repeated clicks.

Keep the shipped surface small. We do not need a full ingest queue before fixing the worst UX and operational behavior.

Prefer fast failure over opaque waiting. A clear 429/503 in a few seconds is better than a disabled button for 30-90 seconds.

## Phase 1: Fast, Clear Failure

Update `backend/services/arxiv_service.py` to classify upstream failures:

- `429 Too Many Requests`: raise or return a typed rate-limit result.
- `404` or empty feed response: paper not found.
- Timeout/network errors: temporary upstream failure.
- XML parse errors: upstream response error.

Then update `backend/routers/papers.py`:

- Return `429` or `503` for arXiv rate limiting.
- Return `502` for other upstream metadata fetch failures.
- Keep `404` only for actual "not found in arXiv" responses.
- Include a user-facing detail string such as "arXiv is rate-limiting indexing right now. Try again in a few minutes."

Frontend changes:

- In `frontend/src/views/PaperDetailView.tsx`, show the backend detail directly for `429`, `502`, and `503`.
- Reset the button state immediately after the error response.
- Optionally add a "Try again later" hint for rate-limit responses.

This is the highest-value fix because it explains the observed production behavior without changing the ingestion architecture.

## Phase 2: Shared ArXiv Backoff

Add process-wide coordination inside `ArxivService`:

- A shared async lock for export API calls.
- A shared `next_allowed_request_at` timestamp.
- A shared `rate_limited_until` timestamp when any request gets `429`.

Behavior:

- Serialize calls to `export.arxiv.org/api/query`.
- Respect the existing minimum 3 second interval across all requests in the process.
- If a `429` has happened recently, fail fast with a typed rate-limit error until the cooldown expires.
- If arXiv provides `Retry-After`, honor it. Otherwise use a conservative fallback such as 5-15 minutes for export API metadata.

This prevents multiple users or repeated clicks from extending the ban window.

## Phase 3: Reduce Blocking Time

Tune retry behavior for interactive indexing:

- Do not retry `429` immediately.
- Keep a small retry budget for transient `5xx` or connection resets.
- Use shorter connect/read timeouts for metadata fetches than the current 30s all-in timeout.

Suggested first pass:

```text
429: no immediate retry; set cooldown and return rate-limit response
5xx/network reset: retry once after short backoff
timeout: retry once if connect/read timeout was short
empty arXiv feed: no retry; return 404
```

The button should normally resolve in under 5 seconds, except when arXiv is genuinely slow but still responding.

## Phase 4: Fallback Metadata Source

Since `https://arxiv.org/abs/{id}` can be reachable while `export.arxiv.org` is throttled, add a fallback path for basic metadata:

- Fetch the regular abstract page.
- Parse title, authors, abstract, published/updated date, categories, and PDF link from page metadata or page structure.
- Only use this fallback when export API returns `429` or a temporary upstream failure.

Keep this fallback conservative:

- If required fields are missing, return a clear upstream failure instead of creating partial bad rows.
- Do not parse PDF content for basic indexing.
- Log when fallback is used so we can track reliability.

This allows indexing to continue during export API throttling without introducing a large new dependency.

## Phase 5: Optional Background Jobs

Only introduce a queue if synchronous indexing remains painful after the above changes.

Possible shape:

```text
POST /papers/index/{arxiv_id}
  -> create indexing job
  -> return 202 { job_id, status: "queued" }

GET /papers/index-jobs/{job_id}
  -> queued | running | succeeded | failed | rate_limited
```

Frontend:

- Button starts the job.
- UI polls job status.
- On success, navigate/refetch the paper page.
- On failure, show the job error.

This is more work and adds operational surface, so defer it until fast failure plus shared backoff is proven insufficient.

## Observability

Add structured logs around indexing:

- `arxiv_id`
- source endpoint (`paper_detail` vs `submit`)
- result (`success`, `not_found`, `rate_limited`, `upstream_error`, `db_error`)
- elapsed time
- retry count
- whether fallback metadata was used

Useful counters:

- arXiv metadata request count
- arXiv `429` count
- indexing success count
- indexing failure count by reason
- p50/p95 indexing request duration

Even without a metrics stack, consistent log lines will make `logs/backend.log` enough to debug incidents.

## Verification

Backend tests:

- `429` from arXiv export returns `429` or `503`, not `404`.
- Empty arXiv feed still returns `404`.
- Existing-paper check still returns `409` for the admin endpoint.
- Submit endpoint returns the same temporary upstream error for arXiv IDs.
- Shared cooldown makes the second request fail fast after a simulated `429`.

Frontend checks:

- A rate-limit response clears `Indexing...` and shows a readable message.
- A successful index still refetches the paper.
- A `409` still shows the already-indexed error path.

Manual production check:

```bash
uv run --env-file backend/keys.env python - <<'PY'
import httpx
from backend.config import get_settings

settings = get_settings()
response = httpx.post(
    "http://localhost:8000/api/v1/papers/index/2605.18736",
    headers={"X-Admin-Token": settings.admin_api_token},
    timeout=20,
)
print(response.status_code)
print(response.text[:500])
PY
```

When arXiv is throttling, this should return quickly with a temporary-rate-limit message. When arXiv is healthy, it should index the paper and return `200`.

## Rollout

1. Implement typed arXiv errors and endpoint status mapping.
2. Update frontend error handling copy.
3. Restart backend and rebuild/reload frontend.
4. Verify against a throttled export API response and a known healthy arXiv ID.
5. Add shared cooldown/backoff.
6. Re-test repeated clicks and concurrent requests.
7. Consider the abstract-page fallback if export API throttling remains frequent.
