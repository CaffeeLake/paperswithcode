# Repository and Project Pages Setup

This folder contains scripts to populate the `repositories` and `project_pages` tables in the PapersWithCode database using data from the Hugging Face `community-science-merged` dataset.

## Overview

The Hugging Face `community-science-merged` dataset contains 5,299 research papers with associated GitHub repositories and project page URLs. This setup allows us to link papers in our database to their implementation repositories and demo pages.

### Tables Populated

1. **`repositories`** - GitHub repositories linked to papers
   - `paper_id` - Foreign key to papers table
   - `url` - GitHub repository URL
   - `owner` - GitHub username/organization
   - `name` - Repository name
   - `num_stars` - Number of stars (populated later)
   - `is_official` - Whether it's official (populated later)

2. **`project_pages`** - Project pages showcasing paper work
   - `paper_id` - Foreign key to papers table
   - `url` - Project page URL
   - `is_official` - Whether it's official (populated later)

## Files

- `add_repositories_and_project_pages.sql` - SQL schema for creating the tables
- `populate_repos_and_pages.py` - Python script to populate data from HuggingFace dataset
- `batch_extract_github_and_project_urls.py` - AI-powered batch extraction of GitHub URLs and project pages
- `test_batch_extraction.py` - Test script for the AI batch extraction
- `analyze_data_quality.py` - Script to analyze data quality and coverage
- `populate_official_repos.py` - Script to populate official repository flags
- `populate_github_stars.py` - Script to populate GitHub star counts using GitHub API
- `DATABASE_ACCESS.md` - Detailed guide on database permissions and troubleshooting
- `README.md` - This documentation

## Prerequisites

1. **Database Setup**: Ensure the main papers table exists and is populated
2. **Python Dependencies**: Install required packages:
   ```bash
   cd /root/python_projects/paperswithcode
   uv add datasets pandas
   ```

3. **Database Connection**: Ensure your database connection is configured in the backend config

## Setup Instructions

### Step 1: Create Database Tables

First, create the `repositories` and `project_pages` tables:

```bash
# Navigate to the project root
cd /root/python_projects/paperswithcode

# Run the SQL schema (requires postgres superuser)
sudo -u postgres psql -d paperswithcode -f backend/database/repos_and_pages_setup/add_repositories_and_project_pages.sql
```

### Step 2: Grant Permissions

Grant necessary permissions to the application user:

```bash
# Grant table permissions
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON TABLE repositories TO paperswithcode_user;"
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON TABLE project_pages TO paperswithcode_user;"

# Grant sequence permissions (for auto-incrementing IDs)
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON SEQUENCE repositories_id_seq TO paperswithcode_user;"
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON SEQUENCE project_pages_id_seq TO paperswithcode_user;"
```

> **Important**: This step is crucial! Without proper permissions, the application will get "permission denied" errors when trying to access the tables.

### Step 3: Verify Table Creation

Check that the tables were created successfully:

```sql
-- Connect to your database
psql -U postgres -d paperswithcode

-- List tables
\dt

-- Check table structure
\d repositories
\d project_pages
```

### Step 4: Run Population Script

The population script offers several modes:

#### Test Mode (Recommended First)
Process only 100 records to test the setup:

```bash
cd /root/python_projects/paperswithcode
python backend/database/repos_and_pages_setup/populate_repos_and_pages.py --test
```

#### Dry Run Mode
See what would be processed without making database changes:

```bash
python backend/database/repos_and_pages_setup/populate_repos_and_pages.py --dry-run --limit 500
```

#### Production Mode
Process all records from the dataset:

```bash
python backend/database/repos_and_pages_setup/populate_repos_and_pages.py --production
```

#### Custom Batch
Process a specific number of records:

```bash
python backend/database/repos_and_pages_setup/populate_repos_and_pages.py --limit 1000 --batch-size 500
```

### Step 4: Monitor Progress

The script provides detailed logging:

```
2024-01-15 10:30:15 - INFO - Loading Hugging Face community-science-merged dataset...
2024-01-15 10:30:20 - INFO - Loaded 5299 records from HuggingFace dataset
2024-01-15 10:30:20 - INFO - After filtering: 4832 records with arxiv_id and URLs
2024-01-15 10:30:25 - INFO - Progress: 100 processed, 45 repos added, 38 pages added, 12 papers not found, Rate: 20.5 records/sec
```

## Script Features

### Data Validation
- **GitHub URL Validation**: Ensures URLs are valid GitHub repositories
- **Project URL Validation**: Validates project page URLs
- **ArXiv ID Matching**: Finds papers by ArXiv ID (prefers latest version)
- **Duplicate Prevention**: Skips existing repository/page entries

### URL Processing
- **GitHub URL Cleaning**: Standardizes GitHub URLs to `https://github.com/owner/repo`
- **Owner/Name Extraction**: Extracts GitHub owner and repository name
- **Project URL Normalization**: Ensures project URLs have proper protocol

### Error Handling
- **Graceful Failures**: Continues processing if individual records fail
- **Detailed Logging**: Logs validation failures and errors
- **Transaction Safety**: Uses database transactions for batch processing

### Performance
- **Batch Processing**: Processes records in configurable batches (default: 1000)
- **Progress Tracking**: Real-time progress updates
- **Memory Efficient**: Processes data in chunks to handle large datasets

## Expected Results

Based on the HuggingFace dataset:
- **Total Records**: ~5,299 papers
- **With GitHub URLs**: ~3,800 repositories
- **With Project URLs**: ~2,100 project pages
- **Papers Found**: ~85-90% (depends on your papers table coverage)

