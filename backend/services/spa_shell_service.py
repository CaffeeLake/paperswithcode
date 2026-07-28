"""Load and safely customize the active Vite SPA shell."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from backend.config import get_settings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_INDEX_PATH = (
    _PROJECT_ROOT.parent / "pwc-releases" / "current" / "frontend-dist" / "index.html"
)
_DIST_INDEX_PATH = _PROJECT_ROOT / "frontend" / "dist" / "index.html"
_SRC_INDEX_PATH = _PROJECT_ROOT / "frontend" / "index.html"

_cached_index_html: Optional[str] = None
_cached_index_mtime: Optional[float] = None
_cached_index_path: Optional[Path] = None


def load_index_html() -> Optional[str]:
    """Load the deployed shell, with release/build/source fallbacks in development."""
    global _cached_index_html, _cached_index_mtime, _cached_index_path

    settings = get_settings()
    paths = (
        (settings.frontend_dist_path / "index.html",)
        if settings.is_deployed
        else (_RELEASE_INDEX_PATH, _DIST_INDEX_PATH, _SRC_INDEX_PATH)
    )
    for path in paths:
        if not path.exists():
            continue
        try:
            mtime = path.stat().st_mtime
            if (
                _cached_index_html is not None
                and _cached_index_mtime == mtime
                and _cached_index_path == path
            ):
                return _cached_index_html
            html = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read SPA index from %s: %s", path, exc)
            continue
        _cached_index_html = html
        _cached_index_mtime = mtime
        _cached_index_path = path
        return html
    return None


def inject_head(shell: str, head_html: str) -> str:
    marker = "</head>"
    if marker not in shell:
        raise ValueError("SPA shell is missing </head>")
    return shell.replace(marker, f"{head_html}\n{marker}", 1)


def replace_document_head(shell: str, head_html: str) -> str:
    """Remove generic document metadata before adding page-specific metadata."""
    patterns = (
        r"<title\b[^>]*>.*?</title>",
        r'<meta\b[^>]*\bname=["\']description["\'][^>]*>',
        r'<meta\b[^>]*\bname=["\']robots["\'][^>]*>',
        r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>',
    )
    for pattern in patterns:
        shell = re.sub(pattern, "", shell, count=1, flags=re.IGNORECASE | re.DOTALL)
    return inject_head(shell, head_html)


def inject_root_document(shell: str, document_html: str) -> str:
    for marker in ('<div id="root"></div>', '<div id="root"></div>\n'):
        if marker in shell:
            return shell.replace(marker, f'<div id="root">{document_html}</div>', 1)
    raise ValueError("SPA shell is missing an empty #root mount")


def reset_cache() -> None:
    """Test helper for shell path/content changes."""
    global _cached_index_html, _cached_index_mtime, _cached_index_path
    _cached_index_html = None
    _cached_index_mtime = None
    _cached_index_path = None
