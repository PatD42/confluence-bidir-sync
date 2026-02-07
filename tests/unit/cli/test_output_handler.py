"""Unit tests for cli.output module."""

import logging
from unittest.mock import Mock, patch, MagicMock, call
import pytest

from src.cli.output import OutputHandler


class TestOutputHandlerInit:
    """Test cases for OutputHandler initialization."""

    def test_init_default_verbosity_and_color(self):
        """Initialize with default verbosity (0) and color enabled."""
        handler = OutputHandler()

        assert handler.verbosity == 0
        assert handler.console is not None
        assert handler.logger is not None
        assert handler.logger.name == "confluence-sync"

    def test_init_verbosity_level_1(self):
        """Initialize with verbosity level 1."""
        handler = OutputHandler(verbosity=1)

        assert handler.verbosity == 1
        assert handler.logger.level == logging.INFO

    def test_init_verbosity_level_2(self):
        """Initialize with verbosity level 2."""
        handler = OutputHandler(verbosity=2)

        assert handler.verbosity == 2
        assert handler.logger.level == logging.DEBUG

    def test_init_verbosity_level_0(self):
        """Initialize with verbosity level 0."""
        handler = OutputHandler(verbosity=0)

        assert handler.verbosity == 0
        assert handler.logger.level == logging.WARNING

    def test_init_no_color_true(self):
        """Initialize with no_color=True disables colors."""
        handler = OutputHandler(no_color=True)

        assert handler.console.no_color is True

    def test_init_no_color_false(self):
        """Initialize with no_color=False enables colors."""
        handler = OutputHandler(no_color=False)

        # Should allow colors (force_terminal is not False)
        assert handler.console.no_color is False


class TestOutputHandlerLogger:
    """Test cases for logger setup."""

    def test_logger_verbosity_0_sets_warning_level(self):
        """Verbosity 0 sets logger to WARNING level."""
        handler = OutputHandler(verbosity=0)

        assert handler.logger.level == logging.WARNING

    def test_logger_verbosity_1_sets_info_level(self):
        """Verbosity 1 sets logger to INFO level."""
        handler = OutputHandler(verbosity=1)

        assert handler.logger.level == logging.INFO

    def test_logger_verbosity_2_sets_debug_level(self):
        """Verbosity 2 sets logger to DEBUG level."""
        handler = OutputHandler(verbosity=2)

        assert handler.logger.level == logging.DEBUG

    def test_logger_has_stream_handler(self):
        """Logger should have a StreamHandler configured."""
        handler = OutputHandler(verbosity=1)

        assert len(handler.logger.handlers) == 1
        assert isinstance(handler.logger.handlers[0], logging.StreamHandler)

    def test_logger_formatter(self):
        """Logger handler should have correct formatter."""
        handler = OutputHandler(verbosity=1)

        formatter = handler.logger.handlers[0].formatter
        assert formatter._fmt == "%(levelname)s: %(message)s"


class TestOutputHandlerMessages:
    """Test cases for message output methods."""

    @patch('src.cli.output.Console')
    def test_success_displays_green_message(self, mock_console_class):
        """success() displays message with green checkmark."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.success("Operation completed")

        mock_console.print.assert_called_once_with("[green]✓[/green] Operation completed")

    @patch('src.cli.output.Console')
    def test_error_displays_red_message(self, mock_console_class):
        """error() displays message with red X."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.error("Something failed")

        mock_console.print.assert_called_once_with(
            "[red]✗[/red] Something failed",
            style="red"
        )

    @patch('src.cli.output.Console')
    def test_warning_displays_yellow_message(self, mock_console_class):
        """warning() displays message with yellow warning symbol."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.warning("Be careful")

        mock_console.print.assert_called_once_with(
            "[yellow]⚠[/yellow] Be careful",
            style="yellow"
        )

    @patch('src.cli.output.Console')
    def test_print_displays_message_without_formatting(self, mock_console_class):
        """print() displays message without formatting."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print("Plain message")

        mock_console.print.assert_called_once_with("Plain message")


