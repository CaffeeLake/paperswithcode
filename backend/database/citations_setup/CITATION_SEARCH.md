# Citation-Based Search Enhancement

This document describes the citation-based search enhancement that prioritizes important papers based on their citation counts from the Semantic Scholar API.

## Overview

The enhanced search functionality uses citation counts as an importance metric to ensure that highly cited papers (like "AN IMAGE IS WORTH 16X16 WORDS: TRANSFORMERS FOR IMAGE RECOGNITION AT SCALE" for "vision transformer" queries) appear higher in search results.

## Features

### 1. Citation Count Integration

- **Database Schema**: Added `citation_count`, `semantic_scholar_id`, and `citation_updated_at` fields to the `papers` table
- **API Models**: Updated `Paper` and `PaperSummary` models to include citation count information
- **Automatic Updates**: Citation counts are updated periodically from the Semantic Scholar API

### 2. Enhanced Search Ranking

The search algorithm now uses a multi-tier approach with citation-based ranking:

1. **Exact title matches** (highest priority) - sorted by citation count
2. **Title contains query** (medium priority) - sorted by citation count  
3. **Full-text search** (lowest priority) - sorted by combined relevance + citation importance

### 3. Semantic Scholar Integration

- **Paper Lookup**: Search papers by title, ArXiv ID, or Semantic Scholar ID
- **Citation Updates**: Batch update citation counts with rate limiting
- **Enhanced Search**: Supplement local results with highly cited papers from Semantic Scholar

## API Endpoints

### Enhanced Search Endpoint

```http
GET /papers/search?q={query}&limit={limit}&enhanced={boolean}
```

**Parameters:**
- `q`: Search query (required)
- `limit`: Maximum results (1-100, default: 10)
- `enhanced`: Use Semantic Scholar integration (default: false)

**Example:**
```bash
curl "http://localhost:8000/papers/search?q=vision%20transformer&limit=5&enhanced=true"
```

### Citation Update Endpoint

```http
POST /papers/update-citations?limit={limit}
```

**Parameters:**
- `limit`: Maximum papers to update (1-1000, default: 100)

**Example:**
```bash
curl -X POST "http://localhost:8000/papers/update-citations?limit=50"
```

## Database Schema Changes

### New Fields in `papers` Table

```sql
ALTER TABLE papers 
ADD COLUMN citation_count INTEGER DEFAULT 0,
ADD COLUMN semantic_scholar_id VARCHAR(100),
ADD COLUMN citation_updated_at TIMESTAMP WITH TIME ZONE;
```

### New Indexes

```sql
CREATE INDEX idx_papers_citation_count ON papers(citation_count DESC);
CREATE INDEX idx_papers_semantic_scholar_id ON papers(semantic_scholar_id);
```

## Setup Instructions

### 1. Database Migration

For existing databases, run the migration script:

```bash
psql -U postgres -d paperswithcode -f backend/database/setup/add_citation_fields.sql
```

For new databases, the fields are included in the main schema:

```bash
psql -U postgres -d paperswithcode -f backend/database/setup/setup_database.sql
```

### 2. Install Dependencies

```bash
uv add httpx  # For async HTTP requests to Semantic Scholar API
```

### 3. Populate Citation Counts

Run the citation population script to fetch citation counts for existing papers:

```bash
cd backend
python populate_citations.py --limit 100
```

### 4. Test the Implementation

```bash
cd backend
python test_citation_search.py
```

## Configuration

### Rate Limiting

The Semantic Scholar service includes built-in rate limiting:

- **Request Delay**: 1 second between requests
- **Rate Limit Handling**: Automatic retry with backoff on 429 responses
- **Update Frequency**: Citation counts updated weekly per paper

### API Key (Optional)

For higher rate limits, you can provide a Semantic Scholar API key:

```python
semantic_scholar_service = SemanticScholarService(db, api_key="your-api-key")
```

## Search Algorithm Details

### Citation-Based Ranking Formula

For full-text search results, the ranking combines:

1. **Text Relevance**: PostgreSQL's `ts_rank` score
2. **Citation Importance**: `log(max(citation_count, 1)) / 10.0`

```sql
ORDER BY (
    ts_rank(to_tsvector('english', title || ' ' || abstract), query) + 
    (log(greatest(citation_count, 1)) / 10.0)
) DESC
```

### Search Priority Levels

1. **Level 1**: Exact title matches → Sort by citation count → Sort by date
2. **Level 2**: Title contains query → Sort by citation count → Sort by date
3. **Level 3**: Full-text matches → Sort by combined score → Sort by citation count → Sort by date

## Performance Considerations

### Database Indexes

- `idx_papers_citation_count`: Optimizes citation-based sorting
- `idx_papers_semantic_scholar_id`: Fast lookups for API updates
- Existing full-text search indexes remain unchanged

### API Rate Limits

- **Unauthenticated**: ~100 requests per 5 minutes
- **With API Key**: ~1000 requests per 5 minutes
- **Batch Updates**: Automatic rate limiting with delays

### Caching Strategy

- Citation counts cached in database
- Weekly update frequency prevents excessive API calls
- Failed API requests don't break search functionality

## Example Usage

### Basic Citation-Enhanced Search

```python
from services.paper_service import PaperService

service = PaperService(db)
results = service.search_papers("vision transformer", limit=10)

# Results now prioritized by citation count within relevance tiers
for paper in results:
    print(f"{paper.title} ({paper.citation_count} citations)")
```

### Enhanced Search with Semantic Scholar

```python
results = await service.search_papers_with_semantic_scholar("vision transformer", limit=10)

# Includes highly cited papers from Semantic Scholar API
for paper in results:
    print(f"{paper.title} ({paper.citation_count} citations)")
```

### Manual Citation Updates

```python
from services.semantic_scholar_service import SemanticScholarService

service = SemanticScholarService(db)
updated_count = await service.batch_update_citation_counts(limit=50)
print(f"Updated {updated_count} papers")
```

## Troubleshooting

### Common Issues

1. **"httpx not found"**: Run `uv add httpx`
2. **Database errors**: Run the migration script
3. **API rate limits**: Reduce batch size or add delays
4. **No citation data**: Papers may not be in Semantic Scholar

### Debugging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Fallback Behavior

- If Semantic Scholar API fails, search falls back to local database only
- Missing citation counts default to 0
- Search functionality remains available even without citation data

## Future Enhancements

### Planned Features

1. **Field Normalization**: Adjust citation counts by research field
2. **Temporal Weighting**: Consider paper age in importance calculation
3. **Author Impact**: Include author h-index in ranking
4. **Conference Prestige**: Weight by conference/journal impact factor

### API Improvements

1. **Bulk Citation Updates**: Batch API for multiple papers
2. **Real-time Updates**: WebSocket for live citation updates
3. **Citation Trends**: Historical citation growth data
4. **Related Papers**: Citation-based paper recommendations
