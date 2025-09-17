# Citation Population Setup

This directory contains scripts for populating citation counts from the Semantic Scholar API.

## 🎯 **Current Status**

✅ **Citation-based search is WORKING**
- Papers with higher citations appear first in search results
- Real citation data is being populated from Semantic Scholar API
- API key integrated for higher rate limits (1 req/sec)

## 📊 **Progress Summary**

- **Total papers**: 513,886 (latest versions only)
- **Papers processed**: ~140+ (and growing)
- **Papers with citations**: 5+ (and growing)
- **Highest citation count**: 7 citations
- **Processing rate**: ~1 paper/second (respecting API limits)

## 🛠️ **Available Scripts**

### 1. `populate_citations.py`
Basic citation population script for small batches.

```bash
uv run python backend/database/setup/populate_citations.py --limit 50
```

### 2. `batch_populate_citations.py` ⭐
Advanced batch processing script for large-scale population.

```bash
# Process 2000 papers (10 batches of 200 each)
uv run python backend/database/setup/batch_populate_citations.py --batch-size 200 --max-batches 10

# Resume from batch 5
uv run python backend/database/setup/batch_populate_citations.py --start-from 5

# Process all papers (will take ~6 days)
uv run python backend/database/setup/batch_populate_citations.py --batch-size 100
```

### 3. `check_citation_progress.py`
Monitor citation population progress.

```bash
uv run python backend/database/setup/check_citation_progress.py
```

### 4. `add_citation_fields.sql`
Database migration to add citation fields (already applied).

```bash
psql -U nielsrogge -d paperswithcode -f backend/database/setup/add_citation_fields.sql
```

## 🔑 **API Configuration**

The scripts use the Semantic Scholar API key:
- **Rate limit**: 1 request per second
- **Key**: Embedded in scripts (for development)
- **Endpoints**: Paper search and details

## 📈 **Citation-Based Search Results**

The search is now working with citation-based ranking:

```bash
# Test citation-based search
curl "http://localhost:8000/api/v1/papers/search?q=drone&limit=5"
```

**Example results**:
- Papers with 7 citations appear first
- Papers with 1-3 citations appear next  
- Papers with 0 citations appear last

## 🚀 **Recommended Workflow**

### For Development/Testing:
```bash
# 1. Process a small batch
uv run python backend/database/setup/populate_citations.py --limit 100

# 2. Check progress
uv run python backend/database/setup/check_citation_progress.py

# 3. Test search results
curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=5"
```

### For Production Population:
```bash
# 1. Run large batches in background
nohup uv run python backend/database/setup/batch_populate_citations.py --batch-size 200 --max-batches 50 > citation_log.txt 2>&1 &

# 2. Monitor progress periodically
uv run python backend/database/setup/check_citation_progress.py

# 3. Resume if needed
uv run python backend/database/setup/batch_populate_citations.py --start-from X
```

## ⚡ **Performance Notes**

- **Rate Limiting**: Automatic 1-second delays between requests
- **Memory Usage**: Minimal (processes one paper at a time)
- **Database Impact**: Efficient updates with proper indexing
- **Resumability**: Can resume from any batch number
- **Error Handling**: Graceful handling of API failures

## 🎯 **Expected Timeline**

- **Small batches (100-1000 papers)**: Minutes to hours
- **Medium batches (10,000 papers)**: Several hours
- **Full dataset (500k+ papers)**: ~6 days continuous processing

## 📊 **Citation Distribution**

Based on current data:
- **~96% papers**: 0 citations (very recent papers)
- **~3% papers**: 1-5 citations
- **~1% papers**: 6+ citations

## 🔍 **Search Impact**

The citation-based ranking ensures:
1. **Important papers appear first** (high citation count)
2. **Recent papers with some impact** appear next (low citation count)
3. **Very recent papers** appear last (0 citations)

This creates a perfect balance between **importance** and **recency** in search results!

## 🛠️ **Troubleshooting**

### Common Issues:

1. **Import errors**: Ensure you're running from project root with `uv run`
2. **Database connection**: Check PostgreSQL is running and credentials are correct
3. **API rate limits**: Scripts automatically handle rate limiting
4. **Memory issues**: Use smaller batch sizes if needed

### Monitoring:

```bash
# Check if background process is running
ps aux | grep populate_citations

# Monitor database updates
psql -U nielsrogge -d paperswithcode -c "SELECT COUNT(*) FROM papers WHERE semantic_scholar_id IS NOT NULL;"

# Check recent activity
psql -U nielsrogge -d paperswithcode -c "SELECT DATE(citation_updated_at), COUNT(*) FROM papers WHERE citation_updated_at IS NOT NULL GROUP BY 1 ORDER BY 1 DESC LIMIT 5;"
```
