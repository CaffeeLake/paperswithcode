-- PostgreSQL database setup for PapersWithCode
-- Starting with just the Papers table - other tables will be added incrementally

-- Create database (run this manually if needed)
-- CREATE DATABASE paperswithcode;

-- Drop table if it exists (for fresh setup)
DROP TABLE IF EXISTS papers CASCADE;

-- PAPERS - Primary entity for research papers with full versioning support
CREATE TABLE papers (
    id BIGSERIAL PRIMARY KEY,               -- Separate ID maintained for performance and non-ArXiv papers
    title TEXT NOT NULL,
    abstract TEXT,
    arxiv_id VARCHAR(50) NOT NULL,          -- Base ArXiv ID (e.g., "1805.10616")
    version VARCHAR(10) DEFAULT 'v1',       -- Version (e.g., "v1", "v2", "v3")
    is_latest_version BOOLEAN DEFAULT TRUE, -- Flag for latest version of this paper
    date_published DATE,
    proceeding VARCHAR(200),
    conference VARCHAR(200),
    conference_url_abs VARCHAR(500),
    conference_url_pdf VARCHAR(500),
    citation_count INTEGER DEFAULT 0,       -- Citation count from Semantic Scholar
    semantic_scholar_id VARCHAR(100),       -- Semantic Scholar paper ID for API lookups
    citation_updated_at TIMESTAMP WITH TIME ZONE, -- Last time citation count was updated
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint: one paper can't have duplicate versions
    UNIQUE(arxiv_id, version)
);

-- Indexes for Performance
CREATE INDEX idx_papers_title_search ON papers USING gin(to_tsvector('english', title));
CREATE INDEX idx_papers_abstract_search ON papers USING gin(to_tsvector('english', abstract));
CREATE INDEX idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX idx_papers_date_published ON papers(date_published DESC);
CREATE INDEX idx_papers_conference ON papers(conference);
CREATE INDEX idx_papers_version ON papers(version);
CREATE INDEX idx_papers_latest_version ON papers(is_latest_version);
CREATE INDEX idx_papers_citation_count ON papers(citation_count DESC);
CREATE INDEX idx_papers_semantic_scholar_id ON papers(semantic_scholar_id);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for papers table
CREATE TRIGGER update_papers_updated_at
    BEFORE UPDATE ON papers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create view for latest paper versions only
CREATE VIEW latest_papers AS
SELECT * FROM papers WHERE is_latest_version = TRUE;

-- Add comments for documentation
COMMENT ON TABLE papers IS 'Research papers with full ArXiv versioning support';
COMMENT ON COLUMN papers.arxiv_id IS 'Base ArXiv ID without version (e.g., "1805.10616")';
COMMENT ON COLUMN papers.version IS 'ArXiv version (e.g., "v1", "v2", "v3")';
COMMENT ON COLUMN papers.is_latest_version IS 'Flag indicating if this is the latest version of the paper';
COMMENT ON COLUMN papers.citation_count IS 'Number of citations from Semantic Scholar API';
COMMENT ON COLUMN papers.semantic_scholar_id IS 'Semantic Scholar paper ID for API lookups';
COMMENT ON COLUMN papers.citation_updated_at IS 'Timestamp when citation count was last updated';