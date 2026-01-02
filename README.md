# retro-romset-cleaner

ROM deduplication tool for retro game collections. Identifies and removes duplicates based on:

- Exact hash matches (MD5)
- Region priority (USA > Europe > Japan > World)
- Revision variants (keeps latest)
- Format preferences (per-platform)
- Bad dumps, betas, prototypes, hacks (always removed)

## Installation

```bash
uv tool install .
```

Or run directly:

```bash
uv run main.py --scan
```

## Usage

```bash
# Default: scan (if needed) + dry-run showing what would be removed
retro-romset-cleaner

# Scan and analyze ROMs (read-only)
retro-romset-cleaner --scan

# Generate CSV report of duplicates
retro-romset-cleaner --report

# Show what would be removed
retro-romset-cleaner --purge --dry-run

# Move duplicates to quarantine folder
retro-romset-cleaner --purge --quarantine

# Permanently delete duplicates
retro-romset-cleaner --purge --delete
```

### Options

| Flag | Description |
|------|-------------|
| `--scan` | Scan ROMs directory and find duplicates |
| `--report` | Generate CSV report (`duplicate_report.csv`) |
| `--purge` | Remove duplicates (requires `--dry-run`, `--quarantine`, or `--delete`) |
| `--dry-run` | Show what would be removed without making changes |
| `--quarantine` | Move duplicates to `../_quarantine/` instead of deleting |
| `--delete` | Permanently delete duplicates (requires confirmation) |
| `--no-hash` | Skip MD5 computation for faster scanning |
| `--roms-dir PATH` | Custom ROMs directory (default: `../roms/`) |
| `--platform NAME` | Process only a specific platform |

## Expected Directory Structure

```
parent/
├── roms/
│   ├── Nintendo 64/
│   │   ├── Game (USA).z64
│   │   └── Game (Europe).z64
│   └── SNES/
│       └── Game (USA) (Rev 1).sfc
└── retro-romset-cleaner/
    └── main.py
```

## License

MIT