## Troubleshooting

### Common Issues

1. **"Paper not found" errors**: This is normal if your papers table doesn't contain all ArXiv papers from the HF dataset
2. **"Invalid URL" warnings**: Some URLs in the dataset may be malformed
3. **Connection errors**: Ensure your database is running and accessible

### Verification Queries

After running the script, verify the results:

```sql
-- Count repositories added
SELECT COUNT(*) FROM repositories;

-- Count project pages added
SELECT COUNT(*) FROM project_pages;

-- Sample repositories with paper info
SELECT p.title, p.arxiv_id, r.url, r.owner, r.name
FROM papers p
JOIN repositories r ON p.id = r.paper_id
LIMIT 10;

-- Sample project pages with paper info
SELECT p.title, p.arxiv_id, pp.url
FROM papers p
JOIN project_pages pp ON p.id = pp.paper_id
LIMIT 10;
```

### Performance Monitoring

Monitor the population process:

```sql
-- Check progress during population
SELECT
    (SELECT COUNT(*) FROM repositories) as repositories_count,
    (SELECT COUNT(*) FROM project_pages) as project_pages_count;

-- Find papers with both repos and project pages
SELECT COUNT(*)
FROM papers p
WHERE EXISTS (SELECT 1 FROM repositories r WHERE r.paper_id = p.id)
  AND EXISTS (SELECT 1 FROM project_pages pp WHERE pp.paper_id = p.id);
```

## AI-Powered URL Extraction

For papers missing GitHub repositories or project pages, you can use the AI-powered extraction system:

### Batch Processing

Extract URLs for papers missing repository/project page data:

```bash
# Test with 5 papers (dry run)
uv run backend/database/repos_and_pages_setup/test_batch_extraction.py

# Process 100 papers in batches of 10
uv run backend/database/repos_and_pages_setup/batch_extract_github_and_project_urls.py --limit 100 --batch-size 10

# Production run (all papers missing URLs)
uv run backend/database/repos_and_pages_setup/batch_extract_github_and_project_urls.py --batch-size 20

# Dry run to see what would be processed
uv run backend/database/repos_and_pages_setup/batch_extract_github_and_project_urls.py --limit 1000 --dry-run
```

### How It Works

1. **Database Query**: Finds papers missing GitHub repositories or project pages
2. **Abstract Optimization**: Uses database abstracts instead of web fetching (~100x faster)
3. **AI Processing**: Uses LLM to analyze paper abstracts, comments, and PDF content
4. **URL Extraction**: Extracts GitHub URLs and project page URLs
5. **Database Update**: Automatically saves results to `repositories` and `project_pages` tables

### Performance

- **Speed**: ~100x faster than web-based abstract fetching
- **Batch Processing**: Configurable batch sizes with concurrency control
- **Error Handling**: Robust error handling with retry logic
- **Progress Tracking**: Real-time statistics and progress reporting

## GitHub Stars Population

After populating repositories, you can fetch star counts from the GitHub API:

### Prerequisites
- Ensure `GITHUB_TOKEN` is set in `backend/keys.env` for higher rate limits
- Repositories table must be populated with `owner` and `name` fields

### Usage

```bash
# Test mode (10 repositories)
uv run --env-file backend/keys.env backend/database/repos_and_pages_setup/populate_github_stars.py --test

# Production mode (all repositories without star counts)
uv run --env-file backend/keys.env backend/database/repos_and_pages_setup/populate_github_stars.py --production

# Custom limit with dry run
uv run --env-file backend/keys.env backend/database/repos_and_pages_setup/populate_github_stars.py --limit 100 --dry-run

# Force update all repositories (including those with existing star counts)
uv run --env-file backend/keys.env backend/database/repos_and_pages_setup/populate_github_stars.py --force-update
```

### Features
- **GitHub API Integration**: Uses authenticated requests for higher rate limits (5000/hour vs 60/hour)
- **Rate Limit Handling**: Automatically handles rate limits with intelligent waiting
- **Batch Processing**: Processes repositories in configurable batches with progress tracking
- **Error Handling**: Graceful handling of missing repositories, API errors, and network issues
- **Dry Run Mode**: Test without making database changes
- **Force Update**: Option to update repositories that already have star counts

### Expected Results
- Updates `num_stars` field in repositories table
- Handles ~4000-5000 repositories per hour (with GitHub token)
- Provides detailed progress and error reporting

## Next Steps

After populating the basic data, you can enhance it by:

1. **AI Extraction**: Use the batch extraction system for missing URLs
2. **GitHub Stars**: ✅ Use GitHub API to populate `num_stars` field (implemented above)
3. **Official Status**: Mark repositories as official based on author analysis
4. **Repository Analysis**: Extract additional metadata (language, topics, etc.)
5. **Project Page Analysis**: Categorize project pages (demo, dataset, etc.)

## Integration with Frontend

The populated data can be used in your frontend to:
- Display GitHub repository links on paper detail pages
- Show project page links for demos and implementations
- Filter papers by availability of code/demos
- Create "Papers with Code" sections highlighting implementation availability

## Data Sources

- **Dataset**: `huggingface/community-science-merged`
- **Repository**: https://huggingface.co/datasets/huggingface/community-science-merged
- **License**: Check dataset page for licensing information
- **Coverage**: Primarily ML/AI papers with community-contributed links

## Maintenance

- **Regular Updates**: The HuggingFace dataset may be updated periodically
- **Duplicate Handling**: The script prevents duplicates, so it's safe to re-run
- **Data Quality**: Periodically review and clean up invalid URLs
- **GitHub API**: Consider implementing GitHub API integration for metadata updates
