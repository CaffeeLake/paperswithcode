# Admin Editing Feature for Papers

## Overview

This feature allows admin users to manually edit the tasks and methods associated with papers through the web interface. The feature includes:

- **Backend API endpoints** for updating paper-task and paper-method associations
- **Frontend UI components** with multi-select dialogs for easy editing
- **Real-time updates** with automatic data refresh after saves

## Backend Implementation

### API Endpoints

#### Update Paper Tasks
```
PUT /api/v1/papers/{paper_id}/tasks?task_ids=1&task_ids=2&task_ids=3
```

**Description:** Updates the tasks associated with a paper. Replaces all existing task associations with the provided list.

**Parameters:**
- `paper_id` (path): Database ID of the paper
- `task_ids` (query, multiple): List of task IDs to associate with the paper

**Response:** Updated `Paper` object with new task associations

**Example:**
```bash
curl -X PUT "http://localhost:8000/api/v1/papers/123/tasks?task_ids=1&task_ids=5&task_ids=10"
```

#### Update Paper Methods
```
PUT /api/v1/papers/{paper_id}/methods?method_ids=1&method_ids=2&method_ids=3
```

**Description:** Updates the methods associated with a paper. Replaces all existing method associations with the provided list.

**Parameters:**
- `paper_id` (path): Database ID of the paper
- `method_ids` (query, multiple): List of method IDs to associate with the paper

**Response:** Updated `Paper` object with new method associations

**Example:**
```bash
curl -X PUT "http://localhost:8000/api/v1/papers/123/methods?method_ids=2&method_ids=7&method_ids=15"
```

### Database Changes

The implementation uses the existing database schema:

- **`paper_tasks`** table: Many-to-many relationship between papers and tasks
- **`paper_methods`** table: Many-to-many relationship between papers and methods

The update operations:
1. Validate that the paper exists
2. Validate that all provided task/method IDs exist
3. Delete existing associations
4. Create new associations
5. Commit changes in a transaction

### Service Layer

Located in `backend/services/paper_service.py`:

- `update_paper_tasks(paper_id: int, task_ids: List[int]) -> Paper`
- `update_paper_methods(paper_id: int, method_ids: List[int]) -> Paper`

These methods handle validation, database transactions, and error handling.

## Frontend Implementation

### User Interface

The editing UI is integrated into the paper detail page (`/papers/arxiv/{arxiv_id}`) with:

1. **Edit Buttons**: Small "Edit" buttons appear in the Tasks and Methods card headers
2. **Multi-Select Dialogs**: Click "Edit" to open a dialog with checkboxes for all available tasks/methods
3. **Search/Scroll**: Dialogs support scrolling through large lists
4. **Real-time Updates**: After saving, the page automatically refreshes to show updated data

### Components Modified

#### PaperDetail.tsx
- Added state management for editing mode and selected items
- Implemented handlers for opening dialogs and saving changes
- Added two Dialog components for tasks and methods
- Integrated with TanStack Query for data fetching and mutations

#### PaperResources.tsx
- Added optional `onEditTasks` and `onEditMethods` props
- Added "Edit" buttons to Tasks and Methods card headers
- Maintained backward compatibility (edit buttons only appear when handlers are provided)

#### API Client (lib/api.ts)
- Added `updatePaperTasks(paperId: string, taskIds: number[]): Promise<Paper>`
- Added `updatePaperMethods(paperId: string, methodIds: number[]): Promise<Paper>`

## Usage

### As an Admin User

1. **Navigate to a paper page**: Go to any paper detail page (e.g., `/papers/arxiv/2312.11805`)

2. **Edit Tasks**:
   - Click the "Edit" button in the Tasks card
   - A dialog will open showing all available tasks
   - Check/uncheck tasks as needed
   - Click "Save Changes" to apply

3. **Edit Methods**:
   - Click the "Edit" button in the Methods card
   - A dialog will open showing all available methods
   - Check/uncheck methods as needed
   - Click "Save Changes" to apply

4. **Review Changes**: The page will automatically refresh to show updated tasks/methods

### State Management

The feature uses:
- **Local State** (`useState`) for dialog visibility and selected items
- **TanStack Query** for:
  - Fetching all tasks/methods when dialogs open
  - Mutations for update operations
  - Automatic cache invalidation after successful updates

### Error Handling

- **Frontend**: Shows loading states and disables buttons during saves
- **Backend**: Validates all inputs and returns appropriate error messages:
  - 404: Paper not found
  - 400: Invalid task/method IDs
  - 500: Database errors

## Testing

### Manual Testing Steps

1. **Start the backend**:
   ```bash
   cd /root/python_projects/paperswithcode
   ./start_services.sh
   ```

2. **Open a paper page** in your browser:
   ```
   http://localhost:5173/papers/arxiv/2312.11805
   ```

3. **Test editing tasks**:
   - Click "Edit" in the Tasks card
   - Select/deselect some tasks
   - Click "Save Changes"
   - Verify the tasks are updated on the page

4. **Test editing methods**:
   - Click "Edit" in the Methods card
   - Select/deselect some methods
   - Click "Save Changes"
   - Verify the methods are updated on the page

### API Testing

Test the endpoints directly:

```bash
# Update tasks for paper ID 123
curl -X PUT "http://localhost:8000/api/v1/papers/123/tasks?task_ids=1&task_ids=2&task_ids=3" \
  -H "Content-Type: application/json"

# Update methods for paper ID 123
curl -X PUT "http://localhost:8000/api/v1/papers/123/methods?method_ids=5&method_ids=10" \
  -H "Content-Type: application/json"
```

## Future Enhancements

Potential improvements:

1. **Authentication**: Add admin authentication to protect edit endpoints
2. **Search**: Add search/filter functionality in the edit dialogs
3. **Bulk Editing**: Allow editing multiple papers at once
4. **History**: Track changes and show edit history
5. **Suggestions**: Use AI to suggest relevant tasks/methods based on paper content
6. **Validation**: Add business logic validation (e.g., minimum number of tasks)

## Files Modified

### Backend
- `backend/services/paper_service.py` - Added update methods
- `backend/routers/papers.py` - Added PUT endpoints

### Frontend
- `frontend/src/pages/PaperDetail.tsx` - Added edit UI and state management
- `frontend/src/components/PaperResources.tsx` - Added edit buttons
- `frontend/src/lib/api.ts` - Added API client methods

## Troubleshooting

### Issue: Edit buttons don't appear
- **Solution**: Make sure you're passing `onEditTasks` and `onEditMethods` props to `PaperResources`

### Issue: Dialog shows "Loading..." indefinitely
- **Solution**: Check that the backend API is running and `/api/v1/tasks` and `/api/v1/methods` endpoints work

### Issue: Save doesn't work
- **Solution**: Check browser console for errors. Verify paper ID is valid and tasks/methods IDs exist in database

### Issue: Changes don't appear after save
- **Solution**: Check that query cache invalidation is working. Try refreshing the page manually.
