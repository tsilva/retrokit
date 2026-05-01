"""Theme configuration for asset deployment.

This module handles loading and validating theme configurations
that define how generated assets should be deployed to theme folders.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ThemeFiles(BaseModel):
    """File mappings for a theme."""

    device: str = "device.png"
    logo_dark_color: str = "logo_dark_color.png"
    logo_dark_black: str = "logo_dark_black.png"
    logo_light_color: str = "logo_light_color.png"
    logo_light_white: str = "logo_light_white.png"


class ThemeConfig(BaseModel):
    """Configuration for a single theme."""

    base_path: str
    assets_dir: str = "assets/{platform_id}"
    files: ThemeFiles = Field(default_factory=ThemeFiles)

    @field_validator("base_path")
    @classmethod
    def expand_path(cls, v: str) -> str:
        """Expand ~ and environment variables in path."""
        return str(Path(v).expanduser())

    def get_assets_path(self, platform_id: str) -> Path:
        """Get the full assets path for a platform.

        Args:
            platform_id: Platform identifier.

        Returns:
            Full path to the platform's assets directory.
        """
        assets_dir = self.assets_dir.format(platform_id=platform_id)
        return Path(self.base_path) / assets_dir

    def get_file_path(self, platform_id: str, asset_type: str) -> Path:
        """Get the full path for a specific asset file.

        Args:
            platform_id: Platform identifier.
            asset_type: Asset type (device, logo_dark_color, etc.).

        Returns:
            Full path to the asset file.

        Raises:
            ValueError: If asset_type is invalid.
        """
        assets_path = self.get_assets_path(platform_id)
        file_name: str | None = getattr(self.files, asset_type, None)
        if file_name is None:
            raise ValueError(f"Unknown asset type: {asset_type}")
        return assets_path / file_name


class ThemesConfig(BaseModel):
    """Root configuration containing all themes."""

    themes: dict[str, ThemeConfig] = Field(default_factory=dict)

    def get_theme(self, name: str) -> ThemeConfig | None:
        """Get a theme by name.

        Args:
            name: Theme name.

        Returns:
            ThemeConfig if found, None otherwise.
        """
        return self.themes.get(name)

    def list_themes(self) -> list[str]:
        """List all available theme names.

        Returns:
            List of theme names.
        """
        return list(self.themes.keys())


class ThemeConfigError(Exception):
    """Error loading or parsing theme configuration."""

    pass


def find_themes_config() -> Path | None:
    """Find the themes.yaml configuration file.

    Searches in the following locations:
    1. Current working directory
    2. Project root (looking for pyproject.toml)
    3. ~/.config/retrokit/

    Returns:
        Path to themes.yaml if found, None otherwise.
    """
    # Check current directory
    cwd = Path.cwd()
    if (cwd / "themes.yaml").exists():
        return cwd / "themes.yaml"

    # Look for project root by finding pyproject.toml
    current = cwd
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            if (current / "themes.yaml").exists():
                return current / "themes.yaml"
            break
        current = current.parent

    # Check user config directory
    user_config = Path.home() / ".config" / "retrokit" / "themes.yaml"
    if user_config.exists():
        return user_config

    return None


def load_themes_config(path: Path | None = None) -> ThemesConfig:
    """Load themes configuration from YAML file.

    Args:
        path: Optional explicit path to themes.yaml.
              If not provided, searches standard locations.

    Returns:
        ThemesConfig instance.

    Raises:
        ThemeConfigError: If config cannot be loaded or parsed.
    """
    if path is None:
        path = find_themes_config()

    if path is None:
        raise ThemeConfigError(
            "No themes.yaml found. Create one in the project root or ~/.config/retrokit/themes.yaml"
        )

    if not path.exists():
        raise ThemeConfigError(f"Themes config not found: {path}")

    try:
        with path.open("r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ThemeConfigError(f"Invalid YAML in themes config: {e}") from e

    if data is None:
        data = {}

    try:
        return ThemesConfig.model_validate(data)
    except Exception as e:
        raise ThemeConfigError(f"Invalid themes config format: {e}") from e


def create_default_themes_config(path: Path) -> None:
    """Create a default themes.yaml configuration file.

    Args:
        path: Path where to create the config file.
    """
    default_config: dict[str, Any] = {
        "themes": {
            "colorful": {
                "base_path": "/Volumes/RETRO/frontends/Pegasus_mac/themes/COLORFUL",
                "assets_dir": "assets/images/{platform_id}",
                "files": {
                    "device": "device.png",
                    "logo_dark_color": "logo_dark_color.png",
                    "logo_dark_black": "logo_dark_black.png",
                    "logo_light_color": "logo_light_color.png",
                    "logo_light_white": "logo_light_white.png",
                },
            }
        }
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)
