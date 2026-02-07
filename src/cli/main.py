"""Main CLI entry point for confluence-sync command.

This module provides the Typer application that serves as the entry point
for the confluence-sync command-line tool. It uses options on the main command
rather than subcommands for a simpler user experience.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import typer

from src.cli.errors import InitError, CLIError
from src.cli.init_command import InitCommand
from src.cli.models import ExitCode
from src.cli.output import OutputHandler
from src.cli.sync_command import SyncCommand

# Create Typer app - no_args_is_help=False allows running without args
app = typer.Typer(
    name="confluence-sync",
    help="""Bidirectional sync between Confluence and local Markdown files.

QUICK START:
  confluence-sync                                                  # Run 2-way sync
  confluence-sync --init --local <folder> --url <confluence_url>   # Initialize
  confluence-sync --dry-run                                        # Preview changes
  confluence-sync --force-push                                     # Local → Confluence
  confluence-sync --force-pull                                     # Confluence → local

EXAMPLE:
  confluence-sync --init --local ./docs --url https://company.atlassian.net/wiki/spaces/TEAM/pages/123456

NOTE: --excludeParent excludes the parent page from sync (only children are synced).""",
    add_completion=False,
    rich_markup_mode=None,  # Disable Rich markup to avoid compatibility issues
    no_args_is_help=False,
)

# Module logger
logger = logging.getLogger(__name__)

# Help message for when no arguments provided
GETTING_STARTED_MESSAGE = """confluence-sync                                                  # Run 2-way sync

--init --local <folder> --url <confluence_url> [--excludeParent]  # Initialize
--dry-run                                                         # Preview changes
--force-push                                                      # Local → Confluence
--force-pull                                                      # Confluence → local
--help                                                            # Show all options

Example:
  confluence-sync --init --local ./docs --url https://company.atlassian.net/wiki/spaces/TEAM/pages/123456

