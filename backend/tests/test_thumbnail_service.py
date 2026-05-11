from PIL import Image, ImageDraw

from backend.services.thumbnail_service import _trim_blank_page_margins


def test_trim_blank_page_margins_keeps_visible_content_with_padding():
    image = Image.new("RGB", (100, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 30, 79, 109), fill="black")

    trimmed = _trim_blank_page_margins(image)

    assert trimmed.size == (68, 88)
    assert trimmed.getpixel((4, 4)) == (0, 0, 0)


def test_trim_blank_page_margins_leaves_blank_page_unchanged():
    image = Image.new("RGB", (100, 140), "white")

    trimmed = _trim_blank_page_margins(image)

    assert trimmed.size == image.size
