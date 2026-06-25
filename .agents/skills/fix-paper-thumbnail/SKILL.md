---
name: fix-paper-thumbnail
description: Fix or regenerate paperswithcode paper thumbnails that are missing, wrong-sized, letterboxed with white borders, or stale. Use whenever the user mentions a broken paper thumbnail, giant white borders on a paper card, thumbnail too small/squat, preload thumbnails, fix the preview image on a paper page, or asks to make an appropriately sized thumbnail for an arXiv or external paper — even if they only share a paperswithcode.co/paper/… URL or arXiv id. Also use after changing the thumbnail renderer in backend/services/thumbnail_service.py.
---

# Fix Paper Thumbnail

Paper cards render thumbnails in a fixed **160×220** frame with `object-fit: contain`. Thumbnails must therefore be **400×550 JPEG** (width × height) — portrait, aspect ratio **H/W ≥ 1.0**. Wrong-aspect files (especially old **400×282** “squat” renders) letterbox with large white bands top and bottom even when the file “exists”.

This skill regenerates thumbnails through the same pipeline as `.github/workflows/scripts/daily/preload_thumbnails.py` and verifies the result before finishing.

## Pre-flight

Run from repo root with project env:

```bash
uv run --env-file backend/keys.env ...
```

Confirm thumbnail storage is configured:

```bash
grep -E '^PWC_THUMBNAIL_STORAGE_BACKEND=|^PWC_THUMBNAIL_HF_BUCKET_ID=|^PWC_HF_TOKEN=' backend/keys.env | sed 's/=.*/=<set>/'
```

If the backend is down, start it (needed for verification curls):

```bash
./start_services.sh
```

## Diagnose First

Resolve the paper (DB row or API):

```bash
# By arXiv id
curl -s "http://localhost:8000/api/v1/papers/2512.20856" | uv run python -c "
import json,sys; p=json.load(sys.stdin)
print('id', p['id'], 'source', p.get('source'), 'thumbnail_url', p.get('thumbnail_url'))
"

# Check on-disk file + validity
uv run --env-file backend/keys.env python -c "
from pathlib import Path
from backend.config import get_settings
from backend.services.thumbnail_service import build_thumbnail_filename, is_thumbnail_valid, EXPECTED_THUMBNAIL_WIDTH
from PIL import Image

arxiv_id = '2512.20856'
version = 'v1'
fn = build_thumbnail_filename(arxiv_id, version)
cache = Path(get_settings().thumbnail_temp_cache_dir)
path = cache / fn
print('path', path, 'exists', path.exists())
if path.exists():
    with Image.open(path) as img:
        print('size', img.size, 'ratio', round(img.height/img.width, 3))
    print('valid', is_thumbnail_valid(path), 'expected_width', EXPECTED_THUMBNAIL_WIDTH)
"
```

**Common failure modes**

| Symptom | Likely cause |
|--------|----------------|
| Large white bars top/bottom in card | Old squat JPEG (~400×282) or browser/nginx cache of `?fit=fit3` |
| File exists but cron skips regen | `is_thumbnail_valid()` is false — corrupt, wrong width, or H/W < 1.0 |
| API 404 on thumbnail | Missing locally; bucket mirror not run yet |
| External paper, no image | `papers.thumbnail_url` unset; need `generate_external_thumbnail` |

Compare production vs local when user still sees a bad image:

```bash
curl -s "https://paperswithcode.co/api/thumbnails/2512_20856_v1.jpg?fit=fit4&b=$(date +%s)" -o /tmp/prod.jpg
curl -s "http://localhost:8000/api/thumbnails/2512_20856_v1.jpg?fit=fit4" -o /tmp/local.jpg
uv run python -c "from PIL import Image; print('prod', Image.open('/tmp/prod.jpg').size); print('local', Image.open('/tmp/local.jpg').size)"
```

## Regenerate (preferred)

Use the bundled script for one or a few papers:

```bash
uv run --env-file backend/keys.env \
  .agents/skills/fix-paper-thumbnail/scripts/regenerate_thumbnail.py 2512.20856

# Or by paperswithcode URL / numeric paper id
uv run --env-file backend/keys.env \
  .agents/skills/fix-paper-thumbnail/scripts/regenerate_thumbnail.py \
  --url https://paperswithcode.co/paper/2512.20856

uv run --env-file backend/keys.env \
  .agents/skills/fix-paper-thumbnail/scripts/regenerate_thumbnail.py --paper-id 54972
```

