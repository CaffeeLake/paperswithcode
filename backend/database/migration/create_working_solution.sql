-- Create a working solution for the normalized project_pages structure
-- This script creates the necessary database objects for the normalized structure to work

-- =============================================================================
-- STEP 1: CREATE A PROPER VIEW THAT SQLALCHEMY CAN USE
-- =============================================================================

-- Drop existing view if it exists
DROP VIEW IF EXISTS project_pages_api CASCADE;

-- Create a view that SQLAlchemy can use for the normalized project_pages
CREATE VIEW project_pages_api AS
SELECT
    id,
    url,
    is_official,
    source,
    created_at,
    updated_at
FROM project_pages_normalized;

-- =============================================================================
-- STEP 2: CREATE INSTEAD OF TRIGGERS FOR THE VIEW (if needed for inserts/updates)
-- =============================================================================

-- Create a function to handle inserts through the view
CREATE OR REPLACE FUNCTION project_pages_api_insert()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO project_pages_normalized (id, url, is_official, source, created_at, updated_at)
    VALUES (NEW.id, NEW.url, NEW.is_official, NEW.source, NEW.created_at, NEW.updated_at);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create a function to handle updates through the view
CREATE OR REPLACE FUNCTION project_pages_api_update()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE project_pages_normalized
    SET
        url = NEW.url,
        is_official = NEW.is_official,
        source = NEW.source,
        updated_at = NEW.updated_at
    WHERE id = OLD.id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create a function to handle deletes through the view
CREATE OR REPLACE FUNCTION project_pages_api_delete()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM project_pages_normalized WHERE id = OLD.id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Create INSTEAD OF triggers
CREATE TRIGGER project_pages_api_insert_trigger
    INSTEAD OF INSERT ON project_pages_api
    FOR EACH ROW EXECUTE FUNCTION project_pages_api_insert();

CREATE TRIGGER project_pages_api_update_trigger
    INSTEAD OF UPDATE ON project_pages_api
    FOR EACH ROW EXECUTE FUNCTION project_pages_api_update();

CREATE TRIGGER project_pages_api_delete_trigger
    INSTEAD OF DELETE ON project_pages_api
    FOR EACH ROW EXECUTE FUNCTION project_pages_api_delete();

-- =============================================================================
-- STEP 3: UPDATE FOREIGN KEY CONSTRAINTS
-- =============================================================================

-- Update the foreign key constraint to point to the view (if possible) or normalized table
ALTER TABLE paper_project_pages DROP CONSTRAINT IF EXISTS fk_paper_project_pages_project_page_id;

-- Point to the normalized table
ALTER TABLE paper_project_pages
ADD CONSTRAINT fk_paper_project_pages_project_page_id
    FOREIGN KEY (project_page_id) REFERENCES project_pages_normalized(id) ON DELETE CASCADE;

-- =============================================================================
-- STEP 4: CREATE INDEXES FOR PERFORMANCE
-- =============================================================================

-- Ensure indexes exist on the normalized table
CREATE INDEX IF NOT EXISTS idx_project_pages_normalized_url ON project_pages_normalized(url);
CREATE INDEX IF NOT EXISTS idx_project_pages_normalized_source ON project_pages_normalized(source);
CREATE INDEX IF NOT EXISTS idx_project_pages_normalized_is_official ON project_pages_normalized(is_official);

-- =============================================================================
-- STEP 5: VERIFICATION
-- =============================================================================

-- Show current state
SELECT
    'DATABASE SETUP COMPLETE' as status,
    (SELECT COUNT(*) FROM project_pages) as original_project_pages,
    (SELECT COUNT(*) FROM project_pages_normalized) as normalized_project_pages,
    (SELECT COUNT(*) FROM project_pages_api) as api_view_project_pages,
    (SELECT COUNT(*) FROM paper_project_pages) as total_relationships;

-- Test the view works
SELECT 'VIEW TEST' as test, COUNT(*) as count FROM project_pages_api LIMIT 1;

-- Test the relationships work
SELECT 'RELATIONSHIP TEST' as test, COUNT(*) as count
FROM paper_project_pages ppp
JOIN project_pages_normalized pp ON ppp.project_page_id = pp.id
LIMIT 1;
