# GitHub URLs and Project Pages Extraction - Hourly CRON Job Guide

## Overview

This hourly CRON job uses AI-powered extraction to find GitHub repositories and project pages from academic papers. It processes papers that haven't been analyzed yet (where `urls_extracted = FALSE`) and intelligently extracts official URLs.

## Quick Start

### 1. Prerequisites

Ensure you have the OpenRouter API key set in `backend/keys.env`:

```bash
PWC_OPENROUTER_API_KEY=your_openrouter_api_key_here
```

### 2. Test the Job Manually

Before scheduling, test the job:

```bash
# Test with a small limit (5 papers)
cd /root/python_projects/paperswithcode
uv run --env-file backend/keys.env cron/hourly/extract_urls.py

# Or use the wrapper script
./cron/run_extract_urls_hourly.sh
```

### 3. Schedule in Crontab

Add to your crontab (`crontab -e`):

```bash
# Run hourly at 45 minutes past the hour
45 * * * * cd /root/python_projects/paperswithcode && uv run --env-file backend/keys.env cron/hourly/extract_urls.py
```

## Configuration

The job is configured in `/root/python_projects/paperswithcode/cron/hourly/extract_urls.py`:

```python
self.papers_per_hour = 50      # Papers to process per run
self.batch_size = 10           # Batch size (memory optimized for 4GB RAM)
self.start_year = 2014         # Only process papers from 2014 onwards
self.use_paid_tier = True      # Use paid tier rate limits
```

### Adjusting Processing Rate

**For Free Tier (50 requests/day)**:
- Set `self.papers_per_hour = 2` (run 24 hours = 48 papers/day)
- Only run once per day instead of hourly
- Schedule: `0 3 * * * ...` (3:00 AM daily)

**For Paid Tier (1,000 requests/day)**:
- Set `self.papers_per_hour = 50` (default, safe with buffer)
- Run hourly for 1,200 papers/day capacity
- Can increase to 60-80 papers/hour if needed

**Memory Constrained Systems (< 4GB RAM)**:
- Reduce `self.batch_size = 5` for lower memory usage
- Keep `self.papers_per_hour = 50` (processing rate is batch-independent)

## How It Works

### Processing Logic

1. **Query Selection**: Finds papers where:
   - `urls_extracted = FALSE` (not yet processed)
   - Has abstract and ArXiv ID
   - Published from 2014 onwards
   - Ordered by newest first

2. **AI Extraction**: Uses OpenRouter AI models to:
   - Download and analyze paper PDFs
   - Extract GitHub repository URLs
   - Find project page URLs
   - Verify URL validity

3. **Database Updates**:
   - Saves GitHub URLs to `repositories` table
   - Saves project pages to `project_pages` table
   - Associates with paper via junction tables
   - Marks paper as `urls_extracted = TRUE`

4. **Error Handling**:
   - **Critical errors** (rate limits, PDF failures): Paper stays `FALSE`, can retry
   - **Non-critical errors**: Paper marked `TRUE`, no URLs found
   - Graceful handling of API quotas and network issues

### Coordination with HF API Import

The job intelligently skips papers already processed by the Hugging Face API import:

- HF API papers have `urls_extracted = TRUE` (set during import)
- Only processes papers with `urls_extracted = FALSE`
- No complex query logic needed - simple and efficient

### URL Priority

- **HF API URLs**: Always highest priority (source='hf_api')
- **AI-extracted URLs**: Secondary (source='ai_extraction')
- AI extraction skips if official URL exists (`skip_if_official_exists=True`)

## Monitoring

### Log Files

Logs are saved to `cron/logs/extract_urls_hourly_YYYYMMDD.log`:

```bash
# View today's log
tail -f cron/logs/extract_urls_hourly_$(date +%Y%m%d).log

# View wrapper log
tail -f cron/logs/extract_urls_wrapper_$(date +%Y%m%d).log
```

### Log Output

The job logs comprehensive statistics:

