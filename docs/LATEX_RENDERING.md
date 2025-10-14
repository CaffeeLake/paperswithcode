# LaTeX Rendering in Paper Titles

## Overview

The frontend now supports LaTeX mathematical expressions in paper titles. This allows proper rendering of mathematical notation instead of displaying raw LaTeX markup with dollar signs.

## Implementation

### New Component: `LatexTitle`

Created a reusable React component (`frontend/src/components/LatexTitle.tsx`) that:
- Parses LaTeX expressions in paper titles
- Supports both inline math (`$...$`) and display math (`$$...$$`)
- Uses KaTeX for rendering mathematical expressions
- Falls back to plain text if rendering fails

### Key Features

1. **Inline Math**: Renders expressions like `$2 * n$` as proper mathematical notation
2. **Display Math**: Renders expressions like `$$x^2 + y^2 = z^2$$` in display mode
3. **Error Handling**: Gracefully falls back to plain text if LaTeX rendering fails
4. **Performance**: Uses React `useEffect` hook to render only when title changes

### Dependencies

- **katex**: ^0.16.25 - Core LaTeX rendering library
- **katex/dist/katex.min.css**: KaTeX stylesheet for proper math formatting

### Updated Components

The following components now use the `LatexTitle` component to display paper titles:

1. **`PaperCard.tsx`** - Paper cards in grid view
2. **`TrendingPaperCard.tsx`** - Paper cards in trending/list view
3. **`PaperSearch.tsx`** - Search results dropdown
4. **`PaperDetail.tsx`** - Paper detail page header

### Example Usage

```tsx
import LatexTitle from "@/components/LatexTitle";

// Before
<h1>{paper.title}</h1>

// After
<h1><LatexTitle title={paper.title} /></h1>
```

### Sample Titles That Now Render Correctly

- `$2 * n$ is better than $n^2$: Decomposing Event Coreference Resolution into Two Tractable Problems`
- `$A^2$Nav: Action-Aware Zero-Shot Robot Navigation by Exploiting Vision-and-Language Ability of Foundation Models`
- `$BT^2$: Backward-compatible Training with Basis Transformation`

## Technical Details

### LaTeX Parsing

The component uses regex patterns to identify and replace LaTeX expressions:

1. **Display Math** (`$$...$$`): Rendered with `displayMode: true`
2. **Inline Math** (`$...$`): Rendered with `displayMode: false`

### Security

- Uses KaTeX's `throwOnError: false` option to prevent rendering errors from breaking the UI
- Sanitizes output through KaTeX's built-in security features
- No direct HTML injection; all rendering is handled by KaTeX

### Performance Considerations

- Component uses `useRef` to avoid unnecessary re-renders
- KaTeX rendering is done client-side for flexibility
- CSS is bundled once and reused across all instances

## Testing

### Build Verification

```bash
cd frontend
npm run build
```

Build completed successfully with KaTeX fonts properly bundled (~40 font files included).

### Development Server

```bash
./start_services.sh
```

Frontend accessible at http://localhost:8080

### Browser Testing

1. Navigate to the Papers A-Z page
2. Verify that paper titles with LaTeX expressions render mathematical notation correctly
3. Check that titles without LaTeX expressions still display normally

## Future Enhancements

Potential improvements for the future:

1. **Server-Side Rendering**: Pre-render LaTeX on the server for better initial load performance
2. **LaTeX Preview**: Show preview of LaTeX when editing paper titles
3. **Extended Support**: Add LaTeX rendering to abstracts and other text fields
4. **Caching**: Cache rendered LaTeX output to avoid re-rendering on every component mount

## Troubleshooting

### Issue: Math expressions not rendering

**Solution**: Check that KaTeX CSS is properly imported in the component:
```tsx
import 'katex/dist/katex.min.css';
```

### Issue: Font files not loading

**Solution**: Verify that Vite is properly configured to handle font assets. KaTeX fonts should be automatically bundled during the build process.

### Issue: Rendering errors in console

**Solution**: The component uses `throwOnError: false`, so rendering errors should not break the UI. Check the browser console for specific LaTeX syntax errors.

## References

- [KaTeX Documentation](https://katex.org/)
- [KaTeX GitHub Repository](https://github.com/KaTeX/KaTeX)
- [React KaTeX Integration Guide](https://katex.org/docs/autorender.html)
