# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a ROM deduplication tool for retro game collections. It identifies and removes duplicate ROMs based on hash matches, region priority, format preferences, revision variants, and bad dump indicators.

## Installation

```bash
uv tool install .
```

## Running the Tool

```bash
# Default: scan (if needed) + dry-run showing what would be removed
retro-romset-cleaner

# Scan and analyze ROMs (read-only)
retro-romset-cleaner --scan

# Generate CSV report of duplicates
retro-romset-cleaner --report

# Show what would be removed (dry run)
retro-romset-cleaner --purge --dry-run

# Move duplicates to quarantine folder
retro-romset-cleaner --purge --quarantine

# Permanently delete duplicates
retro-romset-cleaner --purge --delete

# Skip hash computation for faster scanning
retro-romset-cleaner --scan --no-hash

# Process specific platform only
retro-romset-cleaner --scan --platform "Nintendo 64"
```

## Architecture

The tool is a single-file Python script (`main.py`) with no external dependencies beyond the standard library.

**Key Classes:**
- `RomInfo` - Parses ROM filenames to extract metadata (regions, revisions, tags, dump quality indicators)
- `DuplicateDetector` - Scans directories, indexes ROMs by hash and normalized name, identifies duplicates
- `Purger` - Handles file removal with dry-run, quarantine, and delete modes

**Duplicate Detection Phases:**
1. Exact hash matches (MD5)
2. Name-based matches within each platform (considering format preferences)
3. Always-remove bad ROMs (betas, prototypes, hacks, bad dumps)

**Priority Scoring:**
ROMs are ranked by: bad dump status → source variant → good dump tag → region priority → revision number

## Configuration Constants

The following dictionaries in `main.py` control deduplication behavior:
- `REGION_PRIORITY` - Region preference ranking (USA > Europe > Japan > World)
- `REMOVE_TAGS` - Parenthetical tags marking ROMs for removal (Beta, Proto, Pirate, etc.)
- `REMOVE_BRACKET_TAGS` - Square bracket tags for hacks/bad dumps ([h], [b], [p], etc.)
- `PREFERRED_FORMATS` - Per-platform format preferences (e.g., Commodore 64 prefers .d64)
- `SKIP_PLATFORMS` - Platforms excluded from deduplication (MS-DOS, ScummVM, etc.)

## Directory Structure Assumptions

The tool expects ROMs organized as:
```
../roms/
  Platform Name/
    game.rom
    game (USA).rom
```

Output files are created in the script directory:
- `duplicate_report.csv` - Generated report
- `scan_cache.json` - Cached scan results
- `dedup.log` - Log file
