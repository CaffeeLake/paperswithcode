# PapersWithCode API Expansion Plan

## Executive Summary

This document outlines the systematic expansion of the PapersWithCode API from the current Papers-only endpoints to a comprehensive API that replicates and enhances the original PapersWithCode functionality. The expansion follows the legacy `paperswithcode-client` structure while adding modern enhancements.

## Current State Analysis

### Existing API Endpoints (9 total)
```
GET  /api/v1/papers/                           # Get papers with pagination and filtering
GET  /api/v1/papers/search                     # Search papers with citation-based ranking
GET  /api/v1/papers/recent                     # Get recent papers
GET  /api/v1/papers/stats                      # Get paper statistics
GET  /api/v1/papers/{paper_id}                 # Get paper by database ID
GET  /api/v1/papers/arxiv/{arxiv_id}           # Get paper by ArXiv ID
GET  /api/v1/papers/arxiv/{arxiv_id}/versions  # Get all versions of a paper
GET  /api/v1/papers/arxiv/{arxiv_id}/versions/{from_version}/compare/{to_version}  # Compare versions
POST /api/v1/papers/update-citations           # Update citation counts from Semantic Scholar
GET  /api/v1/papers (Legacy)                   # Legacy compatibility endpoint
```

### Database Tables Available
Based on your database schema, we have the following tables ready for API expansion:
- `papers` ✅ (implemented)
- `paper_authors` ✅ (ready for Authors API)
- `paper_tasks` ✅ (ready for Tasks API)
- `paper_methods` ✅ (ready for Methods API)
- `paper_datasets` ✅ (ready for Datasets API)
- `paper_repositories` ✅ (ready for Repositories API)
- `tasks`, `areas` ✅ (ready for hierarchical task structure)
- `methods`, `datasets`, `repositories` ✅ (ready for individual entity APIs)
- `evaluation_tables`, `metrics`, `results` ✅ (ready for Evaluations API)

## API Expansion Phases

### Phase 1: Core Entity Endpoints (Priority: HIGH)
**Timeline: 1-2 weeks**
**Dependencies: Database tables already exist**

#### 1.1 Repositories & Project Pages API (PRIORITIZED)
```
GET  /api/v1/repositories/                           # List repositories
GET  /api/v1/repositories/{repository_id}            # Get specific repository
GET  /api/v1/repositories/{owner}                    # List repos by owner
GET  /api/v1/repositories/{owner}/{name}             # Get specific repository by owner/name
GET  /api/v1/project-pages/                          # List project pages
GET  /api/v1/project-pages/{page_id}                 # Get specific project page
GET  /api/v1/papers/{paper_id}/repositories          # Get repositories for paper
GET  /api/v1/papers/{paper_id}/project-pages         # Get project pages for paper
```

**Implementation Details:**
- **Database Query**: Direct queries on `repositories` and `project_pages` tables
- **Filtering**: By owner, stars, official status, paper association
- **Sorting**: By stars, creation date, official status
- **GitHub Integration**: Support for fetching repository metadata (stars, etc.)
- **Response Model**: `Repository`, `Repositories`, `ProjectPage`, `ProjectPages`

#### 1.2 Authors API
```
GET  /api/v1/authors/                    # List authors with pagination/filtering
GET  /api/v1/authors/{author_id}         # Get specific author details
GET  /api/v1/authors/{author_id}/papers  # Get papers by author
```

**Implementation Details:**
- **Database Query**: Join `authors` with `paper_authors` and `papers`
- **Filtering**: By name, affiliation, paper count
- **Sorting**: By paper count, recent activity, alphabetical
- **Response Model**: `Author`, `Authors` (paginated)

### Phase 2: Extended Entity Endpoints (Priority: MEDIUM)
**Timeline: 2-3 weeks**
**Dependencies: Phase 1 completion**

