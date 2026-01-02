#!/usr/bin/env python3
"""
ROM Deduplication Tool
Analyzes ROM collections to find and remove duplicates based on:
- Exact hash matches
- Region variants (prioritize USA > Europe > Japan > World)
- Betas/Prototypes/Hacks (always remove)
- Format variants (keep preferred format per system)
- Revision variants (keep latest)

Usage:
    python rom_dedup.py --scan              # Scan and analyze (read-only)
    python rom_dedup.py --report            # Generate CSV report
    python rom_dedup.py --purge --dry-run   # Show what would be removed
    python rom_dedup.py --purge --quarantine # Move duplicates to quarantine
    python rom_dedup.py --purge --delete    # Permanently delete duplicates
"""

import os
import re
import sys
import csv
import json
import hashlib
import argparse
import logging
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set

# Get script directory for relative paths
SCRIPT_DIR = Path(__file__).parent.resolve()
DRIVE_ROOT = SCRIPT_DIR.parent
ROMS_DIR = DRIVE_ROOT / "roms"
QUARANTINE_DIR = DRIVE_ROOT / "_quarantine"
REPORT_FILE = SCRIPT_DIR / "duplicate_report.csv"
SCAN_CACHE = SCRIPT_DIR / "scan_cache.json"
LOG_FILE = SCRIPT_DIR / "dedup.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Region priority (higher = better)
REGION_PRIORITY = {
    'USA': 100,
    'U': 100,
    'US': 100,
    'America': 100,
    'Europe': 80,
    'E': 80,
    'EU': 80,
    'World': 70,
    'W': 70,
    'Japan': 50,
    'J': 50,
    'JP': 50,
    'Korea': 40,
    'K': 40,
    'Asia': 40,
    'France': 35,
    'F': 35,
    'Germany': 35,
    'G': 35,
    'Spain': 35,
    'S': 35,
    'Italy': 35,
    'I': 35,
    'Australia': 60,
    'A': 60,
    'Brazil': 30,
    'B': 30,
    'China': 30,
    'C': 30,
}

# Tags that mark ROMs for removal (always remove these)
REMOVE_TAGS = {
    # Betas and prototypes
    'Beta', 'Proto', 'Prototype', 'Sample', 'Demo', 'Preview', 'Promo',
    'Pre-Release', 'Prerelease', 'Debug', 'Test',
    # Pirate/Unlicensed
    'Pirate', 'Unl', 'Unlicensed', 'Bootleg',
    # Special versions to deprioritize
    'BIOS', 'Program',
}

# Bracket tags that mark bad dumps or hacks [tag]
REMOVE_BRACKET_TAGS = {
    'h', 'h1', 'h2', 'h3', 'h4', 'h5',  # Hacks
    't', 't1', 't2', 't3',  # Trainers
    'p', 'p1', 'p2', 'p3', 'p4', 'p5',  # Pirate
    'b', 'b1', 'b2', 'b3',  # Bad dumps
    'o', 'o1',  # Overdump
    'f', 'f1',  # Fixed
    'T+',  # Translation (deprioritize unless only version)
}

# Good dump indicator (prioritize these)
GOOD_DUMP_TAG = '!'

# Source variants to deprioritize when original exists
SOURCE_VARIANTS = {
    'Virtual Console', 'Switch Online', 'Evercade', 'Wii', '3DS',
    'NSO', 'Classic Mini', 'Mini', 'Genesis Mini', 'Mega Drive Mini',
}

# Preferred formats per system (first in list = preferred)
PREFERRED_FORMATS = {
    'Commodore 64': ['.d64', '.g64', '.crt', '.prg', '.t64', '.tap', '.nib'],
    'Commodore VIC-20': ['.d64', '.crt', '.prg', '.t64', '.tap'],
    'Commodore Amiga': ['.adf', '.ipf', '.lha', '.hdf'],
    'Sinclair ZX Spectrum': ['.tzx', '.z80', '.tap', '.sna'],
    'Amstrad CPC': ['.dsk', '.cdt', '.sna'],
    'MSX': ['.rom', '.dsk', '.cas'],
    'Atari ST': ['.st', '.stx', '.msa', '.ipf'],
    'NEC PC-98': ['.hdi', '.fdi', '.d98', '.fdd'],
}

