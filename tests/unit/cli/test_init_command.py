"""Unit tests for cli.init_command.InitCommand module."""

import os
import pytest
from unittest.mock import Mock, patch

from src.cli.init_command import InitCommand
from src.cli.errors import InitError


class TestInitCommandParseConfluenceUrl:
    """Test cases for InitCommand._parse_confluence_url() method."""

    def test_parse_valid_url_with_wiki_path(self):
        """Parse valid Confluence URL with /wiki path."""
        init = InitCommand()
        base_url, space_key, page_id = init._parse_confluence_url(
            "https://example.atlassian.net/wiki/spaces/TEAM/pages/123456"
        )

        assert base_url == "https://example.atlassian.net/wiki"
        assert space_key == "TEAM"
        assert page_id == "123456"

    def test_parse_valid_url_with_page_title(self):
        """Parse valid Confluence URL with page title at end."""
        init = InitCommand()
        base_url, space_key, page_id = init._parse_confluence_url(
            "https://example.atlassian.net/wiki/spaces/TEAM/pages/123456/My-Page-Title"
        )

        assert base_url == "https://example.atlassian.net/wiki"
        assert space_key == "TEAM"
        assert page_id == "123456"

    def test_parse_valid_url_without_wiki_path(self):
        """Parse valid Confluence URL without /wiki path (adds /wiki)."""
        init = InitCommand()
        base_url, space_key, page_id = init._parse_confluence_url(
            "https://confluence.example.com/spaces/MYSPACE/pages/789012"
        )

        assert base_url == "https://confluence.example.com/wiki"
        assert space_key == "MYSPACE"
        assert page_id == "789012"

    def test_parse_valid_url_with_http(self):
        """Parse valid Confluence URL with http (not https)."""
        init = InitCommand()
        base_url, space_key, page_id = init._parse_confluence_url(
            "http://localhost:8090/wiki/spaces/TEST/pages/456789"
        )

        assert base_url == "http://localhost:8090/wiki"
        assert space_key == "TEST"
        assert page_id == "456789"

    def test_parse_invalid_url_no_spaces_path(self):
        """Raise InitError when URL doesn't contain /spaces/."""
        init = InitCommand()

        with pytest.raises(InitError) as exc_info:
            init._parse_confluence_url("https://example.atlassian.net/wiki/pages/123456")

        assert "Invalid Confluence URL format" in str(exc_info.value)
        assert "Supported formats" in str(exc_info.value)

    def test_parse_space_only_url_returns_none_page_id(self):
        """Parse space-only URL returns None for page_id."""
        init = InitCommand()

        base_url, space_key, page_id = init._parse_confluence_url(
            "https://example.atlassian.net/wiki/spaces/TEAM"
        )

        assert base_url == "https://example.atlassian.net/wiki"
        assert space_key == "TEAM"
        assert page_id is None

    def test_parse_space_overview_url_returns_none_page_id(self):
        """Parse space overview URL returns None for page_id."""
        init = InitCommand()

        base_url, space_key, page_id = init._parse_confluence_url(
            "https://example.atlassian.net/wiki/spaces/TEAM/overview"
        )

        assert base_url == "https://example.atlassian.net/wiki"
        assert space_key == "TEAM"
        assert page_id is None

    def test_parse_invalid_url_non_numeric_page_id(self):
        """Raise InitError when page ID is not numeric."""
        init = InitCommand()

        with pytest.raises(InitError) as exc_info:
            init._parse_confluence_url(
                "https://example.atlassian.net/wiki/spaces/TEAM/pages/abc123"
            )

        assert "Invalid Confluence URL format" in str(exc_info.value)

    def test_parse_invalid_url_empty_string(self):
        """Raise InitError when URL is empty."""
        init = InitCommand()

        with pytest.raises(InitError) as exc_info:
            init._parse_confluence_url("")

        # M4: Now validates URLs with urlparse() first
        assert "empty" in str(exc_info.value).lower()

    def test_parse_invalid_url_malformed(self):
        """Raise InitError when URL is malformed."""
        init = InitCommand()

        with pytest.raises(InitError) as exc_info:
            init._parse_confluence_url("not-a-url")

        # M4: Now validates URLs with urlparse() first (checks scheme)
        error_msg = str(exc_info.value).lower()
        assert "scheme" in error_msg or "url" in error_msg


