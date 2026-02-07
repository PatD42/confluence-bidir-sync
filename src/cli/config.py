"""State file loading and validation.

This module handles loading and saving sync state from YAML files
according to ADR-013. State files track project-level sync timestamps
rather than per-file timestamps.
"""

import os
from typing import Dict, Any, Optional
import yaml

from .errors import StateError, StateFilesystemError
from .models import SyncState


class StateManager:
    """Handles state file loading, validation, and saving.

    Manages YAML state files that track the last successful sync timestamp
    at the project level (ADR-013). This timestamp is used for bidirectional
    change detection per ADR-014.

    State file structure:
        last_synced: "2024-01-15T10:30:00Z"

    If the file is missing or corrupted, it's treated as a fresh state
    (never synced) with last_synced=None.
    """

    # Default state directory
    DEFAULT_STATE_DIR = '.confluence-sync'
    DEFAULT_STATE_FILE = 'state.yaml'

    @classmethod
    def load(cls, state_path: str) -> SyncState:
        """Load and parse state from a YAML file.

        Args:
            state_path: Path to the YAML state file

        Returns:
            SyncState object with parsed state

        Raises:
            StateFilesystemError: If file cannot be read (except FileNotFoundError)
            StateError: If state file is invalid or malformed
        """
        # Read file - treat missing file as fresh state
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            # Missing state file is normal for first sync
            return SyncState()
        except PermissionError:
            raise StateFilesystemError(
                state_path,
                'read',
                'Permission denied'
            )
        except Exception as e:
            raise StateFilesystemError(
                state_path,
                'read',
                str(e)
            )

        # Handle empty file
        if not content.strip():
            return SyncState()

        # Parse YAML
        try:
            state_dict = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise StateError(
                f"Invalid YAML syntax: {str(e)}"
            )

        if state_dict is None:
            return SyncState()

        if not isinstance(state_dict, dict):
            raise StateError(
                f"State must be a YAML dictionary, got {type(state_dict).__name__}"
            )

        # Validate and parse
        return cls._parse_state(state_dict)

    @classmethod
    def save(cls, state_path: str, sync_state: SyncState) -> None:
        """Save state to a YAML file.

        Args:
            state_path: Path to the YAML state file
            sync_state: SyncState object to save

        Raises:
            StateFilesystemError: If file cannot be written
        """
        # Convert SyncState to dictionary
        state_dict = {
            'last_synced': sync_state.last_synced,
            'tracked_pages': sync_state.tracked_pages
        }

        # Generate YAML
        yaml_str = yaml.safe_dump(
            state_dict,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False
        )

        # Ensure directory exists
        state_dir = os.path.dirname(state_path)
        if state_dir:
            try:
                os.makedirs(state_dir, exist_ok=True)
            except Exception as e:
                raise StateFilesystemError(
                    state_dir,
                    'create_directory',
                    str(e)
                )

        # Write file
        try:
            with open(state_path, 'w', encoding='utf-8') as f:
                f.write(yaml_str)
        except PermissionError:
            raise StateFilesystemError(
                state_path,
                'write',
                'Permission denied'
            )
        except Exception as e:
            raise StateFilesystemError(
                state_path,
                'write',
                str(e)
            )

    @classmethod
    def _parse_state(cls, state_dict: Dict[str, Any]) -> SyncState:
        """Parse and validate state dictionary.

        Args:
            state_dict: Raw state dictionary from YAML

        Returns:
            Validated SyncState object

        Raises:
            StateError: If state is invalid
        """
        # Extract last_synced (optional field)
        last_synced = state_dict.get('last_synced')

        # Validate type if present
        if last_synced is not None:
            if not isinstance(last_synced, str):
                raise StateError(
                    f"Field 'last_synced' must be a string (ISO 8601 timestamp), got {type(last_synced).__name__}",
                    'last_synced'
                )

            # Validate non-empty string
            if not last_synced.strip():
                raise StateError(
                    "Field 'last_synced' cannot be empty",
                    'last_synced'
                )

            last_synced = last_synced.strip()

        # Extract tracked_pages (optional field)
        tracked_pages = state_dict.get('tracked_pages', {})

        # Validate type if present
        if tracked_pages is not None:
            if not isinstance(tracked_pages, dict):
                raise StateError(
                    f"Field 'tracked_pages' must be a dictionary, got {type(tracked_pages).__name__}",
                    'tracked_pages'
                )

            # Validate all keys and values are strings
            for page_id, path in tracked_pages.items():
                if not isinstance(page_id, str):
                    raise StateError(
                        f"Field 'tracked_pages' keys must be strings, got {type(page_id).__name__}",
                        'tracked_pages'
                    )
                if not isinstance(path, str):
                    raise StateError(
                        f"Field 'tracked_pages' values must be strings, got {type(path).__name__}",
                        'tracked_pages'
                    )
        else:
            tracked_pages = {}

        return SyncState(last_synced=last_synced, tracked_pages=tracked_pages)
