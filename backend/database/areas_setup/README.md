# Areas API Implementation

This directory contains scripts and documentation for the Areas API implementation in the PapersWithCode project.

## Overview

The Areas API provides endpoints to list and retrieve research areas (e.g., Vision, Video, Language, Audio, General, Time-series). This implementation follows the legacy PapersWithCode API specification.

## Database Schema

The `areas` table was already defined in the database migration:

```sql
CREATE TABLE areas (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Relationships

- **Areas → Tasks**: One-to-many relationship. Each area can have multiple tasks associated with it via the `tasks.area_id` foreign key.

## Implementation Components

### 1. Database Models (`backend/models/database.py`)

The `Area` SQLAlchemy model was already implemented:

```python
class Area(Base):
    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="area")
```

### 2. API Models (`backend/models/api.py`)

Added Pydantic models for API responses:

```python
class Area(BaseModel):
    """Research area object."""
    id: str
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Areas(BaseModel):
    """Paginated response for areas."""
    count: int
    next_page: Optional[int] = None
    previous_page: Optional[int] = None
    results: List[Area]
```

### 3. Service Layer (`backend/services/area_service.py`)

Implements business logic for area operations:

- **`get_areas()`**: List areas with pagination, filtering, and sorting
- **`get_area_by_id()`**: Retrieve a specific area by ID
- **`search_areas()`**: Full-text search in area names and descriptions
- **`get_area_task_count()`**: Get the number of tasks for an area

### 4. API Router (`backend/routers/areas.py`)

Defines API endpoints following the legacy specification:

- **`GET /api/v1/areas/`**: List all areas with pagination
- **`GET /api/v1/areas/{area_id}`**: Get a specific area by ID

#### Query Parameters

**List Areas (`GET /api/v1/areas/`):**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (1-based) |
| `page_size` | int | 50 | Number of areas per page (1-500) |
| `q` | string | None | Search query for area names |
| `name` | string | None | Filter by partial name match |
| `ordering` | string | None | Field to sort by: `name`, `created_at` (prefix with `-` for descending) |

**Get Area by ID (`GET /api/v1/areas/{area_id}`):**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `area_id` | string | Yes | Unique area identifier |

### 5. Example Script (`backend/examples/areas_api_example.py`)

Demonstrates how to use the Areas API endpoints.

## Setup and Usage

### 1. Populate Areas Table

Run the populate script to add common research areas:

```bash
uv run --env-file backend/keys.env python backend/database/areas_setup/populate_areas.py --populate
```

This will add the following areas (canonical list, kept in sync with
`populate_areas.py`):
- Vision
- Video
- Language
- General
- Time-series
- Audio

### 2. List Current Areas

To see what's in the database:

```bash
uv run --env-file backend/keys.env python backend/database/areas_setup/populate_areas.py --list
```

### 3. Start the API Server

```bash
uv run --env-file backend/keys.env python backend/run_server.py
```

### 4. Test the API

**List all areas:**
```bash
curl http://localhost:8000/api/v1/areas/
```

**Get a specific area:**
```bash
curl http://localhost:8000/api/v1/areas/1
```

**Search for areas:**
```bash
curl "http://localhost:8000/api/v1/areas/?q=vision"
```

**Filter by name:**
```bash
curl "http://localhost:8000/api/v1/areas/?name=learning"
```

**Sort by name descending:**
```bash
curl "http://localhost:8000/api/v1/areas/?ordering=-name"
```

### 5. Run Example Script

```bash
uv run --env-file backend/keys.env python backend/examples/areas_api_example.py
```

## API Documentation

When the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

The documentation includes:
- Detailed endpoint descriptions
- Request/response schemas
- Example requests and responses
- Interactive API testing

## Legacy API Compatibility

This implementation matches the legacy PapersWithCode API specification:

### Endpoints Implemented

✅ `GET /api/v1/areas/` - List areas with pagination
✅ `GET /api/v1/areas/{area_id}` - Get specific area
⏳ `GET /api/v1/areas/{area_id}/tasks/` - List tasks for an area (pending Task API implementation)

### Response Format

The response format matches the legacy API:

```json
{
  "count": 15,
  "next_page": null,
  "previous_page": null,
  "results": [
    {
      "id": "1",
      "name": "Vision",
      "description": "Research on enabling machines to interpret and understand still images...",
      "created_at": "2025-10-04T10:39:45.702167Z",
      "updated_at": "2025-10-04T10:39:45.702167Z"
    }
  ]
}
```

## Future Enhancements

1. **Tasks Endpoint**: Implement `GET /api/v1/areas/{area_id}/tasks/` to list all tasks in an area
2. **Task Count**: Add `task_count` field to area responses
3. **Paper Count**: Add count of papers associated with each area (via tasks)
4. **Hierarchical Display**: Show area hierarchy if needed
5. **CRUD Operations**: Add POST/PUT/DELETE endpoints for area management (if needed)

## Notes

- The areas table is part of the main database schema — see `docs/DATABASE_SCHEMA_UML.md`
- Areas are referenced by tasks via the `tasks.area_id` foreign key
- The implementation follows the same patterns as the existing Papers and Authors APIs
- All timestamps are stored in UTC with timezone awareness

## Troubleshooting

### No areas in database

Run the populate script:
```bash
uv run --env-file backend/keys.env python backend/database/areas_setup/populate_areas.py --populate
```

### SQLAlchemy warnings

The relationship warnings in `database.py` have been addressed by adding appropriate `overlaps` and `back_populates` parameters.

### Connection errors

Ensure PostgreSQL is running and the `backend/keys.env` file contains valid database credentials.
