# PapersWithCode CRON Jobs

This directory contains all automated CRON job scripts for the PapersWithCode project. These scripts handle daily data updates, maintenance tasks, and periodic processing to keep the database fresh and up-to-date.

## 📁 Directory Structure

```
cron/
├── README.md           # This file - comprehensive cron jobs documentation
├── daily/              # Scripts that run daily (legacy/backup versions)
│   ├── import_hf_daily_papers.py    # Import Hugging Face daily papers
│   ├── update_github_stars.py       # Update GitHub repository stars (1K repos/day)
│   └── update_citations.py          # Update paper citation counts (2K papers/day)
├── hourly/             # Scripts that run hourly (RECOMMENDED - high performance)
│   ├── update_github_stars.py       # Update GitHub repository stars (4.5K repos/hour)
│   ├── update_citations.py          # Update paper citation counts (2.8K papers/hour)
│   └── extract_urls.py              # AI extraction of GitHub URLs and project pages (50 papers/hour)
├── weekly/             # Scripts that run weekly (future expansion)
├── monthly/            # Scripts that run monthly (future expansion)
├── logs/               # Log files from cron job executions (auto-created)
├── utils/              # Shared utilities for cron jobs
│   ├── __init__.py
│   └── cron_helpers.py # Base classes and utilities
└── manage_cron.py      # Management script for testing and monitoring
```

## ⚡ Performance Overview & Job Selection

### **RECOMMENDED: Hourly Jobs (High Performance)**

The hourly jobs are **significantly more efficient** and should be used for production:

| Job Type | Hourly Version | Daily Version | Performance Gain |
|----------|---------------|---------------|------------------|
| **GitHub Stars** | 4,500 repos/hour | 1,000 repos/day | **108x faster** |
| **Citations** | 2,800 papers/hour | 2,000 papers/day | **33x faster** |
| **URL Extraction** | 50 papers/hour | N/A | **AI-powered** |

### **Processing Time Comparisons**

For a database with **66K repositories** and **53K papers**:

| Metric | Hourly Jobs | Daily Jobs |
|--------|-------------|------------|
| **Complete GitHub stars update** | ~15 hours | ~66 days |
| **Complete citations update** | ~19 hours | ~27 days |
| **API utilization** | 90% GitHub, 77% S2 | <3% both APIs |
| **Database freshness** | 7-day cycles | 30+ day cycles |

### **Why Hourly Jobs Are Better**

1. **Massive Performance Gain**: Process entire database in hours vs. months
2. **Better API Utilization**: Use 77-90% of available API capacity vs. <3%
3. **Fresher Data**: Keep repository stars and citations much more up-to-date
4. **Fault Tolerance**: If one hour fails, only lose 1 hour of progress vs. 1 day
5. **Scalability**: Can handle database growth without falling behind

### **Job Selection Guide**

- **Production/Live Sites**: Use hourly jobs (`cron/hourly/`)
- **Development/Testing**: Use daily jobs (`cron/daily/`) for lighter load
- **Initial Data Population**: Use hourly jobs to catch up quickly
- **Maintenance Mode**: Switch to daily jobs temporarily if needed

## 🚀 Quick Setup & Installation

### 1. Database Schema Requirements

The cron jobs require specific timestamp columns to track when data was last updated:

```sql
-- The papers table already has citation_updated_at in paperswithcode_hf database
-- But we need to add the star count tracking column to repositories table:

ALTER TABLE repositories
ADD COLUMN num_stars_updated_at TIMESTAMP WITH TIME ZONE;

-- Create index for better performance
CREATE INDEX idx_repositories_num_stars_updated_at ON repositories(num_stars_updated_at);

-- Verify the citation_updated_at column exists (should already be there):
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'papers' AND column_name = 'citation_updated_at';
```

### 2. Environment Variables Setup

All cron jobs require environment variables from `backend/keys.env`. Ensure these are available:

```bash
# Database connection
PWC_DB_USER=paperswithcode_user
PWC_DB_PASSWORD=paperswithcode123
PWC_DB_HOST=localhost
PWC_DB_PORT=5432
PWC_DB_NAME=paperswithcode_hf

# API Keys
PWC_SEMANTIC_SCHOLAR_API_KEY=6Wa5zD2S3HahK5AAjMRnr6n31usSpq1a3gpksOQa
PWC_HF_TOKEN=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
PWC_GITHUB_TOKEN=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
PWC_OPENROUTER_API_KEY=your_openrouter_api_key_here
```