#### 2.1 Tasks API (MOVED FROM PHASE 1)
```
GET  /api/v1/tasks/                      # List all tasks with hierarchy
GET  /api/v1/tasks/{task_id}             # Get specific task details
GET  /api/v1/tasks/{task_id}/papers      # Get papers for task
GET  /api/v1/tasks/{task_id}/children    # Get subtasks
GET  /api/v1/tasks/{task_id}/parents     # Get parent tasks
GET  /api/v1/areas/                      # List research areas
GET  /api/v1/areas/{area_id}             # Get specific area
GET  /api/v1/areas/{area_id}/tasks       # Get tasks in area
```

**Implementation Details:**
- **Database Query**: Self-referencing joins for task hierarchy
- **Filtering**: By area, level, paper count
- **Hierarchy**: Support parent-child relationships
- **Response Model**: `Task`, `Tasks`, `Area`, `Areas`

#### 2.2 Methods API (MOVED FROM PHASE 1)
```
GET  /api/v1/methods/                    # List all methods
GET  /api/v1/methods/{method_id}         # Get specific method details
GET  /api/v1/methods/{method_id}/papers  # Get papers using method
```

**Implementation Details:**
- **Database Query**: Join `methods` with `paper_methods` and `papers`
- **Filtering**: By name, paper count, publication date
- **Response Model**: `Method`, `Methods`

#### 2.3 Datasets API
```
GET  /api/v1/datasets/                               # List datasets
GET  /api/v1/datasets/{dataset_id}                   # Get specific dataset
GET  /api/v1/datasets/{dataset_id}/papers            # Get papers using dataset
GET  /api/v1/datasets/{dataset_id}/evaluations       # Get evaluation tables
```

**Implementation Details:**
- **Database Query**: Join `datasets` with `paper_datasets` and `papers`
- **Filtering**: By domain, size, paper count
- **Response Model**: `Dataset`, `Datasets`

#### 2.4 Conferences API
```
GET  /api/v1/conferences/                            # List conferences
GET  /api/v1/conferences/{conference_id}             # Get specific conference
GET  /api/v1/conferences/{conference_id}/papers      # Get conference papers
GET  /api/v1/conferences/{conference_id}/proceedings # Get proceedings
```

**Implementation Details:**
- **Database Query**: Join `conferences` with `papers`
- **Filtering**: By year, venue type, paper count
- **Response Model**: `Conference`, `Conferences`, `Proceeding`

### Phase 3: Advanced Features (Priority: MEDIUM-LOW)
**Timeline: 3-4 weeks**
**Dependencies: Phase 2 completion**

#### 3.1 Evaluations API
```
GET  /api/v1/evaluations/                           # List evaluation tables
GET  /api/v1/evaluations/{eval_id}                  # Get specific evaluation table
GET  /api/v1/evaluations/{eval_id}/results          # Get evaluation results
GET  /api/v1/evaluations/{eval_id}/metrics          # Get evaluation metrics
POST /api/v1/evaluations/                           # Create evaluation table (admin)
PUT  /api/v1/evaluations/{eval_id}                  # Update evaluation table (admin)
DELETE /api/v1/evaluations/{eval_id}                # Delete evaluation table (admin)
```

**Implementation Details:**
- **Database Query**: Complex joins across `evaluation_tables`, `results`, `metrics`
- **CRUD Operations**: Full create/read/update/delete support
- **Authentication**: Admin-only for write operations
- **Response Model**: `EvaluationTable`, `Result`, `Metric`

#### 3.2 Cross-Entity Relationship Endpoints
```
GET  /api/v1/papers/{paper_id}/authors              # Paper's authors
GET  /api/v1/papers/{paper_id}/tasks                # Paper's tasks
GET  /api/v1/papers/{paper_id}/methods              # Paper's methods
GET  /api/v1/papers/{paper_id}/datasets             # Paper's datasets
GET  /api/v1/papers/{paper_id}/repositories         # Paper's repositories
GET  /api/v1/papers/{paper_id}/results              # Paper's evaluation results
```

