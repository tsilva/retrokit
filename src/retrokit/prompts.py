"""Prompt templates for Nano Banana Pro image generation.

These prompts use user-provided reference images for accurate reproduction.
"""

from dataclasses import dataclass


@dataclass
class AssetPrompts:
    """Prompt templates optimized for Nano Banana Pro (Gemini 3 Pro Image).

    These prompts are designed to work with user-provided reference images
    to generate accurate platform assets.
    """

    @staticmethod
    def device(platform_name: str) -> str:
        """Generate prompt for device/console image.

        The user provides a reference image (platform.jpg) showing the actual hardware.
        This prompt instructs the model to recreate it as a nostalgic gaming setup.
        """
        return f"""Generate a nostalgic gaming setup image for the {platform_name} based on the reference image provided.

The reference image shows the {platform_name} hardware. Create a complete gaming setup composition in the style of retro gaming nostalgia art.

COMPOSITION REQUIREMENTS (create a complete gaming setup):
- For HOME CONSOLES: Include a CRT television displaying an iconic game from the platform, the console unit, 2 controllers, and any signature accessories (light guns, memory cards, etc.)
- For HANDHELD DEVICES: Show the handheld device with an iconic game displayed on its screen
- For COMPUTERS: Include a period-appropriate CRT monitor showing software/game, the computer unit, keyboard, mouse, and joystick or other peripherals
- For ARCADE: Show multiple arcade cabinets arranged together with game artwork visible

HARDWARE ACCURACY:
- The {platform_name} hardware must match the reference EXACTLY - same shape, colors, buttons, ports, and design details
- All hardware must be historically accurate and instantly recognizable
- Controllers and accessories must be era-appropriate and authentic to the platform

STYLE REQUIREMENTS:
- Photorealistic 3D render quality with clean studio lighting
- 3/4 perspective angle showing depth and dimension
- Items arranged naturally as a gaming setup, not floating
- No text overlays, watermarks, or annotations

SCREEN CONTENT:
- CRT TV or monitor should display recognizable gameplay from an iconic {platform_name} game
- The game on screen should be era-appropriate and visually distinctive

CRITICAL - BACKGROUND REQUIREMENT:
- Solid pure white background #FFFFFF (RGB 255,255,255)
- Absolutely uniform white, no gradients, no shadows, no texture
- Objects float in space - NO floor, NO table, NO surface, NO platform, NO ground
- SHARP HARD EDGES between objects and the white background - NO blur, NO feathering
- NO shadows on the background - the white must be clean and uniform"""

    @staticmethod
    def logo(platform_name: str) -> str:
        """Generate prompt for logo image.

        The user provides a reference image (logo.png) showing the actual logo.
        This prompt instructs the model to recreate it cleanly.
        """
        return f"""Reproduce the {platform_name} logo exactly as shown in the reference image.

The reference image shows the official {platform_name} logo. Recreate this EXACTLY.

CRITICAL ACCURACY REQUIREMENTS:
- Match the reference logo EXACTLY - same typography, colors, layout, and graphical elements
- Use the EXACT colors from the reference logo
- Use the EXACT typography/font from the reference logo
- Include ALL elements (symbols, emblems, text) exactly as shown
- The logo must be IDENTICAL to the reference

RENDERING REQUIREMENTS:
- Text must be crisp, sharp, and perfectly legible
- Vector-quality clean edges with no artifacts
- Colors should be vibrant and match the reference exactly

LAYOUT REQUIREMENTS:
- Wide banner format (21:9 aspect ratio)
- Logo horizontally and vertically centered
- Generous padding around the logo (logo should fill about 60-70% of width)
- Clean minimalist presentation

CRITICAL BACKGROUND REQUIREMENT:
- Solid pure white background #FFFFFF (RGB 255,255,255)
- Absolutely uniform white, no gradients, no shadows, no texture
- SHARP HARD EDGES between the logo and the white background - NO blur, NO feathering, NO anti-aliasing
- This is for transparency extraction - clean edges are essential"""


@dataclass
class AssetType:
    """Asset type configuration."""

    name: str
    aspect_ratio: str
    image_size: str
    target_width: int
    target_height: int
    bg_type: str | None  # None for device (no transparency), "light" for logo
    output_filename: str


def get_device_type(
    width: int = 2160,
    height: int = 2160,
) -> AssetType:
    """Get device asset type configuration."""
    return AssetType(
        name="device",
        aspect_ratio="1:1",
        image_size="2K",
        target_width=width,
        target_height=height,
        bg_type="dark",  # Dark bg (#25283B) for alpha extraction
        output_filename="device.png",
    )


def get_logo_type(
    width: int = 1920,
    height: int = 510,
) -> AssetType:
    """Get logo asset type configuration."""
    return AssetType(
        name="logo",
        aspect_ratio="21:9",
        image_size="2K",
        target_width=width,
        target_height=height,
        bg_type="light",  # White bg for alpha extraction
        output_filename="logo.png",
    )
