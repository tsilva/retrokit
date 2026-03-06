"""ROM deduplication functionality for retrokit."""

import csv
import hashlib
import json
import logging
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Region priority (higher = better)
REGION_PRIORITY = {
    "USA": 100,
    "U": 100,
    "US": 100,
    "America": 100,
    "Europe": 80,
    "E": 80,
    "EU": 80,
    "World": 70,
    "W": 70,
    "Japan": 50,
    "J": 50,
    "JP": 50,
    "Korea": 40,
    "K": 40,
    "Asia": 40,
    "France": 35,
    "F": 35,
    "Germany": 35,
    "G": 35,
    "Spain": 35,
    "S": 35,
    "Italy": 35,
    "I": 35,
    "Australia": 60,
    "A": 60,
    "Brazil": 30,
    "B": 30,
    "China": 30,
    "C": 30,
}

# Tags that mark ROMs for removal
REMOVE_TAGS = {
    "Beta",
    "Proto",
    "Prototype",
    "Sample",
    "Demo",
    "Preview",
    "Promo",
    "Pre-Release",
    "Prerelease",
    "Debug",
    "Test",
    "Alpha",
    "Unl",
    "Unlicensed",
    "Pirate",
    "Hack",
    "Hack",
    "Homebrew",
    "Aftermarket",
    "Alt",
    "Alternative",
    "Rev",
    "Revision",
    " v1",
    " v2",
    " v3",
    " v4",
    " v5",
    " v6",
    " v7",
    " v8",
    " v9",
}

# Bracket tags for bad dumps
REMOVE_BRACKET_TAGS = {"[h", "[b", "[p", "[t", "[o", "[f", "[B", "[c", "[a"}

# Preferred formats per platform
PREFERRED_FORMATS: Dict[str, str] = {}

# Platforms to skip
SKIP_PLATFORMS: Set[str] = set()


@dataclass
class RomInfo:
    """Information about a single ROM file."""

    path: Path
    platform: str
    name: str
    regions: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    revision: Optional[str] = None
    version: Optional[str] = None
    is_beta: bool = False
    is_proto: bool = False
    is_demo: bool = False
    is_hack: bool = False
    is_aftermarket: bool = False
    is_good_dump: bool = False
    md5: Optional[str] = None
    size: int = 0

    def __post_init__(self):
        self._parse_filename()
        if self.path.exists():
            self.size = self.path.stat().st_size

    def _parse_filename(self):
        """Extract metadata from filename."""
        filename = self.path.name

        # Check for revision/version indicators
        rev_match = re.search(r"\(Rev\s*([A-Z0-9]+)\)", filename, re.IGNORECASE)
        if rev_match:
            self.revision = rev_match.group(1).upper()

        ver_match = re.search(r"\(v?([0-9]+\.[0-9]+|[0-9]+)\)", filename)
        if ver_match:
            self.version = ver_match.group(1)

        # Extract regions from parentheses
        region_match = re.findall(r"\(([A-Za-z\s,]+)\)", filename)
        for match in region_match:
            parts = [p.strip() for p in match.split(",")]
            for part in parts:
                if part in REGION_PRIORITY:
                    self.regions.append(part)

        # Check tags
        for tag in REMOVE_TAGS:
            if tag.lower() in filename.lower():
                self.tags.append(tag)
                if "beta" in tag.lower():
                    self.is_beta = True
                elif "proto" in tag.lower():
                    self.is_proto = True
                elif "demo" in tag.lower():
                    self.is_demo = True
                elif "hack" in tag.lower():
                    self.is_hack = True

        # Check bracket tags
        brackets = re.findall(r"\[([^\]]+)\]", filename)
        for b in brackets:
            for bad_tag in REMOVE_BRACKET_TAGS:
                if b.lower().startswith(bad_tag[1:].lower()):
                    self.is_aftermarket = True
                    break
            if b.lower() in {"[!]", "[a]", "[o]"}:
                self.is_good_dump = True

    def get_region_priority(self) -> int:
        """Get highest region priority."""
        if not self.regions:
            return 0
        return max(REGION_PRIORITY.get(r, 0) for r in self.regions)

    def get_revision_score(self) -> int:
        """Get numeric revision score."""
        if self.revision:
            if self.revision.isdigit():
                return int(self.revision)
            return ord(self.revision[0]) - ord("A") + 1
        if self.version:
            try:
                return int(self.version.replace(".", ""))
            except ValueError:
                return 0
        return 0

    def should_remove(self) -> Tuple[bool, str]:
        """Check if this ROM should be removed."""
        reasons = []

        if self.is_beta:
            reasons.append("Beta")
        if self.is_proto:
            reasons.append("Prototype")
        if self.is_hack:
            reasons.append("Hack")
        if self.is_demo:
            reasons.append("Demo")
        if self.is_aftermarket:
            reasons.append("Aftermarket/Bad dump")
        if self.tags:
            reasons.append(f"Tags: {', '.join(self.tags)}")

        return (len(reasons) > 0, "; ".join(reasons) if reasons else "")


