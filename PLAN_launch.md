# Launch Readiness Plan

## Goal

Prepare `paperswithcode.co` for a first public launch on X and LinkedIn, with enough headroom for a moderate traffic spike and a clear response plan if the VPS starts to struggle.

The production site currently runs on a Hetzner VPS with about 4 GB RAM and 3 CPU cores. Nginx serves the built React app from `frontend/dist`, while API traffic is proxied to a single FastAPI/Uvicorn backend process backed by local PostgreSQL.

## Current Capacity Snapshot

Quick live probes from the VPS showed:

- Static homepage HTML handled about `500 req/s` with low latency.
- Cached `/api/v1/papers/trending` handled about `200-300 req/s`.
- DB-heavy uncached endpoints were much lower:
  - `/api/v1/tasks/trending?limit=8`: about `6 req/s` under load, with latency climbing to several seconds.
  - `/api/v1/papers/?page_size=30&order_by=date_published&time=all_time&include_resources=false`: about `6 req/s` under load, with similar queuing.
  - `/api/v1/tasks/?ordering=-paper_count&page_size=8`: about `15-17 req/s`.

Practical estimate:

- A normal social launch with `100-300` concurrent readers should be fine.
- A burst of `25-50` simultaneous new page loads should work, but some API-backed content may feel slow.
- A sustained viral burst above roughly `5-10` new homepage loads per second can queue backend/Postgres requests unless more homepage API responses are cached.

## Launch Blockers

No hard blocker for a first launch.

The main risk is not serving the static frontend. Nginx is strong enough for that. The risk is a thundering herd of uncached homepage API requests hitting FastAPI/Postgres at the same time.

## VPS Sizing Guidance

Increasing RAM is useful for safety, but it is not the first lever for requests per second.

Current memory after the probe still showed about `1.2-1.4 GB` available, so the launch bottleneck appears to be backend/Postgres work per request rather than memory exhaustion. An upgrade from `4 GB` to `8 GB` RAM would still be reasonable before launch if it is cheap and quick, because it gives Postgres, Nginx cache, OS page cache, and extra Uvicorn workers more breathing room.

Storage is not an urgent launch scaling lever. The disk was roughly half full during the check, and serving static assets or JSON API responses is not likely to be storage-bound. Add storage only if thumbnail/PDF/cache growth is expected to fill the disk, not for more request throughput.

The current VPS reports `x86_64` on AMD EPYC with `3` vCPUs and about `4 GB` RAM, so it is effectively in Hetzner's x86 server family. Hetzner's rescale rules only allow changing to a plan with the same architecture type as the current server, which means this server should be upgradeable to larger x86 plans, not directly to Arm64/CAX. The most likely next step is an x86 shared-resource upgrade around `4 vCPU / 8 GB RAM`; if CPU-bound API traffic remains a concern, an x86 dedicated-resource CCX plan is the stronger performance move.

When rescaling, avoid increasing the primary disk unless storage is actually needed. Hetzner does not support disk downgrades, so choosing "CPU/RAM only" preserves the option to scale back down later.

What helps requests per second most:

1. Cache more public GET endpoints at Nginx or Cloudflare.
2. Avoid expensive database work on first page load.
3. Add `2` backend workers after cache coverage is improved.
4. Tune the slow SQL behind homepage/sidebar endpoints.
5. Upgrade CPU cores if uncached API traffic remains the bottleneck.
6. Add RAM if running more workers, larger Postgres cache, or bigger Nginx cache.

Recommended launch posture:

- For today's first launch, prioritize caching before resizing.
- If upgrading the VPS is easy, move to the next tier with more RAM and CPU, not RAM alone.
- Add `1-2 GB` swap as an emergency buffer if the VPS has none, but do not treat swap as performance capacity.
- Do not buy more storage just for launch traffic.

## Pre-Launch Hardening

### 1. Expand Nginx API Caching

Cache all read-mostly homepage endpoints for at least `60s`:

- `/api/v1/papers/trending`
- `/api/v1/tasks/trending`
- `/api/v1/tasks/?ordering=-paper_count&page_size=8`

Current Nginx config already caches `/api/v1/papers/trending`, but `/api/v1/tasks/trending` did not show cache headers in the live probe, and the top-tasks sidebar endpoint is not covered by the existing cache regex.

Implementation notes:

