"""Integration tests for config persistence.

This module tests the ConfigLoader's configuration persistence functionality
against a real filesystem. Tests verify:
- Loading YAML config files from disk
- Saving YAML config files to disk
- Round-trip persistence (save then load, verify data preserved)
- Directory creation for config files
- Error handling for filesystem issues
- Integration with SyncConfig and SpaceConfig models

Requirements:
- Temporary test directories (provided by fixtures)
- No external API calls (filesystem only)
"""

import pytest
import os
from pathlib import Path
from typing import Dict

from src.file_mapper.config_loader import ConfigLoader
from src.file_mapper.models import SpaceConfig, SyncConfig
from src.file_mapper.errors import ConfigError, FilesystemError


@pytest.mark.integration
class TestConfigPersistence:
    """Integration tests for configuration file persistence."""

    @pytest.fixture(scope="function")
    def sample_sync_config(self, temp_test_dir: Path) -> SyncConfig:
        """Create a sample SyncConfig for testing.

        Args:
            temp_test_dir: Temporary test directory fixture

        Returns:
            SyncConfig with test data
        """
        space1 = SpaceConfig(
            space_key="TEST",
            parent_page_id="123456",
            local_path=str(temp_test_dir / "test-space"),
            exclude_page_ids=["exclude1", "exclude2"]
        )

        space2 = SpaceConfig(
            space_key="DEMO",
            parent_page_id="789012",
            local_path=str(temp_test_dir / "demo-space"),
            exclude_page_ids=[]
        )

        return SyncConfig(
            spaces=[space1, space2],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=str(temp_test_dir / ".confluence-sync" / "temp")
        )

    def test_save_config_creates_file(
        self,
        temp_test_dir: Path,
        sample_sync_config: SyncConfig
    ):
        """Test saving config creates a YAML file on disk.

        Verifies:
        - File is created at specified path
        - File contains valid YAML
        - File is readable

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_config: Sample config fixture
        """
        config_path = temp_test_dir / "config.yaml"

        # Save config
        ConfigLoader.save(str(config_path), sample_sync_config)

        # Verify file exists
        assert config_path.exists(), "Config file should be created"
        assert config_path.is_file(), "Config path should be a file"

        # Verify file is readable
        content = config_path.read_text(encoding='utf-8')
        assert len(content) > 0, "Config file should not be empty"
        assert "spaces:" in content, "Config should contain spaces section"

    def test_save_config_creates_parent_directory(
        self,
        temp_test_dir: Path,
        sample_sync_config: SyncConfig
    ):
        """Test saving config creates parent directories if needed.

        Verifies:
        - Parent directories are created automatically
        - Nested directory structure is created
        - Config file is created in correct location

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_config: Sample config fixture
        """
        # Use nested path that doesn't exist
        config_path = temp_test_dir / ".confluence-sync" / "configs" / "config.yaml"
        assert not config_path.parent.exists(), "Parent directory should not exist yet"

        # Save config
        ConfigLoader.save(str(config_path), sample_sync_config)

        # Verify directory structure created
        assert config_path.parent.exists(), "Parent directory should be created"
        assert config_path.exists(), "Config file should be created"

    def test_load_config_from_file(
        self,
        temp_test_dir: Path
    ):
        """Test loading config from YAML file.

        Verifies:
        - Config is loaded from disk
        - All fields are parsed correctly
        - Data types are correct

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        # Create config file manually
        config_path = temp_test_dir / "config.yaml"
        config_content = """spaces:
  - space_key: "TEST"
    parent_page_id: "123456"
    local_path: "./test-space"
    exclude_page_ids: ["exclude1", "exclude2"]
  - space_key: "DEMO"
    parent_page_id: "789012"
    local_path: "./demo-space"
    exclude_page_ids: []
