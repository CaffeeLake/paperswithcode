-- Migration: Add canonical source paper links to methods
-- Description: Makes "paper introduced method" explicit via methods.source_paper_id
-- Date: 2026-05-09

ALTER TABLE methods
ADD COLUMN IF NOT EXISTS source_paper_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_methods_source_paper_id'
    ) THEN
        ALTER TABLE methods
        ADD CONSTRAINT fk_methods_source_paper_id
        FOREIGN KEY (source_paper_id)
        REFERENCES papers(id)
        ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_methods_source_paper_id
ON methods(source_paper_id);

COMMENT ON COLUMN methods.source_paper_id IS
'Canonical paper that introduced this method; source_url remains a display/source link.';

WITH local_source_methods AS (
    SELECT
        m.id AS method_id,
        m.source_paper_id AS existing_source_paper_id,
        regexp_replace(
            substring(
                m.source_url FROM '(?:^https?://[^/]+|^)/(?:paper|abs|pdf)/([^/?#]+)'
            ),
            '\.pdf$',
            ''
        ) AS source_ref
    FROM methods m
    WHERE m.source_url IS NOT NULL
        AND btrim(m.source_url) <> ''
        AND (
            m.source_url ~ '^/(paper|abs|pdf)/'
            OR m.source_url ~ '^https?://(localhost(:[0-9]+)?|127\.0\.0\.1(:[0-9]+)?|167\.235\.148\.241(:[0-9]+)?|paperswithcode\.co|www\.paperswithcode\.co)/(paper|abs|pdf)/'
        )
),
parsed_source_methods AS (
    SELECT
        method_id,
        existing_source_paper_id,
        regexp_replace(source_ref, 'v[0-9]+$', '') AS source_arxiv_id,
        substring(source_ref FROM 'v[0-9]+$') AS source_version
    FROM local_source_methods
    WHERE source_ref IS NOT NULL
),
resolved_source_methods AS (
    SELECT
        psm.method_id,
        p.id AS paper_id,
        psm.existing_source_paper_id
    FROM parsed_source_methods psm
    JOIN papers p
        ON p.arxiv_id = psm.source_arxiv_id
        AND (
            (psm.source_version IS NULL AND p.is_latest_version)
            OR p.version = psm.source_version
        )
),
already_linked AS (
    SELECT method_id
    FROM resolved_source_methods
    WHERE existing_source_paper_id = paper_id
),
backfilled AS (
    UPDATE methods m
    SET source_paper_id = r.paper_id
    FROM resolved_source_methods r
    WHERE m.id = r.method_id
        AND m.source_paper_id IS DISTINCT FROM r.paper_id
    RETURNING m.id
)
SELECT
    (SELECT count(*) FROM backfilled) AS methods_backfilled,
    (SELECT count(*) FROM already_linked) AS methods_already_linked,
    (
        SELECT count(*)
        FROM methods m
        WHERE m.source_url IS NOT NULL
            AND btrim(m.source_url) <> ''
            AND NOT (
                m.source_url ~ '^/(paper|abs|pdf)/'
                OR m.source_url ~ '^https?://(localhost(:[0-9]+)?|127\.0\.0\.1(:[0-9]+)?|167\.235\.148\.241(:[0-9]+)?|paperswithcode\.co|www\.paperswithcode\.co)/(paper|abs|pdf)/'
            )
    ) AS non_local_source_urls,
    (
        SELECT count(*)
        FROM parsed_source_methods psm
        LEFT JOIN resolved_source_methods r
            ON r.method_id = psm.method_id
        WHERE r.method_id IS NULL
    ) AS unresolved_local_source_urls;

WITH inserted AS (
    INSERT INTO paper_methods (paper_id, method_id)
    SELECT source_paper_id, id
    FROM methods
    WHERE source_paper_id IS NOT NULL
    ON CONFLICT DO NOTHING
    RETURNING paper_id, method_id
)
SELECT count(*) AS paper_methods_inserted_for_source_links
FROM inserted;
