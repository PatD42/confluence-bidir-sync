"""Merge tool integration for conflict resolution.

This module provides the MergeTool class for launching external merge tools
(VS Code, vim, meld, kdiff3, etc.) to resolve merge conflicts. It supports
both predefined tools and custom command templates.
"""

import logging
import os
import shutil
import subprocess
from typing import Optional

from src.git_integration.errors import MergeToolError
from src.git_integration.models import MergeToolResult

logger = logging.getLogger(__name__)

# Merge tool timeout in seconds (30 minutes)
MERGE_TOOL_TIMEOUT = 1800


class MergeTool:
    """Launches external merge tools for conflict resolution.

    This class manages the integration with external merge tools for three-way
    merge conflict resolution. It supports multiple predefined tools and allows
    custom command templates.

    Supported tools:
        - vscode: Visual Studio Code
        - vim: Vim text editor
        - meld: Meld visual diff and merge tool
        - kdiff3: KDiff3 merge tool
        - custom: User-defined command template

    Command templates use these placeholders:
        {LOCAL}: Path to local version file
        {BASE}: Path to base version file
        {REMOTE}: Path to remote version file
        {OUTPUT}: Path to output file for merged result

    Example:
        >>> tool = MergeTool('vscode')
        >>> if tool.validate_available():
        ...     result = tool.launch('local.md', 'base.md', 'remote.md', 'output.md')
        ...     if result.success:
        ...         print('Merge successful')
    """

    # Predefined tool command templates
    TOOL_COMMANDS = {
        "vscode": "code --wait --diff {LOCAL} {REMOTE}",
        "vim": "vim -d {LOCAL} {BASE} {REMOTE}",
        "meld": "meld {LOCAL} {BASE} {REMOTE} --output {OUTPUT}",
        "kdiff3": "kdiff3 {BASE} {LOCAL} {REMOTE} -o {OUTPUT}",
    }

    # Tool executable names for validation
    TOOL_EXECUTABLES = {
        "vscode": "code",
        "vim": "vim",
        "meld": "meld",
        "kdiff3": "kdiff3",
    }

    def __init__(self, tool_name: str = "vscode", custom_command: Optional[str] = None):
        """Initialize merge tool.

        Args:
            tool_name: Tool name (vscode, vim, meld, kdiff3, custom)
            custom_command: Custom command template with {LOCAL}, {BASE}, {REMOTE}, {OUTPUT}
                           Required if tool_name is 'custom'

        Raises:
            MergeToolError: If custom tool_name used without custom_command
        """
        self.tool_name = tool_name
        self.custom_command = custom_command

        # Validate custom tool configuration
        if tool_name == "custom" and not custom_command:
            raise MergeToolError(
                tool_name="custom",
                error="custom_command is required when tool_name is 'custom'",
            )

        # Validate tool_name is known
        if tool_name not in self.TOOL_COMMANDS and tool_name != "custom":
            logger.warning(
                f"Unknown tool name '{tool_name}'. Supported tools: "
                f"{', '.join(self.TOOL_COMMANDS.keys())}, custom"
            )

    def validate_available(self) -> bool:
        """Check if merge tool is installed and in PATH.

        Returns:
            True if available, False otherwise
        """
        # For custom commands, try to extract executable name
        if self.tool_name == "custom":
            if not self.custom_command:
                return False
            # Extract first word as executable name
            executable = self.custom_command.split()[0]
        elif self.tool_name in self.TOOL_EXECUTABLES:
            executable = self.TOOL_EXECUTABLES[self.tool_name]
        else:
            logger.warning(f"Cannot validate unknown tool: {self.tool_name}")
            return False

        # Check if executable is in PATH
        is_available = shutil.which(executable) is not None

        if is_available:
            logger.debug(f"Merge tool '{self.tool_name}' is available: {executable}")
        else:
            logger.warning(
                f"Merge tool '{self.tool_name}' not found in PATH: {executable}"
            )

        return is_available

    def launch(
        self,
        local_file: str,
        base_file: str,
        remote_file: str,
        output_file: str,
    ) -> MergeToolResult:
        """Launch merge tool for three-way merge.

        This method launches the configured merge tool with the provided files
        and waits for it to exit. The tool runs with a 30-minute timeout to allow
        users time to resolve conflicts.

        Args:
            local_file: Local version path
            base_file: Base version path
            remote_file: Remote version path
            output_file: Where to save merged result

        Returns:
            MergeToolResult with success status and resolved content

        Raises:
            MergeToolError: If tool launch fails or exits with error
        """
        # Validate files exist
        for file_path, file_type in [
            (local_file, "local"),
            (base_file, "base"),
            (remote_file, "remote"),
        ]:
            if not os.path.exists(file_path):
                raise MergeToolError(
                    tool_name=self.tool_name,
                    error=f"{file_type} file not found: {file_path}",
                )

        # Get command template
        if self.custom_command:
            command_template = self.custom_command
        elif self.tool_name in self.TOOL_COMMANDS:
            command_template = self.TOOL_COMMANDS[self.tool_name]
        else:
            raise MergeToolError(
                tool_name=self.tool_name,
                error=f"Unknown tool name: {self.tool_name}",
            )

        # Substitute placeholders
        command = command_template.format(
            LOCAL=local_file,
            BASE=base_file,
            REMOTE=remote_file,
            OUTPUT=output_file,
        )

        logger.info(f"Launching merge tool '{self.tool_name}': {command}")

        # Launch tool
        try:
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=MERGE_TOOL_TIMEOUT,
            )

            if result.returncode != 0:
                error_msg = f"Tool exited with code {result.returncode}"
                if result.stderr:
                    error_msg += f": {result.stderr}"

                logger.error(f"Merge tool failed: {error_msg}")
                raise MergeToolError(tool_name=self.tool_name, error=error_msg)

            # Read resolved content from output file
            resolved_content = ""
            if os.path.exists(output_file):
                try:
                    with open(output_file, "r", encoding="utf-8") as f:
                        resolved_content = f.read()
                except OSError as e:
                    raise MergeToolError(
                        tool_name=self.tool_name,
                        error=f"Failed to read output file: {e}",
                    )
            else:
                # Some tools (like vscode --diff) edit the local file in place
                # Try reading from local file
                try:
                    with open(local_file, "r", encoding="utf-8") as f:
                        resolved_content = f.read()
                except OSError as e:
                    raise MergeToolError(
                        tool_name=self.tool_name,
                        error=f"Output file not found and failed to read local file: {e}",
                    )

            logger.info(f"Merge tool '{self.tool_name}' completed successfully")

            return MergeToolResult(
                success=True,
                resolved_content=resolved_content,
                error=None,
            )

        except subprocess.TimeoutExpired:
            error_msg = f"Tool timed out after {MERGE_TOOL_TIMEOUT} seconds"
            logger.error(f"Merge tool timeout: {error_msg}")
            raise MergeToolError(tool_name=self.tool_name, error=error_msg)

        except FileNotFoundError as e:
            error_msg = f"Tool executable not found: {e}"
            logger.error(f"Merge tool launch failed: {error_msg}")
            raise MergeToolError(tool_name=self.tool_name, error=error_msg)

        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Merge tool failed: {error_msg}")
            raise MergeToolError(tool_name=self.tool_name, error=error_msg)