class TestInitCommandValidatePageExists:
    """Test cases for InitCommand._validate_page_exists() method."""

    def test_validate_page_exists_success(self):
        """Successfully validate page exists and return title."""
        mock_api = Mock()
        mock_api.get_page_by_id.return_value = {
            'id': '123456',
            'title': 'My Page'
        }

        init = InitCommand(api_wrapper=mock_api)
        title = init._validate_page_exists("123456", "TEAM")

        assert title == "My Page"
        mock_api.get_page_by_id.assert_called_once_with("123456")

    def test_validate_page_exists_not_found(self):
        """Raise InitError when page not found."""
        mock_api = Mock()
        mock_api.get_page_by_id.return_value = None

        init = InitCommand(api_wrapper=mock_api)

        with pytest.raises(InitError) as exc_info:
            init._validate_page_exists("999999", "TEAM")

        assert "Page not found" in str(exc_info.value)
        assert "999999" in str(exc_info.value)
        assert "TEAM" in str(exc_info.value)

    def test_validate_page_exists_api_error(self):
        """Raise InitError when API call fails."""
        mock_api = Mock()
        mock_api.get_page_by_id.side_effect = Exception("API error")

        init = InitCommand(api_wrapper=mock_api)

        with pytest.raises(InitError) as exc_info:
            init._validate_page_exists("123456", "TEAM")

        assert "Failed to validate page" in str(exc_info.value)
        assert "123456" in str(exc_info.value)

    def test_validate_page_exists_api_wrapper_initialization(self):
        """Initialize API wrapper when not provided."""
        init = InitCommand()

        with patch('src.cli.init_command.Authenticator') as mock_auth_cls:
            with patch('src.cli.init_command.APIWrapper') as mock_api_cls:
                mock_auth = Mock()
                mock_auth_cls.return_value = mock_auth

                mock_api = Mock()
                mock_api.get_page_by_id.return_value = {'id': '123456', 'title': 'Test'}
                mock_api_cls.return_value = mock_api

                title = init._validate_page_exists("123456", "TEAM")

                assert title == "Test"
                mock_auth_cls.assert_called_once()
                mock_api_cls.assert_called_once_with(mock_auth)

    def test_validate_page_exists_api_initialization_error(self):
        """Raise InitError when API wrapper initialization fails."""
        init = InitCommand()

        with patch('src.cli.init_command.Authenticator') as mock_auth_cls:
            mock_auth_cls.side_effect = Exception("Missing credentials")

            with pytest.raises(InitError) as exc_info:
                init._validate_page_exists("123456", "TEAM")

            assert "Failed to initialize Confluence API client" in str(exc_info.value)
            assert "CONFLUENCE_URL" in str(exc_info.value)

    def test_validate_page_exists_returns_unknown_when_no_title(self):
        """Return 'Unknown' when page data has no title."""
        mock_api = Mock()
        mock_api.get_page_by_id.return_value = {'id': '123456'}

        init = InitCommand(api_wrapper=mock_api)
        title = init._validate_page_exists("123456", "TEAM")

        assert title == "Unknown"