page_limit: 50
force_pull: true
force_push: false
temp_dir: ".confluence-sync/temp"
"""
        config_path.write_text(config_content, encoding='utf-8')

        # Load config
        sync_config = ConfigLoader.load(str(config_path))

        # Verify configuration
        assert len(sync_config.spaces) == 2, "Should have 2 spaces"
        assert sync_config.spaces[0].space_key == "TEST"
        assert sync_config.spaces[0].parent_page_id == "123456"
        assert sync_config.spaces[0].local_path == "./test-space"
        assert sync_config.spaces[0].exclude_page_ids == ["exclude1", "exclude2"]

        assert sync_config.spaces[1].space_key == "DEMO"
        assert sync_config.spaces[1].parent_page_id == "789012"
        assert sync_config.spaces[1].exclude_page_ids == []

        assert sync_config.page_limit == 50
        assert sync_config.force_pull is True
        assert sync_config.force_push is False
        assert sync_config.temp_dir == ".confluence-sync/temp"

    def test_load_config_file_not_found(
        self,
        temp_test_dir: Path
    ):
        """Test loading config from non-existent file.

        Verifies:
        - FilesystemError is raised
        - Error message is descriptive

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        nonexistent_path = temp_test_dir / "does-not-exist.yaml"

        with pytest.raises(FilesystemError) as exc_info:
            ConfigLoader.load(str(nonexistent_path))

        error = exc_info.value
        assert error.file_path == str(nonexistent_path)
        assert error.operation == 'read'
        assert "not found" in str(error).lower()

    def test_load_config_invalid_yaml(
        self,
        temp_test_dir: Path
    ):
        """Test loading config with invalid YAML syntax.

        Verifies:
        - ConfigError is raised
        - Error message mentions YAML syntax

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        config_path = temp_test_dir / "invalid.yaml"
        invalid_yaml = """spaces:
  - space_key: "TEST"
    parent_page_id: "123456"
    local_path: "./test-space"
    [invalid syntax here
"""
        config_path.write_text(invalid_yaml, encoding='utf-8')

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_path))

        error = exc_info.value
        assert "yaml" in str(error).lower()

    def test_load_config_empty_file(
        self,
        temp_test_dir: Path
    ):
        """Test loading config from empty file.

        Verifies:
        - ConfigError is raised
        - Error message is descriptive

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        config_path = temp_test_dir / "empty.yaml"
        config_path.write_text("", encoding='utf-8')

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_path))

        error = exc_info.value
        assert "empty" in str(error).lower()

    def test_round_trip_save_and_load(
        self,
        temp_test_dir: Path,
        sample_sync_config: SyncConfig
    ):
        """Test round-trip: save config then load it back.

        Verifies:
        - Data is preserved after save/load cycle
        - All fields match original values
        - No data loss or corruption

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_config: Sample config fixture
        """
        config_path = temp_test_dir / "config.yaml"

        # Save config
        ConfigLoader.save(str(config_path), sample_sync_config)

        # Load it back
        loaded_config = ConfigLoader.load(str(config_path))

        # Verify all fields match
        assert len(loaded_config.spaces) == len(sample_sync_config.spaces)

        for i, (loaded_space, original_space) in enumerate(
            zip(loaded_config.spaces, sample_sync_config.spaces)
        ):
            assert loaded_space.space_key == original_space.space_key, \
                f"Space {i} key should match"
            assert loaded_space.parent_page_id == original_space.parent_page_id, \
                f"Space {i} parent_page_id should match"
            assert loaded_space.local_path == original_space.local_path, \
                f"Space {i} local_path should match"
            assert loaded_space.exclude_page_ids == original_space.exclude_page_ids, \
                f"Space {i} exclude_page_ids should match"

        assert loaded_config.page_limit == sample_sync_config.page_limit
        assert loaded_config.force_pull == sample_sync_config.force_pull
        assert loaded_config.force_push == sample_sync_config.force_push
        assert loaded_config.temp_dir == sample_sync_config.temp_dir

    def test_save_config_overwrites_existing_file(
        self,
        temp_test_dir: Path,
        sample_sync_config: SyncConfig
    ):
        """Test saving config overwrites existing file.

        Verifies:
        - Existing file is overwritten
        - New content replaces old content
        - No corruption or partial updates

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_config: Sample config fixture
        """
        config_path = temp_test_dir / "config.yaml"

        # Create existing file with different content
        old_content = """spaces:
  - space_key: "OLD"
    parent_page_id: "000000"
    local_path: "./old-path"
page_limit: 10
"""
        config_path.write_text(old_content, encoding='utf-8')

        # Save new config
        ConfigLoader.save(str(config_path), sample_sync_config)

        # Load and verify it has new content
        loaded_config = ConfigLoader.load(str(config_path))
        assert loaded_config.spaces[0].space_key == "TEST"  # New value
        assert loaded_config.spaces[0].space_key != "OLD"  # Old value replaced

    def test_load_config_with_defaults(
        self,
        temp_test_dir: Path
    ):
        """Test loading config with optional fields omitted.

        Verifies:
        - Default values are applied
        - Config is still valid
        - Required fields are present

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        config_path = temp_test_dir / "minimal.yaml"
        minimal_config = """spaces:
  - space_key: "TEST"
    parent_page_id: "123456"
    local_path: "./test-space"
