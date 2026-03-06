"""Command-line interface for retrokit.

Retro gaming toolkit: ROM cleaning and asset generation.

Asset Generation Workflow:
1. Place reference images in .input/<platform_id>/
   - platform.jpg (or .png) - photo of the console/device
   - logo.png (or .jpg) - the platform logo
2. Run: retrokit assets generate <platform_id> "<platform_name>"
3. Run: retrokit assets deploy [platform_id] --theme colorful

ROM Cleaning Workflow:
1. Run: retrokit roms scan --roms-dir /path/to/roms
2. Run: retrokit roms report
3. Run: retrokit roms clean --dry-run
4. Run: retrokit roms clean --quarantine (or --delete)
"""

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import get_settings
from .generator import AssetGenerator
from .roms import DuplicateDetector, RomPurger
from .theme_config import (
    ThemeConfigError,
    create_default_themes_config,
    load_themes_config,
)

app = typer.Typer(
    name="retrokit",
    help="Retro gaming toolkit: ROM cleaning and asset generation",
    add_completion=False,
)
console = Console()


# =============================================================================
# ASSETS SUBCOMMAND GROUP
# =============================================================================

assets_app = typer.Typer(
    name="assets",
    help="Generate retro gaming platform assets using Gemini AI",
    add_completion=False,
)
app.add_typer(assets_app, name="assets")


# =============================================================================
# GENERATE COMMAND
# =============================================================================


@assets_app.command()
def generate(
    platform_id: str = typer.Argument(
        ...,
        help="Platform identifier (e.g., 'amigacd32')",
    ),
    platform_name: str = typer.Argument(
        ...,
        help="Full platform name (e.g., 'Commodore Amiga CD32')",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing assets",
    ),
) -> None:
    """Generate platform assets from reference images.

    Reference images must be placed in .input/<platform_id>/:
    - platform.jpg (or .png) - photo of the console/device
    - logo.png (or .jpg) - the platform logo

    Output matches theme structure for direct copying:
    - .output/assets/images/devices/<platform_id>.png
    - .output/assets/images/logos/*/platform_id>.png

    Example:
        retrokit generate amigacd32 "Commodore Amiga CD32"
    """
    try:
        settings = get_settings()
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        console.print("[dim]Make sure GEMINI_API_KEY is set in .env file[/dim]")
        raise typer.Exit(1) from None

    # Check if device already exists (unless force)
    device_path = settings.output_dir / "assets" / "images" / "devices" / f"{platform_id}.png"
    if device_path.exists() and not force:
        console.print(f"[yellow]Assets for '{platform_id}' already exist.[/yellow]")
        console.print("Use --force to regenerate.")
        raise typer.Exit(1)

    # Verify reference images exist
    generator = AssetGenerator(settings, console)
    missing = generator.verify_references(platform_id)

    if missing:
        console.print("[red]Missing reference images:[/red]")
        for m in missing:
            console.print(f"  [red]✗[/red] {m}")
        console.print()
        input_dir = settings.get_input_dir(platform_id)
        console.print(f"[bold]Please add reference images to:[/bold] {input_dir}")
        console.print("  - platform.jpg (or .png) - photo of the console")
        console.print("  - logo.png (or .jpg) - the platform logo")
        raise typer.Exit(1)

    # Print header
    info = Table.grid(padding=1)
    info.add_column(style="bold cyan", justify="right")
    info.add_column()
    info.add_row("Platform ID:", platform_id)
    info.add_row("Platform Name:", platform_name)
    info.add_row("Input:", str(settings.get_input_dir(platform_id)))
    info.add_row("Output:", str(settings.output_dir / "assets" / "images"))

    console.print(Panel(info, title="[bold]Generating Assets[/bold]"))

    # Generate assets
    result = generator.generate(platform_id, platform_name)

    # Print summary
    console.print()
    if result.success:
        console.print(Panel("[bold green]Generation Complete[/bold green]"))
        console.print()

        table = Table(title="Generated Files")
        table.add_column("File", style="cyan")
        table.add_column("Dimensions", justify="right")

        for asset in result.assets:
            rel_path = asset.output_path.relative_to(settings.output_dir)
            table.add_row(
                str(rel_path),
                f"{asset.dimensions[0]}x{asset.dimensions[1]}",
            )
        console.print(table)

        console.print()
        console.print("[bold]To deploy, copy output to your theme:[/bold]")
        console.print(f"  cp -r {settings.output_dir}/ /path/to/theme/")
    else:
        console.print(Panel("[bold red]Generation Failed[/bold red]"))
        console.print()
        for name, error in result.errors:
            console.print(f"  [red]✗[/red] {name}: {error}")
        raise typer.Exit(1)


