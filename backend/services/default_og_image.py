"""
Render the static default Open Graph image used when a paper has no
thumbnail on disk yet.

The image is rendered lazily on first request and cached in memory because:
  - It only depends on a few hard-coded brand colours; nothing changes per
    request, so re-rendering on every call would waste CPU.
  - Generating it at runtime means we don't have to commit a binary asset.
  - Pillow is already a dependency of the thumbnail pipeline.
"""

from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


_OG_WIDTH = 1200
_OG_HEIGHT = 630

_BG_COLOUR = (26, 24, 20)
_CARD_COLOUR = (250, 248, 244)
_ACCENT_COLOUR = (220, 86, 47)
_MUTED_COLOUR = (110, 100, 88)

_TITLE = "Papers with Code"
_TAGLINE = "Trending AI research, code, and benchmarks"
_DOMAIN = "paperswithcode.co"


_cached_png: Optional[bytes] = None


def _load_font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    """Try a few well-known font paths, fall back to Pillow's default."""
    candidates_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVu-Sans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    candidates_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    candidates = candidates_bold if weight == "bold" else candidates_regular
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _render() -> bytes:
    image = Image.new("RGB", (_OG_WIDTH, _OG_HEIGHT), _BG_COLOUR)
    draw = ImageDraw.Draw(image)

    margin = 64
    inner = (margin, margin, _OG_WIDTH - margin, _OG_HEIGHT - margin)
    draw.rectangle(inner, fill=_CARD_COLOUR)

    accent_w = 14
    draw.rectangle(
        (inner[0], inner[1], inner[0] + accent_w, inner[3]),
        fill=_ACCENT_COLOUR,
    )

    text_left = inner[0] + accent_w + 56
    text_right = inner[2] - 56

    title_font = _load_font(size=104, weight="bold")
    tagline_font = _load_font(size=44)
    domain_font = _load_font(size=36, weight="bold")

    title_y = inner[1] + 130
    draw.text((text_left, title_y), _TITLE, fill=_BG_COLOUR, font=title_font)

    tagline_y = title_y + 150
    draw.text((text_left, tagline_y), _TAGLINE, fill=_MUTED_COLOUR, font=tagline_font)

    domain_y = inner[3] - 90
    draw.text((text_left, domain_y), _DOMAIN, fill=_ACCENT_COLOUR, font=domain_font)
    underline_y = domain_y + 60
    domain_bbox = draw.textbbox((text_left, domain_y), _DOMAIN, font=domain_font)
    draw.rectangle(
        (text_left, underline_y, domain_bbox[2], underline_y + 4),
        fill=_ACCENT_COLOUR,
    )

    # Tiny redundancy so unused arg is referenced.
    _ = text_right

    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def get_default_og_image_bytes() -> bytes:
    """Return the cached PNG bytes for the default OG image, generating on first call."""
    global _cached_png
    if _cached_png is None:
        _cached_png = _render()
    return _cached_png
