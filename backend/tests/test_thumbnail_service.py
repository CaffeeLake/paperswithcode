from pathlib import Path

from PIL import Image, ImageDraw

from backend.services.thumbnail_service import (
    EXPECTED_THUMBNAIL_WIDTH,
    _trim_blank_page_margins,
    is_thumbnail_valid,
)


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


def _save_jpeg(path: Path, width: int, height: int) -> None:
    Image.new("RGB", (width, height), "white").save(path, "JPEG", quality=85)


def test_is_thumbnail_valid_accepts_expected_width_jpeg(tmp_path: Path):
    path = tmp_path / "good.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH, 560)
    assert is_thumbnail_valid(path) is True


def test_is_thumbnail_valid_rejects_wrong_width_jpeg(tmp_path: Path):
    path = tmp_path / "wrong.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH // 2, 280)
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_rejects_corrupt_file(tmp_path: Path):
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"this is not a JPEG")
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_rejects_empty_file(tmp_path: Path):
    path = tmp_path / "empty.jpg"
    path.write_bytes(b"")
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_rejects_missing_file(tmp_path: Path):
    assert is_thumbnail_valid(tmp_path / "missing.jpg") is False


def test_is_thumbnail_valid_rejects_non_jpeg_format(tmp_path: Path):
    path = tmp_path / "wrong_format.jpg"
    Image.new("RGB", (EXPECTED_THUMBNAIL_WIDTH, 560), "white").save(path, "PNG")
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_rejects_squat_thumbnail(tmp_path: Path):
    # Older buggy renders produced 400x258 (H/W = 0.645) by clipping the
    # height. These are correct width but visually broken in card layouts.
    path = tmp_path / "squat.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH, 258)
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_accepts_portrait_thumbnail(tmp_path: Path):
    path = tmp_path / "portrait.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH, 480)
    assert is_thumbnail_valid(path) is True
