"""Security-boundary and image-processing regression tests."""

from importlib.metadata import version
from io import BytesIO

import pytest
from PIL import Image, ImageCms, UnidentifiedImageError

from retrokit.image_processor import get_image_dimensions, has_alpha_channel, resize_image


def _version_tuple(distribution: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version(distribution).split(".") if part.isdigit())


def test_locked_packages_are_outside_vulnerable_ranges() -> None:
    assert _version_tuple("Pillow") >= (12, 3, 0)
    assert _version_tuple("Pygments") >= (2, 20, 0)


def test_valid_image_pipeline_and_malformed_input_rejection(tmp_path) -> None:
    image_path = tmp_path / "asset.png"
    Image.new("RGBA", (16, 12), (10, 20, 30, 128)).save(image_path)

    assert get_image_dimensions(image_path) == (16, 12)
    assert resize_image(image_path, 8, 6) == (16, 12, 8, 6)
    assert get_image_dimensions(image_path) == (8, 6)
    assert has_alpha_channel(image_path)

    with pytest.raises(UnidentifiedImageError):
        Image.open(BytesIO(b"not-an-image")).load()


def test_pillow_rejects_imagecms_output_mode_mismatch() -> None:
    profile = ImageCms.createProfile("sRGB")
    transform = ImageCms.buildTransform(profile, profile, "RGBA", "RGBA")
    source = Image.new("RGBA", (8, 1), (1, 2, 3, 4))

    valid_output = Image.new("RGBA", source.size)
    assert transform.apply(source, valid_output).mode == "RGBA"

    mismatched_output = Image.new("L", source.size)
    with pytest.raises(ValueError, match="mode"):
        transform.apply(source, mismatched_output)
