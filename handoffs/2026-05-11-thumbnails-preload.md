# Handoff — Instant thumbnails on every page

## What the user wants (final, unambiguous)

> Instant thumbnails on every page. Preload all thumbnails, store them in the HF bucket, serve them via the API so the frontend can directly display them. **No versioning** of thumbnails.

That is the only requirement. Everything below serves that goal.

## Current state at handoff

- HF bucket `nielsr/pwc-thumbnail` (private, ~944 MB, 39 864 files) is the durable store.
- VPS local cache `./thumbnail_cache/` mirrors the bucket (~898 MB, 39 849 files at last check). Daily cron `.github/workflows/cron-mirror-thumbnails-to-disk.yml` keeps it in sync; the bootstrap pass already ran during the previous session.
- `/api/thumbnails/{filename}` now does **strictly disk-only lookup**: no on-the-fly PDF rasterisation, no per-request HF round-trip. Misses return 404 and the frontend's `<img onError>` shows a placeholder.
- `THUMBNAIL_GENERATION = 2` versioning was reverted. Filenames are just `{safe_id}_{version}.jpg`. The router's gen-1 fallback hack has been removed. Backend was restarted.
- Verified: 20 / 20 sample papers on `/tasks/text-to-speech` now serve in 2–5 ms each from local disk.

## Big remaining piece: 43 396 missing thumbnails

Latest `--dry-run` (16:13 UTC): **39 504 cached, 43 396 to generate**, out of 82 900 latest-version arXiv papers.

A full backfill is **already running in the background**:

```bash
nohup bash -c 'PYTHONPATH=.github/workflows uv run --env-file backend/keys.env \
  python -m scripts.daily.preload_thumbnails --max-failures -1' \
  > logs/preload_thumbnails_backfill.log 2>&1 &
```

- PID at handoff time: **545945** (verify with `ps -p 545945`). Started 16:13 UTC, generating ~1 paper / sec at startup; will drop to roughly the PDF-download-bound rate after the warm "already cached" portion is skipped.
- Log: `logs/preload_thumbnails_backfill.log`.
- `--max-failures -1` disables the abort-on-failures cap so transient arXiv/Xet errors don't kill the multi-day run.
- Estimated duration: **2.5–7.5 days continuous** at the VPS's sequential pace. Each generation writes the JPEG to **both** local disk and the bucket, so the local mirror grows alongside the bucket — no separate re-mirror needed.

### Monitoring + recovery

```bash
# progress
tail -f logs/preload_thumbnails_backfill.log
ps -p 545945 -o pid,etime,rss,%mem,cmd

# count progress
ls /root/python_projects/paperswithcode/thumbnail_cache | wc -l
```

If the kernel OOM-kills the preload process (4 GB RAM is tight; pdf2image at 150 DPI spikes 200–300 MB), the user-facing `/api/thumbnails/...` will keep working — the request path no longer touches generation at all. Just restart with the same command. The script will skip everything already in the bucket.

If repeated OOMs become a problem, the cheap mitigation is to lower DPI in `backend/services/thumbnail_service.py:_convert_pdf_to_thumbnail` (currently `dpi=150` → try `dpi=100` or `dpi=75`). Restart backend not needed since the preload uses its own ThumbnailService instance.

## What changed this session (working tree, none committed)

- `backend/services/thumbnail_service.py` — removed the staged `THUMBNAIL_GENERATION = 2` regime + the `_g{N}` parse regex; kept the simple `build_thumbnail_filename` + `parse_filename`; **added `get_local_thumbnail_path`** (disk-only); kept full-page rendering (the rest of the staged crop change is harmless).
- `backend/routers/thumbnails.py` — `serve_thumbnail` is now a 10-line local-disk lookup; no fallback dance, no generation, no bucket round-trip.
- `.github/workflows/scripts/daily/mirror_thumbnails_to_disk.py` (new) — `sync_bucket` mirror script.
- `.github/workflows/cron-mirror-thumbnails-to-disk.yml` (new) — daily 05:00 UTC.
- `docs/operations.md`, `.agents/skills/cron-health/SKILL.md` — updated cron tables and process grep regexes.

All other `M`/`??` files in `git status` are from unrelated in-progress threads.

## What to do next

1. **Babysit the backfill.** Poll the log every few hours; restart on OOM with the same command. Done when `would_generate` stops decreasing or `cached` ≈ 82 900.
2. Once the backfill is essentially complete, **verify a sampling of task pages**: text-to-speech, object-detection, image-classification, language-modelling — all 20 / 20 should be 200 OK in low-ms.
3. (Optional) Consider whether to commit the workspace changes. The staged "full first page + `_g2` versioning" change was authored by a previous session; the user explicitly rejected the versioning part. Either commit my router/service simplifications cleanly, or coordinate with whoever staged the other change.
4. (Optional) The `mirror_thumbnails_to_disk` cron is now slightly redundant *while* preload is running, since preload writes locally too. After the backfill it remains the safety net for multi-machine drift and bucket-only writes; leave it.

## Suggested skills for the next session

- **`cron-health`** for verifying both `cron-preload-thumbnails` and the new `cron-mirror-thumbnails-to-disk` are firing and producing fresh work.
- Nothing else from `.agents/skills/` applies.