# =============================================================================
# LIST COMMAND
# =============================================================================


@assets_app.command(name="list")
def list_platforms() -> None:
    """List generated platforms."""
    try:
        settings = get_settings()
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from None

    devices_dir = settings.output_dir / "assets" / "images" / "devices"
    if not devices_dir.exists():
        console.print("[dim]No platforms generated yet.[/dim]")
        return

    platforms = sorted([f.stem for f in devices_dir.glob("*.png")])

    if not platforms:
        console.print("[dim]No platforms generated yet.[/dim]")
        return

    table = Table(title="Generated Platforms")
    table.add_column("Platform ID", style="cyan")
    table.add_column("Device")
    table.add_column("Logos")

    logos_base = settings.output_dir / "assets" / "images" / "logos"

    for platform_id in platforms:
        device_exists = (devices_dir / f"{platform_id}.png").exists()
        logo_count = sum(
            1
            for d in ["Dark - Black", "Dark - Color", "Light - Color", "Light - White"]
            if (logos_base / d / f"{platform_id}.png").exists()
        )
        table.add_row(
            platform_id,
            "[green]✓[/green]" if device_exists else "[red]✗[/red]",
            f"{logo_count}/4",
        )

    console.print(table)


# =============================================================================
# DEPLOY COMMAND
# =============================================================================


@assets_app.command()
def deploy(
    platform_id: str | None = typer.Argument(
        None,
        help="Platform to deploy (omit to deploy all)",
    ),
    theme: str = typer.Option(
        "colorful",
        "--theme",
        "-t",
        help="Theme to deploy to",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be copied without copying",
    ),
) -> None:
    """Deploy generated assets to theme folder.

    Copies device and logo images from output to your theme directory.
    By default deploys all platforms; specify a platform_id for single deploy.

    Examples:
        retrokit deploy                    # Deploy all platforms
        retrokit deploy amigacd32          # Deploy single platform
        retrokit deploy --theme colorful   # Specify theme
        retrokit deploy -n                 # Dry run (show only)
    """
    try:
        settings = get_settings()
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from None

    try:
        themes_config = load_themes_config()
    except ThemeConfigError as e:
        console.print(f"[red]Theme config error:[/red] {e}")
        console.print("Create themes.yaml with: retrokit themes --init")
        raise typer.Exit(1) from None

    theme_config = themes_config.get_theme(theme)
    if not theme_config:
        available = ", ".join(themes_config.list_themes())
        console.print(f"[red]Theme '{theme}' not found.[/red]")
        console.print(f"Available themes: {available}")
        raise typer.Exit(1) from None

    # Get platforms to deploy
    devices_dir = settings.output_dir / "assets" / "images" / "devices"
    if not devices_dir.exists():
        console.print("[red]No generated assets found.[/red]")
        raise typer.Exit(1) from None

    if platform_id:
        if not (devices_dir / f"{platform_id}.png").exists():
            console.print(f"[red]Platform '{platform_id}' not found in output.[/red]")
            raise typer.Exit(1) from None
        platforms = [platform_id]
    else:
        platforms = sorted([f.stem for f in devices_dir.glob("*.png")])

    if not platforms:
        console.print("[dim]No platforms to deploy.[/dim]")
        return

    # Logo directories in output
    logo_dirs = {
        "Dark - Black": settings.output_dir / "assets" / "images" / "logos" / "Dark - Black",
        "Dark - Color": settings.output_dir / "assets" / "images" / "logos" / "Dark - Color",
        "Light - Color": settings.output_dir / "assets" / "images" / "logos" / "Light - Color",
        "Light - White": settings.output_dir / "assets" / "images" / "logos" / "Light - White",
    }

    theme_base = Path(theme_config.base_path)
    if not theme_base.exists() and not dry_run:
        console.print(f"[red]Theme path does not exist:[/red] {theme_base}")
        raise typer.Exit(1) from None

    # Deploy
    action = "Would copy" if dry_run else "Copying"
    console.print(f"\n[bold]Deploying to {theme}[/bold]: {theme_base}\n")

    total_copied = 0
    for pid in platforms:
        console.print(f"[cyan]{pid}[/cyan]")

        # Device
        src_device = devices_dir / f"{pid}.png"
        dst_device = theme_base / "assets" / "images" / "devices" / f"{pid}.png"
        if src_device.exists():
            console.print(f"  {action}: devices/{pid}.png")
            if not dry_run:
                dst_device.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_device, dst_device)
            total_copied += 1

        # Logos
        for logo_name, logo_dir in logo_dirs.items():
            src_logo = logo_dir / f"{pid}.png"
            dst_logo = theme_base / "assets" / "images" / "logos" / logo_name / f"{pid}.png"
            if src_logo.exists():
                console.print(f"  {action}: logos/{logo_name}/{pid}.png")
                if not dry_run:
                    dst_logo.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_logo, dst_logo)
                total_copied += 1

    console.print()
    if dry_run:
        console.print(f"[dim]Dry run: {total_copied} files would be copied[/dim]")
    else:
        console.print(f"[green]Deployed {total_copied} files to {theme}[/green]")


