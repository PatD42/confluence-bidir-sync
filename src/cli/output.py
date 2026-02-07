"""Terminal output handling using Rich library.

This module provides the OutputHandler class for all CLI terminal output.
Uses Rich library for progress bars, spinners, colored output, and formatted
text per ADR-012. Supports verbosity levels and --no-color flag.
"""

import logging
from typing import Optional, Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)
from rich.spinner import Spinner
from rich.live import Live


class OutputHandler:
    """Handles all terminal output using Rich library.

    Provides methods for displaying messages, progress bars, spinners,
    and summaries with color coding and verbosity level control.

    Attributes:
        verbosity: Logging verbosity level (0=summary, 1=info, 2=debug)
        console: Rich Console instance for output
        logger: Python logger for verbose output

    Example:
        >>> handler = OutputHandler(verbosity=1, no_color=False)
        >>> handler.success("Operation completed")
        >>> with handler.spinner("Processing..."):
        ...     # Do work
        ...     pass
    """

    def __init__(self, verbosity: int = 0, no_color: bool = False):
        """Initialize output handler.

        Args:
            verbosity: Verbosity level (0=summary, 1=info, 2=debug)
            no_color: Disable color output if True
        """
        self.verbosity = verbosity
        self.console = Console(
            force_terminal=not no_color,
            no_color=no_color,
            highlight=False,
        )
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Set up Python logger based on verbosity level.

        Returns:
            Configured logger instance
        """
        logger = logging.getLogger("confluence-sync")

        # Set level based on verbosity
        if self.verbosity >= 2:
            logger.setLevel(logging.DEBUG)
        elif self.verbosity >= 1:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.WARNING)

        # Remove existing handlers
        logger.handlers.clear()

        # Add console handler
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(levelname)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def success(self, message: str) -> None:
        """Display success message in green.

        Args:
            message: Success message to display
        """
        self.console.print(f"[green]✓[/green] {message}")

    def error(self, message: str) -> None:
        """Display error message in red.

        Args:
            message: Error message to display
        """
        self.console.print(f"[red]✗[/red] {message}", style="red")

    def warning(self, message: str) -> None:
        """Display warning message in yellow.

        Args:
            message: Warning message to display
        """
        self.console.print(f"[yellow]⚠[/yellow] {message}", style="yellow")

    def info(self, message: str) -> None:
        """Display info message (only if verbosity >= 1).

        Args:
            message: Info message to display
        """
        if self.verbosity >= 1:
            self.console.print(message)

    def debug(self, message: str) -> None:
        """Display debug message (only if verbosity >= 2).

        Args:
            message: Debug message to display
        """
        if self.verbosity >= 2:
            self.console.print(f"[dim]{message}[/dim]")

    def print(self, message: str) -> None:
        """Display message without formatting.

        Args:
            message: Message to display
        """
        self.console.print(message)

    @contextmanager
    def spinner(self, message: str) -> Iterator[None]:
        """Display spinner for single operations.

        Args:
            message: Message to display with spinner

        Yields:
            None

        Example:
            >>> with handler.spinner("Fetching page..."):
            ...     # Do work
            ...     pass
        """
        spinner = Spinner("dots", text=message)
        with Live(spinner, console=self.console, refresh_per_second=10):
            yield

    @contextmanager
    def progress_bar(self, total: int, description: str = "Processing") -> Iterator[Progress]:
        """Display progress bar for multi-item operations.

        Args:
            total: Total number of items to process
            description: Description text for progress bar

        Yields:
            Progress instance for updating progress

        Example:
            >>> with handler.progress_bar(10, "Syncing pages") as progress:
            ...     task = progress.add_task(description, total=10)
            ...     for i in range(10):
            ...         # Do work
            ...         progress.update(task, advance=1)
        """
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self.console,
        )
        with progress:
            yield progress

    def print_summary(
        self,
        pushed_count: int = 0,
        pulled_count: int = 0,
        conflict_count: int = 0,
        unchanged_count: int = 0,
    ) -> None:
        """Display sync summary with color coding.

        Args:
            pushed_count: Number of pages pushed to Confluence
            pulled_count: Number of pages pulled from Confluence
            conflict_count: Number of conflicts detected
            unchanged_count: Number of unchanged pages
        """
        self.console.print("\n[bold]Sync Summary:[/bold]")

        if pushed_count > 0:
            self.console.print(f"  [green]↑[/green] Pushed: {pushed_count} page(s)")

        if pulled_count > 0:
            self.console.print(f"  [blue]↓[/blue] Pulled: {pulled_count} page(s)")

        if conflict_count > 0:
            self.console.print(f"  [red]⚡[/red] Conflicts: {conflict_count} page(s)")

        if unchanged_count > 0:
            self.console.print(f"  [dim]─[/dim] Unchanged: {unchanged_count} page(s)")

        # Overall status
        total = pushed_count + pulled_count + conflict_count + unchanged_count
        if total == 0:
            self.console.print("\n[yellow]No pages to sync[/yellow]")
        elif conflict_count > 0:
            self.console.print("\n[red]Sync completed with conflicts[/red]")
        elif pushed_count == 0 and pulled_count == 0:
            self.console.print("\n[green]Already in sync. No changes detected.[/green]")
        else:
            self.console.print("\n[green]Sync completed successfully[/green]")

    def print_force_summary(self, count: int, direction: str) -> None:
        """Display force operation summary.

        Args:
            count: Number of pages processed
            direction: Either "push" or "pull"
        """
        if direction == "push":
            arrow = "→"
            text = "local → Confluence"
        else:
            arrow = "←"
            text = "Confluence → local"

        self.console.print(
            f"\n[green]{arrow}[/green] Force {direction}ed {count} page(s) ({text})"
        )

    def print_dryrun_summary(
        self,
        to_push: list,
        to_pull: list,
        conflicts: list,
    ) -> None:
        """Display dry run preview of changes.

        Args:
            to_push: List of pages that would be pushed
            to_pull: List of pages that would be pulled
            conflicts: List of conflicting pages
        """
        self.console.print("\n[bold]Dry Run - Changes Preview:[/bold]")

        if to_push:
            self.console.print(f"\n[green]Would push ({len(to_push)} page(s)):[/green]")
            for page in to_push:
                self.console.print(f"  • {page}")

        if to_pull:
            self.console.print(f"\n[blue]Would pull ({len(to_pull)} page(s)):[/blue]")
            for page in to_pull:
                self.console.print(f"  • {page}")

        if conflicts:
            self.console.print(f"\n[red]Conflicts detected ({len(conflicts)} page(s)):[/red]")
            for page in conflicts:
                self.console.print(f"  • {page}")

        if not to_push and not to_pull and not conflicts:
            self.console.print("\n[green]Already in sync. No changes to apply.[/green]")

    def print_deletion_summary(
        self,
        local_deleted: int = 0,
        confluence_deleted: int = 0,
    ) -> None:
        """Display deletion summary with color coding.

        Args:
            local_deleted: Number of pages deleted from local storage
            confluence_deleted: Number of pages deleted from Confluence
        """
        self.console.print("\n[bold]Deletion Summary:[/bold]")

        if local_deleted > 0:
            self.console.print(f"  [red]✗[/red] Local: {local_deleted} page(s) deleted")

        if confluence_deleted > 0:
            self.console.print(f"  [red]✗[/red] Confluence: {confluence_deleted} page(s) deleted")

        # Overall status
        total = local_deleted + confluence_deleted
        if total == 0:
            self.console.print("\n[yellow]No pages deleted[/yellow]")
        else:
            self.console.print(f"\n[green]Deletion completed: {total} page(s) total[/green]")

    def print_move_summary(
        self,
        local_moved: int = 0,
        confluence_moved: int = 0,
    ) -> None:
        """Display move summary with color coding.

        Args:
            local_moved: Number of pages moved in local storage
            confluence_moved: Number of pages moved in Confluence
        """
        self.console.print("\n[bold]Move Summary:[/bold]")

        if local_moved > 0:
            self.console.print(f"  [blue]↔[/blue] Local: {local_moved} page(s) moved")

        if confluence_moved > 0:
            self.console.print(f"  [blue]↔[/blue] Confluence: {confluence_moved} page(s) moved")

        # Overall status
        total = local_moved + confluence_moved
        if total == 0:
            self.console.print("\n[yellow]No pages moved[/yellow]")
        else:
            self.console.print(f"\n[green]Move completed: {total} page(s) total[/green]")

    def print_merge_summary(
        self,
        merged_count: int = 0,
        conflict_count: int = 0,
        skipped_count: int = 0,
    ) -> None:
        """Display merge summary with color coding.

        Args:
            merged_count: Number of items merged successfully
            conflict_count: Number of conflicts detected
            skipped_count: Number of items skipped
        """
        self.console.print("\n[bold]Merge Summary:[/bold]")

        if merged_count > 0:
            self.console.print(f"  [green]✓[/green] Merged: {merged_count} item(s)")

        if conflict_count > 0:
            self.console.print(f"  [red]⚡[/red] Conflicts: {conflict_count} item(s)")

        if skipped_count > 0:
            self.console.print(f"  [yellow]⊘[/yellow] Skipped: {skipped_count} item(s)")

        # Overall status
        total = merged_count + conflict_count + skipped_count
        if total == 0:
            self.console.print("\n[yellow]No items to merge[/yellow]")
        elif conflict_count > 0:
            self.console.print("\n[red]Merge completed with conflicts[/red]")
        else:
            self.console.print("\n[green]Merge completed successfully[/green]")
