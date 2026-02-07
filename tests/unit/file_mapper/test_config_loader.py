"""Unit tests for file_mapper.config_loader module."""

import os
import tempfile
import pytest
import yaml
from unittest.mock import patch

from src.file_mapper.config_loader import ConfigLoader
from src.file_mapper.errors import ConfigError, FilesystemError
from src.file_mapper.models import SpaceConfig, SyncConfig


class TestConfigLoaderLoad:
    """Test cases for ConfigLoader.load() method."""

    def test_load_valid_config_with_all_fields(self, tmp_path):
        """Load valid configuration with all fields specified."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEAM
    parent_page_id: "123456"
    local_path: ./team-space
    exclude_page_ids:
      - "789012"
      - "345678"
  - space_key: PROD
    parent_page_id: "999888"
    local_path: ./prod-space
    exclude_page_ids: []
page_limit: 50
force_pull: true
force_push: false
temp_dir: .custom-temp
"""
        config_file.write_text(config_content)

        result = ConfigLoader.load(str(config_file))

        assert isinstance(result, SyncConfig)
        assert len(result.spaces) == 2

        # First space
        assert result.spaces[0].space_key == "TEAM"
        assert result.spaces[0].parent_page_id == "123456"
        assert result.spaces[0].local_path == "./team-space"
        assert result.spaces[0].exclude_page_ids == ["789012", "345678"]

        # Second space
        assert result.spaces[1].space_key == "PROD"
        assert result.spaces[1].parent_page_id == "999888"
        assert result.spaces[1].local_path == "./prod-space"
        assert result.spaces[1].exclude_page_ids == []

        # Top-level fields
        assert result.page_limit == 50
        assert result.force_pull is True
        assert result.force_push is False
        assert result.temp_dir == ".custom-temp"

    def test_load_valid_config_with_defaults(self, tmp_path):
        """Load valid configuration using default values for optional fields."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "111111"
    local_path: ./test
"""
        config_file.write_text(config_content)

        result = ConfigLoader.load(str(config_file))

        assert len(result.spaces) == 1
        assert result.spaces[0].exclude_page_ids == []
        assert result.page_limit == 100  # Default
        assert result.force_pull is False  # Default
        assert result.force_push is False  # Default
        assert result.temp_dir == ".confluence-sync/temp"  # Default

    def test_load_valid_config_without_exclude_page_ids(self, tmp_path):
        """Load valid configuration without exclude_page_ids field."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: ./test
"""
        config_file.write_text(config_content)

        result = ConfigLoader.load(str(config_file))

        assert result.spaces[0].exclude_page_ids == []

    def test_load_valid_config_with_null_exclude_page_ids(self, tmp_path):
        """Load valid configuration with null exclude_page_ids."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: ./test
    exclude_page_ids: null
"""
        config_file.write_text(config_content)

        result = ConfigLoader.load(str(config_file))

        assert result.spaces[0].exclude_page_ids == []

    def test_load_file_not_found_raises_error(self, tmp_path):
        """Load non-existent file raises FilesystemError."""
        config_file = tmp_path / "nonexistent.yaml"

        with pytest.raises(FilesystemError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert exc_info.value.file_path == str(config_file)
        assert exc_info.value.operation == "read"
        assert "not found" in str(exc_info.value).lower()

    def test_load_permission_error_raises_filesystem_error(self, tmp_path):
        """Load file without read permission raises FilesystemError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("spaces:\n  - space_key: TEST\n")

        # Make file unreadable
        os.chmod(config_file, 0o000)

        try:
            with pytest.raises(FilesystemError) as exc_info:
                ConfigLoader.load(str(config_file))

            assert exc_info.value.file_path == str(config_file)
            assert exc_info.value.operation == "read"
            assert "Permission denied" in str(exc_info.value)
        finally:
            # Restore permissions for cleanup
            os.chmod(config_file, 0o644)

    def test_load_generic_file_error_raises_filesystem_error(self, tmp_path):
        """Load with generic file error raises FilesystemError."""
        # Test using a directory path instead of file (causes IsADirectoryError)
        config_dir = tmp_path / "config_dir"
        config_dir.mkdir()

        with pytest.raises(FilesystemError) as exc_info:
            ConfigLoader.load(str(config_dir))

        assert exc_info.value.file_path == str(config_dir)
        assert exc_info.value.operation == "read"

    def test_load_invalid_yaml_syntax_raises_error(self, tmp_path):
        """Load file with invalid YAML syntax raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: [unclosed bracket
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Invalid YAML syntax" in str(exc_info.value)

    def test_load_empty_file_raises_error(self, tmp_path):
        """Load empty file raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Configuration file is empty" in str(exc_info.value)

    def test_load_yaml_not_dict_raises_error(self, tmp_path):
        """Load file with non-dict YAML raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("- item1\n- item2\n")

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "must be a YAML dictionary" in str(exc_info.value)
        assert "got list" in str(exc_info.value)

    def test_load_yaml_string_raises_error(self, tmp_path):
        """Load file with string YAML raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("just a string")

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "must be a YAML dictionary" in str(exc_info.value)
        assert "got str" in str(exc_info.value)

    def test_load_missing_spaces_field_raises_error(self, tmp_path):
        """Load file missing required 'spaces' field raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
page_limit: 100
force_pull: false
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Missing required fields: spaces" in str(exc_info.value)

    def test_load_spaces_not_list_raises_error(self, tmp_path):
        """Load file with non-list 'spaces' field raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces: not_a_list
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Field 'spaces' must be a list" in str(exc_info.value)

    def test_load_empty_spaces_list_raises_error(self, tmp_path):
        """Load file with empty 'spaces' list raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces: []
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "At least one space configuration is required" in str(exc_info.value)

    def test_load_space_not_dict_raises_error(self, tmp_path):
        """Load file with non-dict space entry raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - "string instead of dict"
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Space configuration at index 0 must be a dictionary" in str(exc_info.value)

    def test_load_space_missing_space_key_raises_error(self, tmp_path):
        """Load file with space missing space_key raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - parent_page_id: "123"
    local_path: ./test
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Missing required fields in space 0" in str(exc_info.value)
        assert "space_key" in str(exc_info.value)

    def test_load_space_missing_parent_page_id_raises_error(self, tmp_path):
        """Load file with space missing parent_page_id raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    local_path: ./test
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Missing required fields in space 0" in str(exc_info.value)
        assert "parent_page_id" in str(exc_info.value)

    def test_load_space_missing_local_path_raises_error(self, tmp_path):
        """Load file with space missing local_path raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Missing required fields in space 0" in str(exc_info.value)
        assert "local_path" in str(exc_info.value)

    def test_load_space_missing_multiple_fields_raises_error(self, tmp_path):
        """Load file with space missing multiple fields shows all missing."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        error_msg = str(exc_info.value)
        assert "Missing required fields in space 0" in error_msg
        assert "local_path" in error_msg
        assert "parent_page_id" in error_msg

    def test_load_space_empty_space_key_raises_error(self, tmp_path):
        """Load file with empty space_key raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: "  "
    parent_page_id: "123"
    local_path: ./test
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Field 'space_key' in space 0 cannot be empty" in str(exc_info.value)

    def test_load_space_empty_parent_page_id_raises_error(self, tmp_path):
        """Load file with empty parent_page_id raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: ""
    local_path: ./test
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Field 'parent_page_id' in space 0 cannot be empty" in str(exc_info.value)

    def test_load_space_empty_local_path_raises_error(self, tmp_path):
        """Load file with empty local_path raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: "   "
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Field 'local_path' in space 0 cannot be empty" in str(exc_info.value)

    def test_load_space_exclude_page_ids_not_list_raises_error(self, tmp_path):
        """Load file with non-list exclude_page_ids raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: ./test
    exclude_page_ids: "not a list"
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Field 'exclude_page_ids' in space 0 must be a list" in str(exc_info.value)

    def test_load_page_limit_less_than_one_raises_error(self, tmp_path):
        """Load file with page_limit < 1 raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: ./test
page_limit: 0
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Field 'page_limit' must be at least 1" in str(exc_info.value)
        assert "got 0" in str(exc_info.value)

    def test_load_page_limit_negative_raises_error(self, tmp_path):
        """Load file with negative page_limit raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: ./test
page_limit: -5
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Field 'page_limit' must be at least 1" in str(exc_info.value)

    def test_load_force_pull_and_force_push_both_true_raises_error(self, tmp_path):
        """Load file with both force flags true raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: ./test
force_pull: true
force_push: true
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "force_pull" in str(exc_info.value)
        assert "force_push" in str(exc_info.value)
        assert "mutually exclusive" in str(exc_info.value)

    def test_load_converts_field_types(self, tmp_path):
        """Load configuration converts field types appropriately."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: 123
    parent_page_id: 456
    local_path: ./test
    exclude_page_ids:
      - 789
      - 012
page_limit: "50"
"""
        config_file.write_text(config_content)

        result = ConfigLoader.load(str(config_file))

        # Should convert to strings
        assert result.spaces[0].space_key == "123"
        assert result.spaces[0].parent_page_id == "456"
        assert result.spaces[0].local_path == "./test"
        assert result.spaces[0].exclude_page_ids == ["789", "10"]  # Note: 012 is octal, becomes 10
        # Should convert to int
        assert result.page_limit == 50
        assert isinstance(result.page_limit, int)

    def test_load_multiple_spaces(self, tmp_path):
        """Load configuration with multiple space configs."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEAM1
    parent_page_id: "111"
    local_path: ./team1
  - space_key: TEAM2
    parent_page_id: "222"
    local_path: ./team2
  - space_key: TEAM3
    parent_page_id: "333"
    local_path: ./team3
"""
        config_file.write_text(config_content)

        result = ConfigLoader.load(str(config_file))

        assert len(result.spaces) == 3
        assert result.spaces[0].space_key == "TEAM1"
        assert result.spaces[1].space_key == "TEAM2"
        assert result.spaces[2].space_key == "TEAM3"

    def test_load_invalid_optional_field_type_raises_error(self, tmp_path):
        """Load file with invalid type for optional field raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: ./test
page_limit: [1, 2, 3]
"""
        config_file.write_text(config_content)

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_file))

        assert "Invalid field type for optional field" in str(exc_info.value)

    def test_load_space_field_type_conversion_error_raises_error(self):
        """Load with type conversion error in space fields raises ConfigError."""
        # Create a custom class that raises TypeError when converted to string
        class BadType:
            def __str__(self):
                raise TypeError("Cannot convert to string")

        # Directly test _parse_config with a problematic dictionary
        config_dict = {
            'spaces': [
                {
                    'space_key': BadType(),
                    'parent_page_id': '123',
                    'local_path': './test'
                }
            ]
        }

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader._parse_config(config_dict)

        assert "Invalid field type in space 0" in str(exc_info.value)


