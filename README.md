<div align="center">
  <img src="logo.png" alt="retro-romset-cleaner" width="512"/>

  # retro-romset-cleaner

  [![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
  [![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
  [![No Dependencies](https://img.shields.io/badge/Dependencies-None-brightgreen.svg)]()

  **🎮 Clean up your retro ROM collection by automatically identifying and removing duplicates, bad dumps, and unwanted variants 🧹**

</div>

## Features

- **Hash-based deduplication** - Finds exact duplicates via MD5 matching
- **Region priority** - Keeps USA > Europe > Japan > World variants
- **Revision detection** - Automatically keeps the latest revision
- **Bad dump removal** - Removes betas, prototypes, hacks, and bad dumps
- **Format preferences** - Keeps preferred formats per platform (e.g., .d64 for C64)
- **Safe by default** - Dry-run mode shows changes before any files are touched
- **Zero dependencies** - Single Python file, no external packages required

## Quick Start

```bash
# Install
uv tool install .

# Preview what would be removed (safe, read-only)
retro-romset-cleaner

# Move duplicates to quarantine folder
retro-romset-cleaner --purge --quarantine

# Permanently delete duplicates (requires confirmation)
retro-romset-cleaner --purge --delete
```

## Installation

### Using uv (recommended)

```bash
uv tool install .
```

### Run directly without installing

```bash
uv run main.py --scan
```

### Using pip

```bash
pip install .
```

## Usage

### Default Behavior

Running without arguments performs a scan and dry-run:

```bash
retro-romset-cleaner
```

This will:
1. Scan all ROMs in the current directory
2. Generate a CSV report of duplicates
3. Show what would be removed (without actually removing anything)

### Commands

| Command | Description |
|---------|-------------|
| `retro-romset-cleaner` | Scan + dry-run (default) |
| `retro-romset-cleaner --scan` | Scan ROMs directory only |
| `retro-romset-cleaner --report` | Generate CSV duplicate report |
| `retro-romset-cleaner --purge --dry-run` | Preview removals |
| `retro-romset-cleaner --purge --quarantine` | Move duplicates to `_quarantine/` |
| `retro-romset-cleaner --purge --delete` | Permanently delete duplicates |

### Options

| Flag | Description |
|------|-------------|
| `--roms-dir PATH` | Specify ROMs directory (default: current directory) |
| `--platform NAME` | Process only a specific platform |
| `--no-hash` | Skip MD5 computation for faster scanning |

## How It Works

### Duplicate Detection

The tool identifies duplicates in three phases:

1. **Exact hash matches** - Files with identical MD5 hashes
2. **Name-based matches** - Same game, different variants (region, revision, format)
3. **Bad ROM removal** - Betas, prototypes, hacks, and bad dumps

### Priority Scoring

When choosing which ROM to keep, the tool scores each variant:

| Factor | Priority |
|--------|----------|
| Bad dump status | Clean > Bad |
| Source variant | Original > Virtual Console/Mini |
| Good dump tag `[!]` | Verified > Unverified |
| Region | USA > Europe > Japan > World |
| Revision | Higher > Lower |

### Expected Directory Structure

```
roms/
├── Nintendo 64/
│   ├── Game (USA).z64
│   ├── Game (Europe).z64      # duplicate - lower region priority
│   └── Game (USA) (Rev 1).z64 # kept - latest revision
├── SNES/
│   └── Game (USA) [!].sfc     # kept - verified dump
└── Commodore 64/
    ├── Game.d64               # kept - preferred format
    └── Game.tap               # duplicate - non-preferred format
```

### Generated Files

| File | Description |
|------|-------------|
| `duplicate_report.csv` | Full report of all duplicates found |
| `scan_cache.json` | Cached scan results for faster re-runs |
| `dedup.log` | Detailed operation log |

## Configuration

Edit these constants in `main.py` to customize behavior:

| Constant | Purpose | Default |
|----------|---------|---------|
| `REGION_PRIORITY` | Region ranking | USA > Europe > Japan > World |
| `REMOVE_TAGS` | Tags marking bad ROMs | Beta, Proto, Pirate, Demo... |
| `REMOVE_BRACKET_TAGS` | Bracket tags for bad dumps | [h], [b], [p], [t]... |
| `PREFERRED_FORMATS` | Per-platform format preference | C64: .d64, Amiga: .adf... |
| `SKIP_PLATFORMS` | Platforms to skip entirely | MS-DOS, ScummVM, Windows |

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT
