"""Unit tests for file_mapper.filesafe_converter module."""

import pytest
from src.file_mapper.filesafe_converter import FilesafeConverter


class TestTitleToFilename:
    """Test cases for FilesafeConverter.title_to_filename method."""

    def test_basic_space_conversion(self):
        """Spaces should be converted to hyphens."""
        result = FilesafeConverter.title_to_filename("Customer Feedback")
        assert result == "Customer-Feedback.md"

    def test_case_preservation(self):
        """Original case should be preserved exactly."""
        result = FilesafeConverter.title_to_filename("APIReference MixedCASE Test")
        assert result == "APIReference-MixedCASE-Test.md"

    def test_colon_with_space_conversion(self):
        """Colon followed by space should become double hyphen."""
        result = FilesafeConverter.title_to_filename("API Reference: Getting Started")
        assert result == "API-Reference--Getting-Started.md"

    def test_colon_without_space_conversion(self):
        """Colon without space should become double hyphen."""
        result = FilesafeConverter.title_to_filename("Time:10:30:00")
        assert result == "Time--10--30--00.md"

    def test_mixed_colons(self):
        """Mix of colons with and without spaces."""
        result = FilesafeConverter.title_to_filename("Section: Part:2")
        assert result == "Section--Part--2.md"

    def test_ampersand_conversion(self):
        """Ampersand should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename("Q&A Session")
        assert result == "Q-A-Session.md"

    def test_forward_slash_conversion(self):
        """Forward slash should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename("Client/Server Architecture")
        assert result == "Client-Server-Architecture.md"

    def test_backslash_conversion(self):
        """Backslash should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename("Path\\To\\File")
        assert result == "Path-To-File.md"

    def test_question_mark_conversion(self):
        """Question mark should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename("What is REST?")
        assert result == "What-is-REST.md"

    def test_percent_conversion(self):
        """Percent sign should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename("100% Complete")
        # % becomes -, space becomes -, so we get 100--, which stays as --
        assert result == "100--Complete.md"

    def test_asterisk_conversion(self):
        """Asterisk should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename("Important*Notice")
        assert result == "Important-Notice.md"

    def test_pipe_conversion(self):
        """Pipe character should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename("Option A|Option B")
        assert result == "Option-A-Option-B.md"

    def test_double_quote_conversion(self):
        """Double quote should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename('The "Best" Practices')
        # "Best" becomes -Best-, so we get The--Best--Practices
        assert result == "The--Best--Practices.md"

    def test_less_than_conversion(self):
        """Less than symbol should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename("Value<100")
        assert result == "Value-100.md"

    def test_greater_than_conversion(self):
        """Greater than symbol should be converted to hyphen."""
        result = FilesafeConverter.title_to_filename("Score>80")
        assert result == "Score-80.md"

    def test_all_special_characters(self):
        """All special characters in one title."""
        result = FilesafeConverter.title_to_filename("Test/\\?%*|\"<>&:")
        assert result == "Test.md"

    def test_leading_spaces_removed(self):
        """Leading spaces should be trimmed."""
        result = FilesafeConverter.title_to_filename("   Leading Spaces")
        assert result == "Leading-Spaces.md"

    def test_trailing_spaces_removed(self):
        """Trailing spaces should be trimmed."""
        result = FilesafeConverter.title_to_filename("Trailing Spaces   ")
        assert result == "Trailing-Spaces.md"

    def test_leading_and_trailing_spaces(self):
        """Both leading and trailing spaces should be trimmed."""
        result = FilesafeConverter.title_to_filename("   Both Sides   ")
        assert result == "Both-Sides.md"

    def test_multiple_consecutive_spaces(self):
        """Multiple consecutive spaces create multiple hyphens that collapse."""
        result = FilesafeConverter.title_to_filename("Too     Many     Spaces")
        # Each space becomes -, then 3+ consecutive hyphens collapse to --
        assert result == "Too--Many--Spaces.md"

    def test_three_consecutive_hyphens_collapse(self):
        """Three or more consecutive hyphens should collapse to double hyphen."""
        result = FilesafeConverter.title_to_filename("A: : :B")
        assert result == "A--B.md"

    def test_multiple_colons_with_spaces(self):
        """Multiple colons with spaces should be handled correctly."""
        result = FilesafeConverter.title_to_filename("Part: : Section")
        assert result == "Part--Section.md"

    def test_mixed_special_characters_and_spaces(self):
        """Mix of special characters and spaces."""
        result = FilesafeConverter.title_to_filename("API: Users & Roles / Permissions")
        # ": " becomes --, " & " becomes ---, " / " becomes ---
        # 3+ hyphens collapse to --
        assert result == "API--Users--Roles--Permissions.md"

    def test_empty_string(self):
        """Empty string should return .md only."""
        result = FilesafeConverter.title_to_filename("")
        assert result == ".md"

    def test_only_spaces(self):
        """Title with only spaces should return .md only."""
        result = FilesafeConverter.title_to_filename("    ")
        assert result == ".md"

    def test_only_special_characters(self):
        """Title with only special characters."""
        result = FilesafeConverter.title_to_filename("///***")
        assert result == ".md"

    def test_single_word(self):
        """Single word should get .md extension."""
        result = FilesafeConverter.title_to_filename("Introduction")
        assert result == "Introduction.md"

    def test_numbers_preserved(self):
        """Numbers should be preserved."""
        result = FilesafeConverter.title_to_filename("Version 2.0.3")
        assert result == "Version-2.0.3.md"

    def test_dots_preserved(self):
        """Dots should be preserved."""
        result = FilesafeConverter.title_to_filename("file.name.test")
        assert result == "file.name.test.md"

    def test_underscores_preserved(self):
        """Underscores should be preserved."""
        result = FilesafeConverter.title_to_filename("test_case_example")
        assert result == "test_case_example.md"

    def test_hyphens_preserved(self):
        """Existing hyphens should be preserved."""
        result = FilesafeConverter.title_to_filename("pre-existing-hyphens")
        assert result == "pre-existing-hyphens.md"

    def test_unicode_characters_preserved(self):
        """Unicode characters should be preserved."""
        result = FilesafeConverter.title_to_filename("Café Münchën")
        assert result == "Café-Münchën.md"

    def test_parentheses_preserved(self):
        """Parentheses should be preserved."""
        result = FilesafeConverter.title_to_filename("Test (Example)")
        assert result == "Test-(Example).md"

    def test_brackets_preserved(self):
        """Square brackets should be preserved."""
        result = FilesafeConverter.title_to_filename("Test [Draft]")
        assert result == "Test-[Draft].md"

    def test_complex_real_world_example_1(self):
        """Real-world example: technical documentation title."""
        result = FilesafeConverter.title_to_filename("Authentication & Authorization: OAuth 2.0 Flow")
        # " & " becomes ---, ": " becomes --
        assert result == "Authentication--Authorization--OAuth-2.0-Flow.md"

    def test_complex_real_world_example_2(self):
        """Real-world example: API documentation."""
        result = FilesafeConverter.title_to_filename("GET /api/users/{id} - User Details")
        # " /" becomes --, slashes become hyphens, curly braces are preserved
        assert result == "GET--api-users-{id}--User-Details.md"

    def test_complex_real_world_example_3(self):
        """Real-world example: troubleshooting guide."""
        result = FilesafeConverter.title_to_filename('Error: "Connection Refused" | Troubleshooting')
        # ": " becomes --, quotes and pipe become hyphens
        assert result == "Error--Connection-Refused--Troubleshooting.md"


class TestFilenameToTitle:
    """Test cases for FilesafeConverter.filename_to_title method."""

    def test_basic_hyphen_to_space_conversion(self):
        """Hyphens should be converted to spaces."""
        result = FilesafeConverter.filename_to_title("Customer-Feedback.md")
        assert result == "Customer Feedback"

    def test_double_hyphen_to_colon_conversion(self):
        """Double hyphens should be converted to colons (no space after)."""
        result = FilesafeConverter.filename_to_title("API-Reference--Getting-Started.md")
        assert result == "API Reference:Getting Started"

    def test_without_md_extension(self):
        """Should work without .md extension."""
        result = FilesafeConverter.filename_to_title("Customer-Feedback")
        assert result == "Customer Feedback"

    def test_case_preservation(self):
        """Original case should be preserved."""
        result = FilesafeConverter.filename_to_title("APIReference-MixedCASE-Test.md")
        assert result == "APIReference MixedCASE Test"

    def test_single_word(self):
        """Single word filename."""
        result = FilesafeConverter.filename_to_title("Introduction.md")
        assert result == "Introduction"

    def test_multiple_double_hyphens(self):
        """Multiple double hyphens should all become colons (no spaces)."""
        result = FilesafeConverter.filename_to_title("Part--Section--Subsection.md")
        assert result == "Part:Section:Subsection"

    def test_mixed_single_and_double_hyphens(self):
        """Mix of single and double hyphens."""
        result = FilesafeConverter.filename_to_title("API-Guide--Version-2.md")
        assert result == "API Guide:Version 2"

    def test_empty_string(self):
        """Empty string should return empty string."""
        result = FilesafeConverter.filename_to_title("")
        assert result == ""

    def test_only_md_extension(self):
        """Only .md extension should return empty string."""
        result = FilesafeConverter.filename_to_title(".md")
        assert result == ""

    def test_no_hyphens(self):
        """Filename without hyphens."""
        result = FilesafeConverter.filename_to_title("SimpleTitle.md")
        assert result == "SimpleTitle"

    def test_dots_preserved(self):
        """Dots in filename should be preserved."""
        result = FilesafeConverter.filename_to_title("Version-2.0.3.md")
        assert result == "Version 2.0.3"

    def test_underscores_preserved(self):
        """Underscores should be preserved."""
        result = FilesafeConverter.filename_to_title("test_case_example.md")
        assert result == "test_case_example"

    def test_unicode_characters_preserved(self):
        """Unicode characters should be preserved."""
        result = FilesafeConverter.filename_to_title("Café-Münchën.md")
        assert result == "Café Münchën"

    def test_parentheses_preserved(self):
        """Parentheses should be preserved."""
        result = FilesafeConverter.filename_to_title("Test-(Example).md")
        assert result == "Test (Example)"

    def test_brackets_preserved(self):
        """Square brackets should be preserved."""
        result = FilesafeConverter.filename_to_title("Test-[Draft].md")
        assert result == "Test [Draft]"

    def test_lossy_conversion_note(self):
        """Conversion is lossy - can't distinguish colon from double hyphen."""
        # Original title with actual double hyphen would be indistinguishable
        # from a colon-generated double hyphen
        result = FilesafeConverter.filename_to_title("Test--Case.md")
        assert result == "Test:Case"  # Could have been "Test--Case" originally


