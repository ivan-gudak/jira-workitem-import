from pathlib import Path

from markdown_exporter import MarkdownExporter
from pii_scrubber import PiiScrubber


def make_exporter(field_names=None):
    return MarkdownExporter(
        jira_client=None,
        data_dir=Path("/tmp/jira-test-out"),
        scrubber=PiiScrubber(),
        root_key="ROOT",
        field_names=field_names or {},
    )


def test_is_empty_description():
    assert MarkdownExporter._is_empty_description(None) is True
    assert MarkdownExporter._is_empty_description("") is True
    assert MarkdownExporter._is_empty_description("\n\n") is True
    assert MarkdownExporter._is_empty_description("   ") is True
    assert MarkdownExporter._is_empty_description("real text") is False


class FakeOption:
    def __init__(self, value):
        self.value = value


class FakeUser:
    def __init__(self, display_name):
        self.displayName = display_name


def test_format_prose_string_converts_and_scrubs():
    exp = make_exporter()
    out = exp._format_additional_value("h3. Risk\n\nReported by alice@dynatrace.com")
    assert "Risk" in out
    assert "[email]" in out
    assert "alice@dynatrace.com" not in out


def test_format_empty_string_returns_none():
    exp = make_exporter()
    assert exp._format_additional_value("   ") is None
    assert exp._format_additional_value("\n\n") is None


def test_format_single_option_returns_value():
    exp = make_exporter()
    assert exp._format_additional_value(FakeOption("Synthetic")) == "Synthetic"


def test_format_people_list_anonymizes_in_order():
    exp = make_exporter()
    out = exp._format_additional_value([FakeUser("Shari Gigliotti"), FakeUser("Sahil Verma")])
    assert out == "User-1, User-2"


def test_format_single_user_anonymizes():
    exp = make_exporter()
    assert exp._format_additional_value(FakeUser("Shari Gigliotti")) == "User-1"


def test_format_plain_url_string_passthrough():
    exp = make_exporter()
    url = "https://example.com/lightning/r/Account/001/view"
    out = exp._format_additional_value(url)
    assert "https://example.com/lightning/r/Account/001/view" in out


def test_format_option_list_joins_values():
    exp = make_exporter()
    out = exp._format_additional_value([FakeOption("A"), FakeOption("B")])
    assert out == "A, B"