**For system-wide cron jobs**, add to `/etc/environment`:
```bash
PWC_DB_USER=paperswithcode_user
PWC_DB_PASSWORD=paperswithcode123
PWC_DB_HOST=localhost
PWC_DB_PORT=5432
PWC_DB_NAME=paperswithcode_hf
PWC_SEMANTIC_SCHOLAR_API_KEY=6Wa5zD2S3HahK5AAjMRnr6n31usSpq1a3gpksOQa
PWC_HF_TOKEN=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
PWC_GITHUB_TOKEN=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
PWC_OPENROUTER_API_KEY=your_openrouter_api_key_here
```

### 3. Verify Setup

Test that the cron job infrastructure is working:

```bash
cd /root/python_projects/paperswithcode
uv run --env-file backend/keys.env cron/manage_cron.py list
```

### 4. Test Individual Jobs

Test each cron job before scheduling:

```bash
# Test daily Hugging Face papers import
uv run --env-file backend/keys.env cron/manage_cron.py test import_hf_daily_papers

# Test daily GitHub stars update
uv run --env-file backend/keys.env cron/manage_cron.py test update_github_stars

# Test daily citation count update
uv run --env-file backend/keys.env cron/manage_cron.py test update_citations

# Test hourly URL extraction
uv run --env-file backend/keys.env cron/manage_cron.py test extract_urls
```

### 5. Install CRON Jobs

Edit your crontab with `crontab -e` and add these entries:

**RECOMMENDED: High-Performance Hourly Jobs**
```bash
# PapersWithCode CRON Jobs - Hourly High-Performance Updates
# RECOMMENDED for production - processes data 33-108x faster than daily jobs

# Hugging Face papers import at 3:00 AM UTC (Tuesday to Saturday only)
# Papers are submitted Mon-Fri on HF, so we import Tue-Sat to get previous day's papers
0 3 * * 2-6 cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/daily/import_hf_daily_papers.py

# Hourly GitHub stars update (4,500 repos/hour) - RECOMMENDED
0 * * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/hourly/update_github_stars.py

# Hourly citation count update (2,800 papers/hour) - RECOMMENDED
30 * * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/hourly/update_citations.py

# Hourly URL extraction (50 papers/hour) - AI-powered GitHub and project page extraction
45 * * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/hourly/extract_urls.py

# Optional: Clean up old logs weekly on Saturdays at 1:00 AM UTC
0 1 * * 6 cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/manage_cron.py cleanup
```

**Alternative: Conservative Daily Jobs (Legacy)**
```bash
# PapersWithCode CRON Jobs - Daily Conservative Updates
# Use only for development/testing or if you prefer lower API usage

# Hugging Face papers import at 3:00 AM UTC (Tuesday to Saturday only)
# Papers are submitted Mon-Fri on HF, so we import Tue-Sat to get previous day's papers
0 3 * * 2-6 cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/daily/import_hf_daily_papers.py

# Daily GitHub stars update at 4:00 AM UTC (1,000 repos/day)
0 4 * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/daily/update_github_stars.py

# Daily citation count update at 5:00 AM UTC (2,000 papers/day)
0 5 * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/daily/update_citations.py

# Optional: Clean up old logs weekly on Saturdays at 1:00 AM UTC
0 1 * * 6 cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/manage_cron.py cleanup
```

## 📋 Available CRON Jobs

### 🚀 Hourly Jobs (`hourly/`) - **RECOMMENDED**

#### 🔗 GitHub URLs and Project Pages Extraction - Hourly (`extract_urls.py`)
- **Schedule**: Every hour (recommended)
- **Purpose**: AI-powered extraction of GitHub repositories and project pages from papers
- **Performance**: **50 papers/hour** (1,200 papers/day with paid tier)
- **Features**:
  - Uses OpenRouter AI models for intelligent URL extraction
  - Memory-optimized for 4GB RAM systems (batch size: 10)
  - Processes papers from 2014 onwards
  - Skips papers already processed by HF API import (urls_extracted flag)
  - Handles rate limits and PDF download failures gracefully
  - Marks papers as processed to avoid reprocessing
  - Saves URLs with source='ai_extraction' and is_official=True
