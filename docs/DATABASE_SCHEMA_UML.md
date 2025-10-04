# PapersWithCode - Database Schema & UML Design

## Overview

This document provides a comprehensive overview of the database schema for the PapersWithCode project, reflecting the current production database state as of September 2025.

This schema is based on the API client of the legacy [PapersWithCode API](https://paperswithcode-client.readthedocs.io/en/latest/api/index.html), and has been significantly extended with:
- **Hugging Face Integration**: Author profiles, usernames, and project pages
- **Citation Tracking**: Semantic Scholar API integration for real-time citation counts
- **ArXiv Category Classification**: Primary and secondary category tracking
- **Enhanced Performance**: Comprehensive indexing and materialized views
- **Repository Optimization**: Normalized repository structure with efficient CRON job processing
- **Author Ordering**: Proper first/second author tracking in publications

## Current Database Statistics
- **Core Tables**: 15 main entity tables + 6 junction tables
- **Performance Views**: 6 materialized views for optimized queries
- **Backup Tables**: 2 backup tables for data migration safety
- **Indexes**: 50+ indexes for full-text search, filtering, and performance
- **Data Scale**: Designed to handle millions of papers with real-time updates

## Entity Relationship Diagram (UML)

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│     AUTHORS     │    │      PAPERS      │    │      TASKS      │
├─────────────────┤    ├──────────────────┤    ├─────────────────┤
│ id (PK)         │    │ id (PK)          │    │ id (PK)         │
│ name            │    │ title            │    │ name            │
│ hf_username     │    │ abstract         │    │ description     │
│ hf_id           │    │ arxiv_id         │    │ slug            │
│ hf_avatar_url   │    │ version          │    │ parent_id (FK)  │
│ hf_status       │    │ is_latest_version│    │ area_id (FK)    │
│ hf_is_pro       │    │ date_published   │    │ level           │
│ created_at      │    │ proceeding       │    │ created_at      │
│ updated_at      │    │ conference       │    │ updated_at      │
└─────────────────┘    │ conference_url_abs│   └─────────────────┘
                       │ conference_url_pdf│             │
                       │ citation_count   │              │
                       │ semantic_scholar_id│            │
                       │ citation_updated_at│            │
                       │ primary_category │              │
                       │ all_categories   │              │
                       │ urls_extracted   │              │
                       │ created_at       │              │
                       │ updated_at       │              │
                       └──────────────────┘              │ (Self-referencing)
                                │                        │ Parent-Child
                                │                        ▼
                                │              ┌─────────────────┐
                                │              │      AREAS      │
                                │              ├─────────────────┤
                                │              │ id (PK)         │
                                │              │ name            │
                                │              │ description     │
                                │              │ created_at      │
                                │              │ updated_at      │
                                │              └─────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  PAPER_AUTHORS  │    │   PAPER_TASKS   │    │  PAPER_METHODS  │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ paper_id (FK)   │    │ paper_id (FK)   │    │ paper_id (FK)   │
│ author_id (FK)  │    │ task_id (FK)    │    │ method_id (FK)  │
│ author_order    │    │ PRIMARY KEY     │    │ PRIMARY KEY     │
│ PRIMARY KEY     │    │ (paper_id,      │    │ (paper_id,      │
│ (paper_id,      │    │  task_id)       │    │  method_id)     │
│  author_id)     │    └─────────────────┘    └─────────────────┘
└─────────────────┘
        │                       │                       │
        │                       │                       ▼
        │                       │              ┌─────────────────┐
        │                       │              │     METHODS     │
        │                       │              ├─────────────────┤
        │                       │              │ id (PK)         │
        │                       │              │ name            │
        │                       │              │ full_name       │
        │                       │              │ description     │
        │                       │              │ introduced_year │
        │                       │              │ source_url      │
        │                       │              │ source_title    │
        │                       │              │ code_snippet_url│
        │                       │              │ collection_name │
        │                       │              │ collection_desc │
        │                       │              │ collection_parent│
        │                       │              │ collection_area │
        │                       │              │ created_at      │
        │                       │              │ updated_at      │
        │                       │              └─────────────────┘
        │                       │
        │                       ▼
        │              ┌─────────────────┐
        │              │ PAPER_DATASETS  │
        │              ├─────────────────┤
        │              │ paper_id (FK)   │
        │              │ dataset_id (FK) │
        │              │ PRIMARY KEY     │
        │              │ (paper_id,      │
        │              │  dataset_id)    │
        │              └─────────────────┘
        │                       │
        │                       ▼
        │              ┌─────────────────┐
        │              │     DATASETS    │
        │              ├─────────────────┤
        │              │ id (PK)         │
        │              │ name            │
        │              │ full_name       │
        │              │ description     │
        │              │ url             │
        │              │ hf_url          │
        │              │ created_at      │
        │              │ updated_at      │
        │              └─────────────────┘
        │
        ▼
┌─────────────────┐           ┌──────────────────┐
│  REPOSITORIES   │           │   EVALUATIONS    │
├─────────────────┤           ├──────────────────┤
│ id (PK)         │           │ id (PK)          │
│ url (UNIQUE)    │           │ paper_id (FK)    │
│ owner           │           │ task_id (FK)     │
│ name            │           │ dataset_id (FK)  │
│ num_stars       │           │ model_name       │
│ num_stars_upd_at│           │ methodology      │
│ source          │           │ metrics (JSONB)  │
│ created_at      │           │ uses_additional  │
│ updated_at      │           │ best_rank        │
└─────────────────┘           │ external_source  │
        │                     │ created_at       │
        │                     │ updated_at       │
        │                     └──────────────────┘
        │
        ▼
┌─────────────────┐
│PAPER_REPOSITORIES│
├─────────────────┤
│ paper_id (FK)   │
│ repository_id(FK)│
│ is_official     │
│ PRIMARY KEY     │
│ (paper_id,      │
│  repository_id) │
└─────────────────┘
        │
        ▼
┌─────────────────┐
│PAPER_PROJECT_PAGES│
├─────────────────┤
│ paper_id (FK)   │
│ project_page_id │
│ is_official     │
│ source          │
│ created_at      │
│ updated_at      │
│ PRIMARY KEY     │
│ (paper_id,      │
│  project_page_id)│
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ PROJECT_PAGES   │
├─────────────────┤
│ id (PK)         │
│ url             │
│ is_official     │
│ source          │
│ created_at      │
│ updated_at      │
└─────────────────┘
```

## Table Definitions

### 1. PAPERS
**Primary entity for research papers**
```sql
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
    citation_count INTEGER DEFAULT 0,       -- Number of citations from Semantic Scholar
    semantic_scholar_id VARCHAR(100),       -- Semantic Scholar paper ID for citation tracking
    citation_updated_at TIMESTAMP WITH TIME ZONE, -- Last time citations were updated
    primary_category VARCHAR(50),           -- Primary ArXiv category (e.g., "cs.CV", "cs.LG")
    all_categories TEXT[],                  -- All ArXiv categories as array
    urls_extracted BOOLEAN DEFAULT FALSE,   -- Flag indicating if URLs have been extracted
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint: one paper can't have duplicate versions
    UNIQUE(arxiv_id, version)
);

