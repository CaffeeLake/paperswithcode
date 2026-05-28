---
name: add-method
description: Add or update AI/ML method taxonomy rows in the paperswithcode repo database. Use this whenever the user asks to add a method, technique, architecture, attention mechanism, training method, model-family method, or source/visual metadata for a method; says phrases like "make GPT-4 a method", "add X as a method", "link this method to the paper", or "update the method source to point to the paper page"; or gives a method name plus a paper, arXiv id, PapersWithCode URL, Hugging Face report, GitHub explainer, blog post, or says "similarly add this method".
---

# Add a Method

This skill adds curated rows to the `methods` table so method pages, paper pages, and "Introduced" banners render correctly. Prefer small idempotent migrations plus applying the same change to the live database.

## Core Rules

Method source links should point to the canonical source that introduced the method.

- If the source exists as a local `papers` row, set `methods.source_paper_id` and leave `methods.source_url = NULL`. The API will expose a native route like `/paper/{arxiv_id}` or `/paper/{paper_id}`.
- If the method has no real source paper, use a clear source/explainer URL in `methods.source_url` and `methods.source_title`.
- Do not use an external PDF, arXiv URL, Hugging Face PDF, GitHub README, or blog as `source_url` when the actual source paper already has a local PapersWithCode page.
- If a paper introduced the method, also insert `(source_paper_id, method_id)` into `paper_methods`; the paper detail "Introduced" banner depends on the method appearing in `paper.methods`, not just on `methods.source_paper_id`.

Be careful about provenance. The source paper is the paper that introduced, named, or formally described the method. A later explainer, implementation tutorial, or model card can be useful for `code_snippet_url`, `image_url`, and `image_credit`, but it is not the canonical source if an introducing paper exists.

## Workflow

1. Understand the requested method:
   - Record the desired method name, abbreviation, source candidate, and any explainer or visual URL the user provided.
   - Pick a stable slug using lowercase words joined by hyphens, such as `deepseek-sparse-attention`.
   - Search for an existing method by `name`, `slug`, `full_name`, and `keywords` before creating a new row.

2. Resolve the source:
   - If the user provides a paper page such as `https://paperswithcode.co/paper/2512.02556`, query `papers` by arXiv id or id.
   - If the user provides an arXiv id, arXiv URL, HF paper/report, or technical report, first check whether the local `papers` row already exists.
   - If the source is a non-ArXiv technical report or resource and no local paper row exists, use the `add-external-paper` skill first, then return to this workflow with the new `papers.id`.
   - If the user explicitly says there is no source paper, store the best explainer as `source_url`/`source_title` and keep `source_paper_id = NULL`.
   - If the method is part of a model-family chain and the user also asks to connect predecessor/follow-up papers, run `link-paper-lineage` as a separate follow-up after the method row is correct.

3. Choose metadata:
   - `name`: short display name, respecting capitalization users expect.
   - `full_name`: expanded name with abbreviation when useful, e.g. `DeepSeek Sparse Attention (DSA)`.
   - `description`: one concise paragraph explaining what the method does and why it matters. Avoid overclaiming beyond the source. Markdown is supported and rendered with bullet lists, bold/italics, inline code, and KaTeX math. To refer to other methods, papers, tasks, or benchmarks on paperswithcode.co, use **relative markdown links** like `[Transformer](/methods/transformer)`, `[GPT-2](/paper/83630)`, `[Language Modeling](/tasks/language-modeling)`, or `[MMLU](/benchmark/mmlu)`. The frontend rewrites those into in-app navigation. Do not hard-code absolute hosts such as `https://paperswithcode.co`, `http://localhost:8080`, or the staging IP, and avoid linking to external explainers when an internal `/methods/<slug>` or `/paper/<id>` page exists.
   - `keywords`: include exact name, abbreviation, hyphenated variants, and common aliases.
   - `area_id`: resolve by area name. In the live DB, language methods usually use `Language`; migrations can also support older `Natural Language Processing` naming.
   - `introduced_year`: use the source paper year. If there is no source, use the year the method was first introduced or the explainer's publication context only if clear.
   - `code_snippet_url`: optional implementation/example URL.
   - `image_url` and `image_credit`: optional visual and attribution. Use stable direct image URLs where the frontend can render them.

4. Create an idempotent migration:
   - Add a focused SQL file under `backend/database/migrations/`, named like `add_<slug>_method.sql`.
   - Use `INSERT INTO methods (...) VALUES (...) ON CONFLICT (slug) DO UPDATE`.
   - Include `source_paper_id` in both the insert and update when the method has a local source paper.
   - Insert the canonical source paper relation into `paper_methods` when `source_paper_id` is set.

Example migration shape:

```sql
INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    '<slug>',
    '<Name>',
    '<Full Name>',
    '<description>',
    '<keywords>',
    (
        SELECT id
        FROM areas
        WHERE name IN ('Language', 'Natural Language Processing')
        ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END
        LIMIT 1
    ),
    <year>,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '<arxiv_id>'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    '<source paper title>',
    '<example code URL>',
    '<image URL>',
    '<image credit>'
)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug = '<slug>'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
```

For methods with no source paper, omit `source_paper_id` or set it to `NULL`, set a meaningful `source_url`, and skip the `paper_methods` insert unless a real source paper exists.

## Database Access

Run Python and project CLIs from the repo root with the project environment:

```bash
uv run --env-file backend/keys.env python3 ...
```

Apply the migration to the live DB with SQLAlchemy:

```bash
uv run --env-file backend/keys.env python3 - <<'PY'
from pathlib import Path
from sqlalchemy import text
from backend.database.connection import db_manager

sql = Path("backend/database/migrations/<migration>.sql").read_text()
with db_manager.engine.begin() as conn:
    conn.execute(text(sql))
PY
```

Keep writes scoped to the requested method. Do not rewrite unrelated method metadata or paper tags.

## Verification

Verify all of these before reporting done:

1. Query the method row and source paper link:

```sql
SELECT m.id, m.slug, m.name, m.source_paper_id, p.arxiv_id, m.source_url
FROM methods m
LEFT JOIN papers p ON p.id = m.source_paper_id
WHERE m.slug = '<slug>';
```

2. If `source_paper_id` is set, confirm the `paper_methods` row exists:

```sql
SELECT pm.paper_id, pm.method_id
FROM paper_methods pm
JOIN methods m ON m.id = pm.method_id
WHERE m.slug = '<slug>' AND pm.paper_id = m.source_paper_id;
```

3. Hit the method API:

```bash
curl -fsS "http://localhost:8000/api/v1/methods/<slug>" | uv run python3 -m json.tool
```

4. If there is a source paper, hit the paper API and confirm the method is included with matching `source_paper_id`; this is what powers the introduced-method banner:

```bash
curl -fsS "http://localhost:8000/api/v1/papers/<arxiv_id>?include_resources=true" \
  | uv run python3 -c "import json,sys; p=json.load(sys.stdin); print([(m['slug'], m.get('source_paper_id')) for m in p.get('methods') or []])"
```

If the API is stale because the backend needs a restart, run `./start_services.sh` without asking.

## Reporting Back

Report the method slug, method page URL, source behavior, and verification result. Always include the production method URL in the form `https://paperswithcode.co/methods/<slug>` so the user can immediately check the page. Be explicit about whether the method uses:

- a native source paper route via `source_paper_id`, or
- an external explainer URL because no source paper exists.

Mention that the `paper_methods` link was added when the method has a source paper, because that is what makes the source paper's introduced banner appear.
