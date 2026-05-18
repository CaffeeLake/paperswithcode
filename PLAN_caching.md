# Caching Plan

## Goal

Increase launch traffic capacity without making active development painful.

The site should cache public, read-mostly traffic aggressively enough to protect FastAPI/Postgres during spikes, while keeping deploys predictable: after pushing frontend or backend changes, there must be a simple way to refresh or bypass cached URLs.

## Current Setup

Production currently uses:

- Nginx serving the React build from `frontend/dist`.
- Nginx proxying `/api/`, `/docs`, `/health`, and `/thumbnails/` to FastAPI on `localhost:8000`.
- A shared Nginx proxy cache zone at `/var/cache/nginx/pwc`.
- Immutable browser caching for Vite hashed assets under `/assets/`.
- `index.html` marked `no-store`, which is correct for active frontend development.

The launch probe showed:

- Static HTML and cached API responses scale well.
- Uncached DB-heavy homepage endpoints are the bottleneck.
- `/api/v1/papers/trending` was cacheable.
- `/api/v1/tasks/trending` and the homepage top-tasks sidebar need explicit cache coverage.

## Caching Principles

Cache only public GET/HEAD responses.

Do not cache:

- Auth/session endpoints.
- Bookmark endpoints.
- Admin/edit/mutation endpoints.
- POST/PUT/PATCH/DELETE responses.
- Requests with `Authorization`.
- Requests with session cookies.
- Error pages except short-lived `404` if useful.

Prefer short TTLs first. A `60s` cache is enough to collapse launch traffic spikes while keeping development feedback quick.

## Static Frontend

Keep the current split:

- `/assets/*`: cache for `1y` with `immutable`.
- `/index.html`: `no-store`.
- SPA routes: serve `index.html` via `try_files`.

This is development-friendly because Vite emits content-hashed asset filenames. After `npm run build`, new HTML points to new asset URLs, while old assets can safely stay cached.

Deploy workflow for frontend changes:

```bash
cd frontend && npm run build && cd ..
nginx -t && nginx -s reload
```

Hard refresh behavior:

- Browser hard refresh should always re-fetch `index.html`.
- If a browser still appears stale, use DevTools "Empty cache and hard reload".
- Hashed assets do not need purging after normal builds.

## API Cache Coverage

Start with these homepage/public endpoints:

```text
/api/v1/papers/trending
/api/v1/tasks/trending
/api/v1/tasks/top
/api/v1/metrics/directions
/api/v1/tasks/all
/api/v1/evaluations/
```

Recommended TTLs:

- Homepage feed and sidebar endpoints: `60s`.
- Slow public metadata that changes only by cron or deploy: `5m-60m`.
- Thumbnails: `7d`, assuming generated filenames include enough cache identity.

Keep `proxy_cache_lock on` so a burst of identical requests waits on one backend refresh rather than stampeding Postgres.

Use stale cached responses during backend trouble:

```nginx
proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
```

## Development-Friendly Invalidation

Use three layers of freshness control.

### 1. Short TTLs

For launch, `60s` on homepage JSON is the default. That means stale public API data naturally disappears quickly, even without manual purging.

### 2. Manual Cache Busting

Support a query parameter such as `_refresh=<timestamp>` for ad hoc verification:

```text
https://paperswithcode.co/api/v1/tasks/trending?limit=8&_refresh=20260518
```

By default, Nginx cache keys include the full request URI, so a unique query string forces a new cache entry. This is useful for testing, but it does not delete the old cached URL.

### 3. Explicit Purge Script

For active development, add a small purge script that can clear Nginx's local proxy cache after deploys:

```bash
sudo rm -rf /var/cache/nginx/pwc/*
nginx -t && nginx -s reload
```

This is implemented as:

```bash
scripts/purge_nginx_cache.sh
```

Use it after backend changes that affect cached response shapes or after data fixes where waiting `60s` is annoying.

## Optional Admin Bypass Header