-- Note: Full versioning support for ArXiv papers with automatic URL construction
-- Stores base arxiv_id + version separately for optimal flexibility
```

#### URL Construction Utilities
```python
from typing import Optional
from config import settings  # Your app config with DOMAIN_NAME

def get_arxiv_abs_url(arxiv_id: str, version: str = None) -> Optional[str]:
    """
    Construct ArXiv abstract URL from ArXiv ID and version.
    Handles both modern (1805.10616) and legacy (cs.DS/0610046) formats.

    Args:
        arxiv_id: Base ArXiv ID (e.g., "1805.10616")
        version: Version string (e.g., "v2", "v3") - if None, returns latest version URL
    """
    if not arxiv_id:
        return None

    if version and version != 'v1':
        return f"https://arxiv.org/abs/{arxiv_id}{version}"
    else:
        # No version returns latest version (ArXiv default behavior)
        return f"https://arxiv.org/abs/{arxiv_id}"

def get_arxiv_pdf_url(arxiv_id: str, version: str = None) -> Optional[str]:
    """
    Construct ArXiv PDF URL from ArXiv ID and version.
    Handles both modern and legacy formats.
    """
    if not arxiv_id:
        return None

    if version and version != 'v1':
        return f"https://arxiv.org/pdf/{arxiv_id}{version}.pdf"
    else:
        # No version returns latest version (ArXiv default behavior)
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

def get_paper_url(paper_id: int, arxiv_id: str = None, domain: str = "paperswithcode.ai") -> str:
    """
    Construct your platform's paper URL.
    Prefer ArXiv ID for clean URLs, fallback to database ID.
    """
    if arxiv_id:
        # Clean URL: paperswithcode.ai/papers/1805.10616
        return f"https://{domain}/papers/{arxiv_id}"
    else:
        # Fallback for non-ArXiv papers: paperswithcode.ai/papers/12345
        return f"https://{domain}/papers/{paper_id}"

def get_paper_slug_from_title(title: str) -> str:
    """
    Alternative: Generate URL-friendly slug from paper title.
    For even cleaner URLs like: paperswithcode.ai/papers/dynamic-network-model-from-partial
    """
    import re
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')

# Usage in FastAPI endpoints:
def get_paper_with_urls(paper: Paper, request: Request) -> dict:
    domain = request.url.hostname  # Or use settings.DOMAIN_NAME

    return {
        "id": paper.id,
        "title": paper.title,
        "arxiv_id": paper.arxiv_id,
        "version": paper.version,
        "is_latest_version": paper.is_latest_version,
        "url_abs": get_arxiv_abs_url(paper.arxiv_id, paper.version),
        "url_pdf": get_arxiv_pdf_url(paper.arxiv_id, paper.version),
        "paper_url": get_paper_url(paper.id, paper.arxiv_id, domain),
        # ... other fields
    }

# Query helpers for paper versions:
def get_latest_paper_version(db: Session, arxiv_id: str) -> Optional[Paper]:
    """Get the latest version of a paper by ArXiv ID."""
    return db.query(Paper).filter(
        Paper.arxiv_id == arxiv_id,
        Paper.is_latest_version == True
    ).first()

