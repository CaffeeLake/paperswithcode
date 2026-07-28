BEGIN;

ALTER TABLE public.paper_curation_jobs
    ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS thumbnail_status VARCHAR(24),
    ADD COLUMN IF NOT EXISTS thumbnail_requested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS thumbnail_claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS thumbnail_finished_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS thumbnail_attempt_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS thumbnail_url TEXT,
    ADD COLUMN IF NOT EXISTS thumbnail_previous_width INTEGER,
    ADD COLUMN IF NOT EXISTS thumbnail_previous_height INTEGER,
    ADD COLUMN IF NOT EXISTS thumbnail_generated_width INTEGER,
    ADD COLUMN IF NOT EXISTS thumbnail_generated_height INTEGER,
    ADD COLUMN IF NOT EXISTS thumbnail_warnings JSONB,
    ADD COLUMN IF NOT EXISTS thumbnail_error TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'paper_curation_jobs_thumbnail_status_check'
          AND conrelid = 'public.paper_curation_jobs'::regclass
    ) THEN
        ALTER TABLE public.paper_curation_jobs
            ADD CONSTRAINT paper_curation_jobs_thumbnail_status_check
            CHECK (
                thumbnail_status IS NULL
                OR thumbnail_status IN ('queued', 'processing', 'succeeded', 'failed')
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_paper_curation_jobs_thumbnail_queue
    ON public.paper_curation_jobs (thumbnail_status, thumbnail_requested_at);

DO $$
BEGIN
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_jobs
            ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS thumbnail_status VARCHAR(24),
            ADD COLUMN IF NOT EXISTS thumbnail_requested_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS thumbnail_claimed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS thumbnail_finished_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS thumbnail_attempt_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS thumbnail_url TEXT,
            ADD COLUMN IF NOT EXISTS thumbnail_previous_width INTEGER,
            ADD COLUMN IF NOT EXISTS thumbnail_previous_height INTEGER,
            ADD COLUMN IF NOT EXISTS thumbnail_generated_width INTEGER,
            ADD COLUMN IF NOT EXISTS thumbnail_generated_height INTEGER,
            ADD COLUMN IF NOT EXISTS thumbnail_warnings JSONB,
            ADD COLUMN IF NOT EXISTS thumbnail_error TEXT;
        CREATE INDEX IF NOT EXISTS idx_staging_paper_curation_jobs_thumbnail_queue
            ON staging.paper_curation_jobs (thumbnail_status, thumbnail_requested_at);
    END IF;
END $$;

COMMIT;
