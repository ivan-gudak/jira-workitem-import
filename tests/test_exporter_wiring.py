"""export_all/_export_one decide what each ticket directory contains.

The style-driven choices made there -- whether comments get their own file,
which allowlist the attachment handler enforces, and whether the renderer
knows the export -- had no test; only _generate_markdown was covered.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

import markdown_exporter
from attachment_handler import AttachmentHandler
from link_renderer import GITHUB_DOWNLOAD_ALLOWLIST, OutputProfile
from markdown_exporter import MarkdownExporter
from pii_scrubber import PiiScrubber

BASE = "https://example.atlassian.net"


class FakeNamed:
    def __init__(self, name):
        self.name = name


class FakeCommentField:
    def __init__(self, comments):
        self.comments = comments


class FakeComment:
    def __init__(self, body):
        self.body = body
        self.author = type("A", (), {"displayName": "Jane Doe"})()
        self.created = "2026-03-04T10:00:00.000+0000"
        self.updated = self.created


class FakeFields:
    def __init__(self, key, description, comments):
        self.summary = f"{key} summary"
        self.issuetype = FakeNamed("Story")
        self.status = FakeNamed("Open")
        self.description = description
        self.comment = FakeCommentField(comments)


class FakeIssue:
    def __init__(self, key, description="Body text.", comments=()):
        self.key = key
        self.id = "1"
        self.fields = FakeFields(key, description, list(comments))


@dataclass
class FakeNode:
    key: str
    issue: Any
    role: str = "root"
    links: list = field(default_factory=list)


@pytest.fixture(autouse=True)
def no_pull_requests(monkeypatch):
    monkeypatch.setattr(markdown_exporter, "fetch_pull_requests", lambda *a, **k: [])


def export(tmp_path, style, nodes=None):
    nodes = nodes or {"MGD-1": FakeNode("MGD-1", FakeIssue("MGD-1"))}
    exporter = MarkdownExporter(None, tmp_path, PiiScrubber(), root_key="PRODUCT-1",
                                profile=OutputProfile.for_style(style, BASE))
    success, failed = exporter.export_all(nodes)
    assert failed == [], failed
    return exporter, success


# --- Comments: own file, or inlined ------------------------------------------

def test_obsidian_writes_a_separate_comments_file(tmp_path):
    nodes = {"MGD-1": FakeNode("MGD-1", FakeIssue("MGD-1", comments=[FakeComment("Hi.")]))}
    export(tmp_path, "obsidian", nodes)
    assert (tmp_path / "MGD-1" / "MGD-1-comments.md").is_file()
    page = (tmp_path / "MGD-1" / "MGD-1.md").read_text(encoding="utf-8")
    assert "![[MGD-1-comments]]" in page
    assert "Hi." not in page


def test_github_inlines_comments_and_writes_no_second_file(tmp_path):
    """GitHub has no transclusion, so a ![[...]] line would render as text and
    the comments would be unreachable from the ticket page."""
    nodes = {"MGD-1": FakeNode("MGD-1", FakeIssue("MGD-1", comments=[FakeComment("Hi.")]))}
    export(tmp_path, "github", nodes)
    assert not (tmp_path / "MGD-1" / "MGD-1-comments.md").exists()
    page = (tmp_path / "MGD-1" / "MGD-1.md").read_text(encoding="utf-8")
    assert "### Comment #1" in page
    assert "Hi." in page
    assert "[[" not in page


# --- The attachment handler is built from the profile ------------------------

def test_attachment_handler_gets_the_profile_allowlist_and_a_bound_renderer(tmp_path, monkeypatch):
    built = []

    class SpyHandler(AttachmentHandler):
        def __init__(self, client, directory, download_allowlist=None, links=None):
            super().__init__(client, directory, download_allowlist, links)
            built.append(self)

    monkeypatch.setattr(markdown_exporter, "AttachmentHandler", SpyHandler)
    export(tmp_path, "github")

    assert len(built) == 1
    assert built[0].download_allowlist is GITHUB_DOWNLOAD_ALLOWLIST
    # Bound to this ticket, so attachments/ resolves relative to its page.
    assert built[0].links.image("f.png") == "![f.png](attachments/f.png)"


def test_obsidian_attachment_handler_has_no_allowlist(tmp_path, monkeypatch):
    built = []

    class SpyHandler(AttachmentHandler):
        def __init__(self, client, directory, download_allowlist=None, links=None):
            super().__init__(client, directory, download_allowlist, links)
            built.append(self)

    monkeypatch.setattr(markdown_exporter, "AttachmentHandler", SpyHandler)
    export(tmp_path, "obsidian")
    assert built[0].download_allowlist is None
    assert built[0].links.image("f.png") == "![[f.png]]"


# --- The renderer has to know the whole export before any page is written ----

def test_export_all_populates_the_renderer_key_set(tmp_path):
    nodes = {
        "MGD-1": FakeNode("MGD-1", FakeIssue("MGD-1", description="Blocked by MGD-2")),
        "MGD-2": FakeNode("MGD-2", FakeIssue("MGD-2"), role="linked"),
    }
    exporter, count = export(tmp_path, "github", nodes)
    assert count == 2
    assert exporter.profile.renderer.keys == {"MGD-1", "MGD-2"}
    page = (tmp_path / "MGD-1" / "MGD-1.md").read_text(encoding="utf-8")
    assert "[MGD-2](../MGD-2/MGD-2.md)" in page


def test_a_key_outside_the_export_falls_back_to_jira(tmp_path):
    nodes = {"MGD-1": FakeNode("MGD-1", FakeIssue("MGD-1", description="See FOO-9"))}
    export(tmp_path, "github", nodes)
    page = (tmp_path / "MGD-1" / "MGD-1.md").read_text(encoding="utf-8")
    assert f"[FOO-9]({BASE}/browse/FOO-9)" in page


def test_obsidian_keeps_an_unexported_prose_key_as_a_wikilink(tmp_path):
    """Vault-side behaviour: Obsidian resolves by filename across the vault."""
    nodes = {"MGD-1": FakeNode("MGD-1", FakeIssue("MGD-1", description="See FOO-9"))}
    export(tmp_path, "obsidian", nodes)
    page = (tmp_path / "MGD-1" / "MGD-1.md").read_text(encoding="utf-8")
    assert "[[FOO-9]]" in page


# --- Re-export replaces a ticket directory -----------------------------------

def test_re_export_wipes_the_previous_ticket_directory(tmp_path):
    export(tmp_path, "obsidian")
    stale = tmp_path / "MGD-1" / "stale.md"
    stale.write_text("old", encoding="utf-8")
    export(tmp_path, "obsidian")
    assert not stale.exists()
    assert (tmp_path / "MGD-1" / "MGD-1.md").is_file()
