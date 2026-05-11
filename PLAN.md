# Performance Plan — paperswithcode.co

Why the site (and pages like `/benchmark/mcpatlas`) feels slow, and what to do about it.

## Diagnosis

The page itself is fine — `/benchmark/mcpatlas` fires 4 API calls in two waves and on a warm backend they total ~120 ms. The perceived slowness comes from infrastructure and frontend-architecture choices, not from this page or its data.

### Measured cold-vs-warm gap

```
GET /api/v1/papers/recent  attempt 1: TTFB 2.07s
GET /api/v1/papers/recent  attempt 2: TTFB 1.56s
GET /api/v1/papers/recent  attempt 3: TTFB 0.06s
```

After any idle period the single uvicorn worker / Postgres page cache go cold, so the first user after a quiet stretch waits 1–2 s before *anything* renders.

### Root causes (in priority order)

1. **`vite preview` is serving the production frontend.** From `start_services.sh:212-224`, after `npm run build` we run `npm run preview` on port 8080 and nginx proxies `/` to it. `vite preview` is single-threaded Node intended for smoke-testing builds, and it sends `Cache-Control: no-cache` on hashed assets (`/assets/index-*.js`). Result: every visit re-validates the 285 KB-gzipped JS bundle.
2. **Pure CSR, no SSR/SSG.** `frontend/index.html` has an empty `<div id="root"></div>`. Nothing visible until: HTML → JS download → parse → React mount → API waterfall → render.
3. **No code splitting.** `frontend/src/App.tsx` statically imports all 8 view components. A visitor to `/benchmark/mcpatlas` downloads the code for `FeedView`, `PaperDetailView`, etc., yielding a single ~948 KB / 285 KB-gzipped chunk.
4. **API request waterfall on benchmark/paper pages.** In `frontend/src/views/BenchmarkDetailView.tsx`, the `introducingPaperQ` and `evalsQ` queries are gated on `datasetQ.data`, so it's always two sequential round trips. On 200 ms-RTT mobile that's ~400 ms of pure waiting.
5. **Single uvicorn worker on a 3.7 GiB VPS with ~120 MiB free.** No nginx response caching. Every API hit goes Python → Postgres, and cold-cache hits are slow.
6. **`/api/` nginx block uses WebSocket idioms.** `proxy_set_header Connection 'upgrade';` and `proxy_cache_bypass $http_upgrade;` disable keep-alive to uvicorn and prevent any future `proxy_cache` from engaging.
7. **No Brotli.** nginx serves only gzip; `Accept-Encoding: br` falls back to gzip.

### Specific to `/benchmark/mcpatlas`

The dataset returns in ~30 ms with `num_papers: 0` and `paper_count: 0`, so the leaderboard is correctly empty. Nothing benchmark-specific is broken.

## Recommendations (highest impact first)

### 1. Serve `frontend/dist/` from nginx, stop running `vite preview`

**Why first:** biggest user-visible win after the first visit, lowest risk.

Edit `/etc/nginx/sites-enabled/paperswithcode.co`:

```nginx
location / {
    root /root/python_projects/paperswithcode/frontend/dist;
    try_files $uri /index.html;
}

location /assets/ {
    root /root/python_projects/paperswithcode/frontend/dist;
    access_log off;
    expires 1y;
    add_header Cache-Control "public, immutable";
    try_files $uri =404;
}
```

Edit `start_services.sh` to drop the `npm run preview` step — keep `npm run build` so `frontend/dist/` is fresh, but don't start a Node process for it. Reload nginx: `sudo nginx -t && sudo systemctl reload nginx`.

### 2. Add `proxy_cache` for cacheable GETs

**Why:** hides backend cold-start completely for read-heavy endpoints.

In nginx (top-level `http {}` or in a `conf.d/` file):

```nginx
proxy_cache_path /var/cache/nginx/pwc levels=1:2 keys_zone=pwc_api:32m
                 max_size=512m inactive=10m use_temp_path=off;
```

In the `/api/` location:

```nginx
location ~ ^/api/v1/(metrics/directions|tasks/all|datasets/[^/]+|papers/[^/]+|papers/recent|papers/trending|evaluations/) {
    proxy_pass http://localhost:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_cache pwc_api;
    proxy_cache_methods GET;
    proxy_cache_valid 200 60s;
    proxy_cache_valid 404 30s;
    proxy_cache_lock on;
    proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
    add_header X-Cache-Status $upstream_cache_status always;
}
```