class TestConfigLoaderSave:
    """Test cases for ConfigLoader.save() method."""

    def test_save_valid_config(self, tmp_path):
        """Save valid SyncConfig to file."""
        config_file = tmp_path / "config.yaml"

        sync_config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123456",
                    local_path="./test-space",
                    exclude_page_ids=["789012"]
                )
            ],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=".confluence-sync/temp"
        )

        ConfigLoader.save(str(config_file), sync_config)

        assert config_file.exists()

        # Verify content
        loaded = ConfigLoader.load(str(config_file))
        assert len(loaded.spaces) == 1
        assert loaded.spaces[0].space_key == "TEST"
        assert loaded.spaces[0].parent_page_id == "123456"
        assert loaded.spaces[0].local_path == "./test-space"
        assert loaded.spaces[0].exclude_page_ids == ["789012"]
        assert loaded.page_limit == 100

    def test_save_config_with_multiple_spaces(self, tmp_path):
        """Save config with multiple spaces."""
        config_file = tmp_path / "config.yaml"

        sync_config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEAM1",
                    parent_page_id="111",
                    local_path="./team1",
                    exclude_page_ids=[]
                ),
                SpaceConfig(
                    space_key="TEAM2",
                    parent_page_id="222",
                    local_path="./team2",
                    exclude_page_ids=["333", "444"]
                )
            ],
            page_limit=50,
            force_pull=True,
            force_push=False,
            temp_dir=".custom-temp"
        )

        ConfigLoader.save(str(config_file), sync_config)

        # Verify by loading
        loaded = ConfigLoader.load(str(config_file))
        assert len(loaded.spaces) == 2
        assert loaded.spaces[0].space_key == "TEAM1"
        assert loaded.spaces[1].space_key == "TEAM2"
        assert loaded.spaces[1].exclude_page_ids == ["333", "444"]
        assert loaded.force_pull is True

    def test_save_creates_parent_directory(self, tmp_path):
        """Save creates parent directories if they don't exist."""
        config_file = tmp_path / "subdir1" / "subdir2" / "config.yaml"

        sync_config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123",
                    local_path="./test"
                )
            ]
        )

        ConfigLoader.save(str(config_file), sync_config)

        assert config_file.exists()
        assert config_file.parent.exists()

    def test_save_overwrites_existing_file(self, tmp_path):
        """Save overwrites existing config file."""
        config_file = tmp_path / "config.yaml"

        # First save
        sync_config1 = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="OLD",
                    parent_page_id="111",
                    local_path="./old"
                )
            ]
        )
        ConfigLoader.save(str(config_file), sync_config1)

        # Second save (overwrite)
        sync_config2 = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="NEW",
                    parent_page_id="999",
                    local_path="./new"
                )
            ]
        )
        ConfigLoader.save(str(config_file), sync_config2)

        # Verify it was overwritten
        loaded = ConfigLoader.load(str(config_file))
        assert len(loaded.spaces) == 1
        assert loaded.spaces[0].space_key == "NEW"

    def test_save_permission_error_raises_filesystem_error(self, tmp_path):
        """Save to read-only directory raises FilesystemError."""
        config_file = tmp_path / "config.yaml"

        # Make directory read-only
        os.chmod(tmp_path, 0o444)

        sync_config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123",
                    local_path="./test"
                )
            ]
        )

        try:
            with pytest.raises(FilesystemError) as exc_info:
                ConfigLoader.save(str(config_file), sync_config)

            assert exc_info.value.file_path == str(config_file)
            assert exc_info.value.operation == "write"
            assert "Permission denied" in str(exc_info.value)
        finally:
            # Restore permissions for cleanup
            os.chmod(tmp_path, 0o755)

    def test_save_directory_creation_error_raises_filesystem_error(self, tmp_path):
        """Save fails when directory creation fails."""
        # Create a file where we want to create a directory
        blocking_file = tmp_path / "blocking_file"
        blocking_file.write_text("blocking")

        # Try to save to a path that requires creating a directory where a file exists
        config_file = blocking_file / "subdir" / "config.yaml"

        sync_config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123",
                    local_path="./test"
                )
            ]
        )

        with pytest.raises(FilesystemError) as exc_info:
            ConfigLoader.save(str(config_file), sync_config)

        assert exc_info.value.operation == "create_directory"

    def test_save_generic_write_error_raises_filesystem_error(self, tmp_path):
        """Save with generic write error raises FilesystemError."""
        # Create a directory where we want to write a file
        config_dir = tmp_path / "config.yaml"
        config_dir.mkdir()

        sync_config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123",
                    local_path="./test"
                )
            ]
        )

        with pytest.raises(FilesystemError) as exc_info:
            ConfigLoader.save(str(config_dir), sync_config)

        assert exc_info.value.file_path == str(config_dir)
        assert exc_info.value.operation == "write"

    def test_save_generates_valid_yaml_format(self, tmp_path):
        """Save generates properly formatted YAML."""
        config_file = tmp_path / "config.yaml"

        sync_config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123",
                    local_path="./test",
                    exclude_page_ids=["456"]
                )
            ],
            page_limit=75,
            force_pull=False,
            force_push=True,
            temp_dir=".temp"
        )

        ConfigLoader.save(str(config_file), sync_config)

        # Manually parse and verify YAML structure
        with open(config_file, 'r') as f:
            content = yaml.safe_load(f)

        assert 'spaces' in content
        assert isinstance(content['spaces'], list)
        assert len(content['spaces']) == 1
        assert content['spaces'][0]['space_key'] == "TEST"
        assert content['page_limit'] == 75
        assert content['force_pull'] is False
        assert content['force_push'] is True
        assert content['temp_dir'] == ".temp"

    def test_save_with_empty_exclude_page_ids(self, tmp_path):
        """Save config with empty exclude_page_ids list."""
        config_file = tmp_path / "config.yaml"

        sync_config = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="TEST",
                    parent_page_id="123",
                    local_path="./test",
                    exclude_page_ids=[]
                )
            ]
        )

        ConfigLoader.save(str(config_file), sync_config)

        loaded = ConfigLoader.load(str(config_file))
        assert loaded.spaces[0].exclude_page_ids == []

    def test_save_round_trip_preserves_data(self, tmp_path):
        """Save and load preserves all configuration data."""
        config_file = tmp_path / "config.yaml"

        original = SyncConfig(
            spaces=[
                SpaceConfig(
                    space_key="SPACE1",
                    parent_page_id="111111",
                    local_path="./space1",
                    exclude_page_ids=["222222", "333333"]
                ),
                SpaceConfig(
                    space_key="SPACE2",
                    parent_page_id="444444",
                    local_path="./space2",
                    exclude_page_ids=[]
                )
            ],
            page_limit=150,
            force_pull=True,
            force_push=False,
            temp_dir=".custom/temp"
        )

        ConfigLoader.save(str(config_file), original)
        loaded = ConfigLoader.load(str(config_file))

        # Verify all fields preserved
        assert len(loaded.spaces) == len(original.spaces)
        assert loaded.spaces[0].space_key == original.spaces[0].space_key
        assert loaded.spaces[0].parent_page_id == original.spaces[0].parent_page_id
        assert loaded.spaces[0].local_path == original.spaces[0].local_path
        assert loaded.spaces[0].exclude_page_ids == original.spaces[0].exclude_page_ids
        assert loaded.spaces[1].space_key == original.spaces[1].space_key
        assert loaded.page_limit == original.page_limit
        assert loaded.force_pull == original.force_pull
        assert loaded.force_push == original.force_push
        assert loaded.temp_dir == original.temp_dir