# =============================================================================
# THEMES COMMAND
# =============================================================================


@assets_app.command()
def themes(
    init: bool = typer.Option(
        False,
        "--init",
        help="Create a default themes.yaml configuration",
    ),
) -> None:
    """List available themes or create default configuration."""
    if init:
        config_path = Path.cwd() / "themes.yaml"
        if config_path.exists():
            console.print(f"[yellow]themes.yaml already exists:[/yellow] {config_path}")
            if not typer.confirm("Overwrite?"):
                raise typer.Exit(0)

        create_default_themes_config(config_path)
        console.print(f"[green]Created:[/green] {config_path}")
        console.print()
        console.print("Edit this file to configure your theme paths.")
        return

    try:
        themes_config = load_themes_config()
    except ThemeConfigError as e:
        console.print(f"[red]Theme config error:[/red] {e}")
        console.print()
        console.print("Create a themes.yaml with: retrokit themes --init")
        raise typer.Exit(1) from None

    theme_names = themes_config.list_themes()

    if not theme_names:
        console.print("[dim]No themes configured.[/dim]")
        return

    table = Table(title="Available Themes")
    table.add_column("Name", style="cyan")
    table.add_column("Base Path")

    for name in theme_names:
        theme = themes_config.get_theme(name)
        if theme:
            table.add_row(name, theme.base_path)

    console.print(table)


# =============================================================================
# CONFIG COMMAND
# =============================================================================


