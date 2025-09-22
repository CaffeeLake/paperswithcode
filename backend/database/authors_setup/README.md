# Authors Setup for PapersWithCode

This directory contains scripts to set up and populate the authors and paper_authors tables with data from the PapersWithCode JSON dump.

## Overview

The authors system provides:
- **Authors table**: Stores author information with Hugging Face integration support
- **Paper_authors junction table**: Links papers to authors with ordering information
- **Smart name parsing**: Handles various author name formats intelligently
- **Deduplication**: Prevents duplicate authors in the database
- **Author ordering**: Maintains the order of authors as they appear in papers

## Prerequisites

1. **PostgreSQL database** with papers table already set up
2. **Papers data** already imported (see `../papers_setup/`)
3. **Python dependencies** installed via uv

## Quick Setup

### Step 1: Create Authors Tables

Run the SQL schema to create the authors and paper_authors tables:

```bash
# Connect to PostgreSQL and run the schema
sudo -u postgres psql -d paperswithcode -f backend/database/authors_setup/add_authors_tables.sql
```

### Step 2: Grant Permissions (if using application user)

If you have a specific application user, grant permissions:

```bash
# Grant table permissions
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON TABLE authors TO paperswithcode_user;"
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON TABLE paper_authors TO paperswithcode_user;"

# Grant sequence permissions (for auto-incrementing IDs)
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON SEQUENCE authors_id_seq TO paperswithcode_user;"
```

### Step 3: Verify Table Creation

Check that the tables were created successfully:

```sql
-- Connect to your database
psql -U postgres -d paperswithcode

-- List tables (should see authors and paper_authors)
\dt

-- Check table structure
\d authors
\d paper_authors

-- Check views
\dv
```

### Step 4: Populate Authors Data

The population script offers several modes:

#### Test Mode (Recommended First)
Process only 100 papers to test the setup:

```bash
cd /root/python_projects/paperswithcode
uv run backend/database/authors_setup/populate_authors.py --test
```

#### Dry Run Mode
See what would be processed without making database changes:

```bash
uv run backend/database/authors_setup/populate_authors.py --dry-run --limit 500
```

#### Production Mode
Process all papers from the dataset:

```bash
uv run backend/database/authors_setup/populate_authors.py --production
```

#### Custom Batch
Process a specific number of papers:

```bash
uv run backend/database/authors_setup/populate_authors.py --limit 1000
```

## Database Schema

### Authors Table
```sql
CREATE TABLE authors (
    id BIGSERIAL PRIMARY KEY,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,

    -- Hugging Face integration
    hf_username VARCHAR(255) UNIQUE,
    hf_id VARCHAR(50) UNIQUE,
    hf_avatar_url VARCHAR(500),
    hf_status VARCHAR(50),
    hf_is_pro BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Paper_Authors Junction Table
```sql
CREATE TABLE paper_authors (
    paper_id BIGINT NOT NULL,
    author_id BIGINT NOT NULL,
    author_order INTEGER DEFAULT 1,

    PRIMARY KEY (paper_id, author_id),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
);
```

### Useful Views

The setup creates helpful views:

- **`papers_with_authors`**: Papers with comma-separated author lists
- **`authors_with_paper_count`**: Authors with their paper counts

## Name Parsing Logic

The script includes intelligent name parsing that handles:

### Standard Formats
- `"John Smith"` → first_name: "John", last_name: "Smith"
- `"John A. Smith"` → first_name: "John A.", last_name: "Smith"
- `"Smith, John"` → first_name: "John", last_name: "Smith"

### Complex Cases
- `"John Smith Jr."` → first_name: "John", last_name: "Smith Jr."
- `"Dr. John Smith"` → first_name: "Dr. John", last_name: "Smith"
- `"María José García-López"` → first_name: "María José", last_name: "García-López"

### Edge Cases
- Single names are treated as last names
- Empty/invalid names become "Unknown Author"
- Handles international characters and diacritics

## Performance Features

- **Streaming JSON parsing**: Handles 2.2GB file without memory issues
- **Author deduplication**: In-memory cache prevents duplicate database queries
- **Batch processing**: Periodic commits for better performance
- **Progress reporting**: Real-time status updates
- **Error handling**: Continues processing despite individual failures

## Usage Examples

After importing, you can query the data:

```sql
-- Count total authors
SELECT COUNT(*) FROM authors;

