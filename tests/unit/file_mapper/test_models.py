"""Unit tests for file_mapper.models module."""

from src.file_mapper.models import PageNode, LocalPage, SpaceConfig, SyncConfig


class TestPageNode:
    """Test cases for PageNode dataclass."""

    def test_page_node_creation(self):
        """PageNode can be created with all required fields."""
        page = PageNode(
            page_id="123456",
            title="Test Page",
            parent_id="789",
            children=[],
            last_modified="2024-01-15T10:30:00Z",
            space_key="TEST"
        )

        assert page.page_id == "123456"
        assert page.title == "Test Page"
        assert page.parent_id == "789"
        assert page.children == []
        assert page.last_modified == "2024-01-15T10:30:00Z"
        assert page.space_key == "TEST"

    def test_page_node_with_children(self):
        """PageNode can have nested child nodes."""
        child1 = PageNode(
            page_id="111",
            title="Child 1",
            parent_id="123",
            children=[],
            last_modified="2024-01-15T10:30:00Z",
            space_key="TEST"
        )
        child2 = PageNode(
            page_id="222",
            title="Child 2",
            parent_id="123",
            children=[],
            last_modified="2024-01-15T10:30:00Z",
            space_key="TEST"
        )
        parent = PageNode(
            page_id="123",
            title="Parent",
            parent_id=None,
            children=[child1, child2],
            last_modified="2024-01-15T10:30:00Z",
            space_key="TEST"
        )

        assert len(parent.children) == 2
        assert parent.children[0].page_id == "111"
        assert parent.children[1].page_id == "222"

    def test_page_node_with_none_parent(self):
        """PageNode can have None for parent_id."""
        page = PageNode(
            page_id="123",
            title="Root Page",
            parent_id=None
        )

        assert page.parent_id is None

    def test_page_node_default_values(self):
        """PageNode uses default values for optional fields."""
        page = PageNode(
            page_id="123",
            title="Test Page",
            parent_id=None
        )

        assert page.children == []
        assert page.last_modified == ""
        assert page.space_key == ""

    def test_page_node_equality(self):
        """Two PageNode instances with same data should be equal."""
        page1 = PageNode(
            page_id="123",
            title="Test Page",
            parent_id=None,
            children=[],
            last_modified="2024-01-15T10:30:00Z",
            space_key="TEST"
        )

        page2 = PageNode(
            page_id="123",
            title="Test Page",
            parent_id=None,
            children=[],
            last_modified="2024-01-15T10:30:00Z",
            space_key="TEST"
        )

        assert page1 == page2

    def test_page_node_inequality(self):
        """Two PageNode instances with different data should not be equal."""
        page1 = PageNode(
            page_id="123",
            title="Page 1",
            parent_id=None
        )

        page2 = PageNode(
            page_id="456",
            title="Page 2",
            parent_id=None
        )

        assert page1 != page2


class TestLocalPage:
    """Test cases for LocalPage dataclass.

    Note: LocalPage now uses simplified model with only:
    - file_path: path to the markdown file
    - page_id: Confluence page ID (None for new files)
    - content: markdown content (without frontmatter)

    Title is derived from H1 heading or filename. Other metadata
    (space_key, last_synced, etc.) tracked globally in state.yaml.
    """

    def test_local_page_creation(self):
        """LocalPage can be created with all required fields."""
        page = LocalPage(
            file_path="/path/to/page.md",
            page_id="123456",
            content="# Test Page\n\nThis is content."
        )

        assert page.file_path == "/path/to/page.md"
        assert page.page_id == "123456"
        assert page.content == "# Test Page\n\nThis is content."

    def test_local_page_with_none_page_id(self):
        """LocalPage can have None for page_id (new local file)."""
        page = LocalPage(
            file_path="/path/to/new-page.md",
            page_id=None,
            content="New content"
        )

        assert page.page_id is None

    def test_local_page_default_content(self):
        """LocalPage uses empty string as default for content."""
        page = LocalPage(
            file_path="/path/to/page.md",
            page_id="123"
        )

        assert page.content == ""

    def test_local_page_equality(self):
        """Two LocalPage instances with same data should be equal."""
        page1 = LocalPage(
            file_path="/path/to/page.md",
            page_id="123",
            content="Content"
        )

        page2 = LocalPage(
            file_path="/path/to/page.md",
            page_id="123",
            content="Content"
        )

        assert page1 == page2

    def test_local_page_inequality(self):
        """Two LocalPage instances with different data should not be equal."""
        page1 = LocalPage(
            file_path="/path/to/page1.md",
            page_id="123"
        )

        page2 = LocalPage(
            file_path="/path/to/page2.md",
            page_id="456"
        )

        assert page1 != page2


