-- PostgreSQL database setup for PapersWithCode HF (Hugging Face filtered)
-- Complete schema setup for the new paperswithcode_hf database
-- Based on the existing schema but optimized for HF ArXiv papers only

-- Create database (run this manually first)
-- CREATE DATABASE paperswithcode_hf;

-- Drop tables if they exist (for fresh setup)
DROP TABLE IF EXISTS paper_authors CASCADE;
DROP TABLE IF EXISTS paper_tasks CASCADE;
DROP TABLE IF EXISTS paper_methods CASCADE;
DROP TABLE IF EXISTS paper_datasets CASCADE;
DROP TABLE IF EXISTS evaluations CASCADE;
DROP TABLE IF EXISTS repositories CASCADE;
DROP TABLE IF EXISTS project_pages CASCADE;
DROP TABLE IF EXISTS authors CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS methods CASCADE;
DROP TABLE IF EXISTS datasets CASCADE;
DROP TABLE IF EXISTS areas CASCADE;
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

    -- Citation and metadata fields
    citation_count INTEGER DEFAULT 0,       -- Citation count from Semantic Scholar
    semantic_scholar_id VARCHAR(100),       -- Semantic Scholar paper ID for API lookups
    citation_updated_at TIMESTAMP WITH TIME ZONE, -- Last time citation count was updated

    -- ArXiv category fields
    primary_category VARCHAR(50),           -- Primary arXiv category (e.g., cs.AI, eess.IV)
    all_categories TEXT[],                  -- Array of all arXiv categories for this paper

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint: one paper can't have duplicate versions
    UNIQUE(arxiv_id, version)
);

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

