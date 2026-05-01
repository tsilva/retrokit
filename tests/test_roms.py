from pathlib import Path

from retrokit.roms import DuplicateDetector


def write_rom(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_duplicate_detector_prefers_clean_rom_over_beta(tmp_path: Path) -> None:
    roms_dir = tmp_path / "roms"
    write_rom(roms_dir / "Nintendo NES" / "Example Game (USA).nes", b"same rom")
    write_rom(roms_dir / "Nintendo NES" / "Example Game (Beta).nes", b"same rom")

    detector = DuplicateDetector(roms_dir)
    detector.scan()
    detector.find_duplicates()

    assert len(detector.duplicates) == 1
    duplicate = detector.duplicates[0]
    assert duplicate["remove"] == "Nintendo NES/Example Game (Beta).nes"
    assert duplicate["keep"] == "Nintendo NES/Example Game (USA).nes"
    assert duplicate["reason"] == "Exact hash match"