**Implementation Details:**
- **Database Query**: Direct foreign key relationships
- **Caching**: Heavy caching for frequently accessed relationships
- **Response Model**: Reuse existing entity models

### Phase 4: Search & Discovery (Priority: HIGH)
**Timeline: 2-3 weeks**
**Dependencies: Phases 1-2 completion**

#### 4.1 Global Search API
```
GET  /api/v1/search/                                # Global search across all entities
GET  /api/v1/search/papers                          # Enhanced paper search
GET  /api/v1/search/authors                         # Author search
GET  /api/v1/search/repositories                    # Repository search
```

**Implementation Details:**
- **Full-Text Search**: PostgreSQL full-text search with ranking
- **Faceted Search**: Filter by entity type, date ranges, metrics
- **Autocomplete**: Suggest completions for search queries
- **Response Model**: `SearchResults` with mixed entity types

#### 4.2 Recommendation API
```
GET  /api/v1/papers/{paper_id}/similar              # Similar papers
GET  /api/v1/papers/{paper_id}/citing               # Papers citing this paper
GET  /api/v1/papers/{paper_id}/cited-by             # Papers cited by this paper
GET  /api/v1/authors/{author_id}/collaborators      # Author collaborators
```

**Implementation Details:**
- **Similarity Algorithm**: Based on shared tasks, methods, citations
- **Graph Analysis**: Citation network analysis
- **Machine Learning**: Content-based and collaborative filtering
- **Response Model**: Ranked lists with similarity scores

## Implementation Guidelines

### 1. Database Queries & Performance

#### Indexing Strategy
```sql
-- Core indexes for API performance
CREATE INDEX idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX idx_papers_published ON papers(date_published);
CREATE INDEX idx_papers_title_fts ON papers USING gin(to_tsvector('english', title));
CREATE INDEX idx_papers_abstract_fts ON papers USING gin(to_tsvector('english', abstract));

-- Relationship indexes
CREATE INDEX idx_paper_authors_paper_id ON paper_authors(paper_id);
CREATE INDEX idx_paper_authors_author_id ON paper_authors(author_id);
CREATE INDEX idx_paper_tasks_paper_id ON paper_tasks(paper_id);
CREATE INDEX idx_paper_tasks_task_id ON paper_tasks(task_id);

-- Hierarchy indexes
CREATE INDEX idx_tasks_parent_id ON tasks(parent_id);
CREATE INDEX idx_tasks_area_id ON tasks(area_id);
```

#### Query Patterns
```python
# Example: Efficient author papers query
def get_author_papers(author_id: str, page: int = 1, limit: int = 50):
    return (
        session.query(Paper)
        .join(PaperAuthor)
        .filter(PaperAuthor.author_id == author_id)
        .order_by(Paper.date_published.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
```

### 2. Response Models & Serialization

#### Consistent Pagination
```python
class PaginatedResponse(BaseModel):
    count: int
    next_page: Optional[int]
    previous_page: Optional[int]
    results: List[Any]
```

#### Entity Models
```python
# Follow legacy client structure
class Author(BaseModel):
    id: str
    full_name: str
    hf_username: Optional[str] = None
    paper_count: int = 0

class Task(BaseModel):
    id: str
    name: str
    description: str
    parent_id: Optional[str] = None
    area_id: Optional[str] = None
    paper_count: int = 0
```

### 3. Error Handling & Validation

#### Standard Error Responses
```python
class ErrorResponse(BaseModel):
    error: str
    detail: str
    code: Optional[str] = None

class ValidationErrorResponse(BaseModel):
    error: str = "Validation error"
    detail: List[dict]
```

#### HTTP Status Codes
- `200 OK`: Successful GET requests
- `201 Created`: Successful POST requests
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Resource not found
- `422 Unprocessable Entity`: Validation errors
- `500 Internal Server Error`: Server errors

