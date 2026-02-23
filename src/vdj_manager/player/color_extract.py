"""Extract dominant colors from album art for dynamic player theming.

Uses Pillow (optional dependency) to analyze album art images and extract
dominant colors via histogram-based quantization. No scipy required.
"""

import logging
from colorsys import rgb_to_hls

logger = logging.getLogger(__name__)

# Default accent color (Windows-style blue) used when no vibrant color found
DEFAULT_ACCENT: tuple[int, int, int] = (0, 120, 215)

# Minimum saturation (0-1) for a color to be considered "vibrant"
_MIN_SATURATION = 0.25

# Minimum lightness to avoid near-black colors
_MIN_LIGHTNESS = 0.15

# Maximum lightness to avoid near-white colors
_MAX_LIGHTNESS = 0.85


def extract_dominant_colors(image_bytes: bytes, max_colors: int = 5) -> list[tuple[int, int, int]]:
    """Extract dominant colors from album art image bytes.

    Resizes to a 50x50 thumbnail and quantizes to a reduced palette,
    then returns the most frequent colors sorted by frequency.

    Args:
        image_bytes: Raw image bytes (JPEG, PNG, etc.)
        max_colors: Maximum number of dominant colors to return (default 5).

    Returns:
        List of up to ``max_colors`` (R, G, B) tuples sorted by frequency
        (most dominant first). Returns an empty list if Pillow is not
        installed or the image cannot be decoded.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.debug("Pillow not installed; skipping color extraction")
        return []

    try:
        import io

        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB (handles RGBA, palette, grayscale, CMYK, etc.)
        img = img.convert("RGB")

        # Resize to small thumbnail for speed
        img = img.resize((50, 50), Image.LANCZOS)

        # Quantize to a reduced palette using median-cut (Pillow built-in)
        # Request more colors than max_colors so we can filter grays later
        palette_size = max(max_colors * 4, 20)
        quantized = img.quantize(colors=palette_size, method=Image.Quantize.MEDIANCUT)

        # Get the palette data and histogram (pixel counts per palette entry)
        palette_data = quantized.getpalette()
        if palette_data is None:
            return []

        histogram = quantized.histogram()

        # Build (count, color) pairs from palette
        color_counts: list[tuple[int, tuple[int, int, int]]] = []
        for i in range(min(palette_size, len(histogram))):
            count = histogram[i]
            if count == 0:
                continue
            r = palette_data[i * 3]
            g = palette_data[i * 3 + 1]
            b = palette_data[i * 3 + 2]
            color_counts.append((count, (r, g, b)))

        # Sort by frequency (most dominant first)
        color_counts.sort(key=lambda x: x[0], reverse=True)

        # Return up to max_colors
        return [color for _, color in color_counts[:max_colors]]

    except Exception:
        logger.debug("Failed to extract colors from image", exc_info=True)
        return []


def _saturation(r: int, g: int, b: int) -> float:
    """Return the HLS saturation of an RGB color (0-255 range)."""
    _, _, s = rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    return s


def _lightness(r: int, g: int, b: int) -> float:
    """Return the HLS lightness of an RGB color (0-255 range)."""
    _, lightness, _ = rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    return lightness


def pick_accent_color(colors: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    """Select the most vibrant/saturated color from a list of dominant colors.

    Filters out near-gray, near-black, and near-white colors, then picks
    the most saturated remaining color. Falls back to DEFAULT_ACCENT if
    no suitable candidate is found.

    Args:
        colors: List of (R, G, B) tuples (typically from extract_dominant_colors).

    Returns:
        A single (R, G, B) tuple suitable for use as a UI accent color.
    """
    if not colors:
        return DEFAULT_ACCENT

    best_color: tuple[int, int, int] | None = None
    best_saturation = -1.0

    for color in colors:
        r, g, b = color
        s = _saturation(r, g, b)
        light = _lightness(r, g, b)

        # Skip colors that are too gray, too dark, or too bright
        if s < _MIN_SATURATION:
            continue
        if light < _MIN_LIGHTNESS or light > _MAX_LIGHTNESS:
            continue

        if s > best_saturation:
            best_saturation = s
            best_color = color

    if best_color is None:
        return DEFAULT_ACCENT

    return best_color
