# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## Essentials

ALWAYS use `uv run --env-file backend/keys.env` when running Python scripts. This ensures you use the correct environment variables.

To authenticate and connect to the PostGreSQL database, see `docs/POSTGRESQL_GUIDE.md` for details.

Hardware: everything is run on a Hetzner VPS with 4GB of RAM and 80GB of disk space. Hence a lot of scripts are optimized to deal with the low RAM.

## Project Overview

Paperswithcode.ai is a complete recreation of paperswithcode.com built with modern web technologies. The project consists of a React frontend and a FastAPI backend, which uses a PostgreSQL database.

The data was populated from the papers indexed at huggingface.co/papers, and enriched with the legacy PapersWithCode data dump (2.2GB papers, repository links + 236MB evaluation tables, see the /data folder).

The data is enriched using CRON jobs which can be found at the cron/ folder. This involves things like adding new papers from huggingface.co/papers, updating the Github stars of linked repositories, updating the citation count of papers, and so on.

**Tech Stack**:
- **Frontend**: React 18 + TypeScript + Vite + shadcn/ui + Tailwind CSS + TanStack Query + React Router v6
- **Backend**: PostgreSQL database with Python import scripts
- **Package Management**: uv for Python dependencies, npm for frontend

## Essential Commands

### Frontend Commands (in `frontend/` directory)
```bash
# Development
npm run dev          # Start development server
npm run build        # Production build
npm run build:dev    # Development build
npm run preview      # Preview production build
npm run lint         # Run ESLint (ALWAYS run before committing)
```

### Python/Database Commands (in root directory)
```bash
# Package management
uv add package_name  # Add Python dependency (updates pyproject.toml)
uv sync             # Install/sync dependencies from lock file
uv run script.py    # Run Python script in uv environment

# Database setup (in database/ directory)
python test_setup.py          # Test database requirements
python import_papers.py       # Import papers from JSON to PostgreSQL
```

## Architecture & Code Organization

### Project Structure
```
paperswithcode/
├── frontend/            # React frontend application
│   ├── src/
│   │   ├── components/  # Reusable UI components
│   │   │   ├── ui/     # shadcn/ui components (don't edit manually)
│   │   │   ├── Header.tsx
│   │   │   ├── FilterBar.tsx
│   │   │   └── PaperCard.tsx
│   │   ├── pages/      # Route components
│   │   │   ├── Index.tsx
│   │   │   ├── Papers.tsx
│   │   │   ├── PaperDetail.tsx
│   │   │   └── ...
│   │   ├── hooks/      # Custom React hooks
│   │   ├── lib/        # Utility functions
│   │   └── utils/      # Additional utilities
│   ├── package.json
│   └── vite.config.ts
├── database/           # PostgreSQL setup and scripts
│   ├── setup_database.sql    # Database schema
│   ├── import_papers.py      # Data import script
│   ├── test_setup.py         # Setup verification
│   └── README.md            # Database setup guide
├── data/               # Original PapersWithCode data dump
│   ├── papers-with-abstracts.json (2.2GB)
│   └── evaluation-tables.json (236MB)
├── pyproject.toml      # Python dependencies managed by uv
└── uv.lock            # Lockfile for Python dependencies
```

### Frontend Core Structure
- **Entry Point**: `frontend/src/main.tsx` → `frontend/src/App.tsx` (routing setup)
- **Routing**: React Router v6 with routes defined in `frontend/src/App.tsx`
- **State Management**: TanStack Query for server state, React hooks for local state
- **Styling**: Tailwind CSS with custom design system and shadcn/ui components

### Database & Data Sources

#### PostgreSQL Database Schema
The project uses a PostgreSQL database with the following main tables:
- **`papers`**: Main papers table with metadata, abstracts, URLs, dates
- **`paper_authors`**: Authors for each paper (many-to-many relationship)
- **`paper_tasks`**: AI task categories for each paper
- **`paper_methods`**: Methods/techniques used in each paper