class TestSpaceConfig:
    """Test cases for SpaceConfig dataclass."""

    def test_space_config_creation(self):
        """SpaceConfig can be created with all required fields."""
        config = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123456",
            local_path="/path/to/docs",
            exclude_page_ids=["111", "222"]
        )

        assert config.space_key == "TEAM"
        assert config.parent_page_id == "123456"
        assert config.local_path == "/path/to/docs"
        assert config.exclude_page_ids == ["111", "222"]

    def test_space_config_default_exclude_page_ids(self):
        """SpaceConfig uses empty list as default for exclude_page_ids."""
        config = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123456",
            local_path="/path/to/docs"
        )

        assert config.exclude_page_ids == []

    def test_space_config_empty_exclude_page_ids(self):
        """SpaceConfig can have empty list for exclude_page_ids."""
        config = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123456",
            local_path="/path/to/docs",
            exclude_page_ids=[]
        )

        assert config.exclude_page_ids == []

    def test_space_config_equality(self):
        """Two SpaceConfig instances with same data should be equal."""
        config1 = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123456",
            local_path="/path/to/docs",
            exclude_page_ids=["111"]
        )

        config2 = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123456",
            local_path="/path/to/docs",
            exclude_page_ids=["111"]
        )

        assert config1 == config2

    def test_space_config_inequality(self):
        """Two SpaceConfig instances with different data should not be equal."""
        config1 = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123456",
            local_path="/path/to/docs"
        )

        config2 = SpaceConfig(
            space_key="PROD",
            parent_page_id="789012",
            local_path="/path/to/prod"
        )

        assert config1 != config2


class TestSyncConfig:
    """Test cases for SyncConfig dataclass."""

    def test_sync_config_creation(self):
        """SyncConfig can be created with all required fields."""
        space_config = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123456",
            local_path="/path/to/docs"
        )
        config = SyncConfig(
            spaces=[space_config],
            page_limit=200,
            force_pull=True,
            force_push=False,
            temp_dir="/custom/temp"
        )

        assert len(config.spaces) == 1
        assert config.spaces[0].space_key == "TEAM"
        assert config.page_limit == 200
        assert config.force_pull is True
        assert config.force_push is False
        assert config.temp_dir == "/custom/temp"

    def test_sync_config_default_values(self):
        """SyncConfig uses default values for all fields."""
        config = SyncConfig()

        assert config.spaces == []
        assert config.page_limit == 100
        assert config.force_pull is False
        assert config.force_push is False
        assert config.temp_dir == ".confluence-sync/temp"

    def test_sync_config_multiple_spaces(self):
        """SyncConfig can have multiple space configurations."""
        space1 = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123",
            local_path="/path/to/team"
        )
        space2 = SpaceConfig(
            space_key="PROD",
            parent_page_id="456",
            local_path="/path/to/prod"
        )
        config = SyncConfig(spaces=[space1, space2])

        assert len(config.spaces) == 2
        assert config.spaces[0].space_key == "TEAM"
        assert config.spaces[1].space_key == "PROD"

    def test_sync_config_equality(self):
        """Two SyncConfig instances with same data should be equal."""
        space_config = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123",
            local_path="/path/to/docs"
        )
        config1 = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=".confluence-sync/temp"
        )

        config2 = SyncConfig(
            spaces=[space_config],
            page_limit=100,
            force_pull=False,
            force_push=False,
            temp_dir=".confluence-sync/temp"
        )

        assert config1 == config2

    def test_sync_config_inequality(self):
        """Two SyncConfig instances with different data should not be equal."""
        config1 = SyncConfig(page_limit=100)
        config2 = SyncConfig(page_limit=200)

        assert config1 != config2

    def test_sync_config_default_factories_create_separate_instances(self):
        """Each SyncConfig should get its own spaces list instance."""
        config1 = SyncConfig()
        config2 = SyncConfig()

        space_config = SpaceConfig(
            space_key="TEAM",
            parent_page_id="123",
            local_path="/path"
        )
        config1.spaces.append(space_config)

        # Ensure they don't share the same list instance
        assert len(config1.spaces) == 1
        assert len(config2.spaces) == 0