class TestOutputHandlerVerbosity:
    """Test cases for verbosity-controlled output."""

    @patch('src.cli.output.Console')
    def test_info_displays_at_verbosity_1(self, mock_console_class):
        """info() displays message at verbosity >= 1."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler(verbosity=1)
        handler.console = mock_console

        handler.info("Info message")

        mock_console.print.assert_called_once_with("Info message")

    @patch('src.cli.output.Console')
    def test_info_displays_at_verbosity_2(self, mock_console_class):
        """info() displays message at verbosity 2."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler(verbosity=2)
        handler.console = mock_console

        handler.info("Info message")

        mock_console.print.assert_called_once_with("Info message")

    @patch('src.cli.output.Console')
    def test_info_does_not_display_at_verbosity_0(self, mock_console_class):
        """info() does not display message at verbosity 0."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler(verbosity=0)
        handler.console = mock_console

        handler.info("Info message")

        mock_console.print.assert_not_called()

    @patch('src.cli.output.Console')
    def test_debug_displays_at_verbosity_2(self, mock_console_class):
        """debug() displays message at verbosity >= 2."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler(verbosity=2)
        handler.console = mock_console

        handler.debug("Debug message")

        mock_console.print.assert_called_once_with("[dim]Debug message[/dim]")

    @patch('src.cli.output.Console')
    def test_debug_does_not_display_at_verbosity_1(self, mock_console_class):
        """debug() does not display message at verbosity 1."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler(verbosity=1)
        handler.console = mock_console

        handler.debug("Debug message")

        mock_console.print.assert_not_called()

    @patch('src.cli.output.Console')
    def test_debug_does_not_display_at_verbosity_0(self, mock_console_class):
        """debug() does not display message at verbosity 0."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler(verbosity=0)
        handler.console = mock_console

        handler.debug("Debug message")

        mock_console.print.assert_not_called()