class TestConfigLoaderConstants:
    """Test cases for ConfigLoader class constants."""

    def test_required_top_level_fields_constant(self):
        """Required top-level fields constant has correct values."""
        expected = {'spaces'}
        assert ConfigLoader.REQUIRED_TOP_LEVEL_FIELDS == expected

    def test_required_space_fields_constant(self):
        """Required space fields constant has correct values."""
        expected = {'space_key', 'parent_page_id', 'local_path'}
        assert ConfigLoader.REQUIRED_SPACE_FIELDS == expected

    def test_defaults_constant(self):
        """Defaults constant has correct values."""
        assert ConfigLoader.DEFAULTS['page_limit'] == 100
        assert ConfigLoader.DEFAULTS['force_pull'] is False
        assert ConfigLoader.DEFAULTS['force_push'] is False
        assert ConfigLoader.DEFAULTS['temp_dir'] == '.confluence-sync/temp'


class TestConfigLoaderParseConfig:
    """Test cases for ConfigLoader._parse_config() method (tested via load())."""

    def test_parse_config_with_extra_top_level_fields_allowed(self, tmp_path):
        """Parse config with extra top-level fields is allowed."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: ./test
extra_field: "This is extra"
another_field: 42
"""
        config_file.write_text(config_content)

        # Should not raise error (extra fields ignored)
        result = ConfigLoader.load(str(config_file))
        assert result.spaces[0].space_key == "TEST"

    def test_parse_config_with_extra_space_fields_allowed(self, tmp_path):
        """Parse config with extra space fields is allowed."""
        config_file = tmp_path / "config.yaml"
        config_content = """
spaces:
  - space_key: TEST
    parent_page_id: "123"
    local_path: ./test
    extra_field: "ignored"
"""
        config_file.write_text(config_content)

        # Should not raise error (extra fields ignored)
        result = ConfigLoader.load(str(config_file))
        assert result.spaces[0].space_key == "TEST"
