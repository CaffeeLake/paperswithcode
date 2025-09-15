# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PapersWithCode is a complete recreation of PapersWithCode built with modern web technologies. The project uses the original PapersWithCode data dump (2.2GB papers + 236MB evaluation tables) to recreate the full functionality of the original platform.

**Tech Stack**: React 18 + TypeScript + Vite + shadcn/ui + Tailwind CSS + TanStack Query + React Router v6

## Essential Commands

```bash
# Development
npm run dev          # Start development server
npm run build        # Production build
npm run build:dev    # Development build
npm run preview      # Preview production build
npm run lint         # Run ESLint (ALWAYS run before committing)
```

## Architecture & Code Organization

### Core Structure
- **Entry Point**: `src/main.tsx` → `src/App.tsx` (routing setup)
- **Routing**: React Router v6 with routes defined in `src/App.tsx`
- **State Management**: TanStack Query for server state, React hooks for local state
- **Styling**: Tailwind CSS with custom design system and shadcn/ui components
- **Data**: Original PapersWithCode data dump stored in `data/` directory

### Key Directories
```
src/
├── components/          # Reusable UI components
│   ├── ui/             # shadcn/ui components (don't edit manually)
│   ├── Header.tsx      # Main navigation
│   ├── FilterBar.tsx   # Paper filtering
│   └── PaperCard.tsx   # Paper display card
├── pages/              # Route components
│   ├── Index.tsx       # Home (redirects to Papers)
│   ├── Papers.tsx      # Main papers listing
│   ├── PaperDetail.tsx # Individual paper view
│   ├── Tasks.tsx       # AI tasks listing
│   ├── TaskDetail.tsx  # Individual task view
│   ├── Methods.tsx     # Methods/techniques page
│   └── Benchmark.tsx   # Benchmark results
├── hooks/              # Custom React hooks
├── lib/                # Utility functions
└── utils/              # Additional utilities
```

### Data Sources & Types
The project uses two main data files from the original PapersWithCode dump:

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

### TypeScript & React Standards
- Use TypeScript strict mode with proper interfaces for all props
- Follow naming conventions: PascalCase for components, camelCase for hooks
- Import organization: React/external → UI components → custom components → hooks/utils
- Use TanStack Query for data fetching and caching
- Implement proper loading states and error boundaries

### UI & Styling
- Use shadcn/ui components from `src/components/ui/` (don't edit manually)
- Custom design system with paper-specific colors (blue, teal, purple, pink, orange, green)
- Responsive design with mobile-first approach
- Use `cn()` utility for conditional classes

### Data Handling Patterns
```tsx
// Large data loading with dynamic imports
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

### Performance Considerations
- Use virtualization for large lists (2.2GB dataset)
- Implement pagination or infinite scrolling
- Use React.memo(), useMemo(), useCallback() judiciously
- Debounce search inputs
- Clean up subscriptions and timers

## Code Quality Requirements

### Before Committing
1. **ALWAYS run `npm run lint`** - Fix all ESLint errors
2. Check TypeScript compilation errors
3. Test key functionality works
4. Verify responsive design

### Component Development
- Create reusable components in `src/components/`
- Use proper TypeScript interfaces for all props
- Follow React Hooks rules (dependencies, no conditional calls)
- Implement proper loading and error states
- Use semantic HTML elements

## Special Considerations

### Route Management
- All new routes must be added ABOVE the catch-all `*` route in `src/App.tsx`
- Use React Router v6 patterns for navigation

### Data Processing
- Handle large JSON files with dynamic imports
- Implement efficient filtering and sorting for 2.2GB dataset
- Use proper error handling for missing data fields
- Consider memory management for large data operations

## Future Backend Integration
The frontend is designed to eventually connect to a Python backend (FastAPI/Flask) that will serve the PapersWithCode data via REST API with search, filtering, and user management capabilities.