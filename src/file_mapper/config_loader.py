"""YAML configuration loading and validation.

This module handles loading and saving sync configuration from YAML files
according to ADR-012. Configuration files use parent pageID as the anchor
point for the hierarchy rather than local file paths.
"""

import os
from typing import Dict, Any, List
import yaml

from .errors import ConfigError, FilesystemError
from .models import SpaceConfig, SyncConfig


class ConfigLoader:
    """Handles configuration file loading, validation, and saving.

    Manages YAML configuration files that specify which Confluence spaces
    to sync, where to sync them, and sync behavior options. The parent
    pageID serves as the anchor for each space hierarchy (ADR-012).

    Configuration file structure:
        spaces:
          - space_key: "TEAM"
            parent_page_id: "123456"
            local_path: "./team-space"
            exclude_page_ids: ["789012", "345678"]
        page_limit: 100
        force_pull: false
        force_push: false
        temp_dir: ".confluence-sync/temp"
    """

    # Required top-level config fields
    REQUIRED_TOP_LEVEL_FIELDS = {'spaces'}

    # Required fields for each space config
    REQUIRED_SPACE_FIELDS = {'space_key', 'parent_page_id', 'local_path'}

    # Default values for optional fields
    DEFAULTS = {
        'page_limit': 100,
        'force_pull': False,
        'force_push': False,
        'temp_dir': '.confluence-sync/temp'
    }

    @classmethod
    def load(cls, config_path: str) -> SyncConfig:
        """Load and parse configuration from a YAML file.

        Args:
            config_path: Path to the YAML configuration file

        Returns:
            SyncConfig object with parsed configuration

        Raises:
            FilesystemError: If file cannot be read
            ConfigError: If configuration is invalid or malformed
        """
        # Read file
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            raise FilesystemError(
                config_path,
                'read',
                'Configuration file not found'
            )
        except PermissionError:
            raise FilesystemError(
                config_path,
                'read',
                'Permission denied'
            )
        except Exception as e:
            raise FilesystemError(
                config_path,
                'read',
                str(e)
            )

        # Parse YAML
        try:
            config_dict = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise ConfigError(
                f"Invalid YAML syntax: {str(e)}"
            )

        if config_dict is None:
            raise ConfigError("Configuration file is empty")

        if not isinstance(config_dict, dict):
            raise ConfigError(
                f"Configuration must be a YAML dictionary, got {type(config_dict).__name__}"
            )

        # Validate and parse
        return cls._parse_config(config_dict)

    @classmethod
    def save(cls, config_path: str, sync_config: SyncConfig) -> None:
        """Save configuration to a YAML file.

        Args:
            config_path: Path to the YAML configuration file
            sync_config: SyncConfig object to save

        Raises:
            FilesystemError: If file cannot be written
        """
        # Convert SyncConfig to dictionary
        spaces_list = []
        for space in sync_config.spaces:
            space_dict = {
                'space_key': space.space_key,
                'parent_page_id': space.parent_page_id,
                'local_path': space.local_path,
                'confluence_base_url': space.confluence_base_url,
            }
            # Only include optional fields if they have non-default values
            if space.exclude_page_ids:
                space_dict['exclude_page_ids'] = space.exclude_page_ids
            if space.exclude_parent:
                space_dict['exclude_parent'] = space.exclude_parent
            spaces_list.append(space_dict)

        config_dict = {
            'spaces': spaces_list,
            'page_limit': sync_config.page_limit,
            'force_pull': sync_config.force_pull,
            'force_push': sync_config.force_push,
            'temp_dir': sync_config.temp_dir
        }

        # Generate YAML
        yaml_str = yaml.safe_dump(
            config_dict,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False
        )

        # Ensure directory exists
        config_dir = os.path.dirname(config_path)
        if config_dir:
            try:
                os.makedirs(config_dir, exist_ok=True)
            except Exception as e:
                raise FilesystemError(
                    config_dir,
                    'create_directory',
                    str(e)
                )

        # Write file
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(yaml_str)
        except PermissionError:
            raise FilesystemError(
                config_path,
                'write',
                'Permission denied'
            )
        except Exception as e:
            raise FilesystemError(
                config_path,
                'write',
                str(e)
            )

    @classmethod
    def _parse_config(cls, config_dict: Dict[str, Any]) -> SyncConfig:
        """Parse and validate configuration dictionary.

        Args:
            config_dict: Raw configuration dictionary from YAML

        Returns:
            Validated SyncConfig object

        Raises:
            ConfigError: If configuration is invalid
        """
        # Validate required top-level fields
        missing_fields = cls.REQUIRED_TOP_LEVEL_FIELDS - set(config_dict.keys())
        if missing_fields:
            raise ConfigError(
                f"Missing required fields: {', '.join(sorted(missing_fields))}"
            )

        # Parse spaces
        spaces_raw = config_dict.get('spaces')
        if not isinstance(spaces_raw, list):
            raise ConfigError(
                "Field 'spaces' must be a list",
                'spaces'
            )

        if not spaces_raw:
            raise ConfigError(
                "At least one space configuration is required",
                'spaces'
            )

        spaces = []
        for i, space_dict in enumerate(spaces_raw):
            if not isinstance(space_dict, dict):
                raise ConfigError(
                    f"Space configuration at index {i} must be a dictionary",
                    f'spaces[{i}]'
                )

            # Validate required space fields
            missing_space_fields = cls.REQUIRED_SPACE_FIELDS - set(space_dict.keys())
            if missing_space_fields:
                raise ConfigError(
                    f"Missing required fields in space {i}: {', '.join(sorted(missing_space_fields))}",
                    f'spaces[{i}]'
                )

            # Validate field types
            try:
                space_key = str(space_dict['space_key'])
                parent_page_id = str(space_dict['parent_page_id'])
                local_path = str(space_dict['local_path'])

                # Parse exclude_page_ids (optional)
                exclude_page_ids = []
                if 'exclude_page_ids' in space_dict:
                    exclude_raw = space_dict['exclude_page_ids']
                    if exclude_raw is not None:
                        if not isinstance(exclude_raw, list):
                            raise ConfigError(
                                f"Field 'exclude_page_ids' in space {i} must be a list",
                                f'spaces[{i}].exclude_page_ids'
                            )
                        exclude_page_ids = [str(page_id) for page_id in exclude_raw]

                # Parse exclude_parent (optional, default False)
                exclude_parent = bool(space_dict.get('exclude_parent', False))

                # Parse confluence_base_url (optional, default "")
                confluence_base_url = str(space_dict.get('confluence_base_url', ''))

            except (ValueError, TypeError, KeyError) as e:
                raise ConfigError(
                    f"Invalid field type in space {i}: {str(e)}",
                    f'spaces[{i}]'
                )

            # Validate non-empty strings
            if not space_key.strip():
                raise ConfigError(
                    f"Field 'space_key' in space {i} cannot be empty",
                    f'spaces[{i}].space_key'
                )
            if not parent_page_id.strip():
                raise ConfigError(
                    f"Field 'parent_page_id' in space {i} cannot be empty",
                    f'spaces[{i}].parent_page_id'
                )
            if not local_path.strip():
                raise ConfigError(
                    f"Field 'local_path' in space {i} cannot be empty",
                    f'spaces[{i}].local_path'
                )

            spaces.append(SpaceConfig(
                space_key=space_key,
                parent_page_id=parent_page_id,
                local_path=local_path,
                exclude_page_ids=exclude_page_ids,
                exclude_parent=exclude_parent,
                confluence_base_url=confluence_base_url
            ))

        # Parse optional top-level fields with defaults
        page_limit = config_dict.get('page_limit', cls.DEFAULTS['page_limit'])
        force_pull = config_dict.get('force_pull', cls.DEFAULTS['force_pull'])
        force_push = config_dict.get('force_push', cls.DEFAULTS['force_push'])
        temp_dir = config_dict.get('temp_dir', cls.DEFAULTS['temp_dir'])

        # Validate types
        try:
            page_limit = int(page_limit)
            force_pull = bool(force_pull)
            force_push = bool(force_push)
            temp_dir = str(temp_dir)
        except (ValueError, TypeError) as e:
            raise ConfigError(
                f"Invalid field type for optional field: {str(e)}"
            )

        # Validate page_limit value
        if page_limit < 1:
            raise ConfigError(
                f"Field 'page_limit' must be at least 1, got {page_limit}",
                'page_limit'
            )

        # Validate mutually exclusive force flags
        if force_pull and force_push:
            raise ConfigError(
                "Fields 'force_pull' and 'force_push' are mutually exclusive"
            )

        return SyncConfig(
            spaces=spaces,
            page_limit=page_limit,
            force_pull=force_pull,
            force_push=force_push,
            temp_dir=temp_dir
        )
