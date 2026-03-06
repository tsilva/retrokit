"""Image processing utilities for resizing and transparency."""

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import imagequant  # type: ignore[import-untyped]
from PIL import Image


@dataclass
class QuantizeResult:
    """Result of PNG quantization."""

    original_size: int
    quantized_size: int
    reduction_pct: float
    method: str  # "imagequant" or "skipped"


def quantize_png(
    image_path: Path,
    quality: str = "65-80",
) -> QuantizeResult:
    """
    Quantize a PNG image using libimagequant for smaller file sizes.

    Args:
        image_path: Path to the PNG image to quantize
        quality: Quality range (e.g., "65-80") - uses max value

    Returns:
        QuantizeResult with size information
    """
    original_size = image_path.stat().st_size

    # Parse quality range (e.g., "65-80" -> min=65, max=80)
    try:
        if "-" in quality:
            min_q, max_q = map(int, quality.split("-"))
        else:
            min_q, max_q = int(quality), int(quality)
    except ValueError:
        min_q, max_q = 65, 80

    try:
        # Open image
        img: Image.Image = Image.open(image_path)

        # Convert to RGBA if not already
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        # Quantize using libimagequant
        quantized_img = imagequant.quantize_pil_image(
            img,
            dithering_level=1.0,
            max_colors=256,
            min_quality=min_q,
            max_quality=max_q,
        )

        # Save quantized image
        quantized_img.save(image_path, "PNG", optimize=True)

        quantized_size = image_path.stat().st_size
        reduction_pct = (1 - quantized_size / original_size) * 100

        return QuantizeResult(
            original_size=original_size,
            quantized_size=quantized_size,
            reduction_pct=reduction_pct,
            method="imagequant",
        )
    except Exception:
        # Quantization can fail for some images
        return QuantizeResult(
            original_size=original_size,
            quantized_size=original_size,
            reduction_pct=0.0,
            method="skipped",
        )


@dataclass
class AlphaMatteStats:
    """Statistics from alpha matte processing."""

    actual_bg: tuple[int, int, int]
    transparent_pct: float
    edges_pct: float
    opaque_pct: float


@dataclass
class DifferenceMatteStats:
    """Statistics from difference matting processing."""

    transparent_pct: float
    semi_transparent_pct: float
    opaque_pct: float


def get_image_dimensions(image_path: Path) -> tuple[int, int]:
    """Get image width and height."""
    with Image.open(image_path) as img:
        return cast(tuple[int, int], img.size)


def resize_image(
    image_path: Path,
    target_width: int,
    target_height: int,
) -> tuple[int, int, int, int]:
    """
    Resize image to exact dimensions.

    Returns:
        Tuple of (original_width, original_height, new_width, new_height)
    """
    with Image.open(image_path) as img:
        original_size = img.size

        if original_size == (target_width, target_height):
            return (*original_size, *original_size)

        resized = img.resize(
            (target_width, target_height),
            Image.Resampling.LANCZOS,
        )
        resized.save(image_path, "PNG")

        return (*original_size, target_width, target_height)