-- Find papers by author
SELECT p.title, p.arxiv_id, p.date_published
FROM papers_with_authors p
WHERE p.authors ILIKE '%Hinton%';

-- Get most prolific authors
SELECT full_name, paper_count
FROM authors_with_paper_count
ORDER BY paper_count DESC
LIMIT 10;

-- Find co-authors of a specific author
SELECT DISTINCT a2.first_name || ' ' || a2.last_name as coauthor
FROM authors a1
JOIN paper_authors pa1 ON a1.id = pa1.author_id
JOIN paper_authors pa2 ON pa1.paper_id = pa2.paper_id
JOIN authors a2 ON pa2.author_id = a2.id
WHERE a1.first_name || ' ' || a1.last_name = 'Geoffrey Hinton'
AND a2.id != a1.id;
```

## Script Options

The `populate_authors.py` script accepts several command-line options:

```bash
uv run backend/database/authors_setup/populate_authors.py --help
```

Common options:
- `--json-file`: Path to papers JSON file (default: `data/papers-with-abstracts.json`)
- `--test`: Test mode (100 papers)
- `--production`: Production mode (all papers)
- `--limit N`: Process N papers
- `--dry-run`: No database writes
- `--batch-size N`: Batch size for commits (default: 100)

## Monitoring Progress

The script provides detailed statistics:

```
AUTHORS POPULATION STATISTICS
============================================================
Papers processed:           50,000
Authors created:            125,432
Authors found existing:     23,567
Paper-author links created: 187,234
Papers without authors:     12
Name parsing errors:        3
Processing time:            45.67 seconds
Processing rate:            1,095.23 papers/second
============================================================
```

## Troubleshooting

### Common Issues

1. **Permission errors**: Ensure PostgreSQL user has necessary privileges
2. **Papers not found**: Make sure papers table is populated first
3. **Memory issues**: The script uses streaming parsing to handle large files
4. **Encoding issues**: Script handles UTF-8 encoding automatically

### Validation Queries

```sql
-- Check if authors were imported correctly
SELECT COUNT(*) FROM authors;
SELECT COUNT(*) FROM paper_authors;

-- Check for papers without authors
SELECT COUNT(*) FROM papers p
LEFT JOIN paper_authors pa ON p.id = pa.paper_id
WHERE pa.paper_id IS NULL;

-- Check author name distribution
SELECT
    LENGTH(first_name) as first_len,
    LENGTH(last_name) as last_len,
    COUNT(*)
FROM authors
GROUP BY LENGTH(first_name), LENGTH(last_name)
ORDER BY COUNT(*) DESC;
```

## Integration with Frontend

Once populated, the PaperService will automatically use the authors data:

- API responses will include proper author lists
- Author search and filtering will work
- Author profile pages can be built
- Hugging Face integration is ready for future enhancement

## ArXiv API Fallback Script

For papers that are missing authors after the main population script, you can use the ArXiv API fallback script:

### populate_missing_authors_from_arxiv.py

This script fetches author information directly from the ArXiv API for papers that don't have authors in the database.

#### Features
- Fetches author data from ArXiv API for missing papers
- Handles ArXiv API rate limiting (3 seconds between requests)
- Parses author names intelligently
- Provides detailed progress reporting
- Supports dry-run mode for testing

#### Usage Examples

```bash
# Test mode (10 papers)
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv.py --test

# Production mode (all missing papers)
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv.py --production

# Custom batch
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv.py --limit 100

# Dry run (no database writes)
uv run backend/database/authors_setup/populate_missing_authors_from_arxiv.py --dry-run --limit 50
```

#### Performance Notes
- ArXiv API has rate limits (3 seconds between requests recommended)
- Processing 1000 papers takes approximately 50 minutes
- The script handles network errors and retries gracefully
- Progress is reported every 10 papers with ETA estimates

#### When to Use
- After running the main `populate_authors.py` script
- When you notice papers without authors in the frontend
- To fill gaps in author coverage from the original JSON data

## Future Enhancements

The schema supports future features:
- Hugging Face profile integration
- Author disambiguation
- ORCID integration
- Author affiliation tracking
- Citation network analysis