- **Rate Limits**:
  - Paid tier: 1,000 requests/day, 20 requests/minute
  - Conservative usage: 50 papers/hour = 1,200/day (with buffer)
- **API Requirements**: OpenRouter API key (PWC_OPENROUTER_API_KEY in keys.env)

#### ⭐ GitHub Stars Update - Hourly (`update_github_stars.py`)
- **Schedule**: Every hour (recommended)
- **Purpose**: High-performance repository star count updates
- **Performance**: **4,500 repositories/hour** (108x faster than daily)
- **Features**:
  - Optimized rate limiting (0.8s delays = 4,500 req/hour, 90% of GitHub's 5K limit)
  - Larger batches (100 repos) with efficient processing
  - Pre-limited database queries for performance
  - Shorter timeouts and faster error recovery
  - Complete database update in ~15 hours vs. 66 days

#### 📊 Citation Count Update - Hourly (`update_citations.py`)
- **Schedule**: Every hour (recommended)
- **Purpose**: High-performance citation count updates
- **Performance**: **2,800 papers/hour** (33x faster than daily)
- **Features**:
  - Optimized rate limiting (1.3s delays = 2,769 req/hour, 77% of S2's theoretical limit)
  - Conservative buffer for API stability
  - Larger batches (100 papers) with async processing
  - Efficient database pre-limiting
  - Complete database update in ~19 hours vs. 27 days

### 📅 Daily Jobs (`daily/`) - Legacy/Backup

#### 🤗 Hugging Face Daily Papers (`import_hf_daily_papers.py`)
- **Schedule**: Tuesday to Saturday at 3:00 AM UTC (skips Sunday/Monday)
- **Purpose**: Import curated daily papers from Hugging Face API
- **Features**:
  - Fetches papers from previous day (e.g., if run on 2025-09-26, fetches 2025-09-25 papers)
  - Only runs Tue-Sat since papers are submitted Mon-Fri on Hugging Face
  - Populates Papers, Authors, Repositories, and Project_pages tables
  - Enriches author profiles with Hugging Face data (avatars, Pro status, verification)
  - Extracts GitHub repository links and project page URLs
  - Smart duplicate prevention and author matching

#### ⭐ GitHub Stars Update - Daily (`update_github_stars.py`)
- **Schedule**: Daily at 4:00 AM UTC (legacy version)
- **Purpose**: Conservative repository star count updates
- **Performance**: 1,000 repositories/day (use hourly version for production)
- **Features**:
  - Conservative rate limiting (200ms delays, 5s between batches)
  - Smaller batches (50 repos) for stability
  - Processes up to 1,000 repositories per run

#### 📊 Citation Count Update - Daily (`update_citations.py`)
- **Schedule**: Daily at 5:00 AM UTC (legacy version)
- **Purpose**: Conservative citation count updates
- **Performance**: 2,000 papers/day (use hourly version for production)
- **Features**:
  - Conservative rate limiting (1.25s delays = 0.8 req/sec)
  - Smaller batches (50 papers) for stability
  - Processes up to 2,000 papers per run (~40 minutes)

## 🛠️ Management & Monitoring

### Management Script (`manage_cron.py`)

The management script provides comprehensive tools for testing and monitoring:

```bash
# List all available cron jobs
uv run --env-file backend/keys.env cron/manage_cron.py list

# Check status of all jobs
uv run --env-file backend/keys.env cron/manage_cron.py status

# Check status of specific job
uv run --env-file backend/keys.env cron/manage_cron.py status import_hf_daily_papers

# Check status for specific date
uv run --env-file backend/keys.env cron/manage_cron.py status update_citations 20250926

# Test a specific job
uv run --env-file backend/keys.env cron/manage_cron.py test update_github_stars

# Clean up old log files
uv run --env-file backend/keys.env cron/manage_cron.py cleanup

# 🆕 COMPREHENSIVE STATUS SUMMARY (RECOMMENDED)
# Show comprehensive status summary with performance metrics
uv run --env-file backend/keys.env cron/manage_cron.py summary

# Show detailed analysis with full log data
uv run --env-file backend/keys.env cron/manage_cron.py summary --detailed

# Output in JSON format for scripts/monitoring
uv run --env-file backend/keys.env cron/manage_cron.py summary --json

# Analyze last 7 days instead of default 3
uv run --env-file backend/keys.env cron/manage_cron.py summary --days 7
```

### 🆕 Comprehensive Status Summary Features

The `summary` command provides advanced monitoring capabilities:

**Features:**
- 📊 **System Overview**: Available vs. active jobs, scheduling status
- 📈 **Performance Metrics**: Success rates, health scores, processing statistics
- 🚨 **Smart Alerts**: Automatic detection of issues and performance problems
- 💾 **Memory Analysis**: Memory usage tracking for optimized scripts
- 📋 **Job Details**: Individual job status with recent performance history
- 🔍 **Log Analysis**: Intelligent parsing of log files for insights

**Sample Output:**
```
================================================================================
🔄 PAPERSWITHCODE CRON JOBS STATUS SUMMARY
================================================================================
📅 Generated: 2025-09-29T08:45:28.337678

📊 SYSTEM OVERVIEW
----------------------------------------
  HOURLY: 2 jobs available
  DAILY: 1 jobs available
  📋 Total Available: 3
  ⚡ Currently Active: 4

📈 PERFORMANCE SUMMARY
----------------------------------------
  🎯 Jobs Monitored: 6
  💚 Healthy Jobs: 5
  ⚠️  Problematic Jobs: 1
  🔴 Critical Jobs: 0
  📊 Average Health Score: 95.8/100

🚨 ALERTS & ISSUES
----------------------------------------
  ⚠️ [IMPORT_HF_DAILY_PAPERS] Multiple recent errors (5 errors found)
  ℹ️ [SYSTEM] Jobs not scheduled in crontab: update_citations, update_github_stars_optimized

📋 JOB STATUS DETAILS
----------------------------------------
  ✅ UPDATE_CITATIONS_HOURLY
    Status: success | Health: 100/100 💚
    Last Run: 2025-09-29T08:30:01.717197+00:00
    Duration: 0.07s
    Recent: 51 runs, 100.0% success
```

### Log Files

Cron job logs are automatically created in `cron/logs/`:
- `import_hf_daily_papers_YYYYMMDD.log`
- `update_github_stars_YYYYMMDD.log`
- `update_citations_YYYYMMDD.log`

View logs in real-time:
```bash
# Follow today's logs
tail -f cron/logs/import_hf_daily_papers_$(date +%Y%m%d).log
tail -f cron/logs/update_github_stars_$(date +%Y%m%d).log
tail -f cron/logs/update_citations_$(date +%Y%m%d).log
```

## 🔧 Development Guidelines

### Script Structure Template

All cron job scripts follow this structure:

```python
#!/usr/bin/env python3
"""
Brief description of what this cron job does.

Schedule: Daily at X:00 AM UTC
Dependencies: PostgreSQL, API_NAME API
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from cron.utils.cron_helpers import DatabaseCronJob
from backend.config import get_settings

class YourCronJob(DatabaseCronJob):
    def __init__(self):
        super().__init__(
            job_name="your_job_name",
            log_level="INFO"
        )

    def run(self):
        """Main execution logic."""
        try:
            self.logger.info("Starting job execution")
            # Your job logic here
            self.logger.info("Job completed successfully")
        except Exception as e:
            self.logger.error(f"Job failed: {e}")
            raise

if __name__ == "__main__":
    job = YourCronJob()
    success = job.execute()
    sys.exit(0 if success else 1)
```

### Naming Conventions
- Use descriptive names: `update_github_stars.py`, `import_hf_daily_papers.py`
- Use snake_case for all file names
- Include action and data source in name

### Logging Requirements
- **MUST** use proper logging (no print statements)
- Logs written to `cron/logs/` directory with date suffix
- Include job start/end times and execution duration
- Log both success and failure cases with detailed statistics

### Error Handling
- Implement comprehensive error handling with try/catch blocks
- Log errors with full stack traces
- Consider retry logic for transient failures
- Graceful handling of API rate limits and network issues

## 📊 API Rate Limits & Performance

### Hugging Face API
- **Daily Papers**: No strict rate limits, but uses respectful delays
- **Individual Papers**: Fetched for GitHub/project page data
- **Processing**: ~100-500 papers per day typically

### GitHub API
- **Authenticated**: 5,000 requests/hour (15,000 for Enterprise)
- **Rate Strategy**: 200ms delays, 5s between batches, exponential backoff
- **Daily Capacity**: ~1,000 repositories per run

### Semantic Scholar API
- **Rate Limit**: 1 request/second across all endpoints
- **Conservative Implementation**: 0.8 req/sec (1.25s delays)
- **Daily Capacity**: ~2,000 papers per run (~40 minutes)

## 🔍 Troubleshooting

### Common Issues

1. **Environment Variables Not Found**
   ```bash
   # Verify environment file exists and is readable
   cat backend/keys.env

   # Test with explicit env file
   uv run --env-file backend/keys.env cron/manage_cron.py list
   ```

2. **Database Connection Issues**
   ```bash
   # Check PostgreSQL service
   sudo systemctl status postgresql

   # Test database connection
   psql -h localhost -U paperswithcode_user -d paperswithcode_hf
   ```

3. **Permission Denied**
   ```bash
   # Make scripts executable
   chmod +x cron/daily/*.py
   chmod +x cron/manage_cron.py
   ```

4. **API Rate Limits**
   - GitHub: Check rate limit status in logs, jobs will wait automatically
   - Semantic Scholar: Jobs use conservative rate limiting, monitor logs for 429 errors

### Debug Mode

Run jobs with debug logging:
```bash
# Set debug level for detailed logging
PWC_LOG_LEVEL=DEBUG uv run --env-file backend/keys.env cron/manage_cron.py test import_hf_daily_papers
```

### Manual Testing

Always test jobs manually before scheduling:
```bash
cd /root/python_projects/paperswithcode

# Test individual scripts directly
uv run --env-file backend/keys.env cron/daily/import_hf_daily_papers.py
uv run --env-file backend/keys.env cron/daily/update_github_stars.py
uv run --env-file backend/keys.env cron/daily/update_citations.py
```

### System Cron Logs

Check system cron logs for scheduling issues:
```bash
# Ubuntu/Debian
grep CRON /var/log/syslog | tail -20

# CentOS/RHEL
grep CRON /var/log/cron | tail -20
```

## 🔒 Security & Best Practices

### Environment Variables
- **Never** hardcode credentials in scripts
- Use `backend/keys.env` for all sensitive data
- Rotate API keys regularly
- Use least-privilege database accounts

### Monitoring
- Set up log monitoring/alerting for production
- Monitor job execution times and success rates
- Regular review of log files for issues
- Track API usage to avoid hitting limits

### Performance
- Jobs designed to run during off-peak hours (3-6 AM UTC)
- Intelligent batching and rate limiting
- Database optimization through VACUUM ANALYZE
- Automatic log cleanup to prevent disk space issues

## 📈 Expected Daily Processing

With current configuration:
- **Hugging Face Papers**: ~100-500 new papers per day
- **GitHub Stars**: ~1,000 repositories updated per day (daily) or 4,500/hour (hourly)
- **Citations**: ~2,000 papers processed per day (daily) or 2,800/hour (hourly)
- **URL Extraction**: ~50 papers/hour (1,200 papers/day with 24/7 operation)
- **Total Runtime**: ~1-2 hours for all daily jobs, continuous for hourly jobs

## 🔮 Future Expansion

The cron system is designed for easy expansion:
- **Weekly Jobs**: Repository analysis, performance reports
- **Monthly Jobs**: Database optimization, analytics reports
- **Custom Jobs**: Easy to add using the base classes
- **Notifications**: Email/Slack alerts for failures

---

## 📞 Support

For questions or issues with cron jobs:
1. Check the logs first: `cron/logs/`
2. Test manually with debug logging
3. Verify environment variables are set
4. Check system cron logs for scheduling issues
5. Refer to main project documentation in `/docs/`

**Remember**: Always use `uv run --env-file backend/keys.env` for all cron job executions!