"""
        config_path.write_text(minimal_config, encoding='utf-8')

        # Load config
        sync_config = ConfigLoader.load(str(config_path))

        # Verify defaults are applied
        assert sync_config.page_limit == 100, "Should use default page_limit"
        assert sync_config.force_pull is False, "Should use default force_pull"
        assert sync_config.force_push is False, "Should use default force_push"
        assert sync_config.temp_dir == ".confluence-sync/temp", \
            "Should use default temp_dir"

    def test_load_config_with_empty_exclude_list(
        self,
        temp_test_dir: Path
    ):
        """Test loading config with empty exclude_page_ids list.

        Verifies:
        - Empty list is parsed correctly
        - No errors occur
        - Space is still valid

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        config_path = temp_test_dir / "config.yaml"
        config_content = """spaces:
  - space_key: "TEST"
    parent_page_id: "123456"
    local_path: "./test-space"
    exclude_page_ids: []
"""
        config_path.write_text(config_content, encoding='utf-8')

        sync_config = ConfigLoader.load(str(config_path))
        assert sync_config.spaces[0].exclude_page_ids == []

    def test_load_config_without_exclude_list(
        self,
        temp_test_dir: Path
    ):
        """Test loading config without exclude_page_ids field.

        Verifies:
        - Missing exclude_page_ids defaults to empty list
        - Config is still valid

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        config_path = temp_test_dir / "config.yaml"
        config_content = """spaces:
  - space_key: "TEST"
    parent_page_id: "123456"
    local_path: "./test-space"
"""
        config_path.write_text(config_content, encoding='utf-8')

        sync_config = ConfigLoader.load(str(config_path))
        assert sync_config.spaces[0].exclude_page_ids == []

    def test_save_config_with_special_characters(
        self,
        temp_test_dir: Path
    ):
        """Test saving config with special characters in values.

        Verifies:
        - Special characters are properly escaped
        - Unicode characters are preserved
        - Config can be loaded back correctly

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        space = SpaceConfig(
            space_key="TEST",
            parent_page_id="123456",
            local_path="./test-space with spaces & special: chars",
            exclude_page_ids=[]
        )

        config = SyncConfig(
            spaces=[space],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=".confluence-sync/temp"
        )

        config_path = temp_test_dir / "special.yaml"
        ConfigLoader.save(str(config_path), config)

        # Load back and verify
        loaded_config = ConfigLoader.load(str(config_path))
        assert loaded_config.spaces[0].local_path == \
            "./test-space with spaces & special: chars"

    def test_load_config_validates_required_fields(
        self,
        temp_test_dir: Path
    ):
        """Test loading config with missing required fields.

        Verifies:
        - ConfigError is raised
        - Error message identifies missing field
        - Validation happens during load

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        config_path = temp_test_dir / "missing-field.yaml"
        invalid_config = """spaces:
  - space_key: "TEST"
    local_path: "./test-space"
