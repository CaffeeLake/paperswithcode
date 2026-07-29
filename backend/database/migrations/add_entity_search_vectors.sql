-- Additive name-only search schema for benchmarks, methods, and tasks.
-- Existing rows are backfilled separately in bounded committed batches.

ALTER TABLE datasets ADD COLUMN IF NOT EXISTS search_vector tsvector;
ALTER TABLE methods  ADD COLUMN IF NOT EXISTS search_vector tsvector;
ALTER TABLE tasks    ADD COLUMN IF NOT EXISTS search_vector tsvector;

CREATE OR REPLACE FUNCTION pwc_entity_search_normalize(value text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
RETURNS NULL ON NULL INPUT
AS $$
DECLARE
    normalized text := normalize(value, NFKC);
BEGIN
    normalized := translate(
        normalized,
        '⁰¹²³⁴⁵⁶⁷⁸⁹×',
        '0123456789x'
    );
    normalized := replace(normalized, 'τ', 'tau');
    normalized := replace(normalized, 'Τ', 'tau');
    normalized := replace(normalized, 'σ', 'sigma');
    normalized := replace(normalized, 'Σ', 'sigma');
    normalized := regexp_replace(
        normalized,
        '[→←↔⇒⇐⇔⟶⟵]+',
        ' to ',
        'g'
    );
    normalized := translate(normalized, '[]{}‐‑‒–—―', '          ');
    normalized := replace(normalized, chr(92), ' ');
    RETURN trim(
        regexp_replace(
            lower(normalized),
            '[[:space:]_/(),:;_-]+',
            ' ',
            'g'
        )
    );
END;
$$;

CREATE OR REPLACE FUNCTION datasets_search_vector_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.name, '')), 'A');
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION methods_search_vector_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.name, '')), 'A');
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION tasks_search_vector_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.name, '')), 'A');
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS datasets_search_vector_update_trigger ON datasets;
CREATE TRIGGER datasets_search_vector_update_trigger
BEFORE INSERT OR UPDATE OF name ON datasets
FOR EACH ROW EXECUTE FUNCTION datasets_search_vector_update();

DROP TRIGGER IF EXISTS methods_search_vector_update_trigger ON methods;
CREATE TRIGGER methods_search_vector_update_trigger
BEFORE INSERT OR UPDATE OF name ON methods
FOR EACH ROW EXECUTE FUNCTION methods_search_vector_update();

DROP TRIGGER IF EXISTS tasks_search_vector_update_trigger ON tasks;
CREATE TRIGGER tasks_search_vector_update_trigger
BEFORE INSERT OR UPDATE OF name ON tasks
FOR EACH ROW EXECUTE FUNCTION tasks_search_vector_update();
