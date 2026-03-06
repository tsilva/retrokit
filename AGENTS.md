# CLAUDE.md

Retro gaming toolkit — AI-powered platform asset generation for Pegasus Frontend themes and smart ROM collection deduplication.

## Commands

```bash
# Install
uv tool install .

# Asset generation
retrokit assets generate <platform_id> "<Platform Name>"   # Generate device + logo assets
retrokit assets generate amigacd32 "Commodore Amiga CD32"  # Example
retrokit assets list                                        # List generated platforms
retrokit assets deploy [platform_id] --theme colorful       # Deploy to theme directory
retrokit assets deploy --dry-run                            # Preview deployment
retrokit assets themes --init                               # Create default themes.yaml
retrokit assets config                                      # Show current config

# ROM cleaning
retrokit roms scan --roms-dir /path/to/roms                # Scan for duplicates
retrokit roms report --roms-dir /path/to/roms              # Generate CSV report
retrokit roms clean --dry-run                              # Preview removals
retrokit roms clean --quarantine                           # Move to _quarantine/
retrokit roms clean --delete                               # Permanently delete

# ROM options
--no-hash                  # Skip MD5 computation (faster)
--platform "Nintendo 64"   # Process single platform
```

## Architecture

Python package in `src/retrokit/`, Python >=3.11. CLI built with Typer. Entry point: `retrokit.cli:app`.

**Modules:**
- `cli.py` — Typer CLI with `assets` and `roms` subcommand groups
- `config.py` — Pydantic Settings for env-based configuration
- `generator.py` — `AssetGenerator` orchestrates device/logo generation pipeline
- `gemini_client.py` — `GeminiClient` wraps Gemini API for image generation/editing
- `image_processor.py` — Image processing: difference matting, chroma key, alpha extraction, quantization, monochrome conversion, logo variants
- `prompts.py` — `AssetPrompts` templates and `AssetType` configs for device/logo generation
- `theme_config.py` — YAML-based theme configuration for asset deployment
- `roms.py` — `RomInfo`, `DuplicateDetector`, `RomPurger` for ROM deduplication

**Legacy:** `main.py` at project root is the original standalone ROM dedup script (superseded by `src/retrokit/roms.py` + CLI).

**Key dependencies:** pillow, httpx, pydantic-settings, typer, rich, pyyaml, imagequant

**Asset generation pipeline:**
1. User provides reference images in `.input/<platform_id>/` (platform.jpg + logo.png)
2. Gemini API generates device image on white background from reference
3. Gemini edits to black background (same subject)
4. Difference matting extracts precise alpha channel from white/black pair
5. Logo generated from reference, chroma key removes white background
6. 4 logo variants created (dark/light x color/monochrome)
7. All PNGs quantized via libimagequant

**ROM duplicate detection phases:**
1. Exact MD5 hash matches
2. Name-based matches within platform
3. Always-remove bad ROMs (betas, prototypes, hacks, bad dumps)

**Priority scoring:** bad dump > beta/proto/hack/demo > good dump tag > region priority > revision number

## Configuration

### Environment (.env)
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes (assets) | — | Google Gemini API key |
| `RETRO_INPUT_DIR` | No | `.input` | Reference images directory |
| `RETRO_OUTPUT_DIR` | No | `output` | Generated assets directory |
| `RETRO_QUANTIZE` | No | `true` | Enable PNG quantization |
| `RETRO_QUANTIZE_QUALITY` | No | `65-80` | Quantization quality range |

### Theme deployment (themes.yaml)
Defines where assets are deployed. Created via `retrokit assets themes --init`. Searched in cwd, project root, or `~/.config/retrokit/`.

### ROM cleaning constants
Edit in `src/retrokit/roms.py`: `REGION_PRIORITY`, `REMOVE_TAGS`, `REMOVE_BRACKET_TAGS`, `PREFERRED_FORMATS`, `SKIP_PLATFORMS`.

## Directory Structure

```
.input/<platform_id>/          # Reference images (user-provided)
  platform.jpg                 # Device/console photo
  logo.png                     # Official platform logo
output/assets/images/          # Generated assets
  devices/<platform_id>.png    # 2160x2160 device render
  logos/Dark - Black/          # White monochrome logos
  logos/Dark - Color/          # Color logos (for dark themes)
  logos/Light - Color/         # Color logos (for light themes)
  logos/Light - White/         # Black monochrome logos
themes.yaml                   # Theme deployment config
.env                          # API keys and settings
```

## Keep README.md up to date with any significant project changes.