If manual purging becomes too blunt, add an admin-only bypass header:

```text
X-Cache-Bypass: <admin-token>
```

Nginx can bypass cache when this header is present and valid, but this needs care because Nginx cannot easily validate the FastAPI admin token without extra config or an internal auth check.

Prefer the purge script first. It is simple, explicit, and hard to misuse.

## Nginx Implementation Shape

Use a separate cache block for broad safe public patterns.

Example shape:

```nginx
location ~ ^/api/v1/(papers/trending|tasks/(all|top|trending)|metrics/directions|evaluations/) {
    proxy_pass http://localhost:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_cache pwc_api;
    proxy_cache_methods GET HEAD;
    proxy_cache_valid 200 60s;
    proxy_cache_valid 404 30s;
    proxy_cache_lock on;
    proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
    proxy_no_cache $http_authorization $cookie_session;
    proxy_cache_bypass $http_authorization $cookie_session;
    add_header X-Cache-Status $upstream_cache_status always;
}
```

For `/api/v1/tasks/?ordering=-paper_count&page_size=8`, regex matching by query string is awkward in `location`. Use the dedicated endpoint instead:

```text
/api/v1/tasks/top?limit=8
```

The dedicated endpoint is cleaner because it is easy to cache, avoids the general paginated task listing's count query, and documents the homepage use case.

## Cloudflare Option

Cloudflare can add another layer in front of Nginx.

Good Cloudflare candidates:

- Static assets under `/assets/*`.
- Public API GETs for homepage JSON.
- Thumbnails.

Do not put broad "cache everything" rules over `/api/*` until auth, bookmarks, and admin endpoints are carefully excluded.

If Cloudflare is added, define a deploy purge command for:

- `https://paperswithcode.co/`
- `https://paperswithcode.co/index.html`
- Homepage API endpoints.

Keep Nginx caching even with Cloudflare. It protects the backend from cache misses and non-Cloudflare traffic.

## Validation Commands

After Nginx changes:

```bash
nginx -t && nginx -s reload
```

Check cache behavior:

```bash
curl -sSI 'https://paperswithcode.co/api/v1/papers/trending?limit=30&max_age_days=365'
curl -sSI 'https://paperswithcode.co/api/v1/tasks/trending?limit=8'
curl -sSI 'https://paperswithcode.co/api/v1/tasks/top?limit=8'
```

Expected:

- First request: `X-Cache-Status: MISS` or `BYPASS`.
- Second identical request: `X-Cache-Status: HIT`.
- Authenticated/admin requests: `BYPASS` or no cache header.

Check live latency:

```bash
curl -sS -o /dev/null -w '%{http_code} %{time_total}s\n' 'https://paperswithcode.co/api/v1/tasks/trending?limit=8'
```

## Rollout Plan

1. Add cache coverage for `/api/v1/tasks/trending`.
2. Add `/api/v1/tasks/top?limit=8` for the homepage top-tasks sidebar.
3. Add `scripts/purge_nginx_cache.sh`.
4. Validate `X-Cache-Status` headers.
5. Run a small load probe again.
6. Document the cache purge step in deploy instructions.

## Deploy Workflow With Active Development

For frontend-only changes:

```bash
cd frontend && npm run build && cd ..
nginx -t && nginx -s reload
```

No API cache purge should be needed unless frontend behavior depends on cached JSON changing immediately.

For backend response-shape changes affecting cached endpoints:

```bash
./start_services.sh
scripts/purge_nginx_cache.sh
```

For data-only fixes:

```bash
scripts/purge_nginx_cache.sh
```

For quick personal verification without purging everyone:

```text
Add &_refresh=<timestamp> to the API URL, or use browser DevTools with cache disabled.
```

## Open Questions

- Should cache purging be wired into `start_services.sh`, or kept manual to avoid accidental broad purges?
- Should Cloudflare be enabled before launch, or is Nginx caching enough for the first announcement?