TTL of 60 s is conservative; bump to 5–10 minutes for `metrics/directions` and `tasks/all`. Anything that takes a `?` query string still gets cached (nginx keys on full URL by default).

### 3. Clean up the existing `/api/` block

Drop the WebSocket headers so keep-alive to uvicorn works and so caching can engage:

```nginx
location /api/ {
    proxy_pass http://localhost:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 60s;
    proxy_send_timeout    60s;
    proxy_read_timeout    60s;
}
```

### 4. Lazy-load views in the React app

In `frontend/src/App.tsx`:

```tsx
const FeedView           = React.lazy(() => import("@/views/FeedView"));
const PapersListView     = React.lazy(() => import("@/views/PapersListView"));
const PaperDetailView    = React.lazy(() => import("@/views/PaperDetailView"));
const TagsIndexView      = React.lazy(() => import("@/views/TagsIndexView"));
const TagBrowseView      = React.lazy(() => import("@/views/TagBrowseView"));
const MethodsIndexView   = React.lazy(() => import("@/views/MethodsIndexView"));
const MethodDetailView   = React.lazy(() => import("@/views/MethodDetailView"));
const BenchmarkDetailView = React.lazy(() => import("@/views/BenchmarkDetailView"));
const CronDashboard      = React.lazy(() => import("@/pages/CronDashboard"));
```

Wrap `<Routes>` in `<React.Suspense fallback={<RouteFallback />}>`. Expected: initial chunk shrinks from ~285 KB gz to roughly 80–120 KB gz; each route loads its own ~10–40 KB on demand.

### 5. Collapse the benchmark-page waterfall

Two options:

- **Frontend-only:** prefetch `getPaper(introducingPaperId)` and `getEvaluationsByDataset(datasetId)` in parallel using a single `useQueries` once the dataset id is known. They're already parallel, but the dataset request is a dependency. Removes nothing; mostly a code-clarity win.
- **Better — backend:** extend `GET /api/v1/datasets/{id}` to optionally embed the introducing paper (`?include_paper=true`). Then `BenchmarkDetailView` only needs dataset + evals (+ metric-directions in parallel). Saves one full round trip on every benchmark page load.

The frontend change in `frontend/src/views/BenchmarkDetailView.tsx`:

```tsx
const datasetQ = useQuery({
  queryKey: ["dataset", datasetSlug],
  queryFn: () => apiClient.getDatasetBySlug(datasetSlug!, { include_paper: true }),
  enabled: !!datasetSlug,
  staleTime: 10 * 60 * 1000,
});
// drop introducingPaperQ; use datasetQ.data.introducing_paper inline.
```

### 6. Enable Brotli on nginx (optional, ~20% smaller)

Install `libnginx-mod-brotli` (Ubuntu 24.04 packages it) and add to the server block:

```nginx
brotli on;
brotli_comp_level 5;
brotli_types text/plain text/css text/javascript application/javascript application/json image/svg+xml;
```

### 7. Multiple uvicorn workers if RAM allows (optional)

Currently one Python worker @ ~377 MiB resident on 3.7 GiB total. There's not enough headroom for 2–4 workers without risking OOM (we also run Postgres, nginx, vite, etc.). Defer this until `proxy_cache` reduces per-request load enough that one worker is comfortable, or until the VPS gets more RAM. If we later add workers, switch `backend/run_server.py` to `uvicorn --workers 2 --loop uvloop --http httptools backend.main:app`.

## Expected impact

| Change | First-visit gain | Repeat-visit gain |
| --- | --- | --- |
| 1. nginx static + immutable `/assets/` | 0 (same bytes) | ~285 KB → 0 (304s) |
| 2. nginx API cache | hides 1–2 s cold start | 30 ms → ~3 ms |
| 3. clean `/api/` block | small | needed for #2 to work |
| 4. lazy-load views | ~285 KB gz → ~100 KB gz | ~285 KB gz → ~100 KB gz |
| 5. embed introducing paper | one RTT (~30–500 ms) | same |
| 6. brotli | ~285 KB gz → ~230 KB br | same |

After (1)–(5), a cold benchmark visit should land in <1 s instead of 2–5 s, and a warm/repeat visit in well under 300 ms.

## Implementation order

1. nginx changes (1 + 2 + 3) + `start_services.sh` cleanup — one PR, easy to revert, no app-code risk.
2. React lazy-load (4) — one frontend PR.
3. Backend `?include_paper=true` + frontend wire-up (5) — one full-stack PR.
4. Brotli + worker tuning (6, 7) — opportunistic.