class DuplicateDetector:
    """Detects duplicate ROMs in a collection."""

    def __init__(self, roms_dir: Path):
        self.roms_dir = roms_dir
        self.roms: List[RomInfo] = []
        self.duplicates: List[Dict] = []
        self.logger = logging.getLogger(__name__)

    def scan(self, compute_hashes: bool = True, platform_filter: Optional[str] = None):
        """Scan ROMs directory."""
        self.logger.info(f"Scanning {self.roms_dir}...")
        self.roms = []

        for platform_dir in self.roms_dir.iterdir():
            if not platform_dir.is_dir():
                continue

            platform_name = platform_dir.name

            if platform_name in SKIP_PLATFORMS:
                self.logger.info(f"Skipping platform: {platform_name}")
                continue

            if platform_filter and platform_name != platform_filter:
                continue

            for rom_file in platform_dir.rglob("*"):
                if not rom_file.is_file():
                    continue

                rom = RomInfo(
                    path=rom_file,
                    platform=platform_name,
                    name=rom_file.stem,
                )

                if compute_hashes:
                    rom.md5 = self._compute_md5(rom_file)

                self.roms.append(rom)

        self.logger.info(f"Found {len(self.roms)} ROMs")

    def _compute_md5(self, filepath: Path) -> str:
        """Compute MD5 hash of file."""
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def find_duplicates(self):
        """Find duplicate ROMs."""
        self.logger.info("Finding duplicates...")
        self.duplicates = []

        # Group by hash
        hash_groups: Dict[str, List[RomInfo]] = defaultdict(list)
        for rom in self.roms:
            if rom.md5:
                hash_groups[rom.md5].append(rom)

        # Find hash duplicates
        for roms in hash_groups.values():
            if len(roms) > 1:
                keeper = self._select_keeper(roms)
                for rom in roms:
                    if rom != keeper:
                        self.duplicates.append(
                            {
                                "platform": rom.platform,
                                "remove": str(rom.path.relative_to(self.roms_dir)),
                                "keep": str(keeper.path.relative_to(self.roms_dir)),
                                "reason": "Exact hash match",
                                "size": rom.size,
                            }
                        )

        # Group by name within platform
        name_groups: Dict[Tuple[str, str], List[RomInfo]] = defaultdict(list)
        for rom in self.roms:
            key = (rom.platform, rom.name.lower())
            name_groups[key].append(rom)

        # Find name-based duplicates
        for (platform, name), roms in name_groups.items():
            if len(roms) > 1:
                keeper = self._select_keeper(roms)
                for rom in roms:
                    if rom != keeper:
                        reason = self._get_removal_reason(rom, keeper)
                        dup_key = str(rom.path.relative_to(self.roms_dir))
                        # Avoid duplicates from hash matching
                        if not any(d["remove"] == dup_key for d in self.duplicates):
                            self.duplicates.append(
                                {
                                    "platform": rom.platform,
                                    "remove": dup_key,
                                    "keep": str(keeper.path.relative_to(self.roms_dir)),
                                    "reason": reason,
                                    "size": rom.size,
                                }
                            )

        self.logger.info(f"Found {len(self.duplicates)} duplicates")

    def _select_keeper(self, roms: List[RomInfo]) -> RomInfo:
        """Select best ROM to keep from duplicates."""

        def score(rom: RomInfo) -> Tuple:
            return (
                0 if rom.is_aftermarket else 1,
                0 if rom.is_beta else 1,
                0 if rom.is_proto else 1,
                0 if rom.is_hack else 1,
                0 if rom.is_demo else 1,
                1 if rom.is_good_dump else 0,
                rom.get_region_priority(),
                rom.get_revision_score(),
                -len(str(rom.path)),  # Prefer shorter paths
            )

        return max(roms, key=score)

    def _get_removal_reason(self, rom: RomInfo, keeper: RomInfo) -> str:
        """Get reason for removing a ROM."""
        reasons = []

        should_remove, reason = rom.should_remove()
        if should_remove:
            reasons.append(reason)

        if rom.get_region_priority() < keeper.get_region_priority():
            rom_regions = ", ".join(rom.regions) if rom.regions else "Unknown"
            reasons.append(f"Lower region priority: {rom_regions}")

        if rom.get_revision_score() < keeper.get_revision_score():
            rev = rom.revision or rom.version or "base"
            reasons.append(f"Older revision: {rev}")

        if not rom.is_good_dump and keeper.is_good_dump:
            reasons.append("Not verified dump")

        if not reasons:
            reasons.append("Duplicate (name match)")

        return "; ".join(reasons)

    def generate_report(self, output_path: Path) -> Tuple[int, float]:
        """Generate CSV report of duplicates."""
        self.logger.info(f"Writing report to {output_path}...")

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["platform", "remove", "keep", "reason", "size_mb"]
            )
            writer.writeheader()

            for dup in sorted(self.duplicates, key=lambda d: (d["platform"], d["remove"])):
                writer.writerow(
                    {
                        "platform": dup["platform"],
                        "remove": dup["remove"],
                        "keep": dup["keep"],
                        "reason": dup["reason"],
                        "size_mb": f"{dup['size'] / 1_000_000:.2f}",
                    }
                )

        total_size = sum(d["size"] for d in self.duplicates)
        return len(self.duplicates), total_size

    def save_cache(self, path: Path):
        """Save scan results to cache."""
        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "roms": [
                {
                    "path": str(r.path),
                    "md5": r.md5,
                    "size": r.size,
                }
                for r in self.roms
            ],
        }
        with open(path, "w") as f:
            json.dump(cache_data, f)