```
================================================================================
Starting hourly GitHub URLs and Project Pages extraction
================================================================================
Configuration:
  Papers per run: 50
  Batch size: 10
  Start year: 2014
  Rate tier: Paid

📋 Sample of papers to process:
  1. 2409.12345 - Example Paper Title...
     URLs Extracted: False
     Abstract length: 1234 chars

🤖 Starting AI extraction for 2409.12345...
🔗 2409.12345: GitHub=✅ https://github.com/user/repo, Project=✅ https://example.com
💾 Saved GitHub repo: https://github.com/user/repo
💾 Saved project page: https://example.com
✅ 2409.12345: GitHub=✅ Saved, Project=✅ Saved

================================================================================
URL Extraction completed successfully
================================================================================
Papers processed: 50
Papers with GitHub: 35
Papers with Project Page: 28
Papers with both: 20
Papers with neither: 15
API errors: 0
Papers skipped (critical errors): 0
GitHub URL success rate: 70.0%
Project page success rate: 56.0%
Daily capacity (24/7): ~1200 papers
Estimated for 10K papers: 8.3 days
```

### Using manage_cron.py

Check job status:

```bash
# List all jobs
uv run --env-file backend/keys.env cron/manage_cron.py list

# Check status
uv run --env-file backend/keys.env cron/manage_cron.py status extract_urls

# View comprehensive summary
uv run --env-file backend/keys.env cron/manage_cron.py summary
```

## Performance

### Expected Throughput

- **Hourly**: 50 papers/hour
- **Daily (24/7)**: 1,200 papers/day
- **Monthly**: ~36,000 papers/month
- **Time for 10K papers**: ~8.3 days

### API Usage

- **Rate Limit**: 20 requests/minute, 1,000 requests/day (paid tier)
- **Actual Usage**: ~50 requests/hour = 1,200/day with 24/7 operation
- **Utilization**: 80% of daily quota (safe buffer for retries)

### Memory Usage

- **System**: 4GB RAM
- **Process**: ~500-800MB typical
- **Batch Size**: 10 papers (optimized for low memory)
- **Safety Limits**: Stops if memory exceeds 3.5GB

## Database Queries

### Check papers needing extraction

```sql
-- Count papers needing extraction
SELECT COUNT(*)
FROM papers
WHERE urls_extracted = FALSE
  AND abstract IS NOT NULL
  AND arxiv_id IS NOT NULL
  AND date_published >= '2014-01-01';

-- View sample papers
SELECT id, arxiv_id, title, date_published
FROM papers
WHERE urls_extracted = FALSE
  AND abstract IS NOT NULL
  AND arxiv_id IS NOT NULL
  AND date_published >= '2014-01-01'
ORDER BY date_published DESC
LIMIT 10;
```

### Check extraction results

```sql
-- Papers with AI-extracted URLs
SELECT p.arxiv_id, p.title, r.url as github_url, pp.url as project_page
FROM papers p
LEFT JOIN paper_repositories pr ON p.id = pr.paper_id
LEFT JOIN repositories r ON pr.repository_id = r.id AND r.source = 'ai_extraction'
LEFT JOIN paper_project_pages ppp ON p.id = ppp.paper_id
LEFT JOIN project_pages pp ON ppp.project_page_id = pp.id AND pp.source = 'ai_extraction'
WHERE p.urls_extracted = TRUE
ORDER BY p.date_published DESC
LIMIT 20;
```

### Check extraction statistics