class TestRoundTripConversion:
    """Test cases for round-trip conversion (title -> filename -> title)."""

    def test_simple_roundtrip(self):
        """Simple title should survive round-trip."""
        original = "Customer Feedback"
        filename = FilesafeConverter.title_to_filename(original)
        result = FilesafeConverter.filename_to_title(filename)
        assert result == original

    def test_roundtrip_with_colon(self):
        """Title with colon loses space after colon in round-trip."""
        original = "API Reference: Getting Started"
        filename = FilesafeConverter.title_to_filename(original)
        result = FilesafeConverter.filename_to_title(filename)
        # The space after colon is lost in conversion
        assert result == "API Reference:Getting Started"

    def test_roundtrip_case_preservation(self):
        """Case should be preserved in round-trip."""
        original = "MixedCASE Title Example"
        filename = FilesafeConverter.title_to_filename(original)
        result = FilesafeConverter.filename_to_title(filename)
        assert result == original

    def test_lossy_roundtrip_special_characters(self):
        """Special characters are lost in round-trip (lossy conversion)."""
        original = "Q&A Session"
        filename = FilesafeConverter.title_to_filename(original)
        result = FilesafeConverter.filename_to_title(filename)
        # Ampersand is lost and becomes space
        assert result == "Q A Session"

    def test_lossy_roundtrip_forward_slash(self):
        """Forward slash is lost in round-trip."""
        original = "Client/Server"
        filename = FilesafeConverter.title_to_filename(original)
        result = FilesafeConverter.filename_to_title(filename)
        assert result == "Client Server"

    def test_roundtrip_preserves_dots(self):
        """Dots should survive round-trip."""
        original = "Version 2.0.3"
        filename = FilesafeConverter.title_to_filename(original)
        result = FilesafeConverter.filename_to_title(filename)
        assert result == original
