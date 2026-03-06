"""Configuration management using Pydantic Settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Configuration
    gemini_api_key: str
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent"

    # Directories
    input_dir: Path = Field(default=Path(".input"), alias="RETRO_INPUT_DIR")
    output_dir: Path = Field(default=Path("output"), alias="RETRO_OUTPUT_DIR")

    # Image Dimensions
    device_width: int = 2160
    device_height: int = 2160
    logo_width: int = 1920
    logo_height: int = 510

    # Alpha Matte Thresholds
    alpha_bg_threshold: int = 15  # Below = fully transparent
    alpha_fg_threshold: int = 80  # Above = fully opaque

    # Background Colors (RGB)
    bg_dark: tuple[int, int, int] = (37, 40, 59)  # #25283B
    bg_light: tuple[int, int, int] = (255, 255, 255)  # #FFFFFF

    # Features
    enable_google_search: bool = True
    enable_quantization: bool = Field(default=True, alias="RETRO_QUANTIZE")
    quantization_quality: str = Field(default="65-80", alias="RETRO_QUANTIZE_QUALITY")

    def get_input_dir(self, platform_id: str) -> Path:
        """Get input directory for a platform."""
        return self.input_dir / platform_id

    def _find_reference(self, platform_id: str, name: str, extensions: list[str]) -> Path | None:
        """Find a reference file with any of the given extensions."""
        input_dir = self.get_input_dir(platform_id)
        for ext in extensions:
            path = input_dir / f"{name}{ext}"
            if path.exists():
                return path
        return None

    def get_platform_reference(self, platform_id: str) -> Path | None:
        """Get platform/console reference image path."""
        return self._find_reference(platform_id, "platform", [".jpg", ".jpeg", ".png"])

    def get_logo_reference(self, platform_id: str) -> Path | None:
        """Get logo reference image path."""
        return self._find_reference(platform_id, "logo", [".png", ".jpg", ".jpeg"])

    def verify_input_references(self, platform_id: str) -> list[str]:
        """Verify input reference images exist. Returns list of missing."""
        missing = []
        input_dir = self.get_input_dir(platform_id)

        if not input_dir.exists():
            missing.append(f"Input directory: {input_dir}")
            return missing

        if not self.get_platform_reference(platform_id):
            missing.append(f"Platform reference: {input_dir}/platform.(jpg|png)")

        if not self.get_logo_reference(platform_id):
            missing.append(f"Logo reference: {input_dir}/logo.(png|jpg)")

        return missing


def get_settings() -> Settings:
    """Get settings instance. Values loaded from environment/.env file."""
    return Settings()  # type: ignore[call-arg]
