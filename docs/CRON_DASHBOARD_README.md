# CRON Job Dashboard - Complete Guide

## 📋 Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Features](#features)
- [Dashboard Layout](#dashboard-layout)
- [API Documentation](#api-documentation)
- [Monitored Jobs](#monitored-jobs)
- [Understanding Status](#understanding-status)
- [CLI Commands](#cli-commands)
- [Troubleshooting](#troubleshooting)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Recent Updates](#recent-updates)
- [Future Enhancements](#future-enhancements)

---

## Overview

The CRON Job Dashboard provides real-time monitoring and management of automated tasks in the PapersWithCode project. It offers a comprehensive view of all scheduled jobs, their execution status, and overall system health.

### Key Capabilities

✅ **Real-time Monitoring** - Auto-refresh every 30 seconds
✅ **Comprehensive Status** - Success, Failed, Running, Unknown states
✅ **Health Scoring** - Overall system health at a glance
✅ **Error Tracking** - Detailed error messages and logs
✅ **Schedule Display** - Cron schedules and next run predictions
✅ **Mobile Responsive** - Works on all devices
✅ **API Access** - RESTful API for programmatic monitoring

---

## Quick Start

### Access the Dashboard

**Option 1: Direct URL**
```
http://localhost:8080/cron-dashboard
```

**Option 2: Navigation**
Click the "⚡ Status" button in the main header navigation

### Start the Services

```bash
# Start both backend and frontend
cd /root/python_projects/paperswithcode
./start_services.sh
```

Or manually:
```bash
# Terminal 1: Backend
cd /root/python_projects/paperswithcode
uv run --env-file backend/keys.env backend/run_server.py

# Terminal 2: Frontend
cd /root/python_projects/paperswithcode/frontend
npm run dev
```

---

## Features

### 📊 Dashboard Components

#### 1. Summary Statistics Cards
- **Total Jobs**: Count of all monitored jobs
- **Successful**: Jobs that completed successfully
- **Failed**: Jobs with errors
- **Running**: Currently executing jobs
- **Health Score**: Overall system health (0-100%)

#### 2. Job Categories
Jobs are organized by execution frequency:
- **Hourly**: Frequent updates (GitHub stars, citations, etc.)
- **Daily**: Once-a-day operations (paper imports)
- **Weekly**: Periodic maintenance tasks
- **Monthly**: Long-term operations

#### 3. Job Details
Each job displays:
- ✅ Current status with icon and badge
- 🕐 Last execution time (human-readable: "5m ago", "2h ago")
- 📈 Execution duration (smart formatting: 2.5s, 5.3m, 2.1h)
- 📅 Cron schedule (in standard cron format)
- ⚡ Next scheduled run (predicted time)
- ❌ Error messages (if job failed)

#### 4. Interactive Controls
- **Auto-refresh Toggle**: Enable/disable automatic updates
- **Manual Refresh**: Trigger immediate data reload
- **Visual Indicators**: Spinning icons for active operations

---

## Dashboard Layout

### Visual Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ⚡ CRON Job Dashboard                        [🔄 Auto-refresh ON] [↻]  │
│  Monitor and manage automated tasks                                     │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────┬──────────┬──────────┬──────────┬──────────────┐
│ Total    │ Success  │ Failed   │ Running  │ Health Score │
│ Jobs     │          │          │          │              │
│   5      │    4     │    0     │    1     │    80%       │
└──────────┴──────────┴──────────┴──────────┴──────────────┘

🕐 Last updated: 2m ago

┌─────────────────────────────────────────────────────────────────────────┐
│ [HOURLY] Hourly Jobs                                            4 jobs  │
│─────────────────────────────────────────────────────────────────────────│
│                                                                          │
│  ✅ Update Github Stars                                     [Success]   │
│     🕐 Last: 15m ago   📈 Duration: 6.3m   📅 0 * * * *                │
│     ⚡ Next: in 45m                                                     │
│                                                                          │
│  ✅ Calculate Trending Scores                               [Success]   │
│     🕐 Last: 8m ago    📈 Duration: 9.9m   📅 30 * * * *               │
│     ⚡ Next: in 22m                                                     │
│                                                                          │
│  ✅ Extract Urls                                            [Success]   │
│     🕐 Last: 3m ago    📈 Duration: 24.9s  📅 45 * * * *               │
│     ⚡ Next: in 42m                                                     │
│                                                                          │
│  ✅ Update Citations                                        [Success]   │
│     🕐 Last: 18m ago   📈 Duration: 0.4s   📅 30 * * * *               │
│     ⚡ Next: in 12m                                                     │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ [DAILY] Daily Jobs                                              1 job   │
│─────────────────────────────────────────────────────────────────────────│
│                                                                          │
│  ✅ Import Hf Daily Papers                                  [Success]   │
│     🕐 Last: 11h ago   📈 Duration: 34.6s  📅 0 3 * * 2-6              │
│     ⚡ Next: in 13h                                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Color Coding

**Status Badges:**
- ✅ **Success**: Green (#10B981)
- ❌ **Failed**: Red (#EF4444)
- 🔄 **Running**: Blue (#3B82F6) with spinning icon
- ❓ **Unknown**: Gray (#6B7280)

**Category Badges:**
- **HOURLY**: Blue (#3B82F6)
- **DAILY**: Purple (#8B5CF6)
- **WEEKLY**: Orange (#F59E0B)
- **MONTHLY**: Pink (#EC4899)

**Health Score Colors:**
- 🟢 **80-100%**: Green - Healthy
- 🟡 **60-79%**: Yellow - Warning
- 🔴 **0-59%**: Red - Critical

### Time Formatting

Human-readable relative times:
```
Just now          < 1 minute
5m ago            5 minutes ago
2h ago            2 hours ago
3d ago            3 days ago
Oct 8, 10:30 AM   > 7 days ago (absolute)
```

Future times (Next run):
```
in 5m             5 minutes from now
in 2h             2 hours from now
in 3d             3 days from now
```

### Duration Formatting

Smart formatting based on duration:
```
2.5s      < 60 seconds
5.3m      1-60 minutes
2.1h      > 1 hour
```

---

## API Documentation

### Endpoints

#### GET `/api/v1/cron/status`

Returns comprehensive status of all CRON jobs.

**Query Parameters:**
- `days` (optional): Number of days to look back (1-7, default: 1)

**Response:**
```json
{
  "timestamp": "2025-10-11T12:48:45.528270Z",
  "jobs": [
    {
      "job_name": "update_github_stars",
      "category": "hourly",
      "status": "success",
      "last_run": "2025-10-11T12:06:18Z",
      "duration": 378.0,
      "is_running": false,
      "error": null,
      "next_run": "2025-10-11T13:00:00Z",
      "schedule": "0 * * * *"
    }
  ],
  "summary": {
    "total_jobs": 5,
    "success": 5,
    "failed": 0,
    "running": 0,
    "unknown": 0,
    "health_score": 100.0
  }
}
```

#### GET `/api/v1/cron/job/{job_name}`

Returns detailed history for a specific job.

**Query Parameters:**
- `days` (optional): Number of days of history (1-30, default: 3)

**Response:**
```json
{
  "job_name": "update_github_stars",
  "current_status": {
    "date": "20251011",
    "status": "success",
    "last_run": "2025-10-11T12:06:18Z",
    "duration": 378.0,
    "error": null
  },
  "history": [...],
  "metrics": {
    "total_runs": 15,
    "successful_runs": 14,
    "failed_runs": 1,
    "success_rate": 93.33,
    "avg_duration": 365.2
  }
}
```

#### GET `/api/v1/cron/health`

Simple health check for critical jobs.

**Response:**
```json
{
  "healthy": true,
  "timestamp": "2025-10-11T12:48:45.528270Z",
  "issues": [],
  "message": "All critical jobs healthy"
}
```

### API Usage Examples

```bash
# Get all jobs status
curl http://localhost:8000/api/v1/cron/status

# Get specific job details with 7 days history
curl http://localhost:8000/api/v1/cron/job/update_github_stars?days=7

# Check system health
curl http://localhost:8000/api/v1/cron/health

# Format with jq
curl -s http://localhost:8000/api/v1/cron/status | jq '.summary'
```

---

## Monitored Jobs

### Hourly Jobs

#### 1. Update GitHub Stars (`update_github_stars`)
- **Schedule**: `0 * * * *` (Every hour at :00)
- **Purpose**: Updates star counts for GitHub repositories
- **Importance**: Critical for trending calculations
- **Features**: Optimized for low memory usage

#### 2. Calculate Trending Scores (`calculate_trending_scores`)
- **Schedule**: `30 * * * *` (Every hour at :30)
- **Purpose**: Calculates trending scores for papers based on stars
- **Importance**: Powers the trending papers feed
- **Features**: Uses historical data for accurate trends

#### 3. Extract URLs (`extract_urls`)
- **Schedule**: `45 * * * *` (Every hour at :45)
- **Purpose**: Extracts GitHub and project URLs from abstracts
- **Importance**: Enriches paper metadata
- **Features**: Memory-optimized batch processing

#### 4. Update Citations (`update_citations`)
- **Schedule**: `30 * * * *` (Every hour at :30)
- **Purpose**: Fetches citation counts from Semantic Scholar
- **Importance**: Keeps citation metrics current
- **Features**: Rate-limited API integration

### Daily Jobs

#### 1. Import HF Daily Papers (`import_hf_daily_papers`)
- **Schedule**: `0 3 * * 2-6` (3 AM, Tuesday-Saturday)
- **Purpose**: Imports new papers from HuggingFace
- **Importance**: Primary source of new content
- **Features**: Deduplication and metadata enrichment

---

## Understanding Status

### Status Indicators

| Status | Icon | Badge | Meaning |
|--------|------|-------|---------|
| Success | ✅ | 🟢 Green | Job completed successfully |
| Failed | ❌ | 🔴 Red | Job encountered an error |
| Running | 🔄 | 🔵 Blue | Job is currently executing |
| Unknown | ❓ | ⚪ Gray | No recent execution data |

### Health Score Calculation

```
Health Score = (Successful Jobs / Total Jobs) × 100
```

**Interpretation:**
- **80-100%** 🟢 Healthy: System operating normally
- **60-79%** 🟡 Warning: Some issues detected, monitor closely
- **0-59%** 🔴 Critical: Multiple failures, immediate attention needed

### Job Status Meanings

**Success (✅)**
- Job ran to completion without errors
- All operations completed successfully
- Results saved to database
- Log shows "completed successfully"

**Failed (❌)**
- Job encountered an error during execution
- Error message is displayed in dashboard
- Full details available in log file
- Requires investigation and resolution

**Running (🔄)**
- Job is currently executing
- Process is active in the system
- Duration counter is ongoing
- Will update to Success/Failed when complete

**Unknown (❓)**
- Job hasn't run today
- No log file found for current date
- May not be scheduled or disabled
- Check crontab to verify schedule

---

## CLI Commands

### Status Checking

```bash
# View all job statuses
uv run cron/manage_cron.py status

# View specific job
uv run cron/manage_cron.py status update_github_stars

# Get comprehensive summary
uv run cron/manage_cron.py summary --detailed

# View status for specific date
uv run cron/manage_cron.py status update_github_stars 20251011
```

### Job Management

```bash
# Test a job (run immediately)
uv run cron/manage_cron.py test update_citations

# List all available jobs
uv run cron/manage_cron.py list

# View crontab schedule
crontab -l
```

### Log Management

```bash
# View today's log for a job
cat cron/logs/github_stars_optimized_$(date +%Y%m%d).log

# Follow log in real-time
tail -f cron/logs/github_stars_optimized_$(date +%Y%m%d).log

# Clean old logs (30+ days)
uv run cron/manage_cron.py cleanup

# List all log files
ls -lh cron/logs/
```

### System Monitoring

```bash
# Check if job is running
ps aux | grep update_github_stars

# Check memory usage
free -h

# Check disk space
df -h

# View recent log entries
tail -20 cron/logs/github_stars_optimized_$(date +%Y%m%d).log
```

---

## Troubleshooting

### Job Shows as "Unknown"

**Possible Causes:**
- Job hasn't run today
- Log file is missing
- Job not in crontab

**Solutions:**
1. Check if job is scheduled:
   ```bash
   crontab -l | grep job_name
   ```

2. Verify log file exists:
   ```bash
   ls cron/logs/job_name_$(date +%Y%m%d).log
   ```

3. Test run the job manually:
   ```bash
   uv run cron/manage_cron.py test job_name
   ```

### Job Shows as "Failed"

**Possible Causes:**
- Database connection issues
- API rate limits exceeded
- Out of memory
- Network connectivity problems
- Invalid data format

**Solutions:**
1. Read the error message in the dashboard

2. Check full log file:
   ```bash
   cat cron/logs/job_name_$(date +%Y%m%d).log
   ```

3. Verify database connectivity:
   ```bash
   psql -U postgres -d paperswithcode_hf -c "SELECT 1;"
   ```

4. Check system resources:
   ```bash
   free -h          # Memory
   df -h            # Disk space
   ping google.com  # Network
   ```

5. Review API rate limits:
   - Semantic Scholar: 100 requests/5 minutes
   - GitHub API: 5000 requests/hour (authenticated)

### Job Stuck "Running"

**Possible Causes:**
- Job is actually running (long operation)
- Job crashed but process remains
- Deadlock or infinite loop

**Solutions:**
1. Check if process is actually running:
   ```bash
   ps aux | grep job_name
   ```

2. Check memory usage:
   ```bash
   free -h
   top -p $(pgrep -f job_name)
   ```

3. View latest log entries:
   ```bash
   tail -20 cron/logs/job_name_$(date +%Y%m%d).log
   ```

4. If stuck, kill the process:
   ```bash
   pkill -f job_name
   ```

5. Test run manually:
   ```bash
   uv run cron/manage_cron.py test job_name
   ```

### Health Score Is Low

**Steps to Diagnose:**
1. Identify which jobs are failing in the dashboard
2. Review error messages for each failed job
3. Check system resources (memory, disk, network)
4. Verify external API availability
5. Review log files for detailed diagnostics
6. Fix issues starting with critical jobs

**Common Issues:**
- **Memory**: Low memory can cause jobs to fail
  ```bash
  free -h
  # If low, restart services or upgrade server
  ```

- **Database**: Connection pool exhausted
  ```bash
  # Restart backend service
  ./stop_services.sh
  ./start_services.sh
  ```

- **API Limits**: Rate limits exceeded
  ```bash
  # Check logs for 429 errors
  grep "429" cron/logs/*.log
  ```

### Dashboard Not Loading

**Possible Causes:**
- Backend not running
- Frontend not running
- Port conflicts

**Solutions:**
1. Check if services are running:
   ```bash
   lsof -i :8000  # Backend
   lsof -i :8080  # Frontend
   ```

2. Restart services:
   ```bash
   ./stop_services.sh
   ./start_services.sh
   ```

3. Check service logs:
   ```bash
   tail -50 logs/backend.log
   tail -50 logs/frontend.log
   ```

### Auto-refresh Not Working

**Solutions:**
1. Check browser console for errors (F12)
2. Verify API endpoint is accessible:
   ```bash
   curl http://localhost:8000/api/v1/cron/status
   ```
3. Toggle auto-refresh off and on
4. Try manual refresh button
5. Clear browser cache and reload

---

## Configuration

### Change Auto-refresh Interval

Edit `frontend/src/pages/CronDashboard.tsx`:
```typescript
refetchInterval: autoRefresh ? 30000 : false, // Change 30000 to desired ms
```

Common values:
- `10000` - 10 seconds (aggressive)
- `30000` - 30 seconds (default)
- `60000` - 1 minute (relaxed)

### Add Job to Critical List

For health check monitoring, edit `backend/routers/cron.py`:
```python
critical_jobs = [
    "github_stars_optimized",
    "update_citations_hourly",
    "extract_urls_hourly",
    "your_new_job",  # Add here
]
```

### Add New Job to Dashboard

1. Create the job script in appropriate directory:
   - `cron/hourly/` for hourly jobs
   - `cron/daily/` for daily jobs
   - `cron/weekly/` for weekly jobs
   - `cron/monthly/` for monthly jobs

2. Add to crontab:
   ```bash
   crontab -e
   ```

3. Dashboard will automatically detect and display it!

**No code changes needed** - the dashboard uses automatic job discovery.

### Customize Job Display Name

Edit `frontend/src/pages/CronDashboard.tsx`, update the `formatJobName` function:
```typescript
const formatJobName = (jobName: string): string => {
  // Add custom mappings here
  const customNames: Record<string, string> = {
    "update_github_stars": "GitHub Stars Update",
    "your_job": "Your Custom Name"
  };

  return customNames[jobName] || jobName
    .replace(/_/g, " ")
    .split(" ")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
};
```

---

## Architecture

### Technology Stack

**Backend:**
- **Framework**: FastAPI
- **Data Models**: Pydantic for validation
- **Log Parsing**: Custom utilities (`cron/utils/cron_helpers.py`)
- **System Integration**: Subprocess for crontab access
- **Response Format**: JSON with ISO 8601 timestamps (UTC)

**Frontend:**
- **Framework**: React 18 + TypeScript
- **Styling**: Tailwind CSS + shadcn/ui components
- **Data Fetching**: TanStack Query (React Query)
- **Routing**: React Router v6
- **Icons**: lucide-react
- **State Management**: React hooks + Query cache

### File Structure

```
paperswithcode/
├── backend/
│   ├── main.py                          # FastAPI app with cron router
│   └── routers/
│       └── cron.py                      # CRON API endpoints (407 lines)
├── frontend/
│   └── src/
│       ├── App.tsx                      # Routes including /cron-dashboard
│       ├── components/
│       │   └── Header.tsx               # Navigation with Status link
│       └── pages/
│           └── CronDashboard.tsx        # Dashboard UI (420 lines)
├── cron/
│   ├── hourly/                          # Hourly job scripts
│   ├── daily/                           # Daily job scripts
│   ├── weekly/                          # Weekly job scripts
│   ├── monthly/                         # Monthly job scripts
│   ├── logs/                            # Job execution logs
│   ├── utils/
│   │   └── cron_helpers.py              # Log parsing utilities
│   └── manage_cron.py                   # CLI management tool
└── docs/
    └── CRON_DASHBOARD_README.md         # This file
```

### Data Flow

```
CRON Jobs (via crontab)
    ↓
Log Files (cron/logs/*.log)
    ↓
Backend API (cron_helpers.py parses logs)
    ↓
JSON Response (REST API /api/v1/cron/*)
    ↓
Frontend Dashboard (TanStack Query fetches)
    ↓
User Interface (React components render)
```

### Key Backend Features

1. **Automatic Job Discovery**: Scans `cron/` directories to find all scripts
2. **Active Job Detection**: Reads crontab to get scheduled jobs
3. **Next Run Calculation**: Estimates next execution based on cron schedule
4. **Job Description Extraction**: Pulls docstrings from job scripts
5. **Log Parsing**: Extracts status, duration, errors from log files
6. **Name Mapping**: Handles differences between script and log names
7. **Timezone Handling**: All timestamps in UTC with ISO 8601 format

### Key Frontend Features

1. **TanStack Query Integration**: Efficient data fetching with caching
2. **Auto-refresh**: Configurable interval (default 30s)
3. **Loading States**: Smooth loading indicators
4. **Error Handling**: User-friendly error messages
5. **Time Formatting**: Human-readable relative times
6. **Duration Formatting**: Smart formatting (s/m/h)
7. **Health Score**: Color-coded visual indicator
8. **Responsive Design**: Mobile-friendly layout
9. **Accessibility**: WCAG AA compliant

---

## Recent Updates

### October 11, 2025 - Timezone Fix

**Issue**: Dashboard was showing incorrect times for "Last run" and "Next run"
- Hourly jobs showed "Last: 2h ago" when they ran 45 minutes ago
- Next run times showed "Next: Overdue" when they were in the future

**Root Cause**: Backend returning timestamps without timezone info, causing browser to interpret them in local timezone instead of UTC.

**Fix Applied**:
1. Changed all `datetime.now()` to `datetime.utcnow()` in backend
2. Updated timestamp format to ISO 8601 with "Z" suffix: `2025-10-11T12:06:18Z`
3. Added conversion for log timestamps to UTC format
4. Created separate `formatFutureDate()` function in frontend for next run times

**Result**: ✅ All times now display correctly
- "Last: 42m ago" instead of "Last: 2h ago"
- "Next: in 11m" instead of "Next: Overdue"

### October 11, 2025 - Duration Display Fix

**Issue**: Duration was not showing for GitHub Stars and Trending Score jobs

**Root Cause**: These jobs log "Runtime: X minutes" instead of "Duration: X seconds"

**Fix Applied**: Enhanced `cron_helpers.py` to parse both formats:
```python
elif "Runtime:" in line:
    # Handle "Runtime: X minutes" or "Runtime: X seconds"
    runtime_str = line.split("Runtime:")[-1].strip()
    parts = runtime_str.split()
    value = float(parts[0])
    unit = parts[1].lower()
    if "minute" in unit:
        status["duration"] = value * 60
    elif "second" in unit:
        status["duration"] = value
    elif "hour" in unit:
        status["duration"] = value * 3600
```

**Result**: ✅ Duration now displays for all jobs
- GitHub Stars: 378.0s (6.3 minutes)
- Trending Scores: 594.0s (9.9 minutes)

---

## Future Enhancements

Potential improvements for the dashboard:

### Short-term (High Priority)

1. **Historical Charts**
   - Execution time trends over days/weeks
   - Success rate visualization
   - Health score history graph

2. **Email Notifications**
   - Alert on job failures
   - Daily health summary
   - Configurable thresholds

3. **Job Control from UI**
   - Manual trigger button for each job
   - Pause/resume functionality
   - Schedule modification

### Medium-term

4. **Performance Metrics**
   - Average execution time per job
   - Resource consumption tracking
   - Processing throughput metrics
   - Comparison with baseline

5. **Advanced Filtering**
   - Filter jobs by status
   - Search by job name
   - Category show/hide toggles
   - Date range selection

6. **Export Functionality**
   - Download status reports (CSV/JSON)
   - Export historical data
   - Scheduled reports

### Long-term

7. **Webhook Integration**
   - Slack notifications
   - Discord webhooks
   - Custom webhook endpoints
   - Microsoft Teams integration

8. **Real-time Updates**
   - WebSocket streaming
   - Live log tailing
   - Real-time status changes
   - Push notifications

9. **Dark Mode**
   - Theme support
   - User preference storage
   - System theme detection

10. **Mobile App**
    - Native iOS app
    - Native Android app
    - Push notifications
    - Offline status viewing

11. **Advanced Analytics**
    - Predictive failure detection
    - Resource optimization suggestions
    - Performance benchmarking
    - Anomaly detection

12. **Multi-environment Support**
    - Staging vs Production
    - Environment switcher
    - Separate configurations
    - Cross-environment comparison

---

## Best Practices

### Daily Operations

- ✅ Check dashboard **once per day** minimum
- ✅ Keep health score **above 80%**
- ✅ Fix failed jobs **within 24 hours**
- ✅ Review error messages promptly
- ✅ Monitor critical jobs closely
- ✅ Keep auto-refresh **ON** during monitoring sessions

### Weekly Reviews

- ✅ Review average execution durations
- ✅ Check for recurring error patterns
- ✅ Verify all jobs ran as scheduled
- ✅ Clean old log files (if >30 days)
- ✅ Test manual job execution
- ✅ Update job documentation if needed

### Monthly Tasks

- ✅ Review and optimize slow jobs
- ✅ Update cron schedules if needed
- ✅ Check disk space for log files
- ✅ Review system resource usage
- ✅ Update critical jobs list
- ✅ Document any configuration changes

### Monitoring Tips

1. **Use Auto-refresh Wisely**
   - Enable during active monitoring
   - Disable to reduce server load
   - 30-second interval is usually sufficient

2. **Understand Your Jobs**
   - Know which jobs are critical
   - Understand typical execution times
   - Recognize normal vs abnormal patterns

3. **Act on Failures Quickly**
   - Read error messages carefully
   - Check logs for full context
   - Fix root cause, not just symptoms

4. **Keep Logs Clean**
   - Run cleanup monthly
   - Archive important logs
   - Monitor disk space usage

---

## Quick Reference

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `R` or `F5` | Manual refresh |
| `A` | Toggle auto-refresh |
| `Esc` | Close modals (future) |

### Status Icons Quick Guide

| Icon | Status | Action Needed |
|------|--------|---------------|
| ✅ | Success | None - job healthy |
| ❌ | Failed | Investigate immediately |
| 🔄 | Running | Monitor for completion |
| ❓ | Unknown | Check if scheduled |

### Health Score Guide

| Score | Status | Action |
|-------|--------|--------|
| 80-100% | 🟢 Healthy | Monitor normally |
| 60-79% | 🟡 Warning | Investigate issues |
| 0-59% | 🔴 Critical | Fix immediately |

### Log File Locations

**Path**: `/root/python_projects/paperswithcode/cron/logs/`
**Format**: `{job_name}_{YYYYMMDD}.log`
**Retention**: 30 days (automatic cleanup)

### Quick Links

- **Dashboard**: [http://localhost:8080/cron-dashboard](http://localhost:8080/cron-dashboard)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/api/v1/cron/health](http://localhost:8000/api/v1/cron/health)

---

## Support & Resources

### Documentation
- **CRON Jobs README**: `cron/README.md`
- **Backend API**: `backend/README.md`
- **Database Guide**: `docs/POSTGRESQL_GUIDE.md`
- **API Docs**: http://localhost:8000/docs

### CLI Tools
```bash
# Management script
uv run cron/manage_cron.py --help

# View status
uv run cron/manage_cron.py status

# Test job
uv run cron/manage_cron.py test {job_name}

# Clean logs
uv run cron/manage_cron.py cleanup
```

### Troubleshooting Steps
1. Check dashboard error messages
2. Review job logs in `cron/logs/`
3. Run status check via CLI
4. Test job manually
5. Check system resources
6. Verify database connectivity
7. Review this documentation

### Getting Help
- Check logs: `cron/logs/`
- Run CLI tools: `cron/manage_cron.py`
- Review documentation: `docs/`
- Check backend logs: `logs/backend.log`
- Check frontend logs: `logs/frontend.log`

---

## Conclusion

The CRON Job Dashboard is a production-ready monitoring solution that provides:

✨ **Real-time visibility** into all automated tasks
✨ **Clean, intuitive** user interface
✨ **Comprehensive API** for programmatic access
✨ **Automatic discovery** of new jobs
✨ **Best practices** for TypeScript and Python development
✨ **Seamless integration** with existing infrastructure
✨ **Full test coverage** and production-ready code

Access the dashboard at [http://localhost:8080/cron-dashboard](http://localhost:8080/cron-dashboard) and start monitoring your automated tasks today!

---

**Document Version**: 2.0.0
**Last Updated**: October 11, 2025
**Status**: ✅ Production Ready
**Maintainer**: PapersWithCode Team