# Extensions to ignore (not ROMs)
IGNORE_EXTENSIONS = {
    '.txt', '.nfo', '.diz', '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.pdf', '.doc', '.md', '.html', '.htm', '.xml', '.json', '.dat',
    '.cue', '.m3u', '.sfv', '.md5', '.sha1',
    # Game data files (not ROMs)
    '.spr', '.mov', '.dad', '.avi', '.mpg', '.mp3', '.wav', '.ogg',
    '.voc', '.mid', '.xmi', '.pak', '.grp', '.wad', '.cfg', '.ini',
    '.sav', '.srm', '.exe', '.com', '.bat', '.dll', '.so', '.dylib',
}

# Platforms that contain full game installations (skip deduplication)
SKIP_PLATFORMS = {
    'MS-DOS', 'ScummVM', 'Windows', 'Apple Mac OS',
    'Linux', 'DOS', 'PC',
}

# =============================================================================
# FILENAME PARSING
# =============================================================================

class RomInfo:
    """Parsed information about a ROM file."""
    def __init__(self, path: Path):
        self.path = path
        self.filename = path.name
        self.extension = path.suffix.lower()
        self.platform = path.parent.name
        self.size = 0
        self.md5 = None

        # Parsed metadata
        self.base_name = ""
        self.regions: List[str] = []
        self.revision: Optional[str] = None
        self.version: Optional[str] = None
        self.disc_number: Optional[str] = None  # For multi-disc games
        self.side_number: Optional[str] = None  # For multi-side games
        self.tags: Set[str] = set()
        self.bracket_tags: Set[str] = set()
        self.is_bad = False
        self.is_good_dump = False
        self.source_variant: Optional[str] = None

        self._parse_filename()

    def _parse_filename(self):
        """Parse ROM filename to extract metadata."""
        name = self.path.stem

        # Extract all parenthetical tags (Region), (Rev A), (Beta), etc.
        paren_pattern = r'\(([^)]+)\)'
        paren_matches = re.findall(paren_pattern, name)

        # Extract all bracket tags [!], [h1], etc.
        bracket_pattern = r'\[([^\]]+)\]'
        bracket_matches = re.findall(bracket_pattern, name)

        # Get base name by removing all tags
        base = re.sub(paren_pattern, '', name)
        base = re.sub(bracket_pattern, '', base)
        base = re.sub(r'\s+', ' ', base).strip()
        base = re.sub(r'[-_]+$', '', base).strip()
        self.base_name = base

        # Process parenthetical tags
        for tag in paren_matches:
            tag_clean = tag.strip()
            tag_upper = tag_clean.upper()
            tag_parts = [t.strip() for t in re.split(r'[,\s]+', tag_clean)]

            # Check for regions
            for part in tag_parts:
                if part in REGION_PRIORITY or part.upper() in [r.upper() for r in REGION_PRIORITY]:
                    self.regions.append(part)

            # Check for revision
            rev_match = re.match(r'Rev\s*([A-Z0-9]+)', tag_clean, re.IGNORECASE)
            if rev_match:
                self.revision = rev_match.group(1)

            # Check for version
            ver_match = re.match(r'v([\d.]+)', tag_clean, re.IGNORECASE)
            if ver_match:
                self.version = ver_match.group(1)

            # Check for disc/disk number (multi-disc games)
            disc_match = re.match(r'Dis[ck]\s*(\d+)', tag_clean, re.IGNORECASE)
            if disc_match:
                self.disc_number = disc_match.group(1)

            # Check for side number (multi-side games like FDS)
            side_match = re.match(r'Side\s*([AB\d]+)', tag_clean, re.IGNORECASE)
            if side_match:
                self.side_number = side_match.group(1)

            # Check for bad tags
            if tag_clean in REMOVE_TAGS or any(t in tag_clean for t in REMOVE_TAGS):
                self.tags.add(tag_clean)
                self.is_bad = True

            # Check for source variants
            for sv in SOURCE_VARIANTS:
                if sv.lower() in tag_clean.lower():
                    self.source_variant = sv
                    break

        # Process bracket tags
        for tag in bracket_matches:
            tag_clean = tag.strip()
            self.bracket_tags.add(tag_clean)

            if tag_clean == GOOD_DUMP_TAG:
                self.is_good_dump = True
            elif tag_clean.lower() in [t.lower() for t in REMOVE_BRACKET_TAGS]:
                self.is_bad = True
            elif re.match(r'^[hptbof]\d*$', tag_clean, re.IGNORECASE):
                self.is_bad = True

    def get_normalized_name(self) -> str:
        """Get normalized base name for grouping."""
        name = self.base_name.lower()
        # Remove common punctuation differences
        name = re.sub(r"['\"-]", '', name)
        name = re.sub(r'\s+', ' ', name)
        name = name.strip()
        # Include disc/disk number to keep multi-disc games separate
        if self.disc_number:
            name = f"{name} disc {self.disc_number}"
        # Include side number for multi-side games
        if self.side_number:
            name = f"{name} side {self.side_number}"
        return name

    def get_region_priority(self) -> int:
        """Get the highest region priority for this ROM."""
        if not self.regions:
            return 0
        return max(REGION_PRIORITY.get(r, REGION_PRIORITY.get(r.upper(), 0)) for r in self.regions)

    def get_revision_score(self) -> int:
        """Get revision score (higher = newer)."""
        if self.revision:
            # Rev B > Rev A, Rev 2 > Rev 1
            if self.revision.isdigit():
                return int(self.revision)
            elif self.revision.isalpha():
                return ord(self.revision.upper()) - ord('A') + 1
        if self.version:
            # v1.1 > v1.0
            try:
                parts = self.version.split('.')
                score = 0
                for i, p in enumerate(parts):
                    score += int(p) * (100 ** (3-i))
                return score
            except:
                pass
        return 0

    def get_priority_score(self) -> Tuple[int, int, int, int, int]:
        """
        Get overall priority score for comparison.
        Higher tuple = better ROM to keep.
        """
        # Negative is_bad so bad=0 and good=1
        bad_score = 0 if self.is_bad else 1
        good_dump = 1 if self.is_good_dump else 0
        region = self.get_region_priority()
        revision = self.get_revision_score()
        # Prefer non-source-variants
        source = 0 if self.source_variant else 1

        return (bad_score, source, good_dump, region, revision)

    def __repr__(self):
        return f"RomInfo({self.filename})"


