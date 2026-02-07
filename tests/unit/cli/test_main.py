"""Unit tests for main CLI entry point (main.py).

Tests the Typer CLI application using CliRunner.
"""

import logging
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from typer.testing import CliRunner

from src.cli.main import app, _configure_logging, GETTING_STARTED_MESSAGE
from src.cli.models import ExitCode


runner = CliRunner()


class TestConfigureLogging:
    """Test cases for _configure_logging function."""

    def test_verbosity_0_sets_warning_level(self):
        """Verbosity 0 sets logging to WARNING level."""
        with patch('logging.getLogger') as mock_get_logger:
            mock_root_logger = MagicMock()
            mock_get_logger.return_value = mock_root_logger

            _configure_logging(0)

            mock_root_logger.setLevel.assert_called_with(logging.WARNING)

    def test_verbosity_1_sets_info_level(self):
        """Verbosity 1 sets logging to INFO level."""
        with patch('logging.getLogger') as mock_get_logger:
            mock_root_logger = MagicMock()
            mock_get_logger.return_value = mock_root_logger

            _configure_logging(1)

            mock_root_logger.setLevel.assert_called_with(logging.INFO)

    def test_verbosity_2_sets_debug_level(self):
        """Verbosity 2+ sets logging to DEBUG level."""
        with patch('logging.getLogger') as mock_get_logger:
            mock_root_logger = MagicMock()
            mock_get_logger.return_value = mock_root_logger

            _configure_logging(2)

            mock_root_logger.setLevel.assert_called_with(logging.DEBUG)


class TestSyncCommand:
    """Test cases for sync (default) command."""

    @patch('src.cli.main.SyncCommand')
    @patch('src.cli.main.OutputHandler')
    @patch('os.path.exists')
    def test_sync_default_runs_bidirectional(self, mock_exists, mock_output, mock_sync_cmd):
        """Default sync runs bidirectional sync when config exists."""
        # Arrange
        mock_exists.return_value = True  # Config exists
        mock_instance = Mock()
        mock_instance.run.return_value = ExitCode.SUCCESS
        mock_sync_cmd.return_value = mock_instance

        # Act - no options, just run sync
        result = runner.invoke(app, [])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        mock_instance.run.assert_called_once_with(
            dry_run=False,
            force_push=False,
            force_pull=False,
            single_file=None,
            update_timestamp=True,
            cli_exclude_page_ids=None,
        )

    @patch('src.cli.main.SyncCommand')
    @patch('src.cli.main.OutputHandler')
    def test_sync_with_dry_run_flag(self, mock_output, mock_sync_cmd):
        """Sync with --dry-run flag."""
        # Arrange
        mock_instance = Mock()
        mock_instance.run.return_value = ExitCode.SUCCESS
        mock_sync_cmd.return_value = mock_instance

        # Act
        result = runner.invoke(app, ["--dry-run"])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        mock_instance.run.assert_called_once_with(
            dry_run=True,
            force_push=False,
            force_pull=False,
            single_file=None,
            update_timestamp=True,
            cli_exclude_page_ids=None,
        )

    @patch('src.cli.main.SyncCommand')
    @patch('src.cli.main.OutputHandler')
    def test_sync_with_force_push_flag(self, mock_output, mock_sync_cmd):
        """Sync with --force-push flag."""
        # Arrange
        mock_instance = Mock()
        mock_instance.run.return_value = ExitCode.SUCCESS
        mock_sync_cmd.return_value = mock_instance

        # Act
        result = runner.invoke(app, ["--force-push"])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        mock_instance.run.assert_called_once_with(
            dry_run=False,
            force_push=True,
            force_pull=False,
            single_file=None,
            update_timestamp=True,
            cli_exclude_page_ids=None,
        )

    @patch('src.cli.main.SyncCommand')
    @patch('src.cli.main.OutputHandler')
    def test_sync_with_force_pull_flag(self, mock_output, mock_sync_cmd):
        """Sync with --force-pull flag."""
        # Arrange
        mock_instance = Mock()
        mock_instance.run.return_value = ExitCode.SUCCESS
        mock_sync_cmd.return_value = mock_instance

        # Act
        result = runner.invoke(app, ["--force-pull"])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        mock_instance.run.assert_called_once_with(
            dry_run=False,
            force_push=False,
            force_pull=True,
            single_file=None,
            update_timestamp=True,
            cli_exclude_page_ids=None,
        )

    @patch('src.cli.main.SyncCommand')
    @patch('src.cli.main.OutputHandler')
    def test_sync_with_single_file(self, mock_output, mock_sync_cmd):
        """Sync with single file argument."""
        # Arrange
        mock_instance = Mock()
        mock_instance.run.return_value = ExitCode.SUCCESS
        mock_sync_cmd.return_value = mock_instance

        # Act - file is a positional argument
        result = runner.invoke(app, ["docs/page.md"])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        mock_instance.run.assert_called_once_with(
            dry_run=False,
            force_push=False,
            force_pull=False,
            single_file="docs/page.md",
            update_timestamp=False,  # False when single_file provided
            cli_exclude_page_ids=None,
        )

    @patch('src.cli.main.SyncCommand')
    @patch('src.cli.main.OutputHandler')
    def test_sync_with_verbosity_flag(self, mock_output_cls, mock_sync_cmd):
        """Sync with --verbosity flag."""
        # Arrange
        mock_instance = Mock()
        mock_instance.run.return_value = ExitCode.SUCCESS
        mock_sync_cmd.return_value = mock_instance

        # Act
        result = runner.invoke(app, ["-v", "2", "--dry-run"])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        # Verify OutputHandler was created with correct verbosity
        mock_output_cls.assert_called_once_with(verbosity=2, no_color=False)

    @patch('src.cli.main.SyncCommand')
    @patch('src.cli.main.OutputHandler')
    def test_sync_with_no_color_flag(self, mock_output_cls, mock_sync_cmd):
        """Sync with --no-color flag."""
        # Arrange
        mock_instance = Mock()
        mock_instance.run.return_value = ExitCode.SUCCESS
        mock_sync_cmd.return_value = mock_instance

        # Act
        result = runner.invoke(app, ["--no-color", "--dry-run"])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        # Verify OutputHandler was created with no_color=True
        mock_output_cls.assert_called_once_with(verbosity=0, no_color=True)