class TestInitCommandCheckConfigExists:
    """Test cases for InitCommand._check_config_exists() method."""

    def test_check_config_exists_when_no_file(self, tmp_path):
        """No error when config file doesn't exist."""
        config_path = str(tmp_path / "config.yaml")
        init = InitCommand(config_path=config_path)

        # Should not raise
        init._check_config_exists()

    def test_check_config_exists_when_file_exists(self, tmp_path):
        """Raise InitError when config file exists."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("existing config")

        init = InitCommand(config_path=str(config_path))

        with pytest.raises(InitError) as exc_info:
            init._check_config_exists()

        assert "already exists" in str(exc_info.value)
        assert str(config_path) in str(exc_info.value)
        assert "delete it first" in str(exc_info.value)


class TestInitCommandCreateDirectories:
    """Test cases for InitCommand._create_directories() method."""

    def test_create_directories_success(self, tmp_path):
        """Successfully create config and local directories."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")
        local_path = str(tmp_path / "docs")

        init = InitCommand(config_path=config_path)
        init._create_directories(local_path)

        assert os.path.exists(tmp_path / ".confluence-sync")
        assert os.path.exists(tmp_path / "docs")

    def test_create_directories_already_exist(self, tmp_path):
        """No error when directories already exist."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")
        local_path = str(tmp_path / "docs")

        # Pre-create directories
        os.makedirs(tmp_path / ".confluence-sync")
        os.makedirs(tmp_path / "docs")

        init = InitCommand(config_path=config_path)

        # Should not raise
        init._create_directories(local_path)

    def test_create_directories_config_dir_error(self, tmp_path):
        """Raise InitError when config directory creation fails."""
        # Create a file where directory should be
        blocking_file = tmp_path / ".confluence-sync"
        blocking_file.write_text("blocking")

        config_path = str(blocking_file / "config.yaml")
        local_path = str(tmp_path / "docs")

        init = InitCommand(config_path=config_path)

        with pytest.raises(InitError) as exc_info:
            init._create_directories(local_path)

        assert "Failed to create config directory" in str(exc_info.value)

    def test_create_directories_local_path_error(self, tmp_path):
        """Raise InitError when local directory creation fails."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")

        # Create a file where directory should be
        blocking_file = tmp_path / "docs"
        blocking_file.write_text("blocking")
        local_path = str(blocking_file)

        init = InitCommand(config_path=config_path)

        with pytest.raises(InitError) as exc_info:
            init._create_directories(local_path)

        assert "Failed to create local directory" in str(exc_info.value)

    def test_create_directories_normalizes_path(self, tmp_path):
        """Normalize local path (remove trailing slash)."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")
        local_path = str(tmp_path / "docs/")  # Trailing slash

        init = InitCommand(config_path=config_path)
        init._create_directories(local_path)

        assert os.path.exists(tmp_path / "docs")


class TestInitCommandRun:
    """Test cases for InitCommand.run() method."""

    def test_run_success_creates_config(self, tmp_path):
        """Successfully run init command and create config."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")
        local_path = str(tmp_path / "docs")

        mock_api = Mock()
        mock_api.get_page_by_id.return_value = {
            'id': '123456',
            'title': 'My Page'
        }

        init = InitCommand(api_wrapper=mock_api, config_path=config_path)

        # Run init with URL-based format
        init.run(
            local_path=local_path,
            confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456",
            exclude_parent=False
        )

        # Verify directories created
        assert os.path.exists(tmp_path / ".confluence-sync")
        assert os.path.exists(tmp_path / "docs")

        # Verify config file created
        assert os.path.exists(config_path)

        # Verify API was called
        mock_api.get_page_by_id.assert_called_once_with("123456")

    def test_run_fails_when_config_exists(self, tmp_path):
        """Fail init when config already exists."""
        config_path = tmp_path / ".confluence-sync" / "config.yaml"
        os.makedirs(config_path.parent)
        config_path.write_text("existing config")

        mock_api = Mock()
        init = InitCommand(api_wrapper=mock_api, config_path=str(config_path))

        with pytest.raises(InitError) as exc_info:
            init.run(
                local_path=str(tmp_path / "docs"),
                confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456"
            )

        assert "already exists" in str(exc_info.value)

        # API should not be called when config exists
        mock_api.get_page_by_id.assert_not_called()

    def test_run_fails_on_invalid_url(self, tmp_path):
        """Fail init when Confluence URL format is invalid."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")

        mock_api = Mock()
        init = InitCommand(api_wrapper=mock_api, config_path=config_path)

        with pytest.raises(InitError) as exc_info:
            init.run(
                local_path=str(tmp_path / "docs"),
                confluence_url="https://invalid.url/not-confluence"
            )

        assert "Invalid Confluence URL format" in str(exc_info.value)

    def test_run_fails_when_page_not_found(self, tmp_path):
        """Fail init when page doesn't exist in Confluence."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")

        mock_api = Mock()
        mock_api.get_page_by_id.return_value = None

        init = InitCommand(api_wrapper=mock_api, config_path=config_path)

        with pytest.raises(InitError) as exc_info:
            init.run(
                local_path=str(tmp_path / "docs"),
                confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/999999"
            )

        assert "Page not found" in str(exc_info.value)

    def test_run_workflow_order(self, tmp_path):
        """Verify run() executes steps in correct order."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")
        local_path = str(tmp_path / "docs")

        mock_api = Mock()
        mock_api.get_page_by_id.return_value = {'id': '123456', 'title': 'Test'}

        init = InitCommand(api_wrapper=mock_api, config_path=config_path)

        # Track method calls
        call_order = []

        original_check = init._check_config_exists
        original_parse = init._parse_confluence_url
        original_validate = init._validate_page_exists
        original_create = init._create_directories

        def track_check():
            call_order.append('check')
            return original_check()

        def track_parse(url):
            call_order.append('parse')
            return original_parse(url)

        def track_validate(page_id, space_key):
            call_order.append('validate')
            return original_validate(page_id, space_key)

        def track_create(local_path):
            call_order.append('create')
            return original_create(local_path)

        init._check_config_exists = track_check
        init._parse_confluence_url = track_parse
        init._validate_page_exists = track_validate
        init._create_directories = track_create

        init.run(
            local_path=local_path,
            confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456"
        )

        # Verify order: check, parse, validate, create
        assert call_order == ['check', 'parse', 'validate', 'create']

    def test_run_saves_correct_config_structure(self, tmp_path):
        """Verify config file has correct structure after init."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")
        local_path = str(tmp_path / "docs")

        mock_api = Mock()
        mock_api.get_page_by_id.return_value = {'id': '789012', 'title': 'Root Page'}

        init = InitCommand(api_wrapper=mock_api, config_path=config_path)
        init.run(
            local_path=local_path,
            confluence_url="https://mycompany.atlassian.net/wiki/spaces/MYSPACE/pages/789012/Root-Page"
        )

        # Load and verify config
        from src.file_mapper.config_loader import ConfigLoader
        config = ConfigLoader.load(config_path)

        assert len(config.spaces) == 1
        assert config.spaces[0].space_key == "MYSPACE"
        assert config.spaces[0].parent_page_id == "789012"
        assert config.spaces[0].local_path == local_path
        assert config.spaces[0].exclude_page_ids == []
        assert config.spaces[0].exclude_parent is False
        assert config.spaces[0].confluence_base_url == "https://mycompany.atlassian.net/wiki"
        assert config.page_limit == 100
        assert config.force_pull is False
        assert config.force_push is False
        assert config.temp_dir == ".confluence-sync/temp"

    def test_run_saves_exclude_parent_when_true(self, tmp_path):
        """Verify exclude_parent is saved correctly when True."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")
        local_path = str(tmp_path / "docs")

        mock_api = Mock()
        mock_api.get_page_by_id.return_value = {'id': '123456', 'title': 'Parent'}

        init = InitCommand(api_wrapper=mock_api, config_path=config_path)
        init.run(
            local_path=local_path,
            confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456",
            exclude_parent=True
        )

        # Load and verify config
        from src.file_mapper.config_loader import ConfigLoader
        config = ConfigLoader.load(config_path)

        assert config.spaces[0].exclude_parent is True

    def test_run_fails_gracefully_on_save_error(self, tmp_path):
        """Raise InitError when config save fails."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")
        local_path = str(tmp_path / "docs")

        mock_api = Mock()
        mock_api.get_page_by_id.return_value = {'id': '123456', 'title': 'Test'}

        init = InitCommand(api_wrapper=mock_api, config_path=config_path)

        # Mock ConfigLoader.save to fail
        with patch('src.cli.init_command.ConfigLoader.save') as mock_save:
            mock_save.side_effect = Exception("Write error")

            with pytest.raises(InitError) as exc_info:
                init.run(
                    local_path=local_path,
                    confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456"
                )

            assert "Failed to save configuration" in str(exc_info.value)

    def test_run_normalizes_local_path(self, tmp_path):
        """Normalize local path with trailing slash."""
        config_path = str(tmp_path / ".confluence-sync" / "config.yaml")
        local_path = str(tmp_path / "docs/")  # Trailing slash

        mock_api = Mock()
        mock_api.get_page_by_id.return_value = {'id': '123456', 'title': 'Test'}

        init = InitCommand(api_wrapper=mock_api, config_path=config_path)
        init.run(
            local_path=local_path,
            confluence_url="https://example.atlassian.net/wiki/spaces/TEAM/pages/123456"
        )

        # Load and verify config - path should be normalized
        from src.file_mapper.config_loader import ConfigLoader
        config = ConfigLoader.load(config_path)

        # Path should not end with slash
        assert not config.spaces[0].local_path.endswith('/')


