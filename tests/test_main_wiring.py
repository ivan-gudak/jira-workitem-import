"""main() decides layout, link style, and whether a registry is written.

Those decisions are one-liners with no other test covering them, so the whole
entry point is exercised here with Jira, the graph walk, and the exporter
replaced — no network, no real export.
"""

import sys
from dataclasses import dataclass, field
from typing import Any

import pytest

import main as main_module


class FakeNamed:
    def __init__(self, name):
        self.name = name


class FakeFields:
    def __init__(self, key, itype):
        self.summary = f"{key} summary"
        self.issuetype = FakeNamed(itype)
        self.status = FakeNamed("Open")
        self.parent = None


class FakeIssue:
    def __init__(self, key, itype="Story"):
        self.key = key
        self.id = "1"
        self.fields = FakeFields(key, itype)


@dataclass
class FakeNode:
    key: str
    issue: Any
    role: str
    links: list = field(default_factory=list)


class FakeAuth:
    server = "https://jira.example"

    def get_jira_client(self):
        return type("FakeClient", (), {"fields": staticmethod(lambda: [])})()


@pytest.fixture
def run_main(monkeypatch):
    """Run main() with the outside world stubbed; return what it wired up."""
    seen = {}

    class FakeWalker:
        def __init__(self, client):
            pass

        def walk(self, jira_id):
            return {
                jira_id: FakeNode(jira_id, FakeIssue(jira_id, "Epic"), "root"),
                "MGD-2": FakeNode("MGD-2", FakeIssue("MGD-2"), "linked"),
            }

    class FakeExporter:
        def __init__(self, client, data_dir, scrubber, root_key="",
                     field_names=None, profile=None):
            seen["import_dir"] = data_dir
            seen["profile"] = profile
            seen["root_key"] = root_key

        def export_all(self, nodes):
            seen["nodes"] = nodes
            return len(nodes), []

    monkeypatch.setattr(main_module, "JiraAuth", FakeAuth)
    monkeypatch.setattr(main_module, "GraphWalker", FakeWalker)
    monkeypatch.setattr(main_module, "MarkdownExporter", FakeExporter)

    def run(argv, env=None):
        for name in ("SPECS_PATH", "VAULT_PATH"):
            monkeypatch.delenv(name, raising=False)
        for name, value in (env or {}).items():
            monkeypatch.setenv(name, value)
        monkeypatch.setattr(sys, "argv", ["main.py", *argv])
        main_module.main()
        return seen

    return run


def make_specs(tmp_path, *vi_dirs):
    specs = tmp_path / "specs"
    (specs / "specifications").mkdir(parents=True)
    (specs / ".git").mkdir()
    for name in vi_dirs:
        (specs / "specifications" / name).mkdir()
    return specs


def make_ideas(specs, *idea_dirs):
    (specs / "ideas").mkdir()
    for name in idea_dirs:
        (specs / "ideas" / name).mkdir()
    return specs


class FakeUser:
    def __init__(self, name):
        self.displayName = name


def root_walker(summary, assignee=None):
    """A GraphWalker stand-in whose only ticket, the root, has this summary."""
    class Walker:
        def __init__(self, client):
            pass

        def walk(self, jira_id):
            issue = FakeIssue(jira_id, "Epic")
            issue.fields.summary = summary
            issue.fields.assignee = FakeUser(assignee) if assignee else None
            return {jira_id: FakeNode(jira_id, issue, "root")}
    return Walker


def make_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


# --- Style inference ---------------------------------------------------------

def test_specs_destination_infers_github_style(run_main, tmp_path, capsys):
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    seen = run_main(["PRODUCT-1"], {"SPECS_PATH": str(specs)})
    assert seen["profile"].renderer.style == "github"
    assert seen["profile"].inline_comments is True
    assert "Links: github" in capsys.readouterr().out


def test_vault_destination_infers_obsidian_style(run_main, tmp_path, capsys):
    vault = make_vault(tmp_path)
    seen = run_main(["PRODUCT-1"], {"VAULT_PATH": str(vault)})
    assert seen["profile"].renderer.style == "obsidian"
    assert seen["profile"].inline_comments is False
    assert "Links: obsidian" in capsys.readouterr().out