### 4. Caching Strategy

#### Redis Caching Layers
```python
# Cache frequently accessed data
@cache(expire=3600)  # 1 hour
def get_paper_by_id(paper_id: str):
    pass

@cache(expire=1800)  # 30 minutes
def get_task_hierarchy():
    pass

@cache(expire=300)   # 5 minutes
def get_trending_papers():
    pass
```

## Testing Strategy

### 1. Unit Tests
- **Model Tests**: Validate Pydantic models and SQLAlchemy relationships
- **Service Tests**: Test business logic and data transformations
- **Utility Tests**: Test helper functions and utilities

### 2. Integration Tests
- **API Endpoint Tests**: Test full request/response cycles
- **Database Tests**: Test complex queries and transactions
- **Cache Tests**: Test caching behavior and invalidation

### 3. Performance Tests
- **Load Testing**: Test API under concurrent requests
- **Query Performance**: Test database query execution times
- **Memory Usage**: Monitor memory consumption under load

## Monitoring & Observability

### 1. Metrics Collection
```python
# Key metrics to track
- API response times per endpoint
- Database query execution times
- Cache hit/miss ratios
- Error rates by endpoint
- Request volume by endpoint
```

### 2. Logging Strategy
```python
# Structured logging
import structlog

logger = structlog.get_logger()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    logger.info(
        "api_request",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code,
        process_time=process_time
    )
    return response
```

## Migration & Deployment

### 1. Gradual Rollout
1. **Phase 1**: Deploy new endpoints alongside existing ones
2. **Phase 2**: Update frontend to use new endpoints progressively
3. **Phase 3**: Monitor performance and fix issues
4. **Phase 4**: Deprecate old endpoints after full migration

### 2. Backward Compatibility
- **Versioning**: Use `/api/v1/` prefix for all new endpoints
- **Legacy Support**: Maintain existing endpoints during transition
- **Documentation**: Clear migration guides for API consumers

### 3. Database Migrations
```python
# Alembic migration example
def upgrade():
    # Add new indexes for API performance
    op.create_index('idx_authors_name', 'authors', ['name'])
    op.create_index('idx_tasks_hierarchy', 'tasks', ['parent_id', 'level'])
```

## Success Metrics

### 1. Performance Targets
- **API Response Time**: < 200ms for 95th percentile
- **Database Query Time**: < 100ms for complex joins
- **Cache Hit Rate**: > 80% for frequently accessed data
- **Uptime**: > 99.9% availability

### 2. Functionality Targets
- **API Coverage**: 100% of legacy client functionality
- **Data Accuracy**: 100% consistency with source data
- **Search Quality**: Relevant results for 90% of queries
- **Documentation**: 100% endpoint coverage in OpenAPI docs

### 3. User Experience Targets
- **Frontend Integration**: Seamless replacement of hardcoded data
- **Error Handling**: Clear, actionable error messages
- **API Discoverability**: Intuitive endpoint structure
- **Developer Experience**: Comprehensive documentation and examples

## Next Steps

### Immediate Actions (Week 1)
1. **Review and approve** this expansion plan
2. **Set up development environment** for API expansion
3. **Create GitHub issues** for each phase and endpoint
4. **Begin Phase 1 implementation** with Repositories & Project Pages API (PRIORITIZED)

### Short-term Goals (Month 1)
1. **Complete Phase 1**: Repositories, Project Pages, and Authors APIs
2. **Set up monitoring** and logging infrastructure
3. **Write comprehensive tests** for new endpoints
4. **Update API documentation** with new endpoints
5. **Integrate repositories and project pages into frontend paper display**

### Long-term Goals (Month 2-3)
1. **Complete Phases 2-3**: All entity endpoints
2. **Implement advanced search** and recommendation features
3. **Optimize performance** and add caching
4. **Full frontend integration** and legacy endpoint deprecation

---

*This document will be updated as implementation progresses and requirements evolve.*
