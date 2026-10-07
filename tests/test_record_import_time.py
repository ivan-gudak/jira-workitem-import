"""An import records when it ran and when each ticket last changed, so a reader
can tell whether Jira moved on since — a file's modification time cannot, because
git sets it at checkout."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest

import markdown_exporter
from index_generator import generate_import_index
from link_renderer import GithubLinks, OutputProfile
from markdown_exporter import MarkdownExporter
from pii_scrubber import PiiScrubber

BASE = "https://example.atlassian.net"


class FakeNamed:
    def __init__(self, name):
        self.name = name


class FakeFields:
    def __init__(self, key, updated):
        self.summary = f"{key} summary"
        self.issuetype = FakeNamed("Story")
        self.status = FakeNamed("Open")
        self.description = "Body."
        self.comment = type("C", (), {"comments": []})()
        self.parent = None
        if updated is not None:
            self.updated = updated


class FakeIssue:
    def __init__(self, key, updated="2026-10-06T06:45:15.383+0100"):
        self.key = key
        self.id = "1"
        self.fields = FakeFields(key, updated)


@dataclass
class FakeNode:
    key: str
    issue: Any
    role: str = "root"
    links: list = field(default_factory=list)


@pytest.fixture(autouse=True)
def no_pull_requests(monkeypatch):
    monkeypatch.setattr(markdown_exporter, "fetch_pull_requests", lambda *a, **k: [])


def export_page(tmp_path, issue):
    nodes = {issue.key: FakeNode(issue.key, issue)}
    exporter = MarkdownExporter(None, tmp_path, PiiScrubber(), root_key=issue.key,
                                profile=OutputProfile.for_style("github", BASE))
    _, failed = exporter.export_all(nodes)
    assert failed == []
    return (tmp_path / issue.key / f"{issue.key}.md").read_text(encoding="utf-8")


def frontmatter(page):
    return page.split("---\n")[1]


def test_page_records_jira_updated_in_utc(tmp_path):
    page = export_page(tmp_path, FakeIssue("MGD-1"))
    assert 'updated: "2026-10-06T05:45:15.383Z"' in frontmatter(page)


def test_updated_is_the_last_frontmatter_key(tmp_path):
    lines = frontmatter(export_page(tmp_path, FakeIssue("MGD-1"))).strip().splitlines()
    assert lines[-1].startswith("updated: ")


def test_page_without_updated_writes_no_line(tmp_path):
    page = export_page(tmp_path, FakeIssue("MGD-1", updated=None))
    assert "updated:" not in frontmatter(page)


def test_index_records_the_import_time_under_its_title():
    issue = FakeIssue("PRODUCT-1")
    nodes = {"PRODUCT-1": FakeNode("PRODUCT-1", issue)}
    when = datetime(2026, 10, 7, 13, 0, 5, tzinfo=timezone.utc)
    out = generate_import_index(None, nodes, "PRODUCT-1", links=GithubLinks(BASE, nodes),
                                layout="flat", imported_at=when)
    assert out.startswith("# Export Index: PRODUCT-1\n\n**Imported:** 2026-10-07T13:00:05Z\n\n## All Exported Work Items")


def test_index_without_a_time_is_unchanged():
    issue = FakeIssue("PRODUCT-1")
    nodes = {"PRODUCT-1": FakeNode("PRODUCT-1", issue)}
    out = generate_import_index(None, nodes, "PRODUCT-1", links=GithubLinks(BASE, nodes), layout="flat")
    assert "**Imported:**" not in out
    assert out.startswith("# Export Index: PRODUCT-1\n\n## All Exported Work Items")