@assets_app.command()
def config() -> None:
    """Show current configuration."""
    try:
        settings = get_settings()
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from None

    table = Table(title="Current Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("API URL", settings.gemini_api_url)
    api_key_display = f"{settings.gemini_api_key[:8]}..." if settings.gemini_api_key else "Not set"
    table.add_row("API Key", api_key_display)
    if settings.enable_google_search:
        google_status = "[green]Enabled[/green]"
    else:
        google_status = "[dim]Disabled[/dim]"
    table.add_row("Google Search", google_status)
    table.add_row("Input Dir", str(settings.input_dir))
    table.add_row("Output Dir", str(settings.output_dir))
    table.add_row("Device Size", f"{settings.device_width}x{settings.device_height}")
    table.add_row("Logo Size", f"{settings.logo_width}x{settings.logo_height}")

    console.print(table)


# =============================================================================
# ROMS SUBCOMMAND GROUP
# =============================================================================

roms_app = typer.Typer(
    name="roms",
    help="ROM deduplication and cleaning tools",
    add_completion=False,
)
app.add_typer(roms_app, name="roms")


@roms_app.command()
def scan(
    roms_dir: Path = typer.Option(
        Path.cwd(),
        "--roms-dir",
        "-d",
        help="ROMs directory to scan",
    ),
    no_hash: bool = typer.Option(
        False,
        "--no-hash",
        help="Skip MD5 computation (faster)",
    ),
    platform: str = typer.Option(
        None,
        "--platform",
        "-p",
        help="Only process specific platform",
    ),
) -> None:
    """Scan ROMs directory for duplicates."""
    if not roms_dir.exists():
        console.print(f"[red]ROMs directory not found:[/red] {roms_dir}")
        raise typer.Exit(1)

    detector = DuplicateDetector(roms_dir)
    detector.scan(compute_hashes=not no_hash, platform_filter=platform)
    detector.find_duplicates()

    cache_path = Path("scan_cache.json")
    detector.save_cache(cache_path)

    console.print(f"[green]Scanned {len(detector.roms)} ROMs[/green]")
    console.print(f"[yellow]Found {len(detector.duplicates)} duplicates[/yellow]")


@roms_app.command()
def report(
    roms_dir: Path = typer.Option(
        Path.cwd(),
        "--roms-dir",
        "-d",
        help="ROMs directory",
    ),
) -> None:
    """Generate duplicate report CSV."""
    detector = DuplicateDetector(roms_dir)

    # Try to load from cache
    cache_path = Path("scan_cache.json")
    if cache_path.exists():
        import json

        with open(cache_path) as f:
            cache_data = json.load(f)
        # Reconstruct ROMs from cache
        from .roms import RomInfo

        detector.roms = [
            RomInfo(
                path=Path(r["path"]),
                platform=Path(r["path"]).parent.name,
                name=Path(r["path"]).stem,
                md5=r.get("md5"),
                size=r.get("size", 0),
            )
            for r in cache_data["roms"]
        ]
        detector.find_duplicates()
    else:
        console.print("[yellow]No scan cache found. Run 'retrokit roms scan' first.[/yellow]")
        raise typer.Exit(1)

    report_path = Path("duplicate_report.csv")
    count, total_size = detector.generate_report(report_path)

    console.print(f"[green]Report saved:[/green] {report_path}")
    console.print(f"[dim]Duplicates: {count}, Space: {total_size / 1_000_000_000:.2f} GB[/dim]")


@roms_app.command()
def clean(
    roms_dir: Path = typer.Option(
        Path.cwd(),
        "--roms-dir",
        "-d",
        help="ROMs directory",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be removed without removing",
    ),
    quarantine: bool = typer.Option(
        False,
        "--quarantine",
        "-q",
        help="Move duplicates to quarantine folder",
    ),
    delete: bool = typer.Option(
        False,
        "--delete",
        help="Permanently delete duplicates (requires confirmation)",
    ),
) -> None:
    """Clean/remove duplicate ROMs."""
    # Load duplicates from report
    report_path = Path("duplicate_report.csv")
    if not report_path.exists():
        console.print("[red]No report found. Run 'retrokit roms report' first.[/red]")
        raise typer.Exit(1)

    duplicates = []
    import csv

    with open(report_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            duplicates.append(
                {
                    "platform": row["platform"],
                    "remove": row["remove"],
                    "keep": row["keep"],
                    "reason": row["reason"],
                    "size": float(row["size_mb"]) * 1_000_000,
                }
            )

    if not duplicates:
        console.print("[yellow]No duplicates to clean.[/yellow]")
        return

    # Determine mode
    if delete:
        mode = "delete"
        console.print("\n[red bold]*** WARNING: This will PERMANENTLY DELETE files! ***[/red bold]")
        confirm = typer.prompt("Type 'DELETE' to confirm")
        if confirm != "DELETE":
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)
    elif quarantine:
        mode = "quarantine"
    else:
        mode = "dry-run"

    quarantine_dir = roms_dir / "_quarantine"
    purger = RomPurger(roms_dir, quarantine_dir)
    count, size, errors = purger.purge(duplicates, mode=mode)

    if mode == "dry-run":
        console.print(f"\n[dim]Dry run: Would remove {len(duplicates)} files[/dim]")
        console.print("[dim]Run with --quarantine or --delete to take action[/dim]")
    else:
        console.print(f"[green]Removed {count} files, freed {size / 1_000_000_000:.2f} GB[/green]")
        if errors:
            console.print(f"[yellow]{len(errors)} errors occurred[/yellow]")


if __name__ == "__main__":
    app()
