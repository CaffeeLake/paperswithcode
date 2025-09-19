-- Add REPOSITORIES and PROJECT_PAGES tables to PapersWithCode database
-- These tables store GitHub repositories and project pages linked to papers

-- REPOSITORIES - GitHub repositories linked to papers
CREATE TABLE IF NOT EXISTS repositories (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    owner VARCHAR(255),
    name VARCHAR(255),
    num_stars INTEGER DEFAULT 0,
    is_official BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- PROJECT_PAGES - Project pages showcasing paper work (demo sites, project websites)
CREATE TABLE IF NOT EXISTS project_pages (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    is_official BOOLEAN DEFAULT FALSE, -- Created by the paper authors
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_repositories_paper_id ON repositories(paper_id);
CREATE INDEX IF NOT EXISTS idx_repositories_url ON repositories(url);
CREATE INDEX IF NOT EXISTS idx_repositories_stars ON repositories(num_stars DESC);
CREATE INDEX IF NOT EXISTS idx_repositories_owner ON repositories(owner);
CREATE INDEX IF NOT EXISTS idx_repositories_name ON repositories(name);

CREATE INDEX IF NOT EXISTS idx_project_pages_paper_id ON project_pages(paper_id);
CREATE INDEX IF NOT EXISTS idx_project_pages_url ON project_pages(url);

-- Add triggers for updated_at columns (reusing the function from papers table)
CREATE TRIGGER update_repositories_updated_at
    BEFORE UPDATE ON repositories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_project_pages_updated_at
    BEFORE UPDATE ON project_pages
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE repositories IS 'GitHub repositories linked to papers';
COMMENT ON COLUMN repositories.paper_id IS 'Foreign key reference to papers table';
COMMENT ON COLUMN repositories.url IS 'Full GitHub repository URL';
COMMENT ON COLUMN repositories.owner IS 'GitHub username/organization that owns the repository';
COMMENT ON COLUMN repositories.name IS 'Repository name';
COMMENT ON COLUMN repositories.num_stars IS 'Number of GitHub stars (to be populated later)';
COMMENT ON COLUMN repositories.is_official IS 'Whether this is the official repository by paper authors';

COMMENT ON TABLE project_pages IS 'Project pages showcasing paper work (demo sites, project websites)';
COMMENT ON COLUMN project_pages.paper_id IS 'Foreign key reference to papers table';
COMMENT ON COLUMN project_pages.url IS 'Full URL to project page';
COMMENT ON COLUMN project_pages.is_official IS 'Whether this is an official project page by paper authors';