class TestInitCommandGetApiWrapper:
    """Test cases for InitCommand._get_api_wrapper() method."""

    def test_get_api_wrapper_returns_existing(self):
        """Return existing API wrapper if already set."""
        mock_api = Mock()
        init = InitCommand(api_wrapper=mock_api)

        result = init._get_api_wrapper()

        assert result is mock_api

    def test_get_api_wrapper_creates_new(self):
        """Create new API wrapper when not set."""
        init = InitCommand()

        with patch('src.cli.init_command.Authenticator') as mock_auth_cls:
            with patch('src.cli.init_command.APIWrapper') as mock_api_cls:
                mock_auth = Mock()
                mock_auth_cls.return_value = mock_auth

                mock_api = Mock()
                mock_api_cls.return_value = mock_api

                result = init._get_api_wrapper()

                assert result is mock_api
                mock_auth_cls.assert_called_once()
                mock_api_cls.assert_called_once_with(mock_auth)

    def test_get_api_wrapper_caches_created_instance(self):
        """Cache created API wrapper for reuse."""
        init = InitCommand()

        with patch('src.cli.init_command.Authenticator') as mock_auth_cls:
            with patch('src.cli.init_command.APIWrapper') as mock_api_cls:
                mock_auth = Mock()
                mock_auth_cls.return_value = mock_auth

                mock_api = Mock()
                mock_api_cls.return_value = mock_api

                result1 = init._get_api_wrapper()
                result2 = init._get_api_wrapper()

                # Should be same instance
                assert result1 is result2

                # Should only create once
                mock_auth_cls.assert_called_once()
                mock_api_cls.assert_called_once()

    def test_get_api_wrapper_error_with_helpful_message(self):
        """Provide helpful error message when API setup fails."""
        init = InitCommand()

        with patch('src.cli.init_command.Authenticator') as mock_auth_cls:
            mock_auth_cls.side_effect = Exception("Auth failed")

            with pytest.raises(InitError) as exc_info:
                init._get_api_wrapper()

            assert "Failed to initialize Confluence API client" in str(exc_info.value)
            assert "CONFLUENCE_URL" in str(exc_info.value)
            assert "CONFLUENCE_USER" in str(exc_info.value)
            assert "CONFLUENCE_API_TOKEN" in str(exc_info.value)


