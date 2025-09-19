-- PostgreSQL Authors Tables Setup for PapersWithCode
-- Creates authors and paper_authors tables with proper relationships and indexes

-- Drop tables if they exist (for fresh setup)
DROP TABLE IF EXISTS paper_authors CASCADE;
DROP TABLE IF EXISTS authors CASCADE;

-- AUTHORS - Author information with Hugging Face integration
CREATE TABLE authors (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,

    -- Hugging Face integration fields
    hf_username VARCHAR(255) UNIQUE,        -- Hugging Face username (e.g., "roadjiang", "yzli")
    hf_id VARCHAR(50) UNIQUE,               -- Hugging Face internal ID from API
    hf_avatar_url VARCHAR(500),             -- Hugging Face avatar URL
    hf_status VARCHAR(50),                  -- HF status: "claimed_verified", "admin_assigned", etc.
    hf_is_pro BOOLEAN DEFAULT FALSE,        -- Hugging Face Pro status

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT authors_name_not_empty CHECK (
        LENGTH(TRIM(name)) > 0
    )
);

-- PAPER_AUTHORS - Junction table for many-to-many relationship between papers and authors
CREATE TABLE paper_authors (
    paper_id BIGINT NOT NULL,
    author_id BIGINT NOT NULL,
    author_order INTEGER DEFAULT 1,         -- Order of author in paper (1st author, 2nd author, etc.)

    -- Primary key is composite
    PRIMARY KEY (paper_id, author_id),

    -- Foreign key constraints
    CONSTRAINT fk_paper_authors_paper_id
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    CONSTRAINT fk_paper_authors_author_id
        FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE,

    -- Ensure author_order is positive
    CONSTRAINT paper_authors_order_positive CHECK (author_order > 0)
);

-- Indexes for Performance
-- Authors table indexes
CREATE INDEX idx_authors_name ON authors(name);
CREATE INDEX idx_authors_hf_username ON authors(hf_username) WHERE hf_username IS NOT NULL;
CREATE INDEX idx_authors_hf_id ON authors(hf_id) WHERE hf_id IS NOT NULL;
CREATE INDEX idx_authors_created_at ON authors(created_at);

-- Full-text search index for author names
CREATE INDEX idx_authors_name_search ON authors
    USING gin(to_tsvector('english', name));

-- Paper_authors junction table indexes
CREATE INDEX idx_paper_authors_paper_id ON paper_authors(paper_id);
CREATE INDEX idx_paper_authors_author_id ON paper_authors(author_id);
CREATE INDEX idx_paper_authors_order ON paper_authors(author_order);

-- Composite index for efficient author lookups by paper
CREATE INDEX idx_paper_authors_paper_order ON paper_authors(paper_id, author_order);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_authors_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for authors table
CREATE TRIGGER update_authors_updated_at
    BEFORE UPDATE ON authors
    FOR EACH ROW
    EXECUTE FUNCTION update_authors_updated_at_column();

-- Create useful views
-- View for papers with their authors (ordered by author_order)
CREATE VIEW papers_with_authors AS
SELECT
    p.id as paper_id,
    p.title,
    p.arxiv_id,
    p.date_published,
    STRING_AGG(
        a.name,
        ', ' ORDER BY pa.author_order
    ) as authors,
    COUNT(a.id) as author_count
FROM papers p
LEFT JOIN paper_authors pa ON p.id = pa.paper_id
LEFT JOIN authors a ON pa.author_id = a.id
GROUP BY p.id, p.title, p.arxiv_id, p.date_published;

-- View for authors with their paper count
CREATE VIEW authors_with_paper_count AS
SELECT
    a.id,
    a.name,
    a.hf_username,
    a.hf_is_pro,
    COUNT(pa.paper_id) as paper_count,
    a.created_at,
    a.updated_at
FROM authors a
LEFT JOIN paper_authors pa ON a.id = pa.author_id
GROUP BY a.id, a.name, a.hf_username, a.hf_is_pro, a.created_at, a.updated_at;

-- Add helpful comments for documentation
COMMENT ON TABLE authors IS 'Authors with Hugging Face integration support';
COMMENT ON TABLE paper_authors IS 'Junction table linking papers to authors with ordering';
COMMENT ON COLUMN authors.hf_username IS 'Hugging Face username for profile integration';
COMMENT ON COLUMN authors.hf_id IS 'Hugging Face internal ID from API';
COMMENT ON COLUMN authors.hf_status IS 'Hugging Face verification status';
COMMENT ON COLUMN paper_authors.author_order IS 'Order of author in paper (1=first author, 2=second, etc.)';
COMMENT ON VIEW papers_with_authors IS 'Papers with comma-separated author list ordered by author_order';
COMMENT ON VIEW authors_with_paper_count IS 'Authors with their total paper count';

-- Grant permissions (adjust user as needed)
-- GRANT ALL PRIVILEGES ON TABLE authors TO paperswithcode_user;
-- GRANT ALL PRIVILEGES ON TABLE paper_authors TO paperswithcode_user;
-- GRANT ALL PRIVILEGES ON SEQUENCE authors_id_seq TO paperswithcode_user;

ANALYZE authors;
ANALYZE paper_authors;