"""  # Missing parent_page_id
        config_path.write_text(invalid_config, encoding='utf-8')

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_path))

        error = exc_info.value
        assert "parent_page_id" in str(error).lower()

    def test_load_config_validates_mutually_exclusive_flags(
        self,
        temp_test_dir: Path
    ):
        """Test loading config with conflicting force flags.

        Verifies:
        - ConfigError is raised
        - Error message mentions mutual exclusivity
        - Both force_pull and force_push cannot be true

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        config_path = temp_test_dir / "conflict.yaml"
        conflicting_config = """spaces:
  - space_key: "TEST"
    parent_page_id: "123456"
    local_path: "./test-space"
force_pull: true
force_push: true
"""
        config_path.write_text(conflicting_config, encoding='utf-8')

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_path))

        error = exc_info.value
        assert "mutually exclusive" in str(error).lower()

    def test_load_config_validates_page_limit(
        self,
        temp_test_dir: Path
    ):
        """Test loading config with invalid page_limit.

        Verifies:
        - ConfigError is raised for page_limit < 1
        - Error message mentions page_limit

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        config_path = temp_test_dir / "invalid-limit.yaml"
        invalid_config = """spaces:
  - space_key: "TEST"
    parent_page_id: "123456"
    local_path: "./test-space"
page_limit: 0
"""
        config_path.write_text(invalid_config, encoding='utf-8')

        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load(str(config_path))

        error = exc_info.value
        assert "page_limit" in str(error).lower()

    def test_multiple_configs_in_same_directory(
        self,
        temp_test_dir: Path,
        sample_sync_config: SyncConfig
    ):
        """Test saving and loading multiple config files in same directory.

        Verifies:
        - Multiple configs can coexist
        - Configs don't interfere with each other
        - Each config maintains its own data

        Args:
            temp_test_dir: Temporary test directory fixture
            sample_sync_config: Sample config fixture
        """
        config_dir = temp_test_dir / "configs"

        # Create first config
        config1_path = config_dir / "config1.yaml"
        space1 = SpaceConfig(
            space_key="SPACE1",
            parent_page_id="111111",
            local_path="./space1"
        )
        config1 = SyncConfig(
            spaces=[space1],
            page_limit=50,
            force_pull=True,
            force_push=False,
            temp_dir=".temp1"
        )
        ConfigLoader.save(str(config1_path), config1)

        # Create second config
        config2_path = config_dir / "config2.yaml"
        space2 = SpaceConfig(
            space_key="SPACE2",
            parent_page_id="222222",
            local_path="./space2"
        )
        config2 = SyncConfig(
            spaces=[space2],
            page_limit=75,
            force_pull=False,
            force_push=True,
            temp_dir=".temp2"
        )
        ConfigLoader.save(str(config2_path), config2)

        # Load and verify both configs
        loaded1 = ConfigLoader.load(str(config1_path))
        loaded2 = ConfigLoader.load(str(config2_path))

        assert loaded1.spaces[0].space_key == "SPACE1"
        assert loaded1.page_limit == 50
        assert loaded1.force_pull is True

        assert loaded2.spaces[0].space_key == "SPACE2"
        assert loaded2.page_limit == 75
        assert loaded2.force_push is True

    def test_config_file_encoding_utf8(
        self,
        temp_test_dir: Path
    ):
        """Test config files are saved and loaded with UTF-8 encoding.

        Verifies:
        - UTF-8 characters are preserved
        - No encoding errors occur
        - International characters work correctly

        Args:
            temp_test_dir: Temporary test directory fixture
        """
        space = SpaceConfig(
            space_key="TEST",
            parent_page_id="123456",
            local_path="./espace-français"  # French characters
        )

        config = SyncConfig(
            spaces=[space],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=".confluence-sync/temp"
        )

        config_path = temp_test_dir / "utf8.yaml"
        ConfigLoader.save(str(config_path), config)

        # Load back and verify UTF-8 is preserved
        loaded_config = ConfigLoader.load(str(config_path))
        assert loaded_config.spaces[0].local_path == "./espace-français"