class TestInitCommandDefaultConfigPath:
    """Test cases for default config path behavior."""

    def test_default_config_path_used(self):
        """Use default config path when not specified."""
        init = InitCommand()

        assert init.config_path == ".confluence-sync/config.yaml"

    def test_custom_config_path_used(self):
        """Use custom config path when specified."""
        init = InitCommand(config_path="/custom/path/config.yaml")

        assert init.config_path == "/custom/path/config.yaml"


class TestInitCommandUrlPattern:
    """Test cases for URL regex patterns."""

    def test_pattern_matches_atlassian_cloud_url(self):
        """Match standard Atlassian Cloud URL with page ID."""
        init = InitCommand()
        match = init.URL_WITH_PAGE_ID.match(
            "https://company.atlassian.net/wiki/spaces/TEAM/pages/123456789"
        )

        assert match is not None
        assert match.group(1) == "https://company.atlassian.net"
        assert match.group(2) == "/wiki"
        assert match.group(3) == "TEAM"
        assert match.group(4) == "123456789"

    def test_pattern_matches_url_with_title(self):
        """Match URL with page title slug."""
        init = InitCommand()
        match = init.URL_WITH_PAGE_ID.match(
            "https://company.atlassian.net/wiki/spaces/TEAM/pages/123456/My-Page-Title"
        )

        assert match is not None
        assert match.group(4) == "123456"

    def test_pattern_matches_url_with_complex_title(self):
        """Match URL with complex page title including multiple segments."""
        init = InitCommand()
        match = init.URL_WITH_PAGE_ID.match(
            "https://company.atlassian.net/wiki/spaces/TEAM/pages/123456/Page/With/Slashes"
        )

        assert match is not None
        assert match.group(4) == "123456"

    def test_pattern_does_not_match_invalid_page_id(self):
        """Don't match URL with non-numeric page ID."""
        init = InitCommand()
        match = init.URL_WITH_PAGE_ID.match(
            "https://company.atlassian.net/wiki/spaces/TEAM/pages/abc123"
        )

        assert match is None

    def test_pattern_matches_self_hosted_url(self):
        """Match self-hosted Confluence URL without /wiki."""
        init = InitCommand()
        match = init.URL_WITH_PAGE_ID.match(
            "https://confluence.company.com/spaces/TEAM/pages/123456"
        )

        assert match is not None
        assert match.group(1) == "https://confluence.company.com"
        assert match.group(2) is None  # No /wiki
        assert match.group(3) == "TEAM"
        assert match.group(4) == "123456"

    def test_space_only_pattern_matches_space_url(self):
        """Match space-only URL."""
        init = InitCommand()
        match = init.URL_SPACE_ONLY.match(
            "https://company.atlassian.net/wiki/spaces/TEAM"
        )

        assert match is not None
        assert match.group(1) == "https://company.atlassian.net"
        assert match.group(2) == "/wiki"
        assert match.group(3) == "TEAM"

    def test_space_only_pattern_matches_overview_url(self):
        """Match space overview URL."""
        init = InitCommand()
        match = init.URL_SPACE_ONLY.match(
            "https://company.atlassian.net/wiki/spaces/TEAM/overview"
        )

        assert match is not None
        assert match.group(3) == "TEAM"
