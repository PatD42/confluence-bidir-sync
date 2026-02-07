"""Unit tests for git_integration.merge_tool module."""

import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.git_integration.errors import MergeToolError
from src.git_integration.merge_tool import MergeTool
from src.git_integration.models import MergeToolResult


class TestMergeTool:
    """Test cases for MergeTool class."""

    @patch("shutil.which")
    def test_validate_vscode_available(self, mock_which):
        """Returns True if 'code' is in PATH (UT-MT-01)."""
        # Arrange
        mock_which.return_value = "/usr/local/bin/code"
        tool = MergeTool("vscode")

        # Act
        result = tool.validate_available()

        # Assert
        assert result is True
        mock_which.assert_called_once_with("code")

    @patch("shutil.which")
    def test_validate_vscode_unavailable(self, mock_which):
        """Returns False if 'code' is not in PATH (UT-MT-02)."""
        # Arrange
        mock_which.return_value = None
        tool = MergeTool("vscode")

        # Act
        result = tool.validate_available()

        # Assert
        assert result is False
        mock_which.assert_called_once_with("code")

    @patch("subprocess.run")
    def test_launch_vscode(self, mock_run):
        """Calls 'code --wait --diff' with correct args (UT-MT-03)."""
        # Arrange
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        tool = MergeTool("vscode")

        # Create temporary test files
        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = os.path.join(tmpdir, "local.md")
            base_file = os.path.join(tmpdir, "base.md")
            remote_file = os.path.join(tmpdir, "remote.md")
            output_file = os.path.join(tmpdir, "output.md")

            # Create the required files
            for file_path in [local_file, base_file, remote_file]:
                with open(file_path, "w") as f:
                    f.write("test content")

            # Write some content to local file (since vscode edits in place)
            with open(local_file, "w") as f:
                f.write("merged content")

            # Act
            result = tool.launch(local_file, base_file, remote_file, output_file)

            # Assert
            assert result.success is True
            assert result.resolved_content == "merged content"
            mock_run.assert_called_once()

            # Verify command structure
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "code"
            assert call_args[1] == "--wait"
            assert call_args[2] == "--diff"
            assert call_args[3] == local_file
            assert call_args[4] == remote_file

    @patch("subprocess.run")
    def test_launch_vim(self, mock_run):
        """Calls 'vim -d' with correct args (UT-MT-04)."""
        # Arrange
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        tool = MergeTool("vim")

        # Create temporary test files
        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = os.path.join(tmpdir, "local.md")
            base_file = os.path.join(tmpdir, "base.md")
            remote_file = os.path.join(tmpdir, "remote.md")
            output_file = os.path.join(tmpdir, "output.md")

            # Create the required files
            for file_path in [local_file, base_file, remote_file]:
                with open(file_path, "w") as f:
                    f.write("test content")

            # Write merged content to local file (vim edits in place)
            with open(local_file, "w") as f:
                f.write("merged with vim")

            # Act
            result = tool.launch(local_file, base_file, remote_file, output_file)

            # Assert
            assert result.success is True
            assert result.resolved_content == "merged with vim"
            mock_run.assert_called_once()

            # Verify command structure
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "vim"
            assert call_args[1] == "-d"
            assert call_args[2] == local_file
            assert call_args[3] == base_file
            assert call_args[4] == remote_file

    @patch("subprocess.run")
    def test_launch_custom_command(self, mock_run):
        """Custom command template expanded correctly (UT-MT-05)."""
        # Arrange
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        custom_cmd = "mymerge {LOCAL} {BASE} {REMOTE} -o {OUTPUT}"
        tool = MergeTool("custom", custom_command=custom_cmd)

        # Create temporary test files
        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = os.path.join(tmpdir, "local.md")
            base_file = os.path.join(tmpdir, "base.md")
            remote_file = os.path.join(tmpdir, "remote.md")
            output_file = os.path.join(tmpdir, "output.md")

            # Create the required files
            for file_path in [local_file, base_file, remote_file]:
                with open(file_path, "w") as f:
                    f.write("test content")

            # Write merged content to output file
            with open(output_file, "w") as f:
                f.write("custom merge result")

            # Act
            result = tool.launch(local_file, base_file, remote_file, output_file)

            # Assert
            assert result.success is True
            assert result.resolved_content == "custom merge result"
            mock_run.assert_called_once()

            # Verify command structure
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "mymerge"
            assert call_args[1] == local_file
            assert call_args[2] == base_file
            assert call_args[3] == remote_file
            assert call_args[4] == "-o"
            assert call_args[5] == output_file

    @patch("subprocess.run")
    def test_tool_timeout(self, mock_run):
        """Raises MergeToolError after 30min timeout (UT-MT-06)."""
        # Arrange
        mock_run.side_effect = subprocess.TimeoutExpired("code", 1800)
        tool = MergeTool("vscode")

        # Create temporary test files
        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = os.path.join(tmpdir, "local.md")
            base_file = os.path.join(tmpdir, "base.md")
            remote_file = os.path.join(tmpdir, "remote.md")
            output_file = os.path.join(tmpdir, "output.md")

            # Create the required files
            for file_path in [local_file, base_file, remote_file]:
                with open(file_path, "w") as f:
                    f.write("test content")

            # Act & Assert
            with pytest.raises(MergeToolError) as exc_info:
                tool.launch(local_file, base_file, remote_file, output_file)

            assert "timed out after 1800 seconds" in str(exc_info.value)
            assert exc_info.value.tool_name == "vscode"

    @patch("subprocess.run")
    def test_tool_exit_nonzero(self, mock_run):
        """Raises MergeToolError with stderr when tool exits non-zero (UT-MT-07)."""
        # Arrange
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Error: Failed to merge files",
            stdout=""
        )
        tool = MergeTool("vim")

        # Create temporary test files
        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = os.path.join(tmpdir, "local.md")
            base_file = os.path.join(tmpdir, "base.md")
            remote_file = os.path.join(tmpdir, "remote.md")
            output_file = os.path.join(tmpdir, "output.md")

            # Create the required files
            for file_path in [local_file, base_file, remote_file]:
                with open(file_path, "w") as f:
                    f.write("test content")

            # Act & Assert
            with pytest.raises(MergeToolError) as exc_info:
                tool.launch(local_file, base_file, remote_file, output_file)

            assert "exited with code 1" in str(exc_info.value)
            assert "Error: Failed to merge files" in str(exc_info.value)
            assert exc_info.value.tool_name == "vim"


