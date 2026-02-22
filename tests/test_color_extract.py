"""Tests for album art color extraction."""

import importlib
import io
from unittest.mock import patch

import pytest

from vdj_manager.player.color_extract import (
    DEFAULT_ACCENT,
    extract_dominant_colors,
    pick_accent_color,
)

# Check if PIL is available for tests that need real images
try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

requires_pil = pytest.mark.skipif(not _HAS_PIL, reason="Pillow not installed")


def _make_solid_image(color: tuple[int, int, int], size: int = 10) -> bytes:
    """Create a solid-color image and return its PNG bytes."""
    img = Image.new("RGB", (size, size), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_two_color_image(
    color1: tuple[int, int, int],
    color2: tuple[int, int, int],
    size: int = 10,
) -> bytes:
    """Create an image split vertically between two colors."""
    img = Image.new("RGB", (size, size), color1)
    for x in range(size // 2, size):
        for y in range(size):
            img.putpixel((x, y), color2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestExtractDominantColors:
    """Tests for extract_dominant_colors function."""

    @requires_pil
    def test_solid_red_image(self):
        """Should return red (or near-red) as dominant color for a solid red image."""
        image_bytes = _make_solid_image((255, 0, 0))
        colors = extract_dominant_colors(image_bytes)

        assert len(colors) >= 1
        # The dominant color should be red or very close to red
        r, g, b = colors[0]
        assert r > 200
        assert g < 50
        assert b < 50

    @requires_pil
    def test_solid_blue_image(self):
        """Should return blue as dominant color for a solid blue image."""
        image_bytes = _make_solid_image((0, 0, 255))
        colors = extract_dominant_colors(image_bytes)

        assert len(colors) >= 1
        r, g, b = colors[0]
        assert r < 50
        assert g < 50
        assert b > 200

    @requires_pil
    def test_returns_up_to_max_colors(self):
        """Should not return more colors than max_colors."""
        image_bytes = _make_two_color_image((255, 0, 0), (0, 0, 255))
        colors = extract_dominant_colors(image_bytes, max_colors=3)

        assert len(colors) <= 3

    @requires_pil
    def test_max_colors_one(self):
        """Should return exactly 1 color when max_colors=1."""
        image_bytes = _make_solid_image((0, 255, 0))
        colors = extract_dominant_colors(image_bytes, max_colors=1)

        assert len(colors) == 1

    @requires_pil
    def test_rgba_image_handled(self):
        """Should handle RGBA images (converts to RGB internally)."""
        img = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        colors = extract_dominant_colors(image_bytes)
        assert len(colors) >= 1

    def test_invalid_bytes_returns_empty(self):
        """Should return empty list for invalid image bytes."""
        colors = extract_dominant_colors(b"not an image")
        assert colors == []

    def test_empty_bytes_returns_empty(self):
        """Should return empty list for empty bytes."""
        colors = extract_dominant_colors(b"")
        assert colors == []

    def test_pillow_not_available_returns_empty(self):
        """Should return empty list when Pillow is not installed."""
        with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
            from vdj_manager.player import color_extract

            importlib.reload(color_extract)

            result = color_extract.extract_dominant_colors(b"anything")
            assert result == []

            # Restore module so other tests work
            importlib.reload(color_extract)


class TestPickAccentColor:
    """Tests for pick_accent_color function."""

    def test_selects_vibrant_over_gray(self):
        """Should select a vibrant/saturated color over a gray one."""
        gray = (128, 128, 128)
        vibrant_red = (220, 30, 30)
        result = pick_accent_color([gray, vibrant_red])
        assert result == vibrant_red

    def test_selects_most_saturated(self):
        """Should select the most saturated color when multiple vibrant colors given."""
        muted_blue = (100, 100, 160)  # low saturation
        vivid_green = (0, 200, 0)  # high saturation
        result = pick_accent_color([muted_blue, vivid_green])
        assert result == vivid_green

    def test_returns_fallback_for_empty_list(self):
        """Should return default accent when given an empty list."""
        result = pick_accent_color([])
        assert result == DEFAULT_ACCENT

    def test_returns_fallback_for_only_grays(self):
        """Should return default accent when given only gray colors."""
        grays = [(128, 128, 128), (64, 64, 64), (200, 200, 200)]
        result = pick_accent_color(grays)
        assert result == DEFAULT_ACCENT

    def test_returns_fallback_for_near_black(self):
        """Should return default accent when given only near-black colors."""
        darks = [(10, 5, 5), (20, 10, 15), (5, 5, 5)]
        result = pick_accent_color(darks)
        assert result == DEFAULT_ACCENT

    def test_returns_fallback_for_near_white(self):
        """Should return default accent when given only near-white colors."""
        whites = [(250, 250, 250), (245, 248, 245), (255, 255, 255)]
        result = pick_accent_color(whites)
        assert result == DEFAULT_ACCENT

    def test_skips_too_dark_picks_bright(self):
        """Should skip near-black and pick a usable vibrant color."""
        near_black = (5, 0, 0)
        vibrant = (0, 150, 255)
        result = pick_accent_color([near_black, vibrant])
        assert result == vibrant

    def test_returns_tuple_of_three_ints(self):
        """Return type should be a tuple of three ints."""
        result = pick_accent_color([(200, 50, 50)])
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert all(isinstance(c, int) for c in result)

    def test_default_accent_value(self):
        """DEFAULT_ACCENT should be the expected blue."""
        assert DEFAULT_ACCENT == (0, 120, 215)
