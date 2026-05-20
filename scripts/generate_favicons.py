"""Generate favicon, apple-touch-icon, and social preview PNGs.

The brand mark is the same nested-square motif used in the site header
(`.brand-mark` in `frontend/src/styles.css`), recreated here at raster sizes
so browsers, iOS home screens, and link-preview cards (WhatsApp, Twitter,
etc.) have explicit assets to fetch instead of falling back to whatever
default the original Lovable template shipped with.

Run with:

    uv run python scripts/generate_favicons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

INK = (26, 24, 20)
BG = (250, 248, 244)
INK_SOFT = (90, 85, 76)

PUBLIC_DIR = Path(__file__).resolve().parents[1] / "frontend" / "public"

SERIF_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
SERIF_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"
SERIF_ITALIC = "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"
SANS_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"


def draw_brand_mark(
    img: Image.Image,
    *,
    cx: int,
    cy: int,
    outer: int,
    outer_fill: tuple[int, int, int] = INK,
    inner_fill: tuple[int, int, int] = BG,
    center_fill: tuple[int, int, int] = INK,
) -> None:
    """Paint the nested-square mark centred at (cx, cy) at side length `outer`."""
    draw = ImageDraw.Draw(img)
    border = round(outer * (6 / 32))
    middle = outer - 2 * border
    center = round(outer * (8 / 32))

    half_outer = outer / 2
    half_inner = middle / 2
    half_center = center / 2

    draw.rectangle(
        (cx - half_outer, cy - half_outer, cx + half_outer, cy + half_outer),
        fill=outer_fill,
    )
    draw.rectangle(
        (cx - half_inner, cy - half_inner, cx + half_inner, cy + half_inner),
        fill=inner_fill,
    )
    draw.rectangle(
        (cx - half_center, cy - half_center, cx + half_center, cy + half_center),
        fill=center_fill,
    )


def generate_favicon_png(path: Path, size: int = 32) -> None:
    img = Image.new("RGBA", (size, size), INK + (255,))
    draw_brand_mark(img, cx=size // 2, cy=size // 2, outer=size)
    img.save(path, "PNG")


def generate_apple_touch_icon(path: Path, size: int = 180) -> None:
    """Apple touch icon: mark on solid background; iOS adds rounded corners."""
    img = Image.new("RGBA", (size, size), BG + (255,))
    mark_size = round(size * 0.55)
    draw_brand_mark(img, cx=size // 2, cy=size // 2, outer=mark_size)
    img.save(path, "PNG")


def generate_social_preview(path: Path, width: int = 1200, height: int = 630) -> None:
    img = Image.new("RGBA", (width, height), BG + (255,))
    draw = ImageDraw.Draw(img)

    mark_size = 220
    mark_cx = width // 2
    mark_cy = height // 2 - 90
    draw_brand_mark(img, cx=mark_cx, cy=mark_cy, outer=mark_size)

    title_regular = ImageFont.truetype(SERIF_REGULAR, 88)
    title_italic = ImageFont.truetype(SERIF_ITALIC, 88)
    tagline_font = ImageFont.truetype(SANS_REGULAR, 30)

    title_y = mark_cy + mark_size // 2 + 56

    papers = "Papers "
    with_code = "with Code"
    papers_w = draw.textlength(papers, font=title_regular)
    with_code_w = draw.textlength(with_code, font=title_italic)
    total_w = papers_w + with_code_w
    title_x = (width - total_w) / 2
    draw.text((title_x, title_y), papers, font=title_regular, fill=INK)
    draw.text(
        (title_x + papers_w, title_y), with_code, font=title_italic, fill=INK_SOFT
    )

    tagline = "Trending AI research papers with code, datasets, and leaderboards."
    tagline_w = draw.textlength(tagline, font=tagline_font)
    draw.text(
        ((width - tagline_w) / 2, title_y + 130),
        tagline,
        font=tagline_font,
        fill=INK_SOFT,
    )

    img.convert("RGB").save(path, "PNG", optimize=True)


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    generate_favicon_png(PUBLIC_DIR / "favicon-32.png", size=32)
    generate_favicon_png(PUBLIC_DIR / "favicon-192.png", size=192)
    generate_apple_touch_icon(PUBLIC_DIR / "apple-touch-icon.png", size=180)
    generate_social_preview(PUBLIC_DIR / "og-image.png")
    print(f"Wrote favicon assets to {PUBLIC_DIR}")


if __name__ == "__main__":
    main()
