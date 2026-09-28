from dataclasses import dataclass
from typing import Any

from index_generator import generate_import_index, update_top_level_index
from link_renderer import GithubLinks, ObsidianLinks

BASE = "https://example.atlassian.net"


class FakeNamed:
    def __init__(self, name):
        self.name = name


class FakeFields:
    def __init__(self, summary, itype, status):
        self.summary = summary
        self.issuetype = FakeNamed(itype)
        self.status = FakeNamed(status)
        self.parent = None


class FakeIssue:
    def __init__(self, key, summary="A summary", itype="Story", status="Open"):
        self.key = key
        self.fields = FakeFields(summary, itype, status)


@dataclass
class FakeNode:
    key: str
    issue: Any
    role: str
    links: list


def make_nodes():
    return {
        "PRODUCT-1": FakeNode("PRODUCT-1", FakeIssue("PRODUCT-1", itype="Epic"), "root",
                              [("blocks", "outward", "MGD-2")]),
        "MGD-2": FakeNode("MGD-2", FakeIssue("MGD-2"), "linked", []),
    }


def test_obsidian_index_keeps_wikilinks_and_backlink():
    nodes = make_nodes()
    links = ObsidianLinks(BASE, nodes.keys())
    out = generate_import_index(None, nodes, "PRODUCT-1", links=links, layout="nested")
    assert "**Main Index:** [[export-index]]" in out
    assert "[[MGD-2]]" in out


def test_default_rendering_matches_obsidian():
    """No renderer supplied: today's behavior, unchanged."""
    nodes = make_nodes()
    links = ObsidianLinks(BASE, nodes.keys())
    assert generate_import_index(None, nodes, "PRODUCT-1") == generate_import_index(
        None, nodes, "PRODUCT-1", links=links, layout="nested"
    )


def test_github_index_uses_relative_links():
    nodes = make_nodes()
    links = GithubLinks(BASE, nodes.keys())
    out = generate_import_index(None, nodes, "PRODUCT-1", links=links, layout="nested")
    assert "[MGD-2](MGD-2/MGD-2.md)" in out
    assert "[[" not in out


def test_flat_layout_omits_the_main_index_backlink():
    """Flat layout writes no export-index.md, so the backlink would 404."""
    nodes = make_nodes()
    links = GithubLinks(BASE, nodes.keys())
    out = generate_import_index(None, nodes, "PRODUCT-1", links=links, layout="flat")
    assert "Main Index" not in out
    assert "export-index" not in out


def test_unexported_link_target_falls_back_to_jira_url():
    nodes = make_nodes()
    nodes["PRODUCT-1"].links = [("blocks", "outward", "FOO-99")]
    links = GithubLinks(BASE, nodes.keys())
    out = generate_import_index(None, nodes, "PRODUCT-1", links=links, layout="flat")
    assert f"[FOO-99]({BASE}/browse/FOO-99)" in out


def _write_import(root, name, row):
    sub = root / name
    sub.mkdir()
    (sub / f"{name}-index.md").write_text(
        "| Key | Type | Status | Summary | Role |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"{row}\n",
        encoding="utf-8",
    )


def test_registry_parses_wikilink_rows(tmp_path):
    _write_import(tmp_path, "PRODUCT-1", "| [[PRODUCT-1]] | Epic | Open | A summary | root |")
    update_top_level_index(tmp_path)
    out = (tmp_path / "export-index.md").read_text(encoding="utf-8")
    assert "Epic" in out and "A summary" in out


def test_registry_parses_markdown_link_rows(tmp_path):
    """Regression: the parser only knew '| [[' and silently lost every field."""
    _write_import(
        tmp_path, "PRODUCT-1",
        "| [PRODUCT-1](PRODUCT-1/PRODUCT-1.md) | Epic | Open | A summary | root |",
    )
    update_top_level_index(tmp_path)
    out = (tmp_path / "export-index.md").read_text(encoding="utf-8")
    assert "Epic" in out and "A summary" in out


def test_registry_rows_are_wikilinks_by_default(tmp_path):
    """Vault output must not change: the aliased wikilink form is preserved."""
    _write_import(tmp_path, "PRODUCT-1", "| [[PRODUCT-1]] | Epic | Open | A summary | root |")
    update_top_level_index(tmp_path)
    out = (tmp_path / "export-index.md").read_text(encoding="utf-8")
    assert "| [[PRODUCT-1-index\\|PRODUCT-1]] | Epic | Open | A summary |" in out


