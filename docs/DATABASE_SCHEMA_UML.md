# PapersWithCode - Database Schema & UML Design

## Overview
This document provides a comprehensive database schema design for the PapersWithCode project, based on the analysis of:
1. Original PapersWithCode JSON data dumps (papers-with-abstracts.json & evaluation-tables.json)
2. PapersWithCode API client model structures
3. Frontend requirements from the existing React application
4. **Hugging Face API integration** for enhanced author profiles and cross-platform synchronization

## Entity Relationship Diagram (UML)

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│     AUTHORS     │    │      PAPERS      │    │      TASKS      │
├─────────────────┤    ├──────────────────┤    ├─────────────────┤
│ id (PK)         │    │ id (PK)          │    │ id (PK)         │
│ first_name      │    │ title            │    │ name            │
│ last_name       │    │ abstract         │    │ description     │
│ hf_username     │    │ arxiv_id         │    │ slug            │
│ hf_id           │    │ version          │    │ parent_id (FK)  │
│ hf_avatar_url   │    │ is_latest_version│    │ area_id (FK)    │
│ hf_status       │    │ date_published   │    │ level           │
│ hf_is_pro       │    │ proceeding       │    │ updated_at      │
│ created_at      │    │ conference       │    └─────────────────┘
│ updated_at      │    │ conference_url_abs│             │
└─────────────────┘    │ conference_url_pdf│             │
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
│ PRIMARY KEY     │    │ PRIMARY KEY     │    │ PRIMARY KEY     │
│ (paper_id,      │    │ (paper_id,      │    │ (paper_id,      │
│  author_id)     │    │  task_id)       │    │  method_id)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
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
│ paper_id (FK)   │───────────│ paper_id (FK)    │
│ url             │           │ task_id (FK)     │
│ owner           │           │ dataset_id (FK)  │
│ name            │           │ model_name       │
│ num_stars       │           │ methodology      │
│ is_official     │           │ metrics (JSONB)  │
│ created_at      │           │ uses_additional  │
│ updated_at      │           │ best_rank        │
└─────────────────┘           │ best_metric      │
        │                     │ external_source  │
        │                     │ created_at       │
        │                     │ updated_at       │
        │                     └──────────────────┘
        │
        ▼
┌─────────────────┐
│ PROJECT_PAGES   │
├─────────────────┤
│ id (PK)         │
│ paper_id (FK)   │
│ url             │
│ is_official     │
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
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
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
**AI tasks with hierarchical structure - Built from evaluation-tables.json**
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
**GitHub repositories linked to papers**
```sql
CREATE TABLE repositories (
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
```

### 8. PROJECT_PAGES
**Project pages showcasing paper work (e.g., demo sites, project websites)**
```sql
CREATE TABLE project_pages (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    is_official BOOLEAN DEFAULT FALSE, -- Created by the paper authors
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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

## Junction Tables (Many-to-Many Relationships)

### 10. PAPER_AUTHORS
```sql
CREATE TABLE paper_authors (
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    author_id BIGINT REFERENCES authors(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, author_id)
);
```

### 11. PAPER_TASKS
```sql
CREATE TABLE paper_tasks (
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, task_id)
);
```

### 12. PAPER_METHODS
```sql
CREATE TABLE paper_methods (
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    method_id BIGINT REFERENCES methods(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, method_id)
);
```

### 13. PAPER_DATASETS
```sql
CREATE TABLE paper_datasets (
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    dataset_id BIGINT REFERENCES datasets(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, dataset_id)
);
```

## Key Relationships

### One-to-Many
- `areas` → `tasks` (area can have many tasks)
- `tasks` → `tasks` (hierarchical: parent task can have many child tasks)
- `papers` → `repositories` (paper can have multiple GitHub repos)
- `papers` → `evaluations` (paper can have multiple benchmark results)
- `tasks` → `evaluations` (task can be evaluated with multiple papers)
- `datasets` → `evaluations` (dataset can be used in multiple evaluations)

### Many-to-Many
- `papers` ↔ `authors` (via paper_authors)
- `papers` ↔ `tasks` (via paper_tasks)
- `papers` ↔ `methods` (via paper_methods)
- `papers` ↔ `datasets` (via paper_datasets)

## Indexes for Performance

```sql
-- Full-text search indexes
CREATE INDEX idx_papers_title_search ON papers USING gin(to_tsvector('english', title));
CREATE INDEX idx_papers_abstract_search ON papers USING gin(to_tsvector('english', abstract));

-- Common lookup indexes
CREATE INDEX idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX idx_papers_date_published ON papers(date_published DESC);
CREATE INDEX idx_papers_conference ON papers(conference);

-- Hierarchical task indexes
CREATE INDEX idx_tasks_parent_id ON tasks(parent_id);
CREATE INDEX idx_tasks_area_id ON tasks(area_id);

-- Author indexes for Hugging Face integration
CREATE INDEX idx_authors_hf_username ON authors(hf_username);
CREATE INDEX idx_authors_hf_id ON authors(hf_id);
CREATE INDEX idx_authors_name_search ON authors(first_name, last_name);

-- Junction table indexes
CREATE INDEX idx_paper_authors_paper_id ON paper_authors(paper_id);
CREATE INDEX idx_paper_authors_author_id ON paper_authors(author_id);
CREATE INDEX idx_paper_tasks_paper_id ON paper_tasks(paper_id);
CREATE INDEX idx_paper_tasks_task_id ON paper_tasks(task_id);

-- Evaluation indexes
CREATE INDEX idx_evaluations_paper_task_dataset ON evaluations(paper_id, task_id, dataset_id);
CREATE INDEX idx_evaluations_metrics ON evaluations USING gin(metrics);

-- Repository indexes
CREATE INDEX idx_repositories_paper_id ON repositories(paper_id);
CREATE INDEX idx_repositories_stars ON repositories(num_stars DESC);

-- Project page indexes
CREATE INDEX idx_project_pages_paper_id ON project_pages(paper_id);
```

## Hugging Face Integration Strategy

### Author Name Parsing Logic
Since the original PapersWithCode data contains full names as strings (e.g., "Shaofei Cai", "Alexander Kirillov"), we need to parse these into first_name and last_name:

```python
def parse_author_name(full_name: str) -> tuple[str, str]:
    """
    Parse full name into first_name and last_name.
    Handles common academic name patterns.
    """
    parts = full_name.strip().split()

    if len(parts) == 1:
        return parts[0], ""
    elif len(parts) == 2:
        return parts[0], parts[1]
    else:
        # For names with middle names/initials, take first as first_name, rest as last_name
        return parts[0], " ".join(parts[1:])

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
1. **Initial Migration**: Parse all author names from PapersWithCode data into first_name/last_name
2. **HF Enrichment**: Query Hugging Face API to find matching authors and populate HF fields
3. **Ongoing Sync**: Periodically sync with HF API to update author profiles and discover new papers

### Author Matching Strategy
- Match by exact full name reconstruction (`first_name + " " + last_name`)
- Use fuzzy matching for variations (initials, nicknames)
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

This schema design provides a robust foundation for the PapersWithCode backend while maintaining compatibility with the existing frontend and the original PapersWithCode data structure, enhanced with modern Hugging Face ecosystem integration.