class TestInitCommand:
    """Test cases for --init option."""

    @patch('src.cli.main.InitCommand')
    @patch('src.cli.main.OutputHandler')
    def test_init_success(self, mock_output_cls, mock_init_cmd_cls):
        """Init command succeeds."""
        # Arrange
        mock_output = Mock()
        mock_output.spinner.return_value.__enter__ = Mock()
        mock_output.spinner.return_value.__exit__ = Mock()
        mock_output_cls.return_value = mock_output

        mock_init = Mock()
        mock_init.config_path = ".confluence-sync/config.yaml"
        mock_init_cmd_cls.return_value = mock_init

        # Act - using --init --local --url options
        result = runner.invoke(app, [
            "--init",
            "--local", "./docs",
            "--url", "https://example.atlassian.net/wiki/spaces/TEAM/pages/123456"
        ])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        mock_init.run.assert_called_once_with(
            local_path="./docs",
            confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456",
            exclude_parent=False
        )
        mock_output.success.assert_called()

    @patch('src.cli.main.InitCommand')
    @patch('src.cli.main.OutputHandler')
    def test_init_with_exclude_parent(self, mock_output_cls, mock_init_cmd_cls):
        """Init command with --excludeParent flag."""
        # Arrange
        mock_output = Mock()
        mock_output.spinner.return_value.__enter__ = Mock()
        mock_output.spinner.return_value.__exit__ = Mock()
        mock_output_cls.return_value = mock_output

        mock_init = Mock()
        mock_init.config_path = ".confluence-sync/config.yaml"
        mock_init_cmd_cls.return_value = mock_init

        # Act - --excludeParent can be placed anywhere
        result = runner.invoke(app, [
            "--init",
            "--local", "./docs",
            "--url", "https://example.atlassian.net/wiki/spaces/TEAM/pages/123456",
            "--excludeParent"
        ])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        mock_init.run.assert_called_once_with(
            local_path="./docs",
            confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456",
            exclude_parent=True
        )

    @patch('src.cli.main.InitCommand')
    @patch('src.cli.main.OutputHandler')
    def test_init_with_exclude_parent_before_other_options(self, mock_output_cls, mock_init_cmd_cls):
        """Init command with --excludeParent placed before --init."""
        # Arrange
        mock_output = Mock()
        mock_output.spinner.return_value.__enter__ = Mock()
        mock_output.spinner.return_value.__exit__ = Mock()
        mock_output_cls.return_value = mock_output

        mock_init = Mock()
        mock_init.config_path = ".confluence-sync/config.yaml"
        mock_init_cmd_cls.return_value = mock_init

        # Act - --excludeParent before --init
        result = runner.invoke(app, [
            "--excludeParent",
            "--init",
            "--local", "./docs",
            "--url", "https://example.atlassian.net/wiki/spaces/TEAM/pages/123456"
        ])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        mock_init.run.assert_called_once_with(
            local_path="./docs",
            confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456",
            exclude_parent=True
        )

    @patch('src.cli.main.InitCommand')
    @patch('src.cli.main.OutputHandler')
    def test_init_with_verbosity(self, mock_output_cls, mock_init_cmd_cls):
        """Init command with verbosity flag."""
        # Arrange
        mock_output = Mock()
        mock_output.spinner.return_value.__enter__ = Mock()
        mock_output.spinner.return_value.__exit__ = Mock()
        mock_output_cls.return_value = mock_output

        mock_init = Mock()
        mock_init.config_path = ".confluence-sync/config.yaml"
        mock_init_cmd_cls.return_value = mock_init

        # Act
        result = runner.invoke(app, [
            "--init",
            "--local", "./docs",
            "--url", "https://example.atlassian.net/wiki/spaces/TEAM/pages/123456",
            "-v", "1"
        ])

        # Assert
        assert result.exit_code == ExitCode.SUCCESS
        mock_output_cls.assert_called_once_with(verbosity=1, no_color=False)

    def test_init_missing_url(self):
        """Init fails with helpful message when --url is missing."""
        # Act - --init and --local without --url
        result = runner.invoke(app, ["--init", "--local", "./docs"])

        # Assert
        assert result.exit_code == ExitCode.GENERAL_ERROR
        assert "--url" in result.output
        assert "Example:" in result.output

    def test_init_missing_local(self):
        """Init fails with helpful message when --local is missing."""
        # Act - --init and --url without --local
        result = runner.invoke(app, ["--init", "--url", "https://example.com/wiki/spaces/TEST/pages/123"])

        # Assert
        assert result.exit_code == ExitCode.GENERAL_ERROR
        assert "--local" in result.output
        assert "Example:" in result.output

    def test_init_missing_init_flag(self):
        """Init fails with helpful message when --init is missing but --url provided."""
        # Act - only --url without --init
        result = runner.invoke(app, ["--url", "https://example.com/wiki/spaces/TEST/pages/123"])

        # Assert
        assert result.exit_code == ExitCode.GENERAL_ERROR
        assert "--init" in result.output


class TestGettingStarted:
    """Test cases for getting started message."""

    @patch('os.path.exists')
    def test_no_args_without_config_shows_getting_started(self, mock_exists):
        """No arguments without config shows getting started message."""
        mock_exists.return_value = False  # No config

        result = runner.invoke(app, [])

        assert result.exit_code == 0
        assert "--init" in result.output
        assert "--local" in result.output
        assert "--url" in result.output
        assert "--dry-run" in result.output
        assert "Example:" in result.output

    def test_version_flag_shows_version(self):
        """--version flag shows version and exits."""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestHelpMessages:
    """Test cases for help messages."""

    def test_help_shows_options(self):
        """Help shows all available options."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "--init" in result.output
        assert "--local" in result.output
        assert "--url" in result.output
        assert "--dry-run" in result.output
        assert "--force-push" in result.output
        assert "--force-pull" in result.output
        assert "--excludeParent" in result.output
