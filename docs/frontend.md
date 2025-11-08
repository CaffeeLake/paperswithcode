# Frontend Feature Notes

## Tech Stack Recap

- React 18 + TypeScript (Vite dev server)
- TanStack Query for data fetching/caching
- shadcn/ui + Tailwind CSS for components/style
- API client in `frontend/src/lib/api.ts`

Start the dev server with `npm run dev` (port 8080) or use `./start_services.sh` to launch both frontend and backend with background logging.

## Task Detail Page (About / Leaderboards / Papers)

- Implemented in `frontend/src/pages/TaskDetail.tsx` using shadcn Tabs.
- Tabs:
  - **About** – task description, metadata, hero stats.
  - **Leaderboards** – per-dataset cards with top evaluations, rank badges, metric chips, “View all results” CTA.
  - **Papers** – infinite scroll feed with sort options.
- Hooks:
  - `useTaskDatasets` (`frontend/src/hooks/useDatasets.ts`)
  - `useTaskDatasetEvaluations` (`frontend/src/hooks/useEvaluations.ts`)
  - `useTask` / `useTaskPapers` for detail + pagination
- Data requirements: ensure task↔dataset relationships exist (`task_datasets`).

## Admin Editing (Paper Tasks & Methods)

- Paper detail page (`frontend/src/pages/PaperDetail.tsx`) exposes edit dialogs for tasks and methods when handlers are provided.
- Components:
  - `PaperResources.tsx` – renders edit buttons and resource lists
  - Multi-select dialogs fetch available tasks/methods lazily via TanStack Query
- API helpers (`frontend/src/lib/api.ts`):
  - `updatePaperTasks(paperId, taskIds)` → PUT `/papers/{paper_id}/tasks`
  - `updatePaperMethods(paperId, methodIds)` → PUT `/papers/{paper_id}/methods`
- After save, queries are invalidated to refresh UI.

## Trending Papers UI

- Papers page (`frontend/src/pages/Papers.tsx`) switches to the `/papers/trending` endpoint when the “Trending” tab is active and the search box is empty.
- `useTrendingPapers` hook (in `frontend/src/hooks/usePapers.ts`) fetches a finite list with shorter stale time (2 minutes).
- Helper `transformTrendingPaperForUI` normalizes backend response to the existing card shape (repository + GitHub stats).
- Infinite scroll is disabled in trending mode; UI shows “Showing top N trending papers.”

## LaTeX Rendering for Titles

- Component: `frontend/src/components/LatexTitle.tsx`
- Uses KaTeX (`katex` + `katex/dist/katex.min.css`) to render inline (`$...$`) and block (`$$...$$`) math.
- Wrapped around paper titles in list/grid/search/detail components to gracefully render math-heavy titles.
- Error tolerant (`throwOnError: false`) to avoid breaking UI on malformed expressions.

## Method Imagery

- Methods now have an optional `image_url` (see `docs/data-workflows.md` for updating records).
- Display logic can be added to method cards/components by checking `method.image_url` before rendering an `<img>` tag.
- Ensure remote assets use HTTPS and acceptable licensing/attribution.

## Testing Checklist

- `npm run lint`
- `npm run build`
- Manual smoke tests:
  - Task detail tabs load data, respect loading/empty states.
  - Editing tasks/methods updates UI and persists to backend.
  - Trending tab switches endpoints and renders GitHub stats.
  - Paper titles with `$…$` render via KaTeX.

_Last updated: 7 November 2025_
