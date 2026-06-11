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
