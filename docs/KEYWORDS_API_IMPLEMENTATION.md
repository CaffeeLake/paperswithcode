# Keywords Management API Implementation

## Overview

This document describes the implementation of keyword management functionality for both tasks and methods in the PapersWithCode backend API.

## What Was Implemented

### 1. Database Schema Updates

**File Modified:** `backend/models/database.py`
- Added `keywords` field to the `Method` model (line 270)
- Field type: `Text`, nullable, stores comma-separated keywords
- Note: `Task` model already had a keywords field

**Migration Scripts Created:**
- `backend/database/migrations/add_keywords_to_methods.sql` - Forward migration
- `backend/database/migrations/rollback_keywords_from_methods.sql` - Rollback migration
- `backend/database/migrations/README.md` - Migration instructions

### 2. API Models Updated

**File Modified:** `backend/models/api.py`

**Added:**
- `keywords` field to `Method` API model (line 611-613)
- New `KeywordUpdate` request model (lines 744-753) for POST/DELETE/PUT operations

### 3. Service Layer Methods

**File Modified:** `backend/services/method_service.py`

**Updated:**
- All `method_dict` conversions now include the `keywords` field
- Methods return Method objects with keywords populated

**Added Methods:**
- `add_keywords(method_id, keywords)` - Appends keywords, avoids duplicates
- `remove_keywords(method_id, keywords)` - Removes specific keywords
- `replace_keywords(method_id, keywords)` - Replaces all keywords

**File Modified:** `backend/services/task_service.py`

**Added Methods:**
- `add_keywords(task_id, keywords)` - Appends keywords, avoids duplicates
- `remove_keywords(task_id, keywords)` - Removes specific keywords
- `replace_keywords(task_id, keywords)` - Replaces all keywords

### 4. API Endpoints

**File Modified:** `backend/routers/methods.py`

**Added Endpoints:**
- `POST /api/v1/methods/{method_id}/keywords` - Add keywords
- `DELETE /api/v1/methods/{method_id}/keywords` - Remove keywords
- `PUT /api/v1/methods/{method_id}/keywords` - Replace keywords

**File Modified:** `backend/routers/tasks.py`

**Added Endpoints:**
- `POST /api/v1/tasks/{task_id}/keywords` - Add keywords
- `DELETE /api/v1/tasks/{task_id}/keywords` - Remove keywords
- `PUT /api/v1/tasks/{task_id}/keywords` - Replace keywords

## Usage Examples

### Adding Keywords to a Method

```bash
# Add "function-calling" keyword to "function calling" method
curl -X POST http://localhost:8000/api/v1/methods/function-calling/keywords \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["function-calling", "tool-use"]}'
```

### Removing Keywords from a Method

```bash
# Remove a keyword
curl -X DELETE http://localhost:8000/api/v1/methods/function-calling/keywords \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["old-keyword"]}'
```

### Replacing All Keywords for a Method

```bash
# Replace all keywords
curl -X PUT http://localhost:8000/api/v1/methods/function-calling/keywords \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["function-calling", "tool-calling", "function-call"]}'
```

### Task Examples

The same operations work for tasks:

```bash
# Add keywords to a task
curl -X POST http://localhost:8000/api/v1/tasks/computer-use-agents/keywords \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["agent", "computer-use"]}'
```

## Example Use Case: Function Calling Method

For the "function calling" method, you can now easily add the "function-calling" keyword:

```bash
# Step 1: Check current keywords
curl http://localhost:8000/api/v1/methods/function-calling

# Step 2: Add the new keyword
curl -X POST http://localhost:8000/api/v1/methods/function-calling/keywords \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["function-calling"]}'

# Step 3: Verify the update
curl http://localhost:8000/api/v1/methods/function-calling
```

The method should now have "function-calling" added to its existing keywords: "function calling, function call, tool calling, tool call, tool use, function-calling"

## Implementation Details

### Keyword Storage Format
- Keywords are stored as comma-separated strings in the database
- Leading/trailing whitespace is automatically trimmed
- Duplicate keywords are prevented when adding
- Case-insensitive removal (e.g., "Function-Calling" will match "function-calling")

### ID Resolution
Both methods and tasks support multiple ID formats:
- **Methods:** Numeric ID, slug, or name (case-insensitive)
- **Tasks:** Numeric ID or slug

### Error Handling
- Returns 404 if method/task not found
- Returns 500 for database errors
- Automatic rollback on database operation failure

## Running the Migration

Before using the new functionality, run the database migration:

```bash
psql -U postgres -d paperswithcode_hf -f backend/database/migrations/add_keywords_to_methods.sql
```

## Testing

All endpoints can be tested using the FastAPI interactive documentation:
- Navigate to `http://localhost:8000/docs`
- Find the methods or tasks endpoints
- Test the keyword operations with the interactive UI

## Files Modified

1. `backend/models/database.py` - Added keywords field to Method model
2. `backend/models/api.py` - Added keywords to Method API model, created KeywordUpdate model
3. `backend/services/method_service.py` - Updated conversions, added keyword management
4. `backend/services/task_service.py` - Added keyword management methods
5. `backend/routers/methods.py` - Added 3 keyword endpoints
6. `backend/routers/tasks.py` - Added 3 keyword endpoints

## Files Created

1. `backend/database/migrations/add_keywords_to_methods.sql` - Forward migration
2. `backend/database/migrations/rollback_keywords_from_methods.sql` - Rollback migration
3. `backend/database/migrations/README.md` - Migration instructions
4. `backend/KEYWORDS_API_IMPLEMENTATION.md` - This document

## Notes

- All code passes linting with no errors
- The implementation follows the existing patterns in the codebase
- Database operations use proper transaction handling with rollback on error
- The API is fully documented with OpenAPI/Swagger documentation