# =============================================================================
# DUPLICATE DETECTION
# =============================================================================

class DuplicateDetector:
    """Detects and categorizes duplicate ROMs."""

    def __init__(self, roms_dir: Path):
        self.roms_dir = roms_dir
        self.roms: List[RomInfo] = []
        self.by_hash: Dict[str, List[RomInfo]] = defaultdict(list)
        self.by_name: Dict[str, Dict[str, List[RomInfo]]] = defaultdict(lambda: defaultdict(list))
        self.duplicates: List[Dict] = []

    def scan(self, compute_hashes: bool = True):
        """Scan ROM directory and parse all files."""
        logger.info(f"Scanning {self.roms_dir}...")

        total_files = 0
        for platform_dir in sorted(self.roms_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            if platform_dir.name.startswith('.') or platform_dir.name.startswith('_'):
                continue
            # Skip platforms with full game installations
            if platform_dir.name in SKIP_PLATFORMS:
                logger.info(f"  {platform_dir.name}: SKIPPED (full game installations)")
                continue

            platform_files = 0
            for rom_file in platform_dir.rglob('*'):
                if not rom_file.is_file():
                    continue
                if rom_file.suffix.lower() in IGNORE_EXTENSIONS:
                    continue
                if rom_file.name.startswith('.'):
                    continue
                # Skip files in hidden directories or system folders
                if any(part.startswith('.') for part in rom_file.parts):
                    continue

                try:
                    rom = RomInfo(rom_file)
                    rom.size = rom_file.stat().st_size

                    if compute_hashes and rom.size < 500_000_000:  # Skip huge files
                        rom.md5 = self._compute_md5(rom_file)

                    self.roms.append(rom)
                    platform_files += 1

                    # Index by hash
                    if rom.md5:
                        self.by_hash[rom.md5].append(rom)

                    # Index by normalized name + platform
                    norm_name = rom.get_normalized_name()
                    self.by_name[rom.platform][norm_name].append(rom)

                except Exception as e:
                    logger.warning(f"Error processing {rom_file}: {e}")

            total_files += platform_files
            logger.info(f"  {platform_dir.name}: {platform_files} files")

        logger.info(f"Total: {total_files} ROM files scanned")

    def _compute_md5(self, path: Path) -> str:
        """Compute MD5 hash of file."""
        hasher = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def find_duplicates(self):
        """Identify all duplicate sets and mark keepers."""
        logger.info("Finding duplicates...")
        self.duplicates = []
        processed_paths = set()

        # Phase 1: Exact hash duplicates
        for md5, roms in self.by_hash.items():
            if len(roms) > 1:
                # All are exact duplicates, pick best one
                roms_sorted = sorted(roms, key=lambda r: r.get_priority_score(), reverse=True)
                keeper = roms_sorted[0]

                for rom in roms_sorted[1:]:
                    if rom.path not in processed_paths:
                        self.duplicates.append({
                            'platform': rom.platform,
                            'remove': str(rom.path.relative_to(self.roms_dir)),
                            'keep': str(keeper.path.relative_to(self.roms_dir)),
                            'reason': 'Exact duplicate (hash match)',
                            'size': rom.size,
                        })
                        processed_paths.add(rom.path)

        # Phase 2: Name-based duplicates within each platform
        for platform, name_groups in self.by_name.items():
            for norm_name, roms in name_groups.items():
                if len(roms) <= 1:
                    continue

                # Skip already processed
                remaining = [r for r in roms if r.path not in processed_paths]
                if len(remaining) <= 1:
                    continue

                # Check for format duplicates first
                by_format = defaultdict(list)
                for rom in remaining:
                    by_format[rom.extension].append(rom)

                # Get preferred format for this platform
                preferred_formats = self._get_preferred_formats(platform)

                # Sort formats by preference
                format_order = []
                for fmt in preferred_formats:
                    if fmt in by_format:
                        format_order.append(fmt)
                for fmt in by_format:
                    if fmt not in format_order:
                        format_order.append(fmt)

                # Pick keeper: best ROM from best format
                keeper = None
                for fmt in format_order:
                    if by_format[fmt]:
                        candidates = sorted(by_format[fmt], key=lambda r: r.get_priority_score(), reverse=True)
                        if keeper is None:
                            keeper = candidates[0]
                        break

                if keeper is None:
                    continue

                # Mark others as duplicates
                for rom in remaining:
                    if rom.path == keeper.path:
                        continue
                    if rom.path in processed_paths:
                        continue

                    # Determine reason
                    reason = self._get_removal_reason(rom, keeper)

                    self.duplicates.append({
                        'platform': rom.platform,
                        'remove': str(rom.path.relative_to(self.roms_dir)),
                        'keep': str(keeper.path.relative_to(self.roms_dir)),
                        'reason': reason,
                        'size': rom.size,
                    })
                    processed_paths.add(rom.path)

        # Phase 3: Always-remove bad ROMs (even if no duplicate exists)
        for rom in self.roms:
            if rom.path in processed_paths:
                continue
            if rom.is_bad:
                self.duplicates.append({
                    'platform': rom.platform,
                    'remove': str(rom.path.relative_to(self.roms_dir)),
                    'keep': '(none - bad ROM)',
                    'reason': f'Bad ROM: {", ".join(rom.tags) or ", ".join(rom.bracket_tags)}',
                    'size': rom.size,
                })
                processed_paths.add(rom.path)

        logger.info(f"Found {len(self.duplicates)} duplicates")
        return self.duplicates

    def _get_preferred_formats(self, platform: str) -> List[str]:
        """Get preferred format order for a platform."""
        for plat_name, formats in PREFERRED_FORMATS.items():
            if plat_name.lower() in platform.lower():
                return formats
        return []

    def _get_removal_reason(self, rom: RomInfo, keeper: RomInfo) -> str:
        """Determine why a ROM should be removed."""
        reasons = []

        if rom.is_bad:
            if rom.tags:
                reasons.append(f"Bad variant: {', '.join(rom.tags)}")
            if any(t.lower() in [x.lower() for x in REMOVE_BRACKET_TAGS] for t in rom.bracket_tags):
                reasons.append(f"Bad dump tag: [{', '.join(rom.bracket_tags)}]")

        if rom.source_variant and not keeper.source_variant:
            reasons.append(f"Source variant: {rom.source_variant}")

        if rom.extension != keeper.extension:
            reasons.append(f"Non-preferred format: {rom.extension}")

        if rom.get_region_priority() < keeper.get_region_priority():
            rom_regions = ', '.join(rom.regions) if rom.regions else 'Unknown'
            reasons.append(f"Lower region priority: {rom_regions}")

        if rom.get_revision_score() < keeper.get_revision_score():
            rev = rom.revision or rom.version or 'base'
            reasons.append(f"Older revision: {rev}")

        if not rom.is_good_dump and keeper.is_good_dump:
            reasons.append("Not verified dump")

        if not reasons:
            reasons.append("Duplicate (name match)")

        return '; '.join(reasons)

    def generate_report(self, output_path: Path):
        """Generate CSV report of duplicates."""
        logger.info(f"Writing report to {output_path}...")

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['platform', 'remove', 'keep', 'reason', 'size_mb'])
            writer.writeheader()

            for dup in sorted(self.duplicates, key=lambda d: (d['platform'], d['remove'])):
                writer.writerow({
                    'platform': dup['platform'],
                    'remove': dup['remove'],
                    'keep': dup['keep'],
                    'reason': dup['reason'],
                    'size_mb': f"{dup['size'] / 1_000_000:.2f}",
                })

        total_size = sum(d['size'] for d in self.duplicates)
        logger.info(f"Report written: {len(self.duplicates)} duplicates, {total_size / 1_000_000_000:.2f} GB to remove")

    def save_cache(self, path: Path):
        """Save scan results to cache."""
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'roms': [
                {
                    'path': str(r.path),
                    'md5': r.md5,
                    'size': r.size,
                }
                for r in self.roms
            ]
        }
        with open(path, 'w') as f:
            json.dump(cache_data, f)
        logger.info(f"Cache saved to {path}")