#### Original Data Files
Two main data files from the original PapersWithCode dump:

1. **`data/papers-with-abstracts.json`** (2.2GB) - Complete papers database with:
   - Paper metadata, abstracts, authors, proceedings
   - ArXiv IDs and URLs
   - Associated tasks, methods, datasets
   - GitHub repository links

2. **`data/evaluation-tables.json`** (236MB) - Benchmark evaluation data with:
   - Task descriptions and hierarchies
   - Dataset information and leaderboards
   - Model performance metrics

## Development Guidelines

### Python Development
- **Package Management**: Use `uv add package_name` to add dependencies (auto-updates pyproject.toml)
- **Environment**: All Python scripts run in the uv-managed virtual environment
- **Database Scripts**: Located in `database/` directory with PostgreSQL setup and data import
- **Code Style**: Follow PEP 8, use type hints, proper error handling

### Frontend Development (TypeScript & React)
- **Location**: All frontend code in `frontend/` directory
- Use TypeScript strict mode with proper interfaces for all props
- Follow naming conventions: PascalCase for components, camelCase for hooks
- Import organization: React/external → UI components → custom components → hooks/utils
- Use TanStack Query for data fetching and caching
- Implement proper loading states and error boundaries

### UI & Styling
- Use shadcn/ui components from `frontend/src/components/ui/` (don't edit manually)
- Custom design system with paper-specific colors (blue, teal, purple, pink, orange, green)
- Responsive design with mobile-first approach
- Use `cn()` utility for conditional classes

### Data Handling Patterns
```tsx
// Frontend: Large data loading with dynamic imports
const loadPapersData = async () => {
  const data = await import('../data/papers-with-abstracts.json');
  return data.default;
};

// TanStack Query usage
const usePapersData = () => {
  return useQuery({
    queryKey: ['papers'],
    queryFn: loadPapersData,
    staleTime: 5 * 60 * 1000,
  });
};
```

```python
# Python: Database connection and query patterns
import psycopg2
from psycopg2.extras import RealDictCursor

def get_papers(limit=100):
    with psycopg2.connect(database="paperswithcode_hf") as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM papers_with_authors LIMIT %s", (limit,))
            return cur.fetchall()
```

### Performance Considerations
- Use virtualization for large lists (2.2GB dataset)
- Implement pagination or infinite scrolling
- Use React.memo(), useMemo(), useCallback() judiciously
- Debounce search inputs
- Clean up subscriptions and timers

## Code Quality Requirements

### Before Committing
**Frontend**:
1. **ALWAYS run `npm run lint`** in `frontend/` directory - Fix all ESLint errors
2. Check TypeScript compilation errors
3. Test key functionality works
4. Verify responsive design

**Python**:
1. Run database tests: `python database/test_setup.py`
2. Verify Python scripts run without errors
3. Check that uv environment is properly configured

### Frontend Component Development
- Create reusable components in `frontend/src/components/`
- Use proper TypeScript interfaces for all props
- Follow React Hooks rules (dependencies, no conditional calls)
- Implement proper loading and error states
- Use semantic HTML elements

## Special Considerations

### Route Management
- All new routes must be added ABOVE the catch-all `*` route in `frontend/src/App.tsx`
- Use React Router v6 patterns for navigation

### Data Processing

**Frontend**:
- Handle large JSON files with dynamic imports
- Implement efficient filtering and sorting for 2.2GB dataset
- Use proper error handling for missing data fields
- Consider memory management for large data operations

**Database**:

- Use PostgreSQL for structured queries and full-text search
- Import scripts handle batch processing of large datasets
- Database includes full-text search indexes on paper titles and abstracts
- Use proper connection pooling and error handling

## Future Integration

The project is designed to evolve from JSON file reading to a full PostgreSQL backend that serves data via REST API with advanced search, filtering, and user management capabilities.
