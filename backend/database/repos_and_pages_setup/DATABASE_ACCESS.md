# Database Access Guide

This document explains how to properly access and manage the PostgreSQL database for the PapersWithCode project.

## Database Setup Overview

The project uses PostgreSQL with the following configuration:
- **Database name**: `paperswithcode`
- **Application user**: `paperswithcode_user` (limited permissions)
- **Admin user**: `postgres` (superuser)

## Permission Issue Encountered

### The Problem
When we created the `repositories` and `project_pages` tables using the `postgres` superuser:

```bash
sudo -u postgres psql -d paperswithcode -f add_repositories_and_project_pages.sql
```

The tables were owned by `postgres`, but the application connects as `paperswithcode_user`. This caused permission errors:

```
ERROR: permission denied for table repositories
ERROR: permission denied for table project_pages
```

### The Solution
We needed to grant proper permissions to the application user:

```bash
# Grant table permissions
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON TABLE repositories TO paperswithcode_user;"
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON TABLE project_pages TO paperswithcode_user;"

# Grant sequence permissions (for auto-incrementing IDs)
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON SEQUENCE repositories_id_seq TO paperswithcode_user;"
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON SEQUENCE project_pages_id_seq TO paperswithcode_user;"
```

## Database Access Methods

### 1. Application Access (Python Scripts)
The application uses the `paperswithcode_user` with limited permissions:

```python
# Uses connection settings from backend/config.py
from backend.database.connection import get_database_session

with get_database_session() as db:
    # Your database operations here
    pass
```

**Environment**: Requires `backend/keys.env` file with database credentials.

### 2. Admin Access (Table Creation, Schema Changes)
For administrative tasks, use the `postgres` superuser:

```bash
# Connect as postgres user
sudo -u postgres psql -d paperswithcode

# Or run SQL files directly
sudo -u postgres psql -d paperswithcode -f your_schema_file.sql
```

### 3. Checking Database Users and Permissions

```bash
# List all database users
sudo -u postgres psql -d paperswithcode -c "\du"

# List all tables with ownership
sudo -u postgres psql -d paperswithcode -c "\dt"

# Check permissions for a specific table
sudo -u postgres psql -d paperswithcode -c "\dp repositories"
```

## Best Practices for New Tables

When creating new tables, follow this pattern:

### 1. Create the table as postgres user
```bash
sudo -u postgres psql -d paperswithcode -f your_new_table.sql
```

### 2. Grant permissions to application user
```bash
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON TABLE your_new_table TO paperswithcode_user;"

# If the table has auto-incrementing ID
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON SEQUENCE your_new_table_id_seq TO paperswithcode_user;"
```

### 3. Test with application user
```bash
# Run your Python script to verify permissions
uv run --env-file backend/keys.env your_script.py
```

## Common Permission Commands

```bash
# Grant all permissions on a table
GRANT ALL PRIVILEGES ON TABLE table_name TO paperswithcode_user;

# Grant specific permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE table_name TO paperswithcode_user;

# Grant permissions on all tables in schema
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO paperswithcode_user;

# Grant permissions on all sequences
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO paperswithcode_user;

# Make user owner of a table (alternative approach)
ALTER TABLE table_name OWNER TO paperswithcode_user;
```

## Troubleshooting

### Permission Denied Errors
If you see `permission denied for table X`:

1. Check table ownership: `\dt` in psql
2. Check user permissions: `\dp table_name`
3. Grant necessary permissions as shown above

### Connection Issues
If scripts can't connect to the database:

1. Verify `backend/keys.env` exists and has correct credentials
2. Check if PostgreSQL service is running: `sudo systemctl status postgresql`
3. Verify database exists: `sudo -u postgres psql -l`

### Transaction Errors
If you see `InFailedSqlTransaction` errors:

1. This usually indicates a previous operation failed
2. The script should handle this with proper rollback
3. Check the full error log for the root cause

## Database Connection Configuration

The application reads database settings from:
- `backend/config.py` - Main configuration
- `backend/keys.env` - Environment variables with credentials

Example connection string format:
```
postgresql://paperswithcode_user:password@localhost:5432/paperswithcode
```

## Security Notes

- Never commit database credentials to version control
- Use environment variables for sensitive configuration
- The `paperswithcode_user` should have minimal necessary permissions
- Only use `postgres` superuser for administrative tasks
- Regularly review and audit database permissions

## Quick Reference Commands

```bash
# Connect to database as admin
sudo -u postgres psql -d paperswithcode

# Run SQL file as admin
sudo -u postgres psql -d paperswithcode -f file.sql

# Grant permissions after creating new table
sudo -u postgres psql -d paperswithcode -c "GRANT ALL PRIVILEGES ON TABLE new_table TO paperswithcode_user;"

# Test application connection
uv run --env-file backend/keys.env backend/database/connection.py test
```