class TestMergeToolInitialization:
    """Test cases for MergeTool initialization and validation."""

    def test_custom_tool_without_command_raises_error(self):
        """Custom tool without custom_command raises MergeToolError."""
        with pytest.raises(MergeToolError) as exc_info:
            MergeTool("custom")

        assert "custom_command is required" in str(exc_info.value)

    def test_custom_tool_with_command_succeeds(self):
        """Custom tool with custom_command initializes successfully."""
        tool = MergeTool("custom", custom_command="mymerge {LOCAL} {REMOTE}")
        assert tool.tool_name == "custom"
        assert tool.custom_command == "mymerge {LOCAL} {REMOTE}"

    @patch("shutil.which")
    def test_validate_custom_tool(self, mock_which):
        """Custom tool validation checks first word of command."""
        # Arrange
        mock_which.return_value = "/usr/local/bin/mymerge"
        tool = MergeTool("custom", custom_command="mymerge {LOCAL} {REMOTE}")

        # Act
        result = tool.validate_available()

        # Assert
        assert result is True
        mock_which.assert_called_once_with("mymerge")

    @patch("subprocess.run")
    def test_launch_missing_local_file(self, mock_run):
        """Launch raises MergeToolError if local file doesn't exist."""
        # Arrange
        tool = MergeTool("vscode")

        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = os.path.join(tmpdir, "nonexistent.md")
            base_file = os.path.join(tmpdir, "base.md")
            remote_file = os.path.join(tmpdir, "remote.md")
            output_file = os.path.join(tmpdir, "output.md")

            # Create only base and remote files
            for file_path in [base_file, remote_file]:
                with open(file_path, "w") as f:
                    f.write("test content")

            # Act & Assert
            with pytest.raises(MergeToolError) as exc_info:
                tool.launch(local_file, base_file, remote_file, output_file)

            assert "local file not found" in str(exc_info.value)

    @patch("subprocess.run")
    def test_launch_reads_output_file_when_exists(self, mock_run):
        """Launch reads from output file when it exists (meld, kdiff3 style)."""
        # Arrange
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        tool = MergeTool("meld")

        # Create temporary test files
        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = os.path.join(tmpdir, "local.md")
            base_file = os.path.join(tmpdir, "base.md")
            remote_file = os.path.join(tmpdir, "remote.md")
            output_file = os.path.join(tmpdir, "output.md")

            # Create the required files
            for file_path in [local_file, base_file, remote_file]:
                with open(file_path, "w") as f:
                    f.write("test content")

            # Write merged content to output file (meld writes to output)
            with open(output_file, "w") as f:
                f.write("merged via output file")

            # Act
            result = tool.launch(local_file, base_file, remote_file, output_file)

            # Assert
            assert result.success is True
            assert result.resolved_content == "merged via output file"