def get_all_paper_versions(db: Session, arxiv_id: str) -> List[Paper]:
    """Get all versions of a paper, ordered by version."""
    return db.query(Paper).filter(
        Paper.arxiv_id == arxiv_id
    ).order_by(Paper.version).all()

def create_new_paper_version(db: Session, arxiv_id: str, new_version: str, **paper_data) -> Paper:
    """Create a new version of an existing paper."""
    # Mark all previous versions as not latest
    db.query(Paper).filter(Paper.arxiv_id == arxiv_id).update({"is_latest_version": False})

    # Create new version
    new_paper = Paper(
        arxiv_id=arxiv_id,
        version=new_version,
        is_latest_version=True,
        **paper_data
    )
    db.add(new_paper)
    db.commit()
    return new_paper

# Version browsing and comparison helpers:
def get_paper_version_history(db: Session, arxiv_id: str) -> List[dict]:
    """Get version history with metadata for UI display."""
    versions = db.query(Paper).filter(
        Paper.arxiv_id == arxiv_id
    ).order_by(Paper.version.desc()).all()

    return [
        {
            "id": paper.id,
            "version": paper.version,
            "title": paper.title,
            "is_latest": paper.is_latest_version,
            "date_published": paper.date_published,
            "created_at": paper.created_at,
            "abstract_preview": paper.abstract[:200] + "..." if paper.abstract and len(paper.abstract) > 200 else paper.abstract,
            "url_abs": get_arxiv_abs_url(paper.arxiv_id, paper.version),
            "paper_url": get_paper_url(paper.id, paper.arxiv_id)
        }
        for paper in versions
    ]

def get_version_changes_summary(db: Session, arxiv_id: str, from_version: str, to_version: str) -> dict:
    """Compare two versions and return what changed (for UI display)."""
    old_paper = db.query(Paper).filter(
        Paper.arxiv_id == arxiv_id,
        Paper.version == from_version
    ).first()

    new_paper = db.query(Paper).filter(
        Paper.arxiv_id == arxiv_id,
        Paper.version == to_version
    ).first()

    if not old_paper or not new_paper:
        return None

    changes = {
        "title_changed": old_paper.title != new_paper.title,
        "abstract_changed": old_paper.abstract != new_paper.abstract,
        "date_changed": old_paper.date_published != new_paper.date_published,
        "from_version": from_version,
        "to_version": to_version,
        "time_between_versions": (new_paper.created_at - old_paper.created_at).days if new_paper.created_at and old_paper.created_at else None
    }

    return changes
```

#### Example FastAPI Endpoints for Version Browsing:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/papers/{arxiv_id}")
async def get_paper(arxiv_id: str, version: str = None, db: Session = Depends(get_db)):
    """
    Get paper by ArXiv ID.
    - If version is specified: get that specific version
    - If no version: get latest version
    """
    if version:
        paper = db.query(Paper).filter(
            Paper.arxiv_id == arxiv_id,
            Paper.version == version
        ).first()
    else:
        paper = get_latest_paper_version(db, arxiv_id)

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    return get_paper_with_urls(paper, request)

@router.get("/papers/{arxiv_id}/versions")
async def get_paper_versions(arxiv_id: str, db: Session = Depends(get_db)):
    """Get all versions of a paper with history metadata."""
    versions = get_paper_version_history(db, arxiv_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Paper not found")

    return {
        "arxiv_id": arxiv_id,
        "total_versions": len(versions),
        "versions": versions
    }

@router.get("/papers/{arxiv_id}/versions/{from_version}/compare/{to_version}")
async def compare_versions(
    arxiv_id: str,
    from_version: str,
    to_version: str,
    db: Session = Depends(get_db)
):
    """Compare two versions of a paper."""
    comparison = get_version_changes_summary(db, arxiv_id, from_version, to_version)
    if not comparison:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    return comparison
```

#### Frontend URL Routing Examples:
```typescript
// Your frontend routes for version browsing
const routes = [
  // Latest version (default)
  { path: "/papers/:arxivId", component: PaperDetail },

  // Specific version
  { path: "/papers/:arxivId/v/:version", component: PaperDetail },

  // Version history page
  { path: "/papers/:arxivId/versions", component: PaperVersions },

  // Version comparison
  { path: "/papers/:arxivId/compare/:fromVersion/:toVersion", component: VersionCompare }
];

// Example URLs:
// paperswithcode.ai/papers/1805.10616        <- Latest version
// paperswithcode.ai/papers/1805.10616/v/v2   <- Version 2
// paperswithcode.ai/papers/1805.10616/versions <- All versions
// paperswithcode.ai/papers/1805.10616/compare/v1/v4 <- Compare v1 to v4
```

#### Benefits of This Versioning Approach:
- **Complete Version Tracking**: Store all versions of papers (v1, v2, v3, etc.) as separate rows
- **Latest Version Management**: `is_latest_version` flag for quick latest version queries
- **Flexible URL Construction**: Generate both versioned and unversioned ArXiv URLs as needed
- **Data Integrity**: `UNIQUE(arxiv_id, version)` prevents duplicate versions
- **Historical Preservation**: Keep track of paper evolution over time
- **Efficient Queries**: Easy to find all versions or just the latest of any paper
- **ArXiv Compatibility**: Matches ArXiv's own versioning system perfectly
- **Storage Efficiency**: No redundant URL storage, all constructed on-demand
- **Update Workflow**: Simple process for adding new versions when authors update papers
- **User Experience**: Easy version browsing, comparison, and historical tracking
- **Research Value**: Scholars can see how papers evolve and cite specific versions
- **SEO Friendly**: Clean URLs for both latest and specific versions