# =============================================================================
# PURGE OPERATIONS
# =============================================================================

class Purger:
    """Handles removal/quarantine of duplicate ROMs."""

    def __init__(self, roms_dir: Path, quarantine_dir: Path):
        self.roms_dir = roms_dir
        self.quarantine_dir = quarantine_dir

    def purge(self, duplicates: List[Dict], mode: str = 'dry-run'):
        """
        Remove duplicates.
        mode: 'dry-run', 'quarantine', or 'delete'
        """
        if mode == 'dry-run':
            logger.info("DRY RUN - no files will be modified")

        removed_count = 0
        removed_size = 0
        errors = []

        for dup in duplicates:
            rom_path = self.roms_dir / dup['remove']

            if not rom_path.exists():
                logger.warning(f"File not found: {rom_path}")
                continue

            if mode == 'dry-run':
                logger.info(f"Would remove: {dup['remove']} ({dup['size'] / 1_000_000:.2f} MB)")
                logger.info(f"  Reason: {dup['reason']}")
                logger.info(f"  Keeping: {dup['keep']}")

            elif mode == 'quarantine':
                try:
                    dest = self.quarantine_dir / dup['remove']
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    rom_path.rename(dest)
                    logger.info(f"Quarantined: {dup['remove']}")
                    removed_count += 1
                    removed_size += dup['size']
                except Exception as e:
                    errors.append(f"{rom_path}: {e}")
                    logger.error(f"Error quarantining {rom_path}: {e}")

            elif mode == 'delete':
                try:
                    rom_path.unlink()
                    logger.info(f"Deleted: {dup['remove']}")
                    removed_count += 1
                    removed_size += dup['size']
                except Exception as e:
                    errors.append(f"{rom_path}: {e}")
                    logger.error(f"Error deleting {rom_path}: {e}")

        if mode != 'dry-run':
            logger.info(f"Removed {removed_count} files, freed {removed_size / 1_000_000_000:.2f} GB")
            if errors:
                logger.warning(f"{len(errors)} errors occurred")

        return removed_count, removed_size, errors


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='ROM Deduplication Tool')
    parser.add_argument('--scan', action='store_true', help='Scan ROMs directory')
    parser.add_argument('--report', action='store_true', help='Generate duplicate report')
    parser.add_argument('--purge', action='store_true', help='Remove duplicates')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be removed')
    parser.add_argument('--quarantine', action='store_true', help='Move to quarantine instead of delete')
    parser.add_argument('--delete', action='store_true', help='Permanently delete duplicates')
    parser.add_argument('--no-hash', action='store_true', help='Skip hash computation (faster)')
    parser.add_argument('--roms-dir', type=Path, default=Path.cwd(), help='ROMs directory (default: current directory)')
    parser.add_argument('--platform', type=str, help='Only process specific platform')

    args = parser.parse_args()

    # Default to purge dry-run when no action specified
    if not any([args.scan, args.report, args.purge]):
        args.purge = True
        args.dry_run = True

    # Verify paths
    if not args.roms_dir.exists():
        logger.error(f"ROMs directory not found: {args.roms_dir}")
        sys.exit(1)

    detector = DuplicateDetector(args.roms_dir)

    if args.scan or args.report:
        detector.scan(compute_hashes=not args.no_hash)
        detector.find_duplicates()
        detector.save_cache(SCAN_CACHE)

    if args.report:
        detector.generate_report(REPORT_FILE)
        print(f"\nReport saved to: {REPORT_FILE}")
        print(f"Total duplicates found: {len(detector.duplicates)}")
        total_size = sum(d['size'] for d in detector.duplicates)
        print(f"Total space to recover: {total_size / 1_000_000_000:.2f} GB")

    if args.purge:
        if not detector.duplicates:
            # Load from report if scan wasn't done
            if REPORT_FILE.exists():
                logger.info(f"Loading duplicates from {REPORT_FILE}")
                detector.duplicates = []
                with open(REPORT_FILE, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        detector.duplicates.append({
                            'platform': row['platform'],
                            'remove': row['remove'],
                            'keep': row['keep'],
                            'reason': row['reason'],
                            'size': float(row['size_mb']) * 1_000_000,
                        })
            else:
                logger.error("No duplicates found. Run --scan first.")
                sys.exit(1)

        # Determine mode
        if args.delete:
            mode = 'delete'
            print("\n*** WARNING: This will PERMANENTLY DELETE files! ***")
            confirm = input("Type 'DELETE' to confirm: ")
            if confirm != 'DELETE':
                print("Aborted.")
                return
        elif args.quarantine:
            mode = 'quarantine'
        else:
            mode = 'dry-run'

        purger = Purger(args.roms_dir, QUARANTINE_DIR)
        purger.purge(detector.duplicates, mode=mode)

        # After dry-run, show next steps
        if mode == 'dry-run':
            print(f"\nReport saved to: {REPORT_FILE}")
            print("\nTo permanently delete duplicates, run:")
            print(f"  retro-romset-cleaner --purge --delete --roms-dir {args.roms_dir}")


if __name__ == '__main__':
    main()
