# PapersWithCode FastAPI Backend

A modern FastAPI-based backend that re-implements the deprecated PapersWithCode API with enhanced features for version tracking, full-text search, and comprehensive paper management.

## Features

### Core API Compatibility
- **Paper Endpoints**: Full compatibility with the original PapersWithCode Paper API
- **Pagination**: Efficient pagination with configurable page sizes
- **Search**: Full-text search across paper titles and abstracts
- **Filtering**: Advanced filtering by date, conference, and version status

### Enhanced Features
- **ArXiv Version Tracking**: Complete support for ArXiv paper versions (v1, v2, v3, etc.)
- **URL Construction**: Automatic ArXiv URL generation for abstracts and PDFs
- **Version Comparison**: Compare different versions of the same paper
- **Database Integration**: PostgreSQL with SQLAlchemy ORM
- **Modern Architecture**: FastAPI with async support and automatic API documentation

## Quick Start

### Prerequisites

1. **PostgreSQL Database**: Ensure you have a PostgreSQL database running
2. **Python Dependencies**: Install dependencies using uv

```bash
# Install dependencies
uv sync

# Set up the database (if not already done)
cd database/setup
python setup_database.py
```

### Environment Configuration

Create a `.env` file in the project root:

```env
# Database Configuration
PWC_DB_HOST=localhost
PWC_DB_PORT=5432
PWC_DB_NAME=paperswithcode
PWC_DB_USER=postgres
PWC_DB_PASSWORD=your_password

# Server Configuration
PWC_HOST=0.0.0.0
PWC_PORT=8000
PWC_ENVIRONMENT=development

# API Configuration
PWC_DEFAULT_PAGE_SIZE=50
PWC_MAX_PAGE_SIZE=500
```

### Running the Server

#### Development Mode
```bash
# Using the provided runner script
uv run backend/run_server.py

# Or directly with uvicorn
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

#### Production Mode
```bash
# Set environment to production
export PWC_ENVIRONMENT=production

# Run with production settings
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Testing the API

Once the server is running, you can:

1. **View API Documentation**: Visit `http://localhost:8000/docs`
2. **Health Check**: Visit `http://localhost:8000/health`
3. **Test Endpoints**: Use the interactive docs or curl

```bash
# Get recent papers
curl "http://localhost:8000/api/v1/papers/recent?limit=5"

# Get a specific paper by ArXiv ID
curl "http://localhost:8000/api/v1/papers/arxiv/1805.10616"

# Search papers
curl "http://localhost:8000/api/v1/papers/search?q=transformer&limit=10"

# Get papers with pagination
curl "http://localhost:8000/api/v1/papers/?page=1&page_size=10"
```

## API Endpoints

### Paper Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/papers/` | GET | Get paginated list of papers with filtering |
| `/api/v1/papers/{paper_id}` | GET | Get paper by database ID |
| `/api/v1/papers/arxiv/{arxiv_id}` | GET | Get paper by ArXiv ID (latest version) |
| `/api/v1/papers/arxiv/{arxiv_id}?version=v2` | GET | Get specific version of a paper |
| `/api/v1/papers/arxiv/{arxiv_id}/versions` | GET | Get all versions of a paper |
| `/api/v1/papers/arxiv/{arxiv_id}/versions/{v1}/compare/{v2}` | GET | Compare two versions |
| `/api/v1/papers/search` | GET | Full-text search papers |
| `/api/v1/papers/recent` | GET | Get recently published papers |
| `/api/v1/papers/stats` | GET | Get database statistics |

### Query Parameters

#### `/api/v1/papers/` - Advanced Filtering
- `page`: Page number (default: 1)
- `page_size`: Papers per page (default: 50, max: 500)
- `search`: Search term for title/abstract
- `published_after`: Filter by publication date (YYYY-MM-DD)
- `published_before`: Filter by publication date (YYYY-MM-DD)
- `conference`: Filter by conference name
- `latest_only`: Only include latest versions (default: true)
- `order_by`: Sort field (default: date_published)
- `order_dir`: Sort direction (asc/desc, default: desc)

## API Response Format

