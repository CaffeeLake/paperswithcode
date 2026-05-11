-- External resources schema generalization.
--
-- Generalizes the `papers` table so it can host both ArXiv papers and external
-- resources (vendor blog posts, technical reports, model cards, etc.) without
-- needing parallel relationship tables.
--
-- Two new columns are added:
--
--   - source     (VARCHAR(20)) -> 'arxiv' or 'external'. Existing rows are
--                                  backfilled to 'arxiv'. Future external rows
--                                  are inserted with 'external'.
--   - source_url (VARCHAR(2000)) -> Canonical URL for external rows. For
--                                    `source='arxiv'` rows this stays NULL;
--                                    ArXiv URLs continue to be derived from
--                                    `arxiv_id`.
--
-- `arxiv_id` is also relaxed to be nullable so external rows can omit it. The
-- existing `(arxiv_id, version)` uniqueness constraint is replaced with a
-- partial unique index that only applies when `arxiv_id IS NOT NULL`.
--
-- A partial unique index on `source_url` ensures that two external rows cannot
-- share the same canonical URL. ArXiv rows leave `source_url` NULL and are not
-- constrained by it.
--
-- Idempotent: safe to re-run.

BEGIN;

-- 1. Add source columns.
ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'arxiv';
ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS source_url VARCHAR(2000) NULL;

-- 2. Backfill is implicit via the DEFAULT above; existing rows get
-- `source='arxiv'` and `source_url=NULL`. Re-runs on a populated table also
-- leave existing rows untouched because the column already exists.

-- 3. Drop the old `(arxiv_id, version)` UNIQUE constraint so we can replace it
-- with a partial unique index that allows NULL `arxiv_id`. The constraint may
-- have either of two historical names depending on how the schema was created.
ALTER TABLE papers
    DROP CONSTRAINT IF EXISTS uq_paper_arxiv_version;
ALTER TABLE papers
    DROP CONSTRAINT IF EXISTS papers_arxiv_id_version_key;

-- 4. Make `arxiv_id` nullable. Use ALTER COLUMN ... DROP NOT NULL only when it
-- is currently NOT NULL.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'papers'
          AND column_name = 'arxiv_id'
          AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE papers ALTER COLUMN arxiv_id DROP NOT NULL;
    END IF;
END
$$;

-- 5. Replacement: partial unique index on (arxiv_id, version) for ArXiv rows.
CREATE UNIQUE INDEX IF NOT EXISTS uq_papers_arxiv_id_version_when_present
    ON papers (arxiv_id, version)
    WHERE arxiv_id IS NOT NULL;

-- 6. Partial unique index on source_url for external rows. Two external rows
-- cannot share the same canonical URL.
CREATE UNIQUE INDEX IF NOT EXISTS uq_papers_source_url_external
    ON papers (source_url)
    WHERE source = 'external' AND source_url IS NOT NULL;

-- 7. Index for filtering by source.
CREATE INDEX IF NOT EXISTS idx_papers_source ON papers (source);

-- 8. Constrain `source` to allowed values.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.constraint_column_usage
        WHERE table_name = 'papers'
          AND constraint_name = 'papers_source_check'
    ) THEN
        ALTER TABLE papers
            ADD CONSTRAINT papers_source_check
            CHECK (source IN ('arxiv', 'external'));
    END IF;
END
$$;

-- 9. Enforce identifier presence per source.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.constraint_column_usage
        WHERE table_name = 'papers'
          AND constraint_name = 'papers_source_identifier_check'
    ) THEN
        ALTER TABLE papers
            ADD CONSTRAINT papers_source_identifier_check
            CHECK (
                (source = 'arxiv' AND arxiv_id IS NOT NULL)
                OR (source = 'external' AND source_url IS NOT NULL)
            );
    END IF;
END
$$;

COMMIT;