-- AREAS - Research areas (Computer Vision, NLP, etc.)
CREATE TABLE areas (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- TASKS - AI tasks with hierarchical structure
CREATE TABLE tasks (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    slug VARCHAR(255) UNIQUE,
    parent_id BIGINT REFERENCES tasks(id) ON DELETE SET NULL,  -- Hierarchical: OCR → Active Learning → Active Object Detection
    area_id BIGINT REFERENCES areas(id) ON DELETE SET NULL,    -- Top-level area assignment
    level INTEGER DEFAULT 0,                                   -- 0=top-level, 1=subtask, 2=sub-subtask, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- METHODS - AI methods and techniques
CREATE TABLE methods (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    full_name VARCHAR(500),
    description TEXT,
    introduced_year INTEGER,
    source_paper_id BIGINT REFERENCES papers(id) ON DELETE SET NULL,
    source_url VARCHAR(500),
    source_title VARCHAR(500),
    code_snippet_url VARCHAR(500),
    collection_name VARCHAR(255),
    collection_description TEXT,
    collection_parent VARCHAR(255),
    collection_area VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- DATASETS - Benchmark datasets
CREATE TABLE datasets (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    full_name VARCHAR(500),
    description TEXT,
    url VARCHAR(500),
    hf_url VARCHAR(500), -- Hugging Face dataset URL (e.g., "https://huggingface.co/datasets/squad")
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- REPOSITORIES - GitHub repositories (normalized, no direct paper relationship)
CREATE TABLE repositories (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR(500) NOT NULL UNIQUE,       -- Unique repository URL
    owner VARCHAR(255),
    name VARCHAR(255),
    num_stars INTEGER DEFAULT 0,
    num_stars_updated_at TIMESTAMP WITH TIME ZONE, -- For CRON job tracking
    is_official BOOLEAN DEFAULT FALSE,      -- Generally considered official
    source VARCHAR(50) DEFAULT 'unknown',  -- Source of the repository data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- PROJECT_PAGES - Project pages showcasing paper work (normalized without direct paper reference)
CREATE TABLE project_pages (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR(500) NOT NULL,
    is_official BOOLEAN DEFAULT FALSE, -- Whether this is an official project page by paper authors
    source VARCHAR(50) DEFAULT 'unknown',   -- Source of the project page data (pwc_archive, ai_extraction, manual, etc.)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- EVALUATIONS - Benchmark evaluation results
CREATE TABLE evaluations (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    dataset_id BIGINT REFERENCES datasets(id) ON DELETE CASCADE,
    model_name VARCHAR(255),
    harness VARCHAR(255),
    methodology TEXT,
    metrics JSONB NOT NULL,
    uses_additional_data BOOLEAN DEFAULT FALSE,
    best_rank INTEGER,
    best_metric VARCHAR(100),
    evaluated_on DATE,
    external_source_url VARCHAR(500),
    num_parameters BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT evaluations_num_parameters_non_negative
        CHECK (num_parameters IS NULL OR num_parameters >= 0)
);

-- Junction Tables (Many-to-Many Relationships)

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

-- PAPER_TASKS
CREATE TABLE paper_tasks (
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, task_id)
);

-- PAPER_METHODS
CREATE TABLE paper_methods (
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    method_id BIGINT REFERENCES methods(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, method_id)
);

-- PAPER_DATASETS
CREATE TABLE paper_datasets (
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    dataset_id BIGINT REFERENCES datasets(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, dataset_id)
);

-- PAPER_REPOSITORIES - Junction table for many-to-many relationship between papers and repositories
CREATE TABLE paper_repositories (
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    repository_id BIGINT REFERENCES repositories(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, repository_id)
);

-- PAPER_PROJECT_PAGES - Junction table for many-to-many relationship between papers and project pages
CREATE TABLE paper_project_pages (
    paper_id BIGINT NOT NULL,
    project_page_id BIGINT NOT NULL,

    PRIMARY KEY (paper_id, project_page_id),
    CONSTRAINT fk_paper_project_pages_paper_id
        FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    CONSTRAINT fk_paper_project_pages_project_page_id
        FOREIGN KEY (project_page_id) REFERENCES project_pages(id) ON DELETE CASCADE
);

-- Indexes for Performance

-- Papers table indexes
CREATE INDEX idx_papers_title_search ON papers USING gin(to_tsvector('english', title));
CREATE INDEX idx_papers_abstract_search ON papers USING gin(to_tsvector('english', abstract));
CREATE INDEX idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX idx_papers_date_published ON papers(date_published DESC);
CREATE INDEX idx_papers_conference ON papers(conference);
CREATE INDEX idx_papers_version ON papers(version);
CREATE INDEX idx_papers_latest_version ON papers(is_latest_version);
CREATE INDEX idx_papers_citation_count ON papers(citation_count DESC);
CREATE INDEX idx_papers_semantic_scholar_id ON papers(semantic_scholar_id);
CREATE INDEX idx_papers_primary_category ON papers(primary_category);
CREATE INDEX idx_papers_cs_only ON papers(primary_category) WHERE primary_category LIKE 'cs.%';

-- Authors table indexes
CREATE INDEX idx_authors_name ON authors(name);
CREATE INDEX idx_authors_hf_username ON authors(hf_username) WHERE hf_username IS NOT NULL;
CREATE INDEX idx_authors_hf_id ON authors(hf_id) WHERE hf_id IS NOT NULL;
CREATE INDEX idx_authors_created_at ON authors(created_at);
CREATE INDEX idx_authors_name_search ON authors USING gin(to_tsvector('english', name));

-- Hierarchical task indexes
CREATE INDEX idx_tasks_parent_id ON tasks(parent_id);
CREATE INDEX idx_tasks_area_id ON tasks(area_id);
CREATE INDEX idx_tasks_slug ON tasks(slug);

-- Paper_authors junction table indexes
CREATE INDEX idx_paper_authors_paper_id ON paper_authors(paper_id);
CREATE INDEX idx_paper_authors_author_id ON paper_authors(author_id);
CREATE INDEX idx_paper_authors_order ON paper_authors(author_order);
CREATE INDEX idx_paper_authors_paper_order ON paper_authors(paper_id, author_order);

-- Other junction table indexes
CREATE INDEX idx_paper_tasks_paper_id ON paper_tasks(paper_id);
CREATE INDEX idx_paper_tasks_task_id ON paper_tasks(task_id);
CREATE INDEX idx_paper_methods_paper_id ON paper_methods(paper_id);
CREATE INDEX idx_paper_methods_method_id ON paper_methods(method_id);
CREATE INDEX idx_methods_source_paper_id ON methods(source_paper_id);
CREATE INDEX idx_paper_datasets_paper_id ON paper_datasets(paper_id);
CREATE INDEX idx_paper_datasets_dataset_id ON paper_datasets(dataset_id);

-- Paper_repositories junction table indexes
CREATE INDEX idx_paper_repositories_paper_id ON paper_repositories(paper_id);
CREATE INDEX idx_paper_repositories_repository_id ON paper_repositories(repository_id);

-- Paper_project_pages junction table indexes
CREATE INDEX idx_paper_project_pages_paper_id ON paper_project_pages(paper_id);
CREATE INDEX idx_paper_project_pages_project_page_id ON paper_project_pages(project_page_id);

-- Evaluation indexes
CREATE INDEX idx_evaluations_paper_task_dataset ON evaluations(paper_id, task_id, dataset_id);
CREATE INDEX idx_evaluations_metrics ON evaluations USING gin(metrics);

-- Repository indexes (normalized structure)
CREATE INDEX idx_repositories_url ON repositories(url);
CREATE INDEX idx_repositories_stars ON repositories(num_stars DESC);
CREATE INDEX idx_repositories_owner ON repositories(owner);
CREATE INDEX idx_repositories_name ON repositories(name);
CREATE INDEX idx_repositories_source ON repositories(source);
CREATE INDEX idx_repositories_num_stars_updated_at ON repositories(num_stars_updated_at);
CREATE UNIQUE INDEX idx_repositories_url_unique ON repositories(url);

-- Project page indexes (normalized structure)
CREATE INDEX idx_project_pages_url ON project_pages(url);
CREATE INDEX idx_project_pages_source ON project_pages(source);
CREATE INDEX idx_project_pages_is_official ON project_pages(is_official);

-- Create functions and triggers

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for all tables with updated_at columns
CREATE TRIGGER update_papers_updated_at
    BEFORE UPDATE ON papers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_authors_updated_at
    BEFORE UPDATE ON authors
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_areas_updated_at
    BEFORE UPDATE ON areas
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_methods_updated_at
    BEFORE UPDATE ON methods
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_datasets_updated_at
    BEFORE UPDATE ON datasets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_repositories_updated_at
    BEFORE UPDATE ON repositories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_project_pages_updated_at
    BEFORE UPDATE ON project_pages
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_evaluations_updated_at
    BEFORE UPDATE ON evaluations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create useful views

-- View for latest paper versions only
CREATE VIEW latest_papers AS
SELECT * FROM papers WHERE is_latest_version = TRUE;

-- View for computer science papers only
CREATE VIEW cs_papers AS
SELECT * FROM papers
WHERE primary_category LIKE 'cs.%'
  AND is_latest_version = TRUE;

-- View for papers with their authors (ordered by author_order)
CREATE VIEW papers_with_authors AS
SELECT
    p.id as paper_id,
    p.title,
    p.arxiv_id,
    p.date_published,
    p.primary_category,
    p.citation_count,
    STRING_AGG(
        a.name,
        ', ' ORDER BY pa.author_order
    ) as authors,
    COUNT(a.id) as author_count
FROM papers p
LEFT JOIN paper_authors pa ON p.id = pa.paper_id
LEFT JOIN authors a ON pa.author_id = a.id
GROUP BY p.id, p.title, p.arxiv_id, p.date_published, p.primary_category, p.citation_count;

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

-- Add comments for documentation
COMMENT ON DATABASE paperswithcode_hf IS 'PapersWithCode database filtered to Hugging Face ArXiv papers only';
COMMENT ON TABLE papers IS 'Research papers with full ArXiv versioning support (HF filtered)';
COMMENT ON COLUMN papers.arxiv_id IS 'Base ArXiv ID without version (e.g., "1805.10616")';
COMMENT ON COLUMN papers.version IS 'ArXiv version (e.g., "v1", "v2", "v3")';
COMMENT ON COLUMN papers.is_latest_version IS 'Flag indicating if this is the latest version of the paper';
COMMENT ON COLUMN papers.citation_count IS 'Number of citations from Semantic Scholar API';
COMMENT ON COLUMN papers.semantic_scholar_id IS 'Semantic Scholar paper ID for API lookups';
COMMENT ON COLUMN papers.citation_updated_at IS 'Timestamp when citation count was last updated';
COMMENT ON COLUMN papers.primary_category IS 'Primary arXiv category (e.g., cs.AI, eess.IV)';
COMMENT ON COLUMN papers.all_categories IS 'Array of all arXiv categories for this paper';

COMMENT ON TABLE authors IS 'Authors with Hugging Face integration support';
COMMENT ON TABLE paper_authors IS 'Junction table linking papers to authors with ordering';
COMMENT ON COLUMN authors.hf_username IS 'Hugging Face username for profile integration';
COMMENT ON COLUMN authors.hf_id IS 'Hugging Face internal ID from API';
COMMENT ON COLUMN authors.hf_status IS 'Hugging Face verification status';
COMMENT ON COLUMN paper_authors.author_order IS 'Order of author in paper (1=first author, 2=second, etc.)';

COMMENT ON TABLE repositories IS 'GitHub repositories linked to papers';
COMMENT ON COLUMN repositories.source IS 'Source of the repository data: pwc_archive, ai_extraction, manual, etc.';
COMMENT ON TABLE project_pages IS 'Project pages showcasing paper work (demo sites, project websites)';
COMMENT ON COLUMN project_pages.source IS 'Source of the project page data: pwc_archive, ai_extraction, manual, etc.';

COMMENT ON VIEW latest_papers IS 'Latest versions of all papers';
COMMENT ON VIEW cs_papers IS 'Latest versions of Computer Science papers only';
COMMENT ON VIEW papers_with_authors IS 'Papers with comma-separated author list ordered by author_order';
COMMENT ON VIEW authors_with_paper_count IS 'Authors with their total paper count';

-- Analyze tables for query optimization
ANALYZE papers;
ANALYZE authors;
ANALYZE areas;
ANALYZE tasks;
ANALYZE methods;
ANALYZE datasets;
ANALYZE repositories;
ANALYZE project_pages;
ANALYZE evaluations;
ANALYZE paper_authors;
ANALYZE paper_tasks;
ANALYZE paper_methods;
ANALYZE paper_datasets;
