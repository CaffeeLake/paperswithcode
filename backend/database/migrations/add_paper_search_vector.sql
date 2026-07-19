-- Phase 1 weighted paper full-text search schema.
--
-- This file is transactional and idempotent. It deliberately does not backfill
-- existing rows or build the GIN index: those operations have separate,
-- resumable/bounded commands so production rollout can control lock and disk
-- pressure explicitly.

ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS search_vector tsvector;

CREATE OR REPLACE FUNCTION papers_search_vector_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.abstract, '')), 'B');
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS papers_search_vector_update_trigger ON papers;

CREATE TRIGGER papers_search_vector_update_trigger
BEFORE INSERT OR UPDATE OF title, abstract ON papers
FOR EACH ROW
EXECUTE FUNCTION papers_search_vector_update();
