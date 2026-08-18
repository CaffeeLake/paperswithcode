BEGIN;

ALTER TABLE public.paper_method_evidence
    DROP CONSTRAINT IF EXISTS paper_method_evidence_type_check;
ALTER TABLE public.paper_method_evidence
    ADD CONSTRAINT paper_method_evidence_type_check CHECK (
        evidence_type IN ('source','keyword','reference','curation','manual','legacy_unknown')
    );

CREATE TABLE IF NOT EXISTS paper_curation_workflows (
    id UUID PRIMARY KEY,
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    cohort_date DATE NOT NULL,
    cohort_order INTEGER NOT NULL DEFAULT 0,
    policy_version VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','completed','failed','partial','deferred','canceled','satisfied')),
    review_status VARCHAR(24) NOT NULL DEFAULT 'unreviewed',
    enrich_satisfied_by_job_id UUID,
    evals_satisfied_by_job_id UUID,
    dependency_override BOOLEAN NOT NULL DEFAULT FALSE,
    deferred_reason TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

ALTER TABLE paper_curation_jobs
    ADD COLUMN IF NOT EXISTS parent_workflow_id UUID REFERENCES paper_curation_workflows(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS trigger VARCHAR(24) NOT NULL DEFAULT 'admin',
    ADD COLUMN IF NOT EXISTS cohort_date DATE,
    ADD COLUMN IF NOT EXISTS policy_version VARCHAR(64) NOT NULL DEFAULT 'admin-v1',
    ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100,
    ADD COLUMN IF NOT EXISTS repository_sha VARCHAR(40),
    ADD COLUMN IF NOT EXISTS skill_sha256 VARCHAR(64),
    ADD COLUMN IF NOT EXISTS prompt_sha256 VARCHAR(64),
    ADD COLUMN IF NOT EXISTS model VARCHAR(128),
    ADD COLUMN IF NOT EXISTS reasoning_effort VARCHAR(24),
    ADD COLUMN IF NOT EXISTS codex_cli_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS validator_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS trace_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS trace_uri TEXT,
    ADD COLUMN IF NOT EXISTS trace_sha256 VARCHAR(64),
    ADD COLUMN IF NOT EXISTS trace_attempt_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS proposal JSONB,
    ADD COLUMN IF NOT EXISTS validation_summary JSONB,
    ADD COLUMN IF NOT EXISTS mutation_result JSONB,
    ADD COLUMN IF NOT EXISTS url_candidates JSONB,
    ADD COLUMN IF NOT EXISTS input_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS output_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS duration_ms INTEGER,
    ADD COLUMN IF NOT EXISTS taxonomy_query_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS leaderboard_query_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retry_of_id UUID REFERENCES paper_curation_jobs(id),
    ADD COLUMN IF NOT EXISTS audit_status VARCHAR(24) NOT NULL DEFAULT 'unreviewed';

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'paper_curation_jobs_trigger_check') THEN
        ALTER TABLE paper_curation_jobs ADD CONSTRAINT paper_curation_jobs_trigger_check
            CHECK (trigger IN ('admin','hf-daily-cron','benchmark-promotion'));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'paper_curation_workflows_enrich_job_fkey') THEN
        ALTER TABLE paper_curation_workflows ADD CONSTRAINT paper_curation_workflows_enrich_job_fkey
            FOREIGN KEY (enrich_satisfied_by_job_id) REFERENCES paper_curation_jobs(id);
        ALTER TABLE paper_curation_workflows ADD CONSTRAINT paper_curation_workflows_evals_job_fkey
            FOREIGN KEY (evals_satisfied_by_job_id) REFERENCES paper_curation_jobs(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_paper_curation_workflows_queue
    ON paper_curation_workflows (status, cohort_date DESC, cohort_order);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_paper_curation_workflow
    ON paper_curation_workflows (paper_id)
    WHERE status IN ('queued','running','deferred');
CREATE INDEX IF NOT EXISTS idx_paper_curation_jobs_workflow
    ON paper_curation_jobs (parent_workflow_id, created_at);
CREATE INDEX IF NOT EXISTS idx_paper_curation_jobs_dispatch
    ON paper_curation_jobs (status, priority, cohort_date DESC, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_scheduled_paper_curation_stage
    ON paper_curation_jobs (paper_id, kind, policy_version)
    WHERE trigger <> 'admin' AND status IN ('queued','dispatching','running');

CREATE TABLE IF NOT EXISTS benchmark_curation_candidates (
    id UUID PRIMARY KEY,
    identity_key VARCHAR(64) UNIQUE NOT NULL,
    canonical_name VARCHAR(500) NOT NULL,
    gap_type VARCHAR(48) NOT NULL CHECK (gap_type IN (
        'dataset_missing','task_dataset_association_missing','metric_configuration_missing','task_missing'
    )),
    canonical_url TEXT,
    task_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(24) NOT NULL DEFAULT 'candidate',
    distinct_paper_count INTEGER NOT NULL DEFAULT 0,
    confidence VARCHAR(16),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS benchmark_curation_evidence (
    id UUID PRIMARY KEY,
    candidate_id UUID NOT NULL REFERENCES benchmark_curation_candidates(id) ON DELETE CASCADE,
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES paper_curation_jobs(id),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_benchmark_gap_evidence_job UNIQUE (candidate_id, paper_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_benchmark_curation_evidence_paper
    ON benchmark_curation_evidence (paper_id, candidate_id);

CREATE TABLE IF NOT EXISTS paper_curation_scheduler_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    dispatch_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    paused_at TIMESTAMPTZ,
    pause_reason TEXT,
    pause_condition VARCHAR(64),
    acknowledged_at TIMESTAMPTZ,
    canary_released BOOLEAN NOT NULL DEFAULT FALSE,
    first_enabled_at TIMESTAMPTZ,
    consecutive_trace_failures INTEGER NOT NULL DEFAULT 0,
    consecutive_apply_failures INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO paper_curation_scheduler_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Staging resolves unqualified ORM table names through `staging, public` and
-- keeps all workflow state isolated from production catalog writes.
DO $$ BEGIN
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        CREATE TABLE IF NOT EXISTS staging.paper_curation_workflows
            (LIKE public.paper_curation_workflows INCLUDING ALL);

        ALTER TABLE staging.paper_curation_jobs
            ADD COLUMN IF NOT EXISTS parent_workflow_id UUID,
            ADD COLUMN IF NOT EXISTS trigger VARCHAR(24) NOT NULL DEFAULT 'admin',
            ADD COLUMN IF NOT EXISTS cohort_date DATE,
            ADD COLUMN IF NOT EXISTS policy_version VARCHAR(64) NOT NULL DEFAULT 'admin-v1',
            ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100,
            ADD COLUMN IF NOT EXISTS repository_sha VARCHAR(40),
            ADD COLUMN IF NOT EXISTS skill_sha256 VARCHAR(64),
            ADD COLUMN IF NOT EXISTS prompt_sha256 VARCHAR(64),
            ADD COLUMN IF NOT EXISTS model VARCHAR(128),
            ADD COLUMN IF NOT EXISTS reasoning_effort VARCHAR(24),
            ADD COLUMN IF NOT EXISTS codex_cli_version VARCHAR(64),
            ADD COLUMN IF NOT EXISTS validator_version VARCHAR(64),
            ADD COLUMN IF NOT EXISTS trace_status VARCHAR(32) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS trace_uri TEXT,
            ADD COLUMN IF NOT EXISTS trace_sha256 VARCHAR(64),
            ADD COLUMN IF NOT EXISTS trace_attempt_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS proposal JSONB,
            ADD COLUMN IF NOT EXISTS validation_summary JSONB,
            ADD COLUMN IF NOT EXISTS mutation_result JSONB,
            ADD COLUMN IF NOT EXISTS url_candidates JSONB,
            ADD COLUMN IF NOT EXISTS input_tokens INTEGER,
            ADD COLUMN IF NOT EXISTS output_tokens INTEGER,
            ADD COLUMN IF NOT EXISTS duration_ms INTEGER,
            ADD COLUMN IF NOT EXISTS taxonomy_query_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS leaderboard_query_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS retry_of_id UUID,
            ADD COLUMN IF NOT EXISTS audit_status VARCHAR(24) NOT NULL DEFAULT 'unreviewed';

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'staging_paper_curation_jobs_parent_fkey'
        ) THEN
            ALTER TABLE staging.paper_curation_jobs
                ADD CONSTRAINT staging_paper_curation_jobs_parent_fkey
                FOREIGN KEY (parent_workflow_id)
                REFERENCES staging.paper_curation_workflows(id) ON DELETE CASCADE,
                ADD CONSTRAINT staging_paper_curation_jobs_retry_fkey
                FOREIGN KEY (retry_of_id) REFERENCES staging.paper_curation_jobs(id),
                ADD CONSTRAINT staging_paper_curation_jobs_trigger_check
                CHECK (trigger IN ('admin','hf-daily-cron','benchmark-promotion'));
            ALTER TABLE staging.paper_curation_workflows
                ADD CONSTRAINT staging_paper_curation_workflows_paper_fkey
                FOREIGN KEY (paper_id) REFERENCES public.papers(id) ON DELETE CASCADE,
                ADD CONSTRAINT staging_paper_curation_workflows_enrich_fkey
                FOREIGN KEY (enrich_satisfied_by_job_id)
                REFERENCES staging.paper_curation_jobs(id),
                ADD CONSTRAINT staging_paper_curation_workflows_evals_fkey
                FOREIGN KEY (evals_satisfied_by_job_id)
                REFERENCES staging.paper_curation_jobs(id);
        END IF;

        CREATE INDEX IF NOT EXISTS idx_staging_paper_curation_jobs_workflow
            ON staging.paper_curation_jobs (parent_workflow_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_staging_paper_curation_jobs_dispatch
            ON staging.paper_curation_jobs (status, priority, cohort_date DESC, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_active_scheduled_curation_stage
            ON staging.paper_curation_jobs (paper_id, kind, policy_version)
            WHERE trigger <> 'admin' AND status IN ('queued','dispatching','running');

        CREATE TABLE IF NOT EXISTS staging.benchmark_curation_candidates
            (LIKE public.benchmark_curation_candidates INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.benchmark_curation_evidence
            (LIKE public.benchmark_curation_evidence INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.paper_curation_scheduler_state
            (LIKE public.paper_curation_scheduler_state INCLUDING ALL);

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'staging_benchmark_curation_evidence_candidate_fkey'
        ) THEN
            ALTER TABLE staging.benchmark_curation_evidence
                ADD CONSTRAINT staging_benchmark_curation_evidence_candidate_fkey
                FOREIGN KEY (candidate_id)
                REFERENCES staging.benchmark_curation_candidates(id) ON DELETE CASCADE,
                ADD CONSTRAINT staging_benchmark_curation_evidence_paper_fkey
                FOREIGN KEY (paper_id) REFERENCES public.papers(id) ON DELETE CASCADE,
                ADD CONSTRAINT staging_benchmark_curation_evidence_job_fkey
                FOREIGN KEY (job_id) REFERENCES staging.paper_curation_jobs(id);
        END IF;

        INSERT INTO staging.paper_curation_scheduler_state (id)
            VALUES (1) ON CONFLICT (id) DO NOTHING;
        ALTER TABLE staging.paper_curation_workflows OWNER TO pwc_staging_owner;
        ALTER TABLE staging.benchmark_curation_candidates OWNER TO pwc_staging_owner;
        ALTER TABLE staging.benchmark_curation_evidence OWNER TO pwc_staging_owner;
        ALTER TABLE staging.paper_curation_scheduler_state OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            staging.paper_curation_workflows,
            staging.benchmark_curation_candidates,
            staging.benchmark_curation_evidence,
            staging.paper_curation_scheduler_state TO pwc_staging;
    END IF;
END $$;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON paper_curation_workflows,
            benchmark_curation_candidates, benchmark_curation_evidence,
            paper_curation_scheduler_state TO paperswithcode_user;
    END IF;
END $$;

COMMIT;