### Paper Object
```json
{
  "id": "12345",
  "arxiv_id": "1805.10616",
  "url_abs": "https://arxiv.org/abs/1805.10616",
  "url_pdf": "https://arxiv.org/pdf/1805.10616.pdf",
  "title": "Attention Is All You Need",
  "abstract": "The dominant sequence transduction models...",
  "authors": ["Ashish Vaswani", "Noam Shazeer", "..."],
  "published": "2017-06-12",
  "conference": "NIPS 2017",
  "conference_url_abs": null,
  "conference_url_pdf": null,
  "proceeding": null,
  "version": "v1",
  "is_latest_version": true
}
```

### Paginated Response
```json
{
  "count": 1250,
  "next_page": 2,
  "previous_page": null,
  "results": [
    // ... array of Paper objects
  ]
}
```

## Database Integration

The backend uses SQLAlchemy with PostgreSQL and builds upon the existing database schema:

- **Papers Table**: Core paper information with version tracking
- **Authors Table**: Author information with Hugging Face integration
- **Junction Tables**: Many-to-many relationships (papers ↔ authors, tasks, methods, etc.)
- **Full-text Indexes**: PostgreSQL GIN indexes for efficient searching

## Development

### Project Structure
```
backend/
├── __init__.py
├── main.py                 # FastAPI application entry point
├── config.py              # Configuration management
├── run_server.py          # Development server runner
├── models/
│   ├── api.py            # Pydantic models for API responses
│   └── database.py       # SQLAlchemy models
├── services/
│   └── paper_service.py  # Business logic for paper operations
├── routers/
│   └── papers.py         # FastAPI route handlers
├── database/
│   └── connection.py     # Database connection management
└── utils/
    ├── urls.py           # URL construction utilities
    └── exceptions.py     # Custom exception classes
```

### Adding New Endpoints

1. **Define API Models**: Add Pydantic models in `models/api.py`
2. **Extend Database Models**: Update SQLAlchemy models in `models/database.py`
3. **Create Service Methods**: Add business logic in appropriate service classes
4. **Add Router Endpoints**: Define FastAPI routes in the relevant router
5. **Update Main App**: Include new routers in `main.py`

### Testing Database Connection

```bash
# Test database connection
python -c "from backend.database.connection import get_engine; print('✅ Database connected!' if get_engine().connect() else '❌ Connection failed!')"

# Initialize database tables
python -m backend.database.connection init

# Reset database (development only)
python -m backend.database.connection reset
```

## Configuration Options

All configuration is handled through environment variables with the `PWC_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `PWC_DB_HOST` | localhost | Database host |
| `PWC_DB_PORT` | 5432 | Database port |
| `PWC_DB_NAME` | paperswithcode | Database name |
| `PWC_DB_USER` | postgres | Database user |
| `PWC_DB_PASSWORD` | | Database password |
| `PWC_HOST` | 0.0.0.0 | Server host |
| `PWC_PORT` | 8000 | Server port |
| `PWC_ENVIRONMENT` | development | Environment (development/production) |
| `PWC_DEFAULT_PAGE_SIZE` | 50 | Default pagination size |
| `PWC_MAX_PAGE_SIZE` | 500 | Maximum pagination size |
| `PWC_APP_DOMAIN` | paperswithcode.ai | Domain for URL generation |

## Production Deployment

### Docker (Recommended)

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

COPY backend/ ./backend/
EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Systemd Service

```ini
[Unit]
Description=PapersWithCode FastAPI Backend
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/ai-paper-nexus
Environment=PWC_ENVIRONMENT=production
ExecStart=/path/to/uv/run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name api.paperswithcode.ai;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Monitoring and Logging

The application provides structured logging and can be integrated with monitoring tools:

- **Health Check**: `/health` endpoint for load balancer health checks
- **Metrics**: Built-in FastAPI metrics and database connection pooling stats
- **Logging**: Structured logging with configurable levels
- **Database Monitoring**: Connection pool metrics and query performance tracking

## Contributing

1. **Code Style**: Follow PEP 8 and use type hints
2. **Testing**: Add tests for new endpoints and services
3. **Documentation**: Update API documentation and README
4. **Database Changes**: Include migration scripts for schema changes

## License

This project follows the same license as the main PapersWithCode project.