def _color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Calculate Euclidean distance in RGB space."""
    return math.sqrt(
        (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2
    )


def _clamp(val: float, min_val: int = 0, max_val: int = 255) -> int:
    """Clamp value to range."""
    return max(min_val, min(max_val, int(round(val))))


def make_background_transparent(
    image_path: Path,
    bg_type: str,
    bg_dark: tuple[int, int, int] = (37, 40, 59),
    bg_light: tuple[int, int, int] = (255, 255, 255),
    pure_bg_threshold: int = 15,
    pure_fg_threshold: int = 80,
) -> AlphaMatteStats:
    """
    Remove background color and apply alpha matting with color decontamination.

    Args:
        image_path: Path to the image to process
        bg_type: "dark" or "light" background type
        bg_dark: RGB tuple for dark background color
        bg_light: RGB tuple for light background color
        pure_bg_threshold: Below this distance = fully transparent
        pure_fg_threshold: Above this distance = fully opaque

    Returns:
        AlphaMatteStats with processing statistics
    """
    _ = bg_dark if bg_type == "dark" else bg_light  # reserved for future use

    img = Image.open(image_path).convert("RGBA")
    pixels = img.load()
    assert pixels is not None, "Failed to load image pixels"
    width, height = img.size

    # Sample corner pixels to detect actual background color
    corners: list[tuple[int, int, int]] = [
        cast(tuple[int, int, int, int], pixels[0, 0])[:3],
        cast(tuple[int, int, int, int], pixels[width - 1, 0])[:3],
        cast(tuple[int, int, int, int], pixels[0, height - 1])[:3],
        cast(tuple[int, int, int, int], pixels[width - 1, height - 1])[:3],
    ]

    # Use most common corner color as actual background
    actual_bg: tuple[int, int, int] = Counter(corners).most_common(1)[0][0]
    bg_r, bg_g, bg_b = actual_bg

    fully_transparent = 0
    partially_transparent = 0
    fully_opaque = 0

    for y in range(height):
        for x in range(width):
            pixel = cast(tuple[int, int, int, int], pixels[x, y])
            r, g, b, a = pixel
            dist = _color_distance((r, g, b), actual_bg)

            if dist <= pure_bg_threshold:
                # Pure background - fully transparent
                pixels[x, y] = (r, g, b, 0)
                fully_transparent += 1

            elif dist >= pure_fg_threshold:
                # Pure foreground - fully opaque
                pixels[x, y] = (r, g, b, 255)
                fully_opaque += 1

            else:
                # Edge pixel - graduated alpha with color decontamination
                alpha_float = (dist - pure_bg_threshold) / (
                    pure_fg_threshold - pure_bg_threshold
                )
                alpha = _clamp(alpha_float * 255)

                # Color decontamination: remove background color contribution
                # Original: C = alpha * Foreground + (1-alpha) * Background
                # Solve: F = (C - (1-alpha)*B) / alpha
                if alpha_float > 0.01:
                    new_r = _clamp((r - (1 - alpha_float) * bg_r) / alpha_float)
                    new_g = _clamp((g - (1 - alpha_float) * bg_g) / alpha_float)
                    new_b = _clamp((b - (1 - alpha_float) * bg_b) / alpha_float)
                else:
                    new_r, new_g, new_b = r, g, b

                pixels[x, y] = (new_r, new_g, new_b, alpha)
                partially_transparent += 1

    img.save(image_path, "PNG")

    total = width * height
    return AlphaMatteStats(
        actual_bg=actual_bg,
        transparent_pct=fully_transparent / total * 100,
        edges_pct=partially_transparent / total * 100,
        opaque_pct=fully_opaque / total * 100,
    )


def has_alpha_channel(image_path: Path) -> bool:
    """Check if image has alpha channel."""
    with Image.open(image_path) as img:
        return img.mode in ("RGBA", "LA", "PA")


def chroma_key_transparency(
    image_path: Path,
    color: str = "green",
) -> None:
    """
    Remove background using chroma key.

    Args:
        image_path: Path to the image to process
        color: Background color to remove - "green" or "white"
    """
    img = Image.open(image_path).convert("RGBA")
    pixels = img.load()
    assert pixels is not None, "Failed to load image pixels"
    width, height = img.size

    for y in range(height):
        for x in range(width):
            pixel = cast(tuple[int, int, int, int], pixels[x, y])
            r, g, b, a = pixel

            if color == "green":
                # Detect green-dominant pixels (green screen)
                is_bg = g > r + 30 and g > b + 30 and g > 100
            else:  # white
                # Detect near-white pixels
                is_bg = r > 240 and g > 240 and b > 240

            if is_bg:
                pixels[x, y] = (r, g, b, 0)  # Fully transparent

    img.save(image_path, "PNG")


def auto_remove_background(
    image_path: Path,
    tolerance: int = 80,
    erosion_passes: int = 100,
) -> tuple[int, int, int]:
    """
    Auto-detect and remove background using flood-fill + iterative erosion.

    Two-pass approach for reliable background removal:
    1. Flood-fill from edges removes connected background
    2. Iterative erosion removes trapped background pixels by repeatedly
       eroding bg-colored pixels adjacent to transparent regions

    Args:
        image_path: Path to the image to process
        tolerance: Color distance tolerance for background detection
        erosion_passes: Max erosion iterations (stops early if no changes)

    Returns:
        The detected background color as RGB tuple
    """
    img = Image.open(image_path).convert("RGBA")
    pixels = img.load()
    assert pixels is not None, "Failed to load image pixels"
    width, height = img.size

    # Sample corners to detect background color
    corners = [
        cast(tuple[int, int, int, int], pixels[5, 5])[:3],
        cast(tuple[int, int, int, int], pixels[width - 5, 5])[:3],
        cast(tuple[int, int, int, int], pixels[5, height - 5])[:3],
        cast(tuple[int, int, int, int], pixels[width - 5, height - 5])[:3],
    ]
    bg_color = Counter(corners).most_common(1)[0][0]

    # === PASS 1: Flood fill from edges ===
    visited = [[False] * height for _ in range(width)]
    to_remove: set[tuple[int, int]] = set()

    def flood_fill(start_x: int, start_y: int) -> None:
        stack = [(start_x, start_y)]
        while stack:
            x, y = stack.pop()
            if x < 0 or x >= width or y < 0 or y >= height:
                continue
            if visited[x][y]:
                continue
            visited[x][y] = True

            pixel = cast(tuple[int, int, int, int], pixels[x, y])
            r, g, b, a = pixel
            dist = _color_distance((r, g, b), bg_color)

            if dist < tolerance:
                to_remove.add((x, y))
                stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

    for x in range(width):
        flood_fill(x, 0)
        flood_fill(x, height - 1)
    for y in range(height):
        flood_fill(0, y)
        flood_fill(width - 1, y)

    for x, y in to_remove:
        r, g, b, a = cast(tuple[int, int, int, int], pixels[x, y])
        pixels[x, y] = (r, g, b, 0)

    # === PASS 2: Global removal of pixels close to background ===
    # Removes trapped background in crevices that flood fill couldn't reach
    tight_tolerance = tolerance * 0.6

    for y in range(height):
        for x in range(width):
            pixel = cast(tuple[int, int, int, int], pixels[x, y])
            r, g, b, a = pixel
            if a == 0:
                continue
            dist = _color_distance((r, g, b), bg_color)
            if dist < tight_tolerance:
                pixels[x, y] = (r, g, b, 0)

    # === PASS 2b: Remove any saturated green (shadows/reflections) ===
    # Green backgrounds often have darker green shadows that don't match
    # the bright background but are still obviously green
    bg_is_green = bg_color[1] > bg_color[0] + 50 and bg_color[1] > bg_color[2] + 50

    if bg_is_green:
        for y in range(height):
            for x in range(width):
                pixel = cast(tuple[int, int, int, int], pixels[x, y])
                r, g, b, a = pixel
                if a == 0:
                    continue
                # Remove any green-tinted pixel where G is highest channel
                # and the color is not too dark (not a shadow)
                if g > r and g > b and g > 80:
                    pixels[x, y] = (r, g, b, 0)

    # === PASS 3: Iterative erosion for remaining fringe ===
    # Catches bg-colored pixels at edges that are just outside tight tolerance
    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]

    for _ in range(erosion_passes):
        erode_list: list[tuple[int, int]] = []

        for y in range(height):
            for x in range(width):
                pixel = cast(tuple[int, int, int, int], pixels[x, y])
                r, g, b, a = pixel

                if a == 0:
                    continue

                dist = _color_distance((r, g, b), bg_color)
                if dist >= tolerance:
                    continue

                for dx, dy in neighbors:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        if cast(tuple[int, int, int, int], pixels[nx, ny])[3] == 0:
                            erode_list.append((x, y))
                            break

        if not erode_list:
            break

        for x, y in erode_list:
            r, g, b, a = cast(tuple[int, int, int, int], pixels[x, y])
            pixels[x, y] = (r, g, b, 0)

    img.save(image_path, "PNG")
    return bg_color


def checkerboard_to_transparent(
    image_path: Path,
    tolerance: int = 30,
) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    """
    Detect checkerboard transparency pattern and convert to actual transparency.

    When a model is asked to generate a transparent background, it often renders
    the classic Photoshop-style checkerboard pattern. This function detects that
    pattern and converts it to actual transparency.

    Algorithm:
    1. Sample corner regions (background areas)
    2. Find the two most common colors
    3. Verify they form a checkerboard pattern (alternating)
    4. Replace all pixels matching either color with transparency

    Args:
        image_path: Path to the image to process
        tolerance: Color distance tolerance for matching checkerboard colors

    Returns:
        Tuple of (color1, color2) if detected and processed, None if no pattern found
    """
    img = Image.open(image_path).convert("RGBA")
    pixels = img.load()
    assert pixels is not None, "Failed to load image pixels"
    width, height = img.size

    # Sample 64x64 regions from each corner (offset by 5px to avoid edge artifacts)
    corner_samples: list[tuple[int, int, int]] = []
    sample_size = 64
    offset = 5

    corners = [
        (offset, offset),  # top-left
        (width - sample_size - offset, offset),  # top-right
        (offset, height - sample_size - offset),  # bottom-left
        (width - sample_size - offset, height - sample_size - offset),  # bottom-right
    ]

    for cx, cy in corners:
        for dy in range(sample_size):
            for dx in range(sample_size):
                x, y = cx + dx, cy + dy
                if 0 <= x < width and 0 <= y < height:
                    pixel = cast(tuple[int, int, int, int], pixels[x, y])
                    corner_samples.append(pixel[:3])

    # Find the two most common colors in corners
    color_counts = Counter(corner_samples)
    most_common = color_counts.most_common(2)

    if len(most_common) < 2:
        return None

    color1, count1 = most_common[0]
    color2, count2 = most_common[1]

    # Verify both colors have significant presence (at least 25% each)
    # and together they make up most of the corner samples (>80%)
    total_samples = len(corner_samples)
    min_presence = 0.25
    combined_presence = (count1 + count2) / total_samples

    if count1 < total_samples * min_presence or count2 < total_samples * min_presence:
        return None

    if combined_presence < 0.80:
        return None

    # Replace all pixels matching either checkerboard color with transparency
    for y in range(height):
        for x in range(width):
            pixel = cast(tuple[int, int, int, int], pixels[x, y])
            r, g, b, a = pixel

            dist1 = _color_distance((r, g, b), color1)
            dist2 = _color_distance((r, g, b), color2)

            if dist1 < tolerance or dist2 < tolerance:
                pixels[x, y] = (r, g, b, 0)

    img.save(image_path, "PNG")
    return (color1, color2)


def difference_matte(
    white_bg_path: Path,
    black_bg_path: Path,
    output_path: Path,
) -> DifferenceMatteStats:
    """
    Extract alpha channel using difference matting.

    Compares the same image rendered on white and black backgrounds
    to mathematically calculate the exact transparency of each pixel.

    The formula:
    - pixelDist = distance between white-bg and black-bg pixel colors
    - bgDist = sqrt(3 * 255^2) ≈ 441.67 (distance between pure white and black)
    - alpha = 1 - (pixelDist / bgDist)
    - color = pixel_on_black / alpha (un-premultiply to recover true color)

    This technique preserves:
    - Semi-transparent pixels (glass, shadows)
    - Precise edge alpha values
    - No color halos or artifacts

    Args:
        white_bg_path: Path to image with white background
        black_bg_path: Path to image with black background
        output_path: Path to save the result with extracted alpha

    Returns:
        DifferenceMatteStats with transparency statistics
    """
    # Load both images
    img_white = Image.open(white_bg_path).convert("RGBA")
    img_black = Image.open(black_bg_path).convert("RGBA")

    if img_white.size != img_black.size:
        raise ValueError(
            f"Dimension mismatch: white={img_white.size}, black={img_black.size}"
        )

    width, height = img_white.size
    pixels_white = img_white.load()
    pixels_black = img_black.load()
    assert pixels_white is not None, "Failed to load white image pixels"
    assert pixels_black is not None, "Failed to load black image pixels"

    # Create output image
    output = Image.new("RGBA", (width, height))
    pixels_out = output.load()
    assert pixels_out is not None, "Failed to create output image"

    # Distance between white (255,255,255) and black (0,0,0)
    # sqrt(255^2 + 255^2 + 255^2) ≈ 441.67
    bg_dist = math.sqrt(3 * 255 * 255)

    transparent_count = 0
    semi_transparent_count = 0
    opaque_count = 0

    for y in range(height):
        for x in range(width):
            pixel_w = cast(tuple[int, int, int, int], pixels_white[x, y])
            pixel_b = cast(tuple[int, int, int, int], pixels_black[x, y])

            r_w, g_w, b_w, _ = pixel_w
            r_b, g_b, b_b, _ = pixel_b

            # Calculate distance between the two observed pixels
            pixel_dist = math.sqrt(
                (r_w - r_b) ** 2 + (g_w - g_b) ** 2 + (b_w - b_b) ** 2
            )

            # Calculate alpha:
            # If pixel is 100% opaque: looks same on both backgrounds (dist = 0)
            # If pixel is 100% transparent: looks like backgrounds (dist = bg_dist)
            alpha = 1.0 - (pixel_dist / bg_dist)
            alpha = max(0.0, min(1.0, alpha))  # Clamp to 0-1

            # Color recovery from black background version
            # Since BG is black (0,0,0), formula simplifies to: C / alpha
            if alpha > 0.01:
                r_out = min(255, int(r_b / alpha))
                g_out = min(255, int(g_b / alpha))
                b_out = min(255, int(b_b / alpha))
            else:
                r_out, g_out, b_out = 0, 0, 0

            alpha_int = int(alpha * 255)
            pixels_out[x, y] = (r_out, g_out, b_out, alpha_int)

            # Count for statistics
            if alpha_int == 0:
                transparent_count += 1
            elif alpha_int == 255:
                opaque_count += 1
            else:
                semi_transparent_count += 1

    output.save(output_path, "PNG")

    total = width * height
    return DifferenceMatteStats(
        transparent_pct=transparent_count / total * 100,
        semi_transparent_pct=semi_transparent_count / total * 100,
        opaque_pct=opaque_count / total * 100,
    )


def convert_to_monochrome(
    source_path: Path,
    output_path: Path,
    target_color: tuple[int, int, int],
) -> None:
    """
    Convert a transparent PNG to monochrome while preserving alpha.

    Takes the luminance of each pixel and applies the target color,
    preserving the original alpha channel.

    Args:
        source_path: Path to source image (RGBA with transparency)
        output_path: Path to save the monochrome result
        target_color: RGB tuple for the monochrome color (e.g., white or black)
    """
    img = Image.open(source_path).convert("RGBA")
    pixels = img.load()
    assert pixels is not None, "Failed to load image pixels"
    width, height = img.size

    target_r, target_g, target_b = target_color

    for y in range(height):
        for x in range(width):
            pixel = cast(tuple[int, int, int, int], pixels[x, y])
            r, g, b, a = pixel

            if a > 0:
                # Apply target color, preserve alpha
                pixels[x, y] = (target_r, target_g, target_b, a)

    img.save(output_path, "PNG")


def create_logo_variants_theme_structure(
    source_color_logo: Path,
    platform_id: str,
    logos_dark_black_dir: Path,
    logos_dark_color_dir: Path,
    logos_light_color_dir: Path,
    logos_light_white_dir: Path,
) -> dict[str, Path]:
    """
    Create all logo variants matching theme directory structure.

    The source logo is already in logos_light_color_dir as {platform_id}.png.
    This creates the other 3 variants in their respective directories.

    Args:
        source_color_logo: Path to the color logo with transparency
        platform_id: Platform identifier for filenames
        logos_dark_black_dir: Directory for Dark - Black logos
        logos_dark_color_dir: Directory for Dark - Color logos
        logos_light_color_dir: Directory for Light - Color logos
        logos_light_white_dir: Directory for Light - White logos

    Returns:
        Dict mapping variant name to output path (excludes source which is already saved)
    """
    variants: dict[str, Path] = {}
    filename = f"{platform_id}.png"

    img = Image.open(source_color_logo)

    # Dark - Color: copy of the color logo
    dark_color_path = logos_dark_color_dir / filename
    img.save(dark_color_path, "PNG")
    variants["Dark - Color"] = dark_color_path

    # Dark - Black: white monochrome for dark backgrounds
    dark_black_path = logos_dark_black_dir / filename
    convert_to_monochrome(source_color_logo, dark_black_path, (255, 255, 255))
    variants["Dark - Black"] = dark_black_path

    # Light - White: black monochrome for light backgrounds
    light_white_path = logos_light_white_dir / filename
    convert_to_monochrome(source_color_logo, light_white_path, (0, 0, 0))
    variants["Light - White"] = light_white_path

    img.close()
    return variants