The script calls `ThumbnailService` with `force=True`, uploads to the HF bucket (when `PWC_THUMBNAIL_STORAGE_BACKEND=hf_bucket`), and prints `valid=True` when the JPEG is **400×550** with portrait aspect.

For **external** papers it also sets `papers.thumbnail_url` to the custom thumbnail URL.

### Inline alternative (no script)

```bash
uv run --env-file backend/keys.env python -c "
import asyncio
from backend.services.thumbnail_service import ThumbnailService, is_thumbnail_valid
from PIL import Image

async def main():
    svc = ThumbnailService()
    path = await svc.generate_thumbnail('2512.20856', 'v1', force=True)
    print('path', path, 'valid', is_thumbnail_valid(path))
    with Image.open(path) as img:
        print('size', img.size)

asyncio.run(main())
"
```

External papers: use `generate_external_thumbnail(paper_id, source_url, force=True)` and persist `build_custom_thumbnail_url(filename)` — see `add-external-paper` skill for the full snippet.

## Bulk / cron paths

For many papers, use the preload cron (same renderer):

```bash
# Single trending/visible paper sets
uv run --env-file backend/keys.env \
  .github/workflows/scripts/daily/preload_thumbnails.py \
  --priority trending --limit 50 --refresh-existing

# All locally-invalid/missing arXiv thumbnails
uv run --env-file backend/keys.env \
  .github/workflows/scripts/daily/preload_thumbnails.py \
  --priority missing-all --missing-only --limit 200

# External papers missing thumbnails
uv run --env-file backend/keys.env \
  .github/workflows/scripts/daily/preload_thumbnails.py \
  --priority external-missing --limit 50
```

After bucket uploads, the VPS disk mirror is updated by `mirror_thumbnails_to_disk.py` (daily). Request serving reads **local** `PWC_THUMBNAIL_TEMP_CACHE_DIR` only — regenerating + uploading is enough for this server; mirror cron handles redundancy.

## Verify

```bash
# API returns thumbnail URL with current cache-bust query param
curl -s "http://localhost:8000/api/v1/papers/2512.20856" | uv run python -c "
import json,sys; print(json.load(sys.stdin).get('thumbnail_url'))
"

# JPEG serves 200 with correct dimensions
curl -s -o /tmp/thumb.jpg -w "HTTP %{http_code}\n" \
  "http://localhost:8000/api/thumbnails/2512_20856_v1.jpg?fit=fit4"
uv run python -c "from PIL import Image; print(Image.open('/tmp/thumb.jpg').size)"
```

Success criteria:

- HTTP **200**, JPEG **400×550**
- `is_thumbnail_valid(path)` is **True**
- Card preview fills the frame without letterboxing (no squat aspect)

Tell the user to hard-refresh if they still see an old image — thumbnail URLs include `?fit=…` for cache busting. **Only bump `THUMBNAIL_RENDERER_CACHE_BUST` in `thumbnail_service.py` when the renderer logic changes globally**, then restart the backend (`./start_services.sh`).

## Renderer reference

Implementation lives in `backend/services/thumbnail_service.py`:

- **Target size**: `EXPECTED_THUMBNAIL_WIDTH = 400`, height `400 / (160/220) = 550`
- **Pipeline**: PDF page → trim margins → trim leading/trailing blank → drop sparse footer → **cover-fill** to card aspect
- **Validity**: JPEG, exact width 400, `height/width >= 1.0`

Do not hand-edit JPEGs in the cache; always regenerate from source PDF/page so uploads stay consistent with the cron pipeline.

## When to restart / redeploy

- **Regenerating thumbnails only**: no restart required; file is served from disk immediately.
- **Changed `THUMBNAIL_RENDERER_CACHE_BUST` or thumbnail API code**: `./start_services.sh`
- **Frontend-only** (unlikely for thumbnails): `cd frontend && npm run build && nginx -s reload`

## Report back

Summarize: paper id/arxiv id, old vs new dimensions, `thumbnail_url`, whether validation passed, and whether the user may need a hard refresh for browser cache.