def test_registry_rows_are_relative_links_under_github(tmp_path):
    """export-index.md sits one level above each import directory."""
    _write_import(tmp_path, "PRODUCT-1", "| [[PRODUCT-1]] | Epic | Open | A summary | root |")
    update_top_level_index(tmp_path, links=GithubLinks(BASE, set()))
    out = (tmp_path / "export-index.md").read_text(encoding="utf-8")
    assert "| [PRODUCT-1](PRODUCT-1/PRODUCT-1-index.md) | Epic | Open | A summary |" in out
    assert "[[" not in out


# ---------------------------------------------------------------------------
# Epic hierarchy: _render_tree had no fixture with children, so neither the
# recursion nor its renderer calls ever ran.
# ---------------------------------------------------------------------------

class FakeParent:
    def __init__(self, key):
        self.key = key


def epic_nodes():
    """PRODUCT-1 (Epic) -> MGD-2 (Story) -> MGD-3 (Sub-task)."""
    nodes = {
        "PRODUCT-1": FakeNode(
            "PRODUCT-1", FakeIssue("PRODUCT-1", summary="The epic", itype="Epic"), "root", []),
        "MGD-2": FakeNode(
            "MGD-2", FakeIssue("MGD-2", summary="Child", itype="Story"), "epic_child", []),
        "MGD-3": FakeNode(
            "MGD-3", FakeIssue("MGD-3", summary="Grandchild", itype="Sub-task"), "epic_child", []),
    }
    nodes["MGD-2"].issue.fields.parent = FakeParent("PRODUCT-1")
    nodes["MGD-3"].issue.fields.parent = FakeParent("MGD-2")
    return nodes


def test_epic_hierarchy_renders_children_through_the_renderer():
    nodes = epic_nodes()
    out = generate_import_index(None, nodes, "PRODUCT-1",
                                links=GithubLinks(BASE, nodes.keys()), layout="flat")
    assert "### [PRODUCT-1](PRODUCT-1/PRODUCT-1.md): The epic" in out
    assert "- [MGD-2](MGD-2/MGD-2.md) (Story) — Child" in out
    assert "[[" not in out


def test_epic_hierarchy_indents_grandchildren():
    nodes = epic_nodes()
    out = generate_import_index(None, nodes, "PRODUCT-1",
                                links=GithubLinks(BASE, nodes.keys()), layout="flat")
    assert "\n- [MGD-2](MGD-2/MGD-2.md) (Story) — Child" in out
    assert "\n  - [MGD-3](MGD-3/MGD-3.md) (Sub-task) — Grandchild" in out


def test_epic_hierarchy_uses_wikilinks_under_obsidian():
    nodes = epic_nodes()
    out = generate_import_index(None, nodes, "PRODUCT-1",
                                links=ObsidianLinks(BASE, nodes.keys()), layout="flat")
    assert "### [[PRODUCT-1]]: The epic" in out
    assert "- [[MGD-2]] (Story) — Child" in out
    assert "  - [[MGD-3]] (Sub-task) — Grandchild" in out


def test_an_epic_with_no_children_says_so():
    nodes = {"PRODUCT-1": FakeNode("PRODUCT-1", FakeIssue("PRODUCT-1", itype="Epic"), "root", [])}
    out = generate_import_index(None, nodes, "PRODUCT-1",
                                links=GithubLinks(BASE, nodes.keys()), layout="flat")
    assert "_No children found in export._" in out


def test_epic_link_custom_field_is_honoured_as_a_parent():
    """Older issues carry the Epic Link in customfield_17801, not parent."""
    nodes = epic_nodes()
    nodes["MGD-2"].issue.fields.parent = None
    nodes["MGD-2"].issue.fields.customfield_17801 = "PRODUCT-1"
    out = generate_import_index(None, nodes, "PRODUCT-1",
                                links=GithubLinks(BASE, nodes.keys()), layout="flat")
    assert "- [MGD-2](MGD-2/MGD-2.md) (Story) — Child" in out