Note: --excludeParent excludes the parent page from sync (only children are synced)."""


def _configure_logging(verbosity: int, logdir: Optional[str] = None) -> None:
    """Configure logging based on verbosity level.

    Configures only the 'src' namespace logger to avoid affecting third-party
    libraries. The root logger is left unchanged.

    Args:
        verbosity: Verbosity level (0=WARNING, 1=INFO, 2=DEBUG)
        logdir: Optional directory for log files (creates timestamped log file)
    """
    if verbosity == 0:
        level = logging.WARNING
    elif verbosity == 1:
        level = logging.INFO
    else:  # verbosity >= 2
        level = logging.DEBUG

    # Configure app-specific logger (not root) to avoid affecting libraries
    app_logger = logging.getLogger("src")
    app_logger.setLevel(level)

    # Define log format
    log_format = "%(asctime)s [%(levelname)8s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, datefmt=date_format)

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    app_logger.addHandler(console_handler)

    # File handler (if logdir is specified)
    if logdir:
        # Create log directory if it doesn't exist
        log_path = Path(logdir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Generate timestamped filename using local timezone
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_path / f"confluence-sync_{timestamp}.log"

        # Add file handler with more detailed format
        file_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        file_formatter = logging.Formatter(file_format, datefmt=date_format)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(file_formatter)
        app_logger.addHandler(file_handler)

        logger.info(f"Logging to file: {log_file}")


def _run_init(
    local_folder: str,
    confluence_url: str,
    exclude_parent: bool,
    verbosity: int,
    no_color: bool
) -> None:
    """Run initialization command.

    Args:
        local_folder: Local directory for synced files
        confluence_url: Confluence page URL
        exclude_parent: Whether to exclude parent page from sync
        verbosity: Verbosity level
        no_color: Whether to disable colored output
    """
    # Configure logging
    _configure_logging(verbosity)

    # Create output handler
    output = OutputHandler(verbosity=verbosity, no_color=no_color)

    try:
        # Display init message
        output.info("Initializing sync configuration...")
        output.info(f"  Local folder: {local_folder}")
        output.info(f"  Confluence URL: {confluence_url}")
        if exclude_parent:
            output.info("  Parent page: excluded (only children will sync)")

        # Create init command
        init_cmd = InitCommand()

        # Run init operation
        with output.spinner("Validating Confluence page..."):
            init_cmd.run(
                local_path=local_folder,
                confluence_url=confluence_url,
                exclude_parent=exclude_parent
            )

        # Success
        output.success("Configuration initialized successfully")
        output.info(f"  Config file: {init_cmd.config_path}")
        output.info(f"  Local directory: {local_folder}")
        output.info("")
        output.info("Next steps:")
        output.info("  1. Review .confluence-sync/config.yaml")
        output.info("  2. Run 'confluence-sync' to start syncing")

        raise typer.Exit(ExitCode.SUCCESS)

    except InitError as e:
        logger.error(f"Initialization failed: {e}")
        output.error(f"Initialization failed: {e}")
        raise typer.Exit(ExitCode.GENERAL_ERROR)

    except typer.Exit:
        raise

    except Exception as e:
        logger.exception("Unexpected error during initialization")
        output.error(f"Unexpected error: {e}")
        raise typer.Exit(ExitCode.GENERAL_ERROR)


def _run_sync(
    file: Optional[str],
    dry_run: bool,
    force_push: bool,
    force_pull: bool,
    exclude_confluence: Optional[List[str]],
    exclude_local: Optional[List[str]],
    logdir: Optional[str],
    verbosity: int,
    no_color: bool
) -> None:
    """Run sync command.

    Args:
        file: Optional single file to sync
        dry_run: Preview changes without applying
        force_push: Force local -> Confluence
        force_pull: Force Confluence -> local
        exclude_confluence: Confluence page URLs to exclude (supports wildcards)
        exclude_local: Local file paths to exclude (supports wildcards)
        logdir: Directory for log files
        verbosity: Verbosity level
        no_color: Whether to disable colored output
    """
    # Configure logging
    _configure_logging(verbosity, logdir)

    # Create output handler with verbosity settings
    output = OutputHandler(verbosity=verbosity, no_color=no_color)

    # Process exclusions and persist to config FIRST (before sync runs)
    config_path = ".confluence-sync/config.yaml"
    has_exclusions = (exclude_confluence and len(exclude_confluence) > 0) or (exclude_local and len(exclude_local) > 0)

    if has_exclusions:
        # Load existing config
        from src.file_mapper.config_loader import ConfigLoader
        try:
            config = ConfigLoader.load(config_path)
        except Exception as e:
            output.error(f"Failed to load config: {e}")
            raise typer.Exit(ExitCode.GENERAL_ERROR)

        # Track new exclusions for output
        new_exclude_page_ids = []

        # Parse Confluence URLs to page IDs
        if exclude_confluence:
            from src.file_mapper.frontmatter_handler import FrontmatterHandler
            for url in exclude_confluence:
                _, page_id = FrontmatterHandler.parse_confluence_url(url)
                if page_id:
                    new_exclude_page_ids.append(page_id)
                    output.info(f"Adding exclusion - Confluence page: {page_id} ({url})")
                else:
                    output.error(f"Invalid Confluence URL: {url}")
                    raise typer.Exit(ExitCode.GENERAL_ERROR)

        # Parse local file paths to page IDs (with wildcard support)
        if exclude_local:
            from src.file_mapper.frontmatter_handler import FrontmatterHandler
            for pattern in exclude_local:
                # Expand glob pattern
                matched_files = list(Path(pattern).parent.glob(Path(pattern).name))

                # If pattern contains wildcards but no matches, warn user
                if ('*' in pattern or '?' in pattern) and not matched_files:
                    output.warning(f"No files matched pattern: {pattern}")
                    continue

                # If no wildcards and no match, treat as literal path (error if not found)
                if not matched_files:
                    matched_files = [Path(pattern)]

                for file_path in matched_files:
                    file_path_str = str(file_path)
                    try:
                        with open(file_path_str, 'r', encoding='utf-8') as f:
                            content = f.read()
                        local_page = FrontmatterHandler.parse(file_path_str, content)
                        if local_page.page_id:
                            new_exclude_page_ids.append(local_page.page_id)
                            output.info(f"Adding exclusion - local file: {local_page.page_id} ({file_path_str})")
                        else:
                            output.error(f"Local file has no page_id in frontmatter: {file_path_str}")
                            raise typer.Exit(ExitCode.GENERAL_ERROR)
                    except FileNotFoundError:
                        output.error(f"Local file not found: {file_path_str}")
                        raise typer.Exit(ExitCode.GENERAL_ERROR)
                    except Exception as e:
                        output.error(f"Error reading local file {file_path_str}: {e}")
                        raise typer.Exit(ExitCode.GENERAL_ERROR)

        # Update config with new exclusions (merge with existing)
        if new_exclude_page_ids:
            for space in config.spaces:
                existing = set(space.exclude_page_ids)
                added = set(new_exclude_page_ids) - existing
                existing.update(new_exclude_page_ids)
                space.exclude_page_ids = sorted(list(existing))  # Sort for consistent ordering

                if added:
                    output.info(f"Added {len(added)} new exclusion(s) to config for space '{space.space_key}'")

            # Persist updated config to disk
            try:
                ConfigLoader.save(config_path, config)
                output.success(f"Saved {len(new_exclude_page_ids)} exclusion(s) to {config_path}")
            except Exception as e:
                output.error(f"Failed to save config: {e}")
                raise typer.Exit(ExitCode.GENERAL_ERROR)

    # Create sync command
    sync_cmd = SyncCommand(output_handler=output)

    # Run sync operation (exclusions now in config, no need to pass separately)
    # Single-file sync should not update global timestamp
    exit_code = sync_cmd.run(
        dry_run=dry_run,
        force_push=force_push,
        force_pull=force_pull,
        single_file=file,
        update_timestamp=not bool(file),  # False when single_file provided
        cli_exclude_page_ids=None,  # Exclusions already in config
    )

    # Exit with appropriate code
    raise typer.Exit(exit_code)


@app.command()
def main_command(
    init: bool = typer.Option(
        False,
        "--init",
        help="Initialize sync configuration (requires --local and --url)",
    ),
    local_folder: Optional[str] = typer.Option(
        None,
        "--local",
        help="Local folder path for synced files (used with --init)",
        metavar="FOLDER",
    ),
    init_url: Optional[str] = typer.Option(
        None,
        "--url",
        help="Confluence page URL (used with --init)",
        metavar="URL",
    ),
    exclude_parent: bool = typer.Option(
        False,
        "--excludeParent",
        "--exclude-parent",
        help="With --init: exclude parent page from sync (only sync children)",
    ),
    file: Optional[str] = typer.Argument(
        None,
        help="Optional file path to sync (syncs only this file)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "--dryrun",
        help="Preview changes without applying them",
    ),
    force_push: bool = typer.Option(
        False,
        "--force-push",
        "--forcePush",
        help="Force propagate local changes to Confluence (local -> Confluence)",
    ),
    force_pull: bool = typer.Option(
        False,
        "--force-pull",
        "--forcePull",
        help="Force propagate Confluence changes to local (Confluence -> local)",
    ),
    exclude_confluence: Optional[List[str]] = typer.Option(
        None,
        "--exclude-confluence",
        help="Confluence page URL(s) to exclude from sync (can be used multiple times)",
        metavar="URL",
    ),
    exclude_local: Optional[List[str]] = typer.Option(
        None,
        "--exclude-local",
        help="Local file path(s) to exclude from sync (can be used multiple times)",
        metavar="PATH",
    ),
    logdir: Optional[str] = typer.Option(
        None,
        "--logdir",
        help="Directory for log files (creates timestamped log file)",
    ),
    verbosity: int = typer.Option(
        0,
        "--verbosity",
        "-v",
        help="Verbosity level: 0=summary, 1=info, 2=debug",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
    ),
) -> None:
    """Bidirectional sync between Confluence and local Markdown files.

    \b
    QUICK START:
      confluence-sync                                                  # Run 2-way sync
      confluence-sync --init --local <folder> --url <confluence_url>   # Initialize
      confluence-sync --dry-run                                        # Preview changes
      confluence-sync --force-push                                     # Local → Confluence
      confluence-sync --force-pull                                     # Confluence → local

    \b
    EXCLUSIONS:
      # Exclude by Confluence URL
      confluence-sync --exclude-confluence https://company.atlassian.net/wiki/spaces/TEAM/pages/123456

      # Exclude by local file path
      confluence-sync --exclude-local ./docs/Archive.md

      # Multiple exclusions (can mix both types)
      confluence-sync --exclude-confluence <url1> --exclude-confluence <url2> --exclude-local <file1>

    \b
    EXAMPLE:
      confluence-sync --init --local ./docs --url https://company.atlassian.net/wiki/spaces/TEAM/pages/123456

    NOTE:
      - --excludeParent excludes the parent page from sync (only children are synced)
      - Excluded pages are not deleted, just ignored during sync
    """
    if version:
        typer.echo("confluence-sync version 0.1.0")
        raise typer.Exit()

    # If --init is provided, run initialization
    if init or local_folder is not None or init_url is not None:
        # Validate all required options are provided
        missing = []
        if not init:
            missing.append("--init")
        if local_folder is None:
            missing.append("--local")
        if init_url is None:
            missing.append("--url")

        if missing:
            typer.echo(f"Error: Missing required option(s): {', '.join(missing)}", err=True)
            typer.echo("")
            typer.echo("Example:")
            typer.echo("  confluence-sync --init --local ./docs --url https://company.atlassian.net/wiki/spaces/TEAM/pages/123456")
            raise typer.Exit(ExitCode.GENERAL_ERROR)

        _run_init(local_folder, init_url, exclude_parent, verbosity, no_color)
        return

    # Check if any sync-related options were provided (indicates user wants to sync)
    has_sync_options = dry_run or force_push or force_pull or file is not None or logdir is not None

    # If no options at all, show getting started message
    if not has_sync_options and verbosity == 0 and not no_color:
        # Check if config exists to determine if initialized
        import os
        if not os.path.exists(".confluence-sync/config.yaml"):
            typer.echo(GETTING_STARTED_MESSAGE)
            raise typer.Exit()

    # Run sync (default behavior)
    _run_sync(file, dry_run, force_push, force_pull, exclude_confluence, exclude_local, logdir, verbosity, no_color)


def main() -> None:
    """Main entry point for the CLI application.

    This function is called when the module is executed directly or
    when the console script is invoked.
    """
    app()


# Allow running as: python -m src.cli.main
if __name__ == "__main__":
    main()