```sql
-- Extraction success rates
SELECT
  COUNT(*) as total_processed,
  COUNT(DISTINCT pr.paper_id) as papers_with_github,
  COUNT(DISTINCT ppp.paper_id) as papers_with_project_page,
  ROUND(COUNT(DISTINCT pr.paper_id)::numeric / COUNT(*)::numeric * 100, 1) as github_rate,
  ROUND(COUNT(DISTINCT ppp.paper_id)::numeric / COUNT(*)::numeric * 100, 1) as project_rate
FROM papers p
LEFT JOIN paper_repositories pr ON p.id = pr.paper_id
LEFT JOIN repositories r ON pr.repository_id = r.id AND r.source = 'ai_extraction'
LEFT JOIN paper_project_pages ppp ON p.id = ppp.paper_id
LEFT JOIN project_pages pp ON ppp.project_page_id = pp.id AND pp.source = 'ai_extraction'
WHERE p.urls_extracted = TRUE;
```

## Troubleshooting

### Common Issues

**1. "Rate limit exceeded" errors**
```
Solution: Job handles this automatically. Papers stay unprocessed and will retry.
Check: View log for rate limit messages.
Adjust: Reduce papers_per_hour in extract_urls.py
```

**2. "Failed to download PDF" errors**
```
Solution: ArXiv may be blocking or paper PDF unavailable. Paper stays unprocessed.
Check: Verify ArXiv ID is correct in database.
Manual retry: Will be attempted in next run.
```

**3. "Memory limit reached" warnings**
```
Solution: Job stops automatically when approaching limit.
Adjust: Reduce batch_size from 10 to 5 in extract_urls.py
Check: Monitor system memory with 'free -h'
```

**4. Job not running in cron**
```
Check: Verify crontab entry with 'crontab -l'
Check: View wrapper log for errors
Test: Run manually: './cron/run_extract_urls_hourly.sh'
Verify: Environment file exists: 'ls -l backend/keys.env'
```

**5. "OpenRouter API key not found"**
```
Solution: Add PWC_OPENROUTER_API_KEY to backend/keys.env
Test: 'grep OPENROUTER backend/keys.env'
Reload: Restart cron if using system environment
```

### Debug Mode

Run with verbose output:

```bash
# Manual run with debug logging
cd /root/python_projects/paperswithcode
PWC_LOG_LEVEL=DEBUG uv run --env-file backend/keys.env cron/hourly/extract_urls.py
```

### Test with Small Batch

Modify the script temporarily for testing:

```python
# In extract_urls.py, change:
self.papers_per_hour = 5  # Test with 5 papers only
```

## Best Practices

1. **Start Small**: Test with 5-10 papers before full deployment
2. **Monitor Logs**: Check logs daily for first week
3. **Track API Usage**: Monitor OpenRouter dashboard for quota
4. **Adjust Rate**: Start conservative, increase if stable
5. **Regular Cleanup**: Use log cleanup cron job weekly
6. **Database Backups**: Backup before first run

## Integration

### With HF API Import

The hourly HF API import (`import_hf_daily_papers.py`) and URL extraction work together:

1. HF import runs daily (Tue-Sat at 3:00 AM)
2. Sets `urls_extracted = TRUE` for imported papers
3. URL extraction runs hourly, skips HF papers
4. Processes legacy papers from 2014 onwards

### With Frontend

Extracted URLs automatically appear in:

- Paper detail pages (GitHub badges, project links)
- Repository listings (star counts, trending)
- Search results (filter by has-code)

## Cost Estimation

### OpenRouter Costs (Paid Tier)

Assuming $0.002 per request (varies by model):

- **Hourly**: 50 papers × $0.002 = $0.10/hour
- **Daily**: 1,200 papers × $0.002 = $2.40/day
- **Monthly**: ~36,000 papers × $0.002 = $72/month
- **For 10K papers**: 10,000 × $0.002 = $20

**Note**: Actual costs depend on:
- Model used (DeepSeek-R1, GPT-4, etc.)
- PDF size (larger PDFs = higher costs)
- Success rate (retries increase cost)

## Support

For issues or questions:
1. Check logs in `cron/logs/`
2. Test manually with debug logging
3. Verify environment variables in `backend/keys.env`
4. Check database connection
5. Review main documentation in `/docs/`

---

**Remember**: Always use `uv run --env-file backend/keys.env` when running Python scripts!
