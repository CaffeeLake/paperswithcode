#!/usr/bin/env python3
"""Compose source artwork into a Papers With Code portrait thumbnail."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 400
HEIGHT = 550


def parse_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("colors must use six-digit hex notation")
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("invalid hex color") from exc


def gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        mix = y / (HEIGHT - 1)
        color = tuple(round(a * (1 - mix) + b * mix) for a, b in zip(top, bottom))
        draw.line((0, y, WIDTH, y), fill=color)
    return image.convert("RGBA")


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    return (
        ImageFont.truetype(str(path), size)
        if path.exists()
        else ImageFont.load_default(size=size)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title")
    parser.add_argument("--background", default="#f8f7fb,#f3f5f8")
    parser.add_argument("--quality", type=int, default=90)
    args = parser.parse_args()

    colors = args.background.split(",")
    if len(colors) != 2:
        parser.error("--background must be TOP_HEX,BOTTOM_HEX")
    top, bottom = map(parse_color, colors)

    source = Image.open(args.input).convert("RGBA")
    title_lines = args.title.split("\n") if args.title else []
    art_box = (360, 350 if title_lines else 430)
    scale = min(art_box[0] / source.width, art_box[1] / source.height)
    art = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.LANCZOS,
    )

    canvas = gradient(top, bottom)
    art_area_height = 390 if title_lines else HEIGHT
    x = (WIDTH - art.width) // 2
    y = max(24, (art_area_height - art.height) // 2)
    canvas.alpha_composite(art, (x, y))

    if title_lines:
        draw = ImageDraw.Draw(canvas)
        size = 36 if max(map(len, title_lines)) <= 16 else 30
        font = load_font(size)
        line_height = size + 7
        block_height = len(title_lines) * line_height - 7
        start_y = 420 + max(0, (95 - block_height) // 2)
        for index, line in enumerate(title_lines):
            bounds = draw.textbbox((0, 0), line, font=font)
            draw.text(
                ((WIDTH - (bounds[2] - bounds[0])) // 2, start_y + index * line_height),
                line,
                font=font,
                fill=(27, 29, 36, 255),
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(args.output, "JPEG", quality=args.quality, optimize=True)
    print(args.output)


if __name__ == "__main__":
    main()
