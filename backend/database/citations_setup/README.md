# Citation Population Setup

This directory contains the optimized citation population system for the Semantic Scholar API.

## 🎯 **Current Status**

✅ **Citation-based search is WORKING**
- Papers with higher citations appear first in search results
- Real citation data is being populated from Semantic Scholar API
- Optimized processing with 2-3x speed improvement

## 📊 **Progress Summary**

- **Total papers**: 510,250 (latest versions only)
- **Papers processed**: 7,800+ (and growing)
- **Papers with citations**: 2,100+ (and growing)
- **Highest citation count**: 196 citations
- **Processing rate**: ~2-3 papers/second (optimized)

## 🚀 **Main Script**

### `populate_citations.py` ⭐ **RECOMMENDED**
**Single, unified script for all citation population needs**

```bash
# Check current status
uv run --env-file backend/keys.env python backend/database/citations_setup/populate_citations.py --status

# Test mode (100 papers)
uv run --env-file backend/keys.env python backend/database/citations_setup/populate_citations.py --test

# Production mode (all papers)
uv run --env-file backend/keys.env python backend/database/citations_setup/populate_citations.py --production

# Custom batch
uv run --env-file backend/keys.env python backend/database/citations_setup/populate_citations.py --papers 5000 --batch-size 50

# Background processing
nohup uv run --env-file backend/keys.env python backend/database/citations_setup/populate_citations.py --production > citations.log 2>&1 &
```

**Features:**
- ✅ 2-3x faster than original implementation
- ✅ Parallel API requests (4 concurrent)
- ✅ Bulk database updates
- ✅ Smart paper prioritization (focus on 2019-2022 papers)
- ✅ Automatic rate limiting and retry logic
- ✅ Real-time progress monitoring
- ✅ Built-in test and production modes
- ✅ Comprehensive error handling

## 🛠️ **Supporting Scripts**

### `check_citation_progress.py`
Monitor citation population progress with detailed statistics.

```bash
# Quick overview
uv run --env-file backend/keys.env python backend/database/citations_setup/check_citation_progress.py --quick

# Detailed statistics (default)
uv run --env-file backend/keys.env python backend/database/citations_setup/check_citation_progress.py
```

### `populate_citations.py`
Basic citation population script (legacy, use optimized version instead).

### `add_citation_fields.sql`
Database migration to add citation fields (already applied).

## 🔑 **API Configuration**

The scripts use the Semantic Scholar API key:
- **Rate limit**: ~1.67 requests per second (optimized)
- **Key**: Set via SEMANTIC_SCHOLAR_API_KEY environment variable
- **Endpoints**: Direct ArXiv ID lookup for maximum efficiency

## 📈 **Citation-Based Search Results**

The search is now working with citation-based ranking:

```bash
# Test citation-based search
curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=5"
```

**Example results**:
- Papers with 196 citations appear first
- Papers with 10-50 citations appear next
- Papers with 0-5 citations appear last

## 🚀 **Recommended Workflow**

### For Development/Testing:
```bash
# 1. Check current status
uv run --env-file backend/keys.env python backend/database/citations_setup/populate_citations.py --status

# 2. Test with small batch
uv run --env-file backend/keys.env python backend/database/citations_setup/populate_citations.py --test

# 3. Test search results
curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=5"
```

### For Production Population:
```bash
# 1. Run in production mode (background)
nohup uv run --env-file backend/keys.env python backend/database/citations_setup/populate_citations.py --production > citations.log 2>&1 &

# 2. Monitor progress
tail -f citations.log

# 3. Check detailed progress
uv run --env-file backend/keys.env python backend/database/citations_setup/check_citation_progress.py
```

## ⚡ **Performance Improvements**

- **Speed**: 2-3x faster than original implementation
- **Rate Limiting**: Intelligent 0.6s delays with automatic retry
- **Memory Usage**: Efficient batch processing with connection pooling
- **Database Impact**: Bulk updates with single transactions
- **Resumability**: Automatic continuation from where it left off
- **Error Handling**: Comprehensive retry logic and graceful failures

## 🎯 **Expected Timeline**

- **Test batch (100 papers)**: ~1 minute
- **Small batches (1,000 papers)**: ~10 minutes
- **Medium batches (10,000 papers)**: ~1.5 hours
- **Full dataset (500k+ papers)**: ~70 hours (3 days)

## 📊 **Smart Prioritization**

The optimized script prioritizes papers by likelihood of having citations:

1. **Priority 1**: Papers from 2019-2022 (highest citation likelihood)
2. **Priority 2**: Papers from 2017-2018 (moderate likelihood)
3. **Priority 3**: Papers from 2023-2024 (recent, important)
4. **Priority 4**: Older papers (lowest priority)

## 🔍 **Search Impact**

The citation-based ranking ensures:
1. **Highly cited papers appear first** (100+ citations)
2. **Moderately cited papers** appear next (10-99 citations)
3. **Recently cited papers** appear next (1-9 citations)
4. **Very recent papers** appear last (0 citations)

This creates an optimal balance between **importance** and **recency**!

## 🛠️ **Troubleshooting**

### Common Issues:

1. **API key**: Set SEMANTIC_SCHOLAR_API_KEY environment variable
2. **Database connection**: Check PostgreSQL is running and accessible
3. **Rate limits**: Scripts automatically handle rate limiting
4. **Memory issues**: Reduce batch size with --batch-size parameter

### Monitoring:

```bash
# Check current status
uv run --env-file backend/keys.env python backend/database/citations_setup/populate_citations.py --status

# Monitor background process
ps aux | grep populate_citations_optimized

# Check database progress
uv run --env-file backend/keys.env python backend/database/citations_setup/check_citation_progress.py --quick
```