- Update `/etc/nginx/sites-available/paperswithcode.co`.
- Include exact homepage query patterns or broader safe read-only task endpoints.
- Keep writes, auth endpoints, bookmarks, and admin/edit endpoints uncached.
- Validate with:

```bash
nginx -t && nginx -s reload
curl -sSI 'https://paperswithcode.co/api/v1/tasks/trending?limit=8'
curl -sSI 'https://paperswithcode.co/api/v1/tasks/?ordering=-paper_count&page_size=8'
```

Expected result: `X-Cache-Status: MISS` on first request and `X-Cache-Status: HIT` on repeated requests.

### 2. Consider Multiple Backend Workers

The backend currently starts through `backend/run_server.py`, which runs a single Uvicorn process. That is simple and memory-efficient, but it limits API concurrency.

For launch, consider running `2` Uvicorn workers if memory looks stable after caching:

```bash
uv run --env-file backend/keys.env uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2 --log-level info
```

Do not jump straight to many workers on a 4 GB VPS. Each worker has its own SQLAlchemy pool configuration, so too many workers can increase Postgres memory and connection pressure.

### 3. Reduce Homepage API Work

If there is time, make the homepage as cache-friendly as possible:

- Keep the default feed on `/api/v1/papers/trending`, because it is already cacheable and fast.
- Avoid triggering uncached search or arbitrary listing endpoints on initial page load.
- Keep React Query `staleTime` on sidebar queries so each browser does not repeatedly refetch.

### 4. Pre-Warm Critical Routes

Right before posting, request the main pages and API endpoints once or twice:

```bash
curl -sS -o /dev/null https://paperswithcode.co/
curl -sS -o /dev/null 'https://paperswithcode.co/api/v1/papers/trending?limit=30&max_age_days=365'
curl -sS -o /dev/null 'https://paperswithcode.co/api/v1/tasks/trending?limit=8'
curl -sS -o /dev/null 'https://paperswithcode.co/api/v1/tasks/?ordering=-paper_count&page_size=8'
```

This makes the first visitors less likely to pay cold-cache cost.

## Launch-Day Monitoring

Watch these during and after posting:

```bash
uptime
free -h
sudo tail -f /var/log/nginx/paperswithcode_access.log
sudo tail -f /var/log/nginx/paperswithcode_error.log
tail -f logs/backend.log
```

Useful quick checks:

```bash
curl -sS -o /dev/null -w '%{http_code} %{time_total}s\n' https://paperswithcode.co/
curl -sS -o /dev/null -w '%{http_code} %{time_total}s\n' 'https://paperswithcode.co/api/v1/papers/trending?limit=30&max_age_days=365'
curl -sS -o /dev/null -w '%{http_code} %{time_total}s\n' 'https://paperswithcode.co/api/v1/tasks/trending?limit=8'
```

Watch for:

- Load average staying well above CPU count (`3`) for several minutes.
- Available memory dropping near zero.
- Nginx `499`, `500`, `502`, `503`, or `504` spikes.
- Backend logs filling with slow requests, connection pool timeouts, or Postgres errors.

## Fallback Actions

If the site becomes slow but still serves pages:

1. Increase Nginx cache TTL for read-mostly GET endpoints from `60s` to `5m`.
2. Temporarily cache broader public paper/task listing endpoints.
3. Disable or hide slow sidebar/API widgets if needed.

If the backend starts returning errors:

1. Restart backend:

```bash
pkill -f 'uvicorn.*backend.main:app' || true
nohup uv run --env-file backend/keys.env backend/run_server.py > logs/backend.log 2>&1 &
```

2. If restart is not enough, run with `2` workers.
3. If Postgres is overloaded, prefer caching and reducing request volume over adding more workers.

If the whole VPS is memory pressured:

1. Stop non-launch background jobs.
2. Avoid running CRON/import/extraction scripts during launch.
3. Consider temporarily adding swap as an emergency buffer.

## Later Scaling

After launch, prioritize these before a bigger announcement:

- Put Cloudflare in front of static assets and cacheable API GETs.
- Add a small CDN/cache policy for homepage JSON endpoints.
- Add lightweight request metrics for slow API endpoints.
- Tune expensive SQL queries used by homepage sidebars.
- Move from ad hoc `backend/run_server.py` process management to a systemd service with explicit worker count, restart policy, and resource limits.