### 2. AUTHORS
**Author information with Hugging Face integration**
```sql
CREATE TABLE authors (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,      -- Full author name (e.g., "Geoffrey Hinton", "Yann LeCun")
    hf_username VARCHAR(255) UNIQUE, -- Hugging Face username (e.g., "roadjiang", "yzli")
    hf_id VARCHAR(50) UNIQUE,        -- Hugging Face internal ID from API
    hf_avatar_url VARCHAR(500),      -- Hugging Face avatar URL
    hf_status VARCHAR(50),           -- HF status: "claimed_verified", "admin_assigned", etc.
    hf_is_pro BOOLEAN DEFAULT FALSE, -- Hugging Face Pro status
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 3. AREAS
**Research areas (Computer Vision, NLP, etc.) - Sourced from PapersWithCode API**
```sql
CREATE TABLE areas (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 4. TASKS
**AI tasks with hierarchical structure**

Tasks represent specific AI/ML problems and capabilities, organized hierarchically within research areas. Tasks are fully integrated with the API and support advanced queries including:
- Hierarchical parent-child relationships
- Area-based organization
- Paper count aggregation
- Full-text search across task names and descriptions

**Current Task Coverage** (October 2025):
- **Computer Vision**: Image Classification, Object Detection
- **Robotics**: Vision Language Action Models
- **Natural Language Processing**: Language Modeling, Machine Translation
- **General Tasks**: Vision Language Models, Computer Use Agents

```sql
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
```

**API Integration** (October 2025):
- ✅ **Service Layer**: `TaskService` with full CRUD operations
- ✅ **API Endpoints**:
  - `GET /api/v1/tasks/` - List tasks with pagination/filtering
  - `GET /api/v1/tasks/{task_id}` - Get specific task
  - `GET /api/v1/tasks/{task_id}/children` - Get subtasks
  - `GET /api/v1/tasks/{task_id}/parents` - Get parent hierarchy
- ✅ **Filtering**: By area, parent task, hierarchy level, search query
- ✅ **Hierarchical Queries**: Navigate task hierarchies efficiently

### 5. METHODS
**AI methods and techniques**
```sql
CREATE TABLE methods (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    full_name VARCHAR(500),
    description TEXT,
    introduced_year INTEGER,
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
```

### 6. DATASETS
**Benchmark datasets**
```sql
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
```

### 7. REPOSITORIES
**GitHub repositories (normalized, no direct paper relationship)**
```sql
CREATE TABLE repositories (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR(500) NOT NULL UNIQUE,       -- Unique repository URL
    owner VARCHAR(255),
    name VARCHAR(255),
    num_stars INTEGER DEFAULT 0,
    source VARCHAR(50) DEFAULT 'unknown',   -- Source of the repository data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    num_stars_updated_at TIMESTAMP WITH TIME ZONE -- For CRON job tracking
);

-- Note: is_official is now stored in the paper_repositories junction table
-- since repositories can have different official status for different papers
```

### 7b. PAPER_REPOSITORIES
**Junction table for many-to-many relationship between papers and repositories**
```sql
CREATE TABLE paper_repositories (
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    repository_id BIGINT REFERENCES repositories(id) ON DELETE CASCADE,
    is_official BOOLEAN DEFAULT FALSE,      -- Whether this repository is official for this specific paper
    PRIMARY KEY (paper_id, repository_id)
);
```

### 8. PROJECT_PAGES
**Project pages showcasing paper work (e.g., demo sites, project websites) - normalized without direct paper reference**
```sql
CREATE TABLE project_pages (
    id BIGSERIAL PRIMARY KEY,
    url VARCHAR(500) NOT NULL,
    is_official BOOLEAN DEFAULT FALSE, -- Whether this is an official project page by paper authors
    source VARCHAR(50) DEFAULT 'unknown',   -- Source of the project page data (pwc_archive, ai_extraction, manual, etc.)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 8b. PAPER_PROJECT_PAGES
**Junction table for many-to-many relationship between papers and project pages (simplified to only contain IDs)**
```sql
CREATE TABLE paper_project_pages (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    project_page_id BIGINT NOT NULL REFERENCES project_pages(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, project_page_id)
);
```

### 9. EVALUATIONS
**Benchmark evaluation results**
```sql
CREATE TABLE evaluations (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    dataset_id BIGINT REFERENCES datasets(id) ON DELETE CASCADE,
    model_name VARCHAR(255),
    methodology TEXT,
    metrics JSONB NOT NULL,
    uses_additional_data BOOLEAN DEFAULT FALSE,
    best_rank INTEGER,
    best_metric VARCHAR(100),
    evaluated_on DATE,
    external_source_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## Views and Materialized Views

The database includes several views for optimized queries and reporting:

### Performance Views
- **`authors_with_paper_count`**: Authors with their paper counts for efficient listing
- **`papers_with_authors`**: Papers with concatenated author names for search and display
- **`cs_papers`**: Computer Science papers only (filtered by primary_category starting with 'cs.')
- **`latest_papers`**: Only the latest versions of papers (is_latest_version = true)

### API Views
- **`project_pages_view`**: Simplified project pages view for API responses
- **`project_pages_api`**: API-optimized project pages data

### Backup Tables
- **`repositories_backup`**: Backup of repository data before normalization
- **`repositorybackup`**: Additional repository backup with extended metadata

## Junction Tables (Many-to-Many Relationships)

**Note**: While the SQL definitions below show foreign key constraints for clarity, some junction tables in the current database may not have all foreign key constraints explicitly defined at the database level. The relationships are maintained through application logic and proper indexing.

### 10. PAPER_AUTHORS
```sql
CREATE TABLE paper_authors (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    author_order INTEGER DEFAULT 1,  -- Order of author in paper (1=first author, 2=second, etc.)
    PRIMARY KEY (paper_id, author_id)
);
```

### 11. PAPER_TASKS
```sql
CREATE TABLE paper_tasks (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, task_id)
);
```

### 12. PAPER_METHODS
```sql
CREATE TABLE paper_methods (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    method_id BIGINT NOT NULL REFERENCES methods(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, method_id)
);
```

### 13. PAPER_DATASETS
```sql
CREATE TABLE paper_datasets (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    dataset_id BIGINT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, dataset_id)
);
```

### 14. PAPER_REPOSITORIES
```sql
CREATE TABLE paper_repositories (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    is_official BOOLEAN DEFAULT FALSE,      -- Whether this repository is official for this specific paper
    PRIMARY KEY (paper_id, repository_id)
);
```

### 15. PAPER_PROJECT_PAGES
```sql
CREATE TABLE paper_project_pages (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    project_page_id BIGINT NOT NULL REFERENCES project_pages(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, project_page_id)
);
```

## Key Relationships

### One-to-Many
- `areas` → `tasks` (area can have many tasks)
- `tasks` → `tasks` (hierarchical: parent task can have many child tasks)
- `papers` → `evaluations` (paper can have multiple benchmark results)
- `tasks` → `evaluations` (task can be evaluated with multiple papers)
- `datasets` → `evaluations` (dataset can be used in multiple evaluations)

### Many-to-Many
- `papers` ↔ `authors` (via paper_authors)
- `papers` ↔ `tasks` (via paper_tasks)
- `papers` ↔ `methods` (via paper_methods)
- `papers` ↔ `datasets` (via paper_datasets)
- `papers` ↔ `repositories` (via paper_repositories) **[OPTIMIZED]**
- `papers` ↔ `project_pages` (via paper_project_pages) **[NORMALIZED]**

## Indexes for Performance

```sql
-- Full-text search indexes
CREATE INDEX idx_papers_title_search ON papers USING gin(to_tsvector('english', title));
CREATE INDEX idx_papers_abstract_search ON papers USING gin(to_tsvector('english', abstract));

-- Paper lookup and filtering indexes
CREATE INDEX idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX idx_papers_date_published ON papers(date_published DESC);
CREATE INDEX idx_papers_conference ON papers(conference);
CREATE INDEX idx_papers_latest_version ON papers(is_latest_version);
CREATE INDEX idx_papers_version ON papers(version);
CREATE INDEX idx_papers_citation_count ON papers(citation_count DESC);
CREATE INDEX idx_papers_primary_category ON papers(primary_category);
CREATE INDEX idx_papers_semantic_scholar_id ON papers(semantic_scholar_id);
CREATE INDEX idx_papers_urls_extracted ON papers(urls_extracted);
CREATE INDEX idx_papers_cs_only ON papers(primary_category) WHERE primary_category LIKE 'cs.%';

-- Hierarchical task indexes
CREATE INDEX idx_tasks_parent_id ON tasks(parent_id);
CREATE INDEX idx_tasks_area_id ON tasks(area_id);
CREATE INDEX idx_tasks_slug ON tasks(slug);

-- Author indexes for Hugging Face integration
CREATE INDEX idx_authors_hf_username ON authors(hf_username) WHERE hf_username IS NOT NULL;
CREATE INDEX idx_authors_hf_id ON authors(hf_id) WHERE hf_id IS NOT NULL;
CREATE INDEX idx_authors_name ON authors(name);
CREATE INDEX idx_authors_name_search ON authors USING gin(to_tsvector('english', name));
CREATE INDEX idx_authors_created_at ON authors(created_at);

-- Junction table indexes with enhanced author ordering
CREATE INDEX idx_paper_authors_paper_id ON paper_authors(paper_id);
CREATE INDEX idx_paper_authors_author_id ON paper_authors(author_id);
CREATE INDEX idx_paper_authors_order ON paper_authors(author_order);
CREATE INDEX idx_paper_authors_paper_order ON paper_authors(paper_id, author_order);

CREATE INDEX idx_paper_tasks_paper_id ON paper_tasks(paper_id);
CREATE INDEX idx_paper_tasks_task_id ON paper_tasks(task_id);

CREATE INDEX idx_paper_methods_paper_id ON paper_methods(paper_id);
CREATE INDEX idx_paper_methods_method_id ON paper_methods(method_id);

CREATE INDEX idx_paper_datasets_paper_id ON paper_datasets(paper_id);
CREATE INDEX idx_paper_datasets_dataset_id ON paper_datasets(dataset_id);

-- Evaluation indexes
CREATE INDEX idx_evaluations_paper_task_dataset ON evaluations(paper_id, task_id, dataset_id);
CREATE INDEX idx_evaluations_metrics ON evaluations USING gin(metrics);

-- Repository indexes (optimized structure)
CREATE INDEX idx_repositories_url ON repositories(url);
CREATE INDEX idx_repositories_stars ON repositories(num_stars DESC);
CREATE INDEX idx_repositories_owner ON repositories(owner);
CREATE INDEX idx_repositories_name ON repositories(name);
CREATE INDEX idx_repositories_source ON repositories(source);
CREATE INDEX idx_repositories_num_stars_updated_at ON repositories(num_stars_updated_at);
CREATE INDEX idx_repositories_created_at ON repositories(created_at);
CREATE INDEX idx_repositories_updated_at ON repositories(updated_at);
CREATE UNIQUE INDEX idx_repositories_url_unique ON repositories(url);

-- Paper-Repository junction table indexes
CREATE INDEX idx_paper_repositories_paper_id ON paper_repositories(paper_id);
CREATE INDEX idx_paper_repositories_repository_id ON paper_repositories(repository_id);

-- Project page indexes (normalized structure)
CREATE INDEX idx_project_pages_url ON project_pages(url);
CREATE INDEX idx_project_pages_source ON project_pages(source);
CREATE INDEX idx_project_pages_is_official ON project_pages(is_official);

-- Paper-Project Page junction table indexes
CREATE INDEX idx_paper_project_pages_paper_id ON paper_project_pages(paper_id);
CREATE INDEX idx_paper_project_pages_project_page_id ON paper_project_pages(project_page_id);

-- Backup table indexes for maintenance
CREATE INDEX idx_repositorybackup_paper_id ON repositorybackup(paper_id);
CREATE INDEX idx_repositorybackup_url ON repositorybackup(url);
```

## Hugging Face Integration Strategy

### Author Name Processing Logic
Since the original PapersWithCode data contains full names as strings (e.g., "Shaofei Cai", "Alexander Kirillov"), we simply clean and normalize them:

```python
def clean_author_name(full_name: str) -> str:
    """
    Clean and normalize author name.
    Handles whitespace normalization and basic cleanup.
    """
    if not full_name or not full_name.strip():
        return "Unknown Author"

    # Clean and normalize the name
    name = full_name.strip()
    name = re.sub(r'\s+', ' ', name)  # Normalize whitespace

    return name

def enrich_author_with_hf_data(author_name: str) -> dict:
    """
    Query Hugging Face API to enrich author data.
    This would be done during migration or as a background job.
    """
    # Search HF papers for this author name
    # Extract HF profile data if available
    # Return enriched author data
    pass
```

### Hugging Face Data Enrichment Workflow
1. **Initial Migration**: Clean and normalize all author names from PapersWithCode data
2. **HF Enrichment**: Query Hugging Face API to find matching authors and populate HF fields
3. **Ongoing Sync**: Periodically sync with HF API to update author profiles and discover new papers

### Author Matching Strategy
- Match by exact full name comparison
- Use fuzzy matching for variations (initials, nicknames, different spellings)
- Manual review for ambiguous cases

## Data Migration Strategy

Based on the JSON structure analysis:

### From papers-with-abstracts.json:
- Extract paper fields: title, abstract, arxiv_id, date_published, etc.
- Parse authors array into authors table + paper_authors junction
- **Task mapping**: Map simple task strings to task IDs from the task hierarchy built below
- Parse methods array into methods table + paper_methods junction
- Handle reproduces_paper relationships

### From evaluation-tables.json:
- **Build task hierarchy**: Parse the recursive subtasks structure to create the complete task tree
- **Area assignment**: Assign top-level tasks to appropriate areas (Computer Vision, NLP, etc.)
- **Level calculation**: Set level field based on depth in hierarchy (0=top, 1=sub, 2=sub-sub, etc.)
- Extract benchmark results into evaluations table
- Create datasets from unique dataset names
- Store flexible metrics as JSONB for different evaluation types
- Link evaluations to papers via arxiv_id or paper title matching

### Task Hierarchy Building Process:
```python
def build_task_hierarchy_from_evaluation_tables():
    """
    Process evaluation-tables.json to build the complete task hierarchy.

    Example structure in JSON:
    {
      "description": "OCR description...",
      "subtasks": [
        {
          "description": "Active Learning description...",
          "subtasks": [
            {
              "description": "Active Object Detection",
              "task": "Active Object Detection",
              "subtasks": []
            }
          ],
          "task": "Active Learning"
        }
      ]
    }

    Results in database:
    - OCR (level=0, parent=null, area=Computer Vision)
      - Active Learning (level=1, parent=OCR_ID)
        - Active Object Detection (level=2, parent=Active_Learning_ID)
    """
    pass
```

## Key Features Supported

1. **Hierarchical Tasks**: Parent-child task relationships (e.g., "Computer Vision" → "Object Detection" → "Real-Time Object Detection")

2. **Flexible Metrics**: JSONB storage for different evaluation metrics (accuracy, F1, BLEU, etc.)

3. **Full-text Search**: PostgreSQL's built-in search for papers, abstracts, and methods

4. **Paper Relationships**: Support for papers that reproduce or build on other papers

5. **Repository Integration**: Link papers to their GitHub implementations with framework detection

6. **Temporal Data**: Track when papers were published and when evaluations were conducted

7. **Hugging Face Integration**: Seamless connection to HF ecosystem with author profiles, avatars, and verification status

8. **Citation Tracking**: Integration with Semantic Scholar API for real-time citation counts

9. **ArXiv Category Classification**: Primary and secondary category tracking for better organization

10. **Author Ordering**: Proper first author, second author tracking in paper_authors junction table

11. **URL Extraction Status**: Track which papers have had their URLs extracted for repository/project page discovery

12. **Performance Views**: Materialized views for common queries (authors with paper counts, CS papers only, etc.)

13. **Comprehensive Indexing**: Full-text search, category filtering, citation sorting, and temporal queries optimized

## Benefits of Hugging Face Integration

### Enhanced Author Profiles
- **Rich Author Data**: Display HF avatars, usernames, and verification status
- **Cross-Platform Discovery**: Link papers to HF model repositories and datasets
- **Professional Networking**: Connect researchers across PapersWithCode and Hugging Face

### Data Synchronization
- **Bidirectional Sync**: Discover new papers from HF API and enrich existing data
- **Real-time Updates**: Keep author profiles current with HF status changes
- **Community Integration**: Leverage HF's social features and community data

### User Experience
- **Unified Identity**: Allow users to login with HF credentials
- **Personalization**: Recommend papers based on HF activity and following
- **Seamless Workflow**: Direct links to HF models, datasets, and spaces

## Repository Optimization & CRON Job Enhancement

### 🎯 Problem Identified & Solved

The repository system had two major issues that were successfully resolved:

#### 1. Incomplete Database Migration
The repository deduplication migration was never completed, causing:
- **66,489 total repositories** in backup vs **52,447 unique URLs** (14,042 URL duplicates)
- **49,247 unique owner/name pairs** (2,385 repository duplicates)
- **Excessive API calls** (132 calls for the same repository like `mindspore-ai/models`)
- **Inefficient processing** and potential rate limiting

#### 2. Multiple URLs per Repository
Same GitHub repositories had multiple entries for different paths:
```
mindspore-ai/models - 132 different URLs:
- https://github.com/mindspore-ai/models/tree/master/official/cv/resnet
- https://github.com/mindspore-ai/models/tree/master/official/cv/vgg16
- https://github.com/mindspore-ai/models/tree/master/research/cv/EDSR
... (129 more subdirectory URLs)
```

### ✅ Solutions Implemented

#### 1. Database Deduplication & Migration
**Migration Script**: `backend/database/migration/restore_and_deduplicate.sql`
- **Restored** repositories from backup (66,489 entries)
- **Deduplicated** by URL: 66,489 → 52,447 unique repositories
- **Rebuilt** paper_repositories relationships: 66,489 relationships maintained
- **Result**: No URL duplicates, proper many-to-many structure

#### 2. Optimized CRON Job Architecture
**New Script**: `cron/hourly/update_github_stars_optimized.py`

**Before (Inefficient)**:
- 1 API call per URL
- `mindspore-ai/models`: **132 API calls** (one per subdirectory)
- Processing: Individual repository entries

**After (Optimized)**:
- 1 API call per unique owner/name combination
- `mindspore-ai/models`: **1 API call** → updates all 132 URLs
- Processing: Grouped by repository, massive efficiency gains

#### 3. Performance Improvements Achieved

| Repository | URLs | Old API Calls | New API Calls | Efficiency Gain |
|------------|------|---------------|---------------|-----------------|
| **mindspore-ai/models** | 132 | 132 | 1 | **132x faster** |
| **huggingface/transformers** | 122 | 122 | 1 | **122x faster** |
| **tensorflow/models** | 114 | 114 | 1 | **114x faster** |
| **pwc-1/Paper-9** | 110 | 110 | 1 | **110x faster** |

**Overall System Improvements**:
- **Total API calls/hour**: ~4,500 → ~500-1,000 (**4-9x reduction**)
- **Processing efficiency**: 1 URL/call → 10-100 URLs/call (**10-100x better**)
- **Memory usage**: High → Low (**Significantly reduced**)
- **Rate limit risk**: High → Very low (**Much safer**)

### 🗂️ Implementation Files

#### Essential Files Created:
1. **`cron/hourly/update_github_stars_optimized.py`** - Optimized CRON job
2. **`cron/run_github_stars_optimized.sh`** - Wrapper script
3. **`cron/crontab_optimized.txt`** - Updated crontab configuration
4. **`backend/database/migration/restore_and_deduplicate.sql`** - Database fix
5. **`cron/verify_optimization.py`** - Verification script

#### Updated SQLAlchemy Models:
**File**: `backend/models/database.py`
- **Repository model**: Removed `paper_id`, added `unique=True` for URL
- **New PaperRepository model**: Junction table with relationship metadata
- **Paper model**: Updated to use many-to-many via `secondary="paper_repositories"`

#### Updated Services:
**File**: `backend/services/repository_service_updated.py`
- **Many-to-many support**: All methods updated for new structure
- **Enhanced queries**: Optimized for normalized structure
- **Backward compatibility**: Maintains existing API contracts

### 🚀 Database Architecture Benefits

#### Storage Efficiency
- **Eliminates duplication**: Popular repositories no longer stored hundreds of times
- **Significant space savings**: 60-80% reduction in repository table redundancy
- **Consistent metadata**: Single source of truth for repository information

#### Data Integrity
- **Unique URLs**: Prevents duplicate repositories with URL variations
- **Referential integrity**: Proper foreign key constraints
- **Relationship metadata**: Tracks source and official status per paper

#### Query Performance
- **Faster repository queries**: Normalized data with better indexes
- **Efficient star updates**: Update once instead of hundreds of times
- **Better aggregations**: Easy to count papers per repository

#### CRON Job Optimization
- **API call reduction**: 4-9x fewer GitHub API calls overall
- **Grouped processing**: Process repositories by owner/name, not individual URLs
- **Memory efficiency**: Lower memory usage with grouped operations
- **Rate limit safety**: Much lower API usage prevents rate limiting

### 📊 Migration Results & Verification

#### Database State After Migration:
- ✅ **Total repositories**: 52,447 (all unique URLs)
- ✅ **URL duplicates**: 0 (was 14,042)
- ✅ **Owner/name pairs**: 49,246 unique repositories
- ✅ **Paper relationships**: 66,489 (all preserved)
- ✅ **Zero data loss**: All original relationships maintained
- ✅ **Zero orphaned records**: All relationships have referential integrity

#### CRON Job Performance:
- ✅ **Individual URLs preserved**: Each subdirectory URL remains as separate database row
- ✅ **Efficient API usage**: Only 1 GitHub API call per unique repository
- ✅ **Consistent updates**: All URLs for same repository get same star count
- ✅ **Massive efficiency**: 10-100x improvement for repositories with multiple URLs

### 🎯 Architecture Excellence

This optimization achieves the perfect balance:
- **Database integrity preserved**: Each paper can still link to specific subdirectories
- **API efficiency maximized**: Only 1 call per unique repository
- **Data consistency**: All URLs for same repo get same star count
- **Backward compatibility**: Existing code continues to work
- **Performance gains**: Dramatic reduction in API calls and processing time

The system now processes the same data with **dramatically fewer resources** while maintaining the same update frequency and data quality. Individual URLs like `https://github.com/mindspore-ai/models/tree/master/official/cv/resnet` remain as separate database rows, but the CRON job intelligently groups them for efficient GitHub API usage.

## Schema Evolution Changelog

### Major Updates (September 2025)

#### Papers Table Enhancements
- ✅ **Added `citation_count`**: Real-time citation tracking via Semantic Scholar API
- ✅ **Added `semantic_scholar_id`**: Direct integration with Semantic Scholar database
- ✅ **Added `citation_updated_at`**: Timestamp tracking for citation refresh cycles
- ✅ **Added `primary_category`**: Primary ArXiv category classification (e.g., "cs.CV", "cs.LG")
- ✅ **Added `all_categories`**: Array of all ArXiv categories for comprehensive classification
- ✅ **Added `urls_extracted`**: Flag to track URL extraction status for CRON job optimization

#### Author Relationship Improvements
- ✅ **Added `author_order`** to `paper_authors`: Proper first/second author tracking
- ✅ **Enhanced indexing**: Optimized queries for author ordering and paper listings

#### Performance & Views
- ✅ **Added materialized views**: `authors_with_paper_count`, `papers_with_authors`, `cs_papers`, `latest_papers`
- ✅ **Added API views**: `project_pages_view`, `project_pages_api` for optimized API responses
- ✅ **Comprehensive indexing**: 50+ indexes including full-text search, category filtering, citation sorting

#### Repository System Optimization
- ✅ **Normalized repository structure**: Eliminated 14,042 duplicate URLs
- ✅ **Optimized CRON jobs**: Reduced GitHub API calls by 4-9x through intelligent grouping
- ✅ **Added backup tables**: `repositories_backup`, `repositorybackup` for safe migrations

#### Data Integrity & Constraints
- ✅ **Enhanced unique constraints**: Proper URL uniqueness in repositories
- ✅ **Foreign key relationships**: Improved referential integrity across junction tables
- ✅ **Partial indexes**: Conditional indexes for better performance (e.g., HF usernames, CS papers)

### Migration Safety
- All changes maintain backward compatibility with existing frontend code
- Backup tables preserve original data during schema migrations
- Views provide optimized query paths without breaking existing API contracts

---

This schema design provides a robust, scalable foundation for the PapersWithCode backend while maintaining compatibility with the existing frontend and the original PapersWithCode data structure, enhanced with modern Hugging Face ecosystem integration, real-time citation tracking, and optimized repository storage.
