-- Versioned pgvector storage for related papers and hybrid search.
-- Apply only to an isolated PostgreSQL 16 database until deployment is authorized.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS paper_embedding_generations (
    id bigserial PRIMARY KEY,
    model_name text NOT NULL,
    model_revision text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions BETWEEN 32 AND 4096),
    input_format_version text NOT NULL,
    normalization text NOT NULL DEFAULT 'l2' CHECK (normalization = 'l2'),
    query_instruction_version text NOT NULL,
    bucket_run_uri text NOT NULL,
    ranking_version text NOT NULL DEFAULT 'dense-v1',
    validation_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL CHECK (status IN ('loading', 'ready', 'active', 'retired', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    activated_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_embedding_one_active
ON paper_embedding_generations ((status)) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS paper_embeddings (
    generation_id bigint NOT NULL REFERENCES paper_embedding_generations(id),
    paper_id bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    embedding halfvec NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (generation_id, paper_id)
) PARTITION BY LIST (generation_id);

CREATE OR REPLACE FUNCTION validate_paper_embedding_dimensions()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_dimensions integer;
BEGIN
    SELECT dimensions INTO STRICT expected_dimensions
    FROM paper_embedding_generations WHERE id = NEW.generation_id;
    IF vector_dims(NEW.embedding) <> expected_dimensions THEN
        RAISE EXCEPTION 'embedding dimension % does not match generation dimension %',
            vector_dims(NEW.embedding), expected_dimensions;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS paper_embeddings_validate_dimensions ON paper_embeddings;
CREATE TRIGGER paper_embeddings_validate_dimensions
BEFORE INSERT OR UPDATE OF generation_id, embedding ON paper_embeddings
FOR EACH ROW EXECUTE FUNCTION validate_paper_embedding_dimensions();

CREATE OR REPLACE FUNCTION create_paper_embedding_partition(
    requested_generation_id bigint,
    requested_dimensions integer
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    partition_name text := format('paper_embeddings_g%s', requested_generation_id);
    declared_dimensions integer;
BEGIN
    SELECT dimensions INTO STRICT declared_dimensions
    FROM paper_embedding_generations WHERE id = requested_generation_id;
    IF declared_dimensions <> requested_dimensions THEN
        RAISE EXCEPTION 'generation dimensions % do not match requested %',
            declared_dimensions, requested_dimensions;
    END IF;
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF paper_embeddings FOR VALUES IN (%s)',
        partition_name, requested_generation_id
    );
END;
$$;

CREATE TABLE IF NOT EXISTS embedding_pipeline_runs (
    run_id text NOT NULL,
    generation_id bigint REFERENCES paper_embedding_generations(id),
    kind text NOT NULL CHECK (kind IN ('export', 'job', 'import', 'retention')),
    status text NOT NULL,
    row_count bigint,
    artifact_uri text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    PRIMARY KEY (run_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_embedding_pipeline_runs_started
ON embedding_pipeline_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS paper_lexeme_document_frequencies (
    lexeme text PRIMARY KEY,
    document_frequency bigint NOT NULL,
    corpus_size bigint NOT NULL,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION refresh_paper_lexeme_document_frequencies()
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE inserted bigint;
DECLARE total_documents bigint;
BEGIN
    SELECT count(*) INTO total_documents FROM papers WHERE is_latest_version;
    TRUNCATE paper_lexeme_document_frequencies;
    INSERT INTO paper_lexeme_document_frequencies
        (lexeme, document_frequency, corpus_size)
    SELECT word, ndoc, total_documents
    FROM ts_stat('SELECT search_vector FROM papers WHERE is_latest_version AND search_vector IS NOT NULL');
    GET DIAGNOSTICS inserted = ROW_COUNT;
    RETURN inserted;
END;
$$;