class RomPurger:
    """Handles removal/quarantine of duplicate ROMs."""

    def __init__(self, roms_dir: Path, quarantine_dir: Path):
        self.roms_dir = roms_dir
        self.quarantine_dir = quarantine_dir
        self.logger = logging.getLogger(__name__)

    def purge(self, duplicates: List[Dict], mode: str = "dry-run") -> Tuple[int, float, List[str]]:
        """
        Remove duplicates.
        mode: 'dry-run', 'quarantine', or 'delete'
        """
        if mode == "dry-run":
            self.logger.info("DRY RUN - no files will be modified")

        removed_count = 0
        removed_size = 0
        errors = []

        for dup in duplicates:
            rom_path = self.roms_dir / dup["remove"]

            if not rom_path.exists():
                self.logger.warning(f"File not found: {rom_path}")
                continue

            if mode == "dry-run":
                self.logger.info(
                    f"Would remove: {dup['remove']} ({dup['size'] / 1_000_000:.2f} MB)"
                )
                self.logger.info(f"  Reason: {dup['reason']}")
                self.logger.info(f"  Keeping: {dup['keep']}")

            elif mode == "quarantine":
                try:
                    dest = self.quarantine_dir / dup["remove"]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(rom_path), str(dest))
                    self.logger.info(f"Quarantined: {dup['remove']}")
                    removed_count += 1
                    removed_size += dup["size"]
                except Exception as e:
                    errors.append(f"{rom_path}: {e}")
                    self.logger.error(f"Error quarantining {rom_path}: {e}")

            elif mode == "delete":
                try:
                    rom_path.unlink()
                    self.logger.info(f"Deleted: {dup['remove']}")
                    removed_count += 1
                    removed_size += dup["size"]
                except Exception as e:
                    errors.append(f"{rom_path}: {e}")
                    self.logger.error(f"Error deleting {rom_path}: {e}")

        if mode != "dry-run":
            self.logger.info(
                f"Removed {removed_count} files, freed {removed_size / 1_000_000_000:.2f} GB"
            )

        return removed_count, removed_size, errors
