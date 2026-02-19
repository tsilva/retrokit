# CLAUDE.md

ROM deduplication tool for retro game collections. Identifies and removes duplicates based on hash matches, region priority, format preferences, revision variants, and bad dump indicators.

## Commands

```bash
# Install
uv tool install .

# Default: auto-scan + dry-run showing what would be removed
retro-romset-cleaner

# Individual operations
retro-romset-cleaner --scan                    # Scan ROMs (read-only)
retro-romset-cleaner --report                  # Generate CSV report
retro-romset-cleaner --purge --dry-run         # Preview removals
retro-romset-cleaner --purge --quarantine      # Move to _quarantine/
retro-romset-cleaner --purge --delete          # Permanently delete

# Options
--no-hash                  # Skip MD5 computation (faster)
--platform "Nintendo 64"   # Process single platform
--roms-dir /path/to/roms   # Specify ROMs directory
```

## Architecture

Single-file Python script (`main.py`), Python >=3.9, no external dependencies.

**Classes:**
- `RomInfo` - Parses filenames for regions, revisions, tags, dump quality
- `DuplicateDetector` - Scans, indexes by hash/name, finds duplicates
- `Purger` - Handles dry-run, quarantine, and delete modes

**Duplicate detection phases:**
1. Exact MD5 hash matches
2. Name-based matches within platform (format preferences apply)
3. Always-remove bad ROMs (betas, prototypes, hacks, bad dumps)

**Priority scoring:** bad dump status > source variant > good dump tag > region priority > revision number

## Configuration

Edit these dictionaries in `main.py` to customize:

| Constant | Purpose | Default |
|----------|---------|---------|
| `REGION_PRIORITY` | Region ranking | USA > Europe > Japan > World |
| `REMOVE_TAGS` | Parenthetical tags to remove | Beta, Proto, Pirate, Demo... |
| `REMOVE_BRACKET_TAGS` | Bracket tags for bad dumps | [h], [b], [p], [t]... |
| `PREFERRED_FORMATS` | Per-platform format preference | C64: .d64, Amiga: .adf... |
| `SKIP_PLATFORMS` | Platforms to skip | MS-DOS, ScummVM, Windows |

## Directory Structure

Expected input:
```
<roms-dir>/
  Platform Name/
    game.rom
    game (USA).rom
```

Generated files (in script directory):
- `scan_cache.json` - Cached scan results
- `duplicate_report.csv` - Removal report
- `dedup.log` - Log file