def test_explicit_export_dir_infers_obsidian_style(run_main, tmp_path):
    seen = run_main(["PRODUCT-1", f"--export-dir={tmp_path / 'out'}"])
    assert seen["profile"].renderer.style == "obsidian"


def test_link_style_flag_overrides_the_inferred_style(run_main, tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    seen = run_main(["PRODUCT-1", "--link-style=obsidian"], {"SPECS_PATH": str(specs)})
    assert seen["profile"].renderer.style == "obsidian"

    seen = run_main(["PRODUCT-1", f"--export-dir={tmp_path / 'o'}", "--link-style=github"])
    assert seen["profile"].renderer.style == "github"


# --- Layout ------------------------------------------------------------------

def test_flat_layout_exports_straight_into_the_destination(run_main, tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    seen = run_main(["PRODUCT-1"], {"SPECS_PATH": str(specs)})
    expected = specs / "specifications" / "PRODUCT-1-slug" / "jira-import"
    assert seen["import_dir"] == expected
    assert (expected / "PRODUCT-1-index.md").is_file()


def test_nested_layout_adds_an_id_level(run_main, tmp_path):
    vault = make_vault(tmp_path)
    seen = run_main(["PRODUCT-1"], {"VAULT_PATH": str(vault)})
    expected = vault / "jira-products" / "PRODUCT-1"
    assert seen["import_dir"] == expected
    assert (expected / "PRODUCT-1-index.md").is_file()


def test_flat_layout_writes_no_registry(run_main, tmp_path):
    """A flat destination holds one import, so export-index.md would be noise
    and the per-import backlink to it would 404."""
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    run_main(["PRODUCT-1"], {"SPECS_PATH": str(specs)})
    root = specs / "specifications" / "PRODUCT-1-slug" / "jira-import"
    assert not (root / "export-index.md").exists()
    assert "Main Index" not in (root / "PRODUCT-1-index.md").read_text(encoding="utf-8")


def test_nested_layout_writes_the_registry(run_main, tmp_path):
    vault = make_vault(tmp_path)
    run_main(["PRODUCT-1"], {"VAULT_PATH": str(vault)})
    registry = vault / "jira-products" / "export-index.md"
    assert registry.is_file()
    assert "PRODUCT-1" in registry.read_text(encoding="utf-8")


# --- The renderer has to know the whole export -------------------------------

def test_renderer_is_told_every_exported_key(run_main, tmp_path):
    """Without this the index degrades every issue link to a Jira URL."""
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    seen = run_main(["PRODUCT-1"], {"SPECS_PATH": str(specs)})
    assert seen["profile"].renderer.keys == {"PRODUCT-1", "MGD-2"}
    index = (specs / "specifications" / "PRODUCT-1-slug" / "jira-import"
             / "PRODUCT-1-index.md").read_text(encoding="utf-8")
    assert "[MGD-2](MGD-2/MGD-2.md)" in index


# --- Failure paths -----------------------------------------------------------

def test_no_destination_exits_1_before_contacting_jira(run_main, capsys):
    with pytest.raises(SystemExit) as exc:
        run_main(["PRODUCT-1"])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "no export destination" in out
    assert "Connected to:" not in out


def test_unresolvable_destination_creates_nothing(run_main, tmp_path, capsys):
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as exc:
        run_main(["PRODUCT-1"], {"VAULT_PATH": str(missing)})
    assert exc.value.code == 1
    assert not missing.exists()
    assert "Connected to:" not in capsys.readouterr().out


def test_an_empty_graph_exits_0_without_writing(run_main, monkeypatch, tmp_path):
    class EmptyWalker:
        def __init__(self, client):
            pass

        def walk(self, jira_id):
            return {}

    monkeypatch.setattr(main_module, "GraphWalker", EmptyWalker)
    vault = make_vault(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run_main(["PRODUCT-1"], {"VAULT_PATH": str(vault)})
    assert exc.value.code == 0
    assert not (vault / "jira-products" / "PRODUCT-1").exists()


# --- Naming a new specs folder from the summary ------------------------------

def test_new_specs_folder_is_named_from_the_summary(run_main, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "GraphWalker", root_walker("Dark mode for dashboards"))
    specs = make_ideas(make_specs(tmp_path))
    seen = run_main(["PRODFB-5"], {"SPECS_PATH": str(specs)})
    expected = specs / "ideas" / "PRODFB-5-dark-mode-for-dashboards" / "jira-import"
    assert seen["import_dir"] == expected
    assert (expected / "PRODFB-5-index.md").is_file()
    assert not (specs / "ideas" / "PRODFB-5").exists()


def test_header_says_the_new_folder_is_named_from_the_summary(run_main, monkeypatch,
                                                              tmp_path, capsys):
    monkeypatch.setattr(main_module, "GraphWalker", root_walker("Dark mode"))
    specs = make_ideas(make_specs(tmp_path))
    run_main(["PRODFB-5"], {"SPECS_PATH": str(specs)})
    out = capsys.readouterr().out
    assert "PRODFB-5-<slug>" in out
    assert "(new folder, named from the ticket summary)" in out


def test_people_in_the_summary_stay_out_of_the_folder_name(run_main, monkeypatch, tmp_path):
    """The scrubber only knows a name once it has seen the ticket's people,
    so they must be registered before the summary is slugged."""
    monkeypatch.setattr(main_module, "GraphWalker",
                        root_walker("Jane Doe wants dark mode", assignee="Jane Doe"))
    specs = make_ideas(make_specs(tmp_path))
    seen = run_main(["PRODFB-5"], {"SPECS_PATH": str(specs)})
    assert seen["import_dir"].parent.name == "PRODFB-5-wants-dark-mode"


def test_summary_with_nothing_sluggable_exports_to_the_bare_key(run_main, monkeypatch,
                                                                tmp_path):
    monkeypatch.setattr(main_module, "GraphWalker", root_walker("!!! ???"))
    specs = make_ideas(make_specs(tmp_path))
    seen = run_main(["PRODFB-5"], {"SPECS_PATH": str(specs)})
    assert seen["import_dir"] == specs / "ideas" / "PRODFB-5" / "jira-import"


def test_existing_folder_is_used_and_no_new_one_appears(run_main, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "GraphWalker", root_walker("A different title now"))
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    seen = run_main(["PRODUCT-1"], {"SPECS_PATH": str(specs)})
    assert seen["import_dir"] == specs / "specifications" / "PRODUCT-1-slug" / "jira-import"
    assert [d.name for d in (specs / "specifications").iterdir()] == ["PRODUCT-1-slug"]


def test_unusable_specs_prints_a_note_and_exports_to_the_vault(run_main, tmp_path, capsys):
    specs = make_specs(tmp_path)              # no ideas/
    vault = make_vault(tmp_path)
    seen = run_main(["PRODFB-5"], {"SPECS_PATH": str(specs), "VAULT_PATH": str(vault)})
    assert seen["import_dir"] == vault / "jira-products" / "PRODFB-5"
    out = capsys.readouterr().out
    assert "Note:" in out
    assert "ideas does not exist" in out
    assert "Falling back to VAULT_PATH." in out
    assert "Links: obsidian" in out


def test_failing_to_create_the_import_dir_exits_1_with_the_path(run_main, monkeypatch,
                                                               tmp_path, capsys):
    monkeypatch.setattr(main_module, "GraphWalker", root_walker("Dark mode"))
    specs = make_ideas(make_specs(tmp_path))
    # A file where the folder should go: the resolver skips files, mkdir cannot.
    (specs / "ideas" / "PRODFB-5-dark-mode").write_text("in the way")
    with pytest.raises(SystemExit) as exc:
        run_main(["PRODFB-5"], {"SPECS_PATH": str(specs)})
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Error: cannot create" in out
    assert "PRODFB-5-dark-mode" in out