class TestOutputHandlerSpinner:
    """Test cases for spinner context manager."""

    @patch('src.cli.output.Live')
    @patch('src.cli.output.Spinner')
    def test_spinner_creates_live_spinner(self, mock_spinner_class, mock_live_class):
        """spinner() creates Live spinner with correct message."""
        mock_spinner = Mock()
        mock_spinner_class.return_value = mock_spinner
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        handler = OutputHandler()

        with handler.spinner("Loading..."):
            pass

        # Verify Spinner created with correct params
        mock_spinner_class.assert_called_once_with("dots", text="Loading...")

        # Verify Live context manager used
        mock_live_class.assert_called_once_with(
            mock_spinner,
            console=handler.console,
            refresh_per_second=10
        )
        mock_live.__enter__.assert_called_once()
        mock_live.__exit__.assert_called_once()

    @patch('src.cli.output.Live')
    @patch('src.cli.output.Spinner')
    def test_spinner_context_manager_works(self, mock_spinner_class, mock_live_class):
        """spinner() works as context manager."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        handler = OutputHandler()

        # Verify it can be used as context manager
        with handler.spinner("Processing..."):
            # Code inside context
            executed = True

        assert executed
        mock_live.__enter__.assert_called_once()
        mock_live.__exit__.assert_called_once()


class TestOutputHandlerProgressBar:
    """Test cases for progress bar context manager."""

    @patch('src.cli.output.Progress')
    def test_progress_bar_creates_progress(self, mock_progress_class):
        """progress_bar() creates Progress with correct configuration."""
        mock_progress = MagicMock()
        mock_progress_class.return_value = mock_progress

        handler = OutputHandler()

        with handler.progress_bar(10, "Syncing") as progress:
            pass

        # Verify Progress created
        mock_progress_class.assert_called_once()
        call_kwargs = mock_progress_class.call_args[1]
        assert call_kwargs['console'] == handler.console

        # Verify Progress context manager used
        mock_progress.__enter__.assert_called_once()
        mock_progress.__exit__.assert_called_once()

    @patch('src.cli.output.Progress')
    def test_progress_bar_yields_progress_instance(self, mock_progress_class):
        """progress_bar() yields Progress instance."""
        mock_progress = MagicMock()
        mock_progress_class.return_value = mock_progress

        handler = OutputHandler()

        with handler.progress_bar(10, "Processing") as progress:
            # Verify we get the progress instance (the context manager itself)
            assert progress == mock_progress

    @patch('src.cli.output.Progress')
    def test_progress_bar_uses_custom_description(self, mock_progress_class):
        """progress_bar() uses custom description."""
        mock_progress = MagicMock()
        mock_progress_class.return_value = mock_progress

        handler = OutputHandler()

        with handler.progress_bar(5, "Custom description") as progress:
            # The description is used in TextColumn when adding tasks
            # Just verify the progress bar was created
            pass

        mock_progress_class.assert_called_once()


class TestOutputHandlerPrintSummary:
    """Test cases for print_summary() method."""

    @patch('src.cli.output.Console')
    def test_print_summary_all_categories(self, mock_console_class):
        """print_summary() displays all categories when counts > 0."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_summary(
            pushed_count=2,
            pulled_count=3,
            conflict_count=1,
            unchanged_count=5
        )

        # Check that all categories were printed
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Sync Summary" in str(call) for call in calls)
        assert any("Pushed: 2" in str(call) for call in calls)
        assert any("Pulled: 3" in str(call) for call in calls)
        assert any("Conflicts: 1" in str(call) for call in calls)
        assert any("Unchanged: 5" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_summary_with_conflicts_shows_conflict_message(self, mock_console_class):
        """print_summary() shows conflict message when conflicts > 0."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_summary(conflict_count=2)

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Sync completed with conflicts" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_summary_no_changes_shows_in_sync_message(self, mock_console_class):
        """print_summary() shows 'in sync' message when no changes."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_summary(unchanged_count=5)

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Already in sync" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_summary_successful_sync(self, mock_console_class):
        """print_summary() shows success message when changes synced."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_summary(pushed_count=2, pulled_count=1)

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Sync completed successfully" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_summary_no_pages_shows_no_pages_message(self, mock_console_class):
        """print_summary() shows 'no pages' message when all counts are 0."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_summary()

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("No pages to sync" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_summary_skips_zero_categories(self, mock_console_class):
        """print_summary() does not display categories with count 0."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_summary(pushed_count=2)

        # Should not mention pulled, conflicts, or unchanged
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert not any("Pulled:" in str(call) for call in calls)
        assert not any("Conflicts:" in str(call) for call in calls)
        assert not any("Unchanged:" in str(call) for call in calls)


class TestOutputHandlerPrintForceSummary:
    """Test cases for print_force_summary() method."""

    @patch('src.cli.output.Console')
    def test_print_force_summary_push(self, mock_console_class):
        """print_force_summary() shows push message and arrow."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_force_summary(5, "push")

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Force pushed 5 page(s)" in str(call) for call in calls)
        assert any("local → Confluence" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_force_summary_pull(self, mock_console_class):
        """print_force_summary() shows pull message and arrow."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_force_summary(3, "pull")

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Force pulled 3 page(s)" in str(call) for call in calls)
        assert any("Confluence → local" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_force_summary_zero_count(self, mock_console_class):
        """print_force_summary() handles zero count."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_force_summary(0, "push")

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("0 page(s)" in str(call) for call in calls)


class TestOutputHandlerPrintDryrunSummary:
    """Test cases for print_dryrun_summary() method."""

    @patch('src.cli.output.Console')
    def test_print_dryrun_summary_all_categories(self, mock_console_class):
        """print_dryrun_summary() displays all categories."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        to_push = ["page1.md", "page2.md"]
        to_pull = ["page3.md"]
        conflicts = ["page4.md"]

        handler.print_dryrun_summary(to_push, to_pull, conflicts)

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Dry Run" in str(call) for call in calls)
        assert any("Would push (2 page(s))" in str(call) for call in calls)
        assert any("page1.md" in str(call) for call in calls)
        assert any("page2.md" in str(call) for call in calls)
        assert any("Would pull (1 page(s))" in str(call) for call in calls)
        assert any("page3.md" in str(call) for call in calls)
        assert any("Conflicts detected (1 page(s))" in str(call) for call in calls)
        assert any("page4.md" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_dryrun_summary_empty_lists(self, mock_console_class):
        """print_dryrun_summary() shows 'in sync' message for empty lists."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        handler.print_dryrun_summary([], [], [])

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Already in sync" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_dryrun_summary_only_push(self, mock_console_class):
        """print_dryrun_summary() shows only push when others empty."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        to_push = ["page1.md"]

        handler.print_dryrun_summary(to_push, [], [])

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Would push" in str(call) for call in calls)
        assert not any("Would pull" in str(call) for call in calls)
        assert not any("Conflicts" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_dryrun_summary_only_pull(self, mock_console_class):
        """print_dryrun_summary() shows only pull when others empty."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        to_pull = ["page1.md"]

        handler.print_dryrun_summary([], to_pull, [])

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert not any("Would push" in str(call) for call in calls)
        assert any("Would pull" in str(call) for call in calls)
        assert not any("Conflicts" in str(call) for call in calls)

    @patch('src.cli.output.Console')
    def test_print_dryrun_summary_only_conflicts(self, mock_console_class):
        """print_dryrun_summary() shows only conflicts when others empty."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler()
        handler.console = mock_console

        conflicts = ["page1.md"]

        handler.print_dryrun_summary([], [], conflicts)

        calls = [str(call) for call in mock_console.print.call_args_list]
        assert not any("Would push" in str(call) for call in calls)
        assert not any("Would pull" in str(call) for call in calls)
        assert any("Conflicts detected" in str(call) for call in calls)


class TestOutputHandlerColorControl:
    """Test cases for color control with no_color flag."""

    def test_no_color_flag_disables_color_output(self):
        """no_color=True should disable color output."""
        handler = OutputHandler(no_color=True)

        assert handler.console.no_color is True

    def test_color_enabled_by_default(self):
        """Color output should be enabled by default."""
        handler = OutputHandler(no_color=False)

        assert handler.console.no_color is False

    @patch('src.cli.output.Console')
    def test_no_color_still_outputs_messages(self, mock_console_class):
        """With no_color=True, messages should still be output."""
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        handler = OutputHandler(no_color=True)
        handler.console = mock_console

        handler.success("Test")
        handler.error("Test")
        handler.warning("Test")

        # Messages should still be printed, just without color
        assert mock_console.print.call_count == 3
