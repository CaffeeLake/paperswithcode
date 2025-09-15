# Database Setup for PapersWithCode

This directory contains scripts to set up and populate a PostgreSQL database with papers data from the PapersWithCode JSON dump.

## Prerequisites

1. **PostgreSQL**: Install PostgreSQL on your system
   ```bash
   # macOS (using Homebrew)
   brew install postgresql
   brew services start postgresql

   # Ubuntu/Debian
   sudo apt-get install postgresql postgresql-contrib
   sudo systemctl start postgresql

   # Windows
   # Download and install from https://www.postgresql.org/download/windows/
   ```

2. **Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Quick Setup

1. **Create the database**:
   ```bash
   # Connect to PostgreSQL as superuser
   psql -U postgres

   # Create database
   CREATE DATABASE paperswithcode;
   \q
   ```

2. **Set up the schema**:
   ```bash
   psql -U postgres -d paperswithcode -f setup_database.sql
   ```

3. **Import papers data**:
   ```bash
   # Set your PostgreSQL password (optional, defaults to 'postgres')
   export POSTGRES_PASSWORD=your_password

   # Run the import script
   python import_papers.py
   ```

## Database Schema

The database consists of four main tables:

- **`papers`**: Main papers table with metadata, abstracts, URLs, etc.
- **`paper_authors`**: Authors for each paper (many-to-many relationship)
- **`paper_tasks`**: Tasks/categories for each paper
- **`paper_methods`**: Methods/techniques used in each paper

## Usage Examples

After importing the data, you can query the database:

```sql
-- Count total papers
SELECT COUNT(*) FROM papers;

-- Find papers by author
SELECT p.title, p.date, p.arxiv_id
FROM papers_with_authors p
WHERE p.authors ILIKE '%Hinton%';

-- Find papers about deep learning
SELECT title, abstract
FROM papers
WHERE title ILIKE '%deep learning%' OR abstract ILIKE '%deep learning%'
LIMIT 10;

-- Get papers with most authors
SELECT title, authors,
       array_length(string_to_array(authors, ', '), 1) as author_count
FROM papers_with_authors
ORDER BY author_count DESC
LIMIT 10;
```

## Script Options

The `import_papers.py` script accepts several command-line options:

```bash
python import_papers.py --help
```

Common options:
- `--json-file`: Path to the papers JSON file (default: `data/papers-with-abstracts.json`)
- `--host`: Database host (default: `localhost`)
- `--database`: Database name (default: `paperswithcode`)
- `--user`: Database user (default: `postgres`)
- `--password`: Database password (or use `POSTGRES_PASSWORD` env var)
- `--batch-size`: Batch size for commits (default: `1000`)

## Performance

- The import process handles the 2.2GB JSON file efficiently with batch processing
- Full-text search indexes are created on title and abstract fields
- The import typically takes 10-30 minutes depending on your hardware

## Troubleshooting

1. **Connection issues**: Make sure PostgreSQL is running and accessible
2. **Permission errors**: Ensure your PostgreSQL user has necessary privileges
3. **Memory issues**: If importing fails due to memory, try reducing the batch size
4. **Encoding issues**: The script handles UTF-8 encoding automatically