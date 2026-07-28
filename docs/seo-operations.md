# SEO operations handoff

The application source provides crawlable paper HTML, canonical metadata,
sitemaps, archives, validation, smoke checks, and the read-only completeness
report. The following operations remain deliberately separate.

## Completeness report

Run against one canonical route identifier:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.report_seo_completeness \
  --paper 2607.24653
```

Run a bounded publication cohort:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.report_seo_completeness \
  --published-since 2026-07-14 --limit 100 --json
```

The command is read-only. Apply any resulting curation through the existing
paper enrichment and evaluation workflows.

## Separate authorization boundaries

- Apply the checked-in staging nginx template with `pwc-nginx staging` only
  after explicit staging-nginx authorization.
- Apply the production nginx template and deploy the application to production
  only after explicit production authorization.
- Cloudflare currently owns the public `robots.txt` response. Add
  `Sitemap: https://paperswithcode.co/sitemap.xml` in that authoritative
  configuration while preserving all existing crawler restrictions and
  `Content-Signal` policy.
- Search Console ownership, baseline export, sitemap submission, URL
  inspection, and indexing requests require access to the apex-domain
  property. Record the fixed cohort and baseline described in
  `IMPROVE_SEO.md` before the production rollout.
- Kimi K3 data curation is not performed by the SEO application code. Verify
  its classification and TLDR, official repository/project page, Hugging Face
  artifacts, method tags, and source-supported evaluations through the
  dedicated curation workflows before requesting indexing.
