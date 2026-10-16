"""src/main.py runs jiramd with this repository's Dynatrace configuration.

The command line, the credentials file and the destinations are the ones this
tool always had; jiramd does the work.
"""

from pathlib import Path

import pytest

import main
from jiramd.config import load_settings
from jiramd.destinations import DestinationError, resolve_destination


# --- the command line -----------------------------------------------------------

def test_a_key_becomes_a_jiramd_export():
    assert main.jiramd_argv(["PRODUCT-1"]) == ["--config", str(main.CONFIG), "export", "PRODUCT-1"]


def test_original_flags_are_translated():
    argv = main.jiramd_argv(["PRODUCT-1", "--export-dir=/x", "--link-style=github"])
    assert argv[-5:] == ["PRODUCT-1", "--export-dir", "/x", "--links", "github"]


def test_flags_with_separate_values_work_too():
    argv = main.jiramd_argv(["PRODUCT-1", "--link-style", "obsidian", "--export-dir", "out"])
    assert argv[-5:] == ["PRODUCT-1", "--export-dir", "out", "--links", "obsidian"]


def test_an_unknown_link_style_is_refused_as_before():
    with pytest.raises(SystemExit):
        main.jiramd_argv(["PRODUCT-1", "--link-style=html"])


# --- credentials ------------------------------------------------------------------

def test_credentials_come_from_the_environment_when_all_three_are_set(tmp_path):
    env = main.credentials({"JIRA_SERVER": "https://s", "JIRA_EMAIL": "e@x", "JIRA_TOKEN": "t"}, tmp_path)
    assert (env["JIRA_URL"], env["JIRA_USER"], env["JIRA_TOKEN"]) == ("https://s", "e@x", "t")


def test_credentials_come_from_jira_config_otherwise(tmp_path):
    (tmp_path / ".jira.config").write_text("SERVER: https://s\nEMAIL: e@x\nTOKEN: t\n", encoding="utf-8")
    env = main.credentials({"JIRA_SERVER": "ignored"}, tmp_path)
    assert (env["JIRA_URL"], env["JIRA_USER"], env["JIRA_TOKEN"]) == ("https://s", "e@x", "t")


def test_without_credentials_nothing_is_set(tmp_path):
    assert main.credentials({}, tmp_path) == {}


# --- the Dynatrace configuration routes exports as before ----------------------------

@pytest.fixture
def places(tmp_path):
    specs = tmp_path / "specs"
    for sub in ("specifications", "ideas", ".git"):
        (specs / sub).mkdir(parents=True)
    vault = tmp_path / "vault"
    vault.mkdir()
    return specs, vault


def resolve(key, env, cwd):
    settings = load_settings(main.CONFIG, env)
    return resolve_destination(key, settings.export.destinations, None, env, cwd)


def test_product_feedback_goes_to_ideas_named_from_the_summary(places, tmp_path):
    specs, vault = places
    target = resolve("PRODFB-7", {"SPECS_PATH": str(specs), "VAULT_PATH": str(vault)}, tmp_path)
    assert target.data_dir == specs / "ideas" / "PRODFB-7" / "jira-import"
    assert (target.layout, target.links, target.pending_name) == ("flat", "github", True)


def test_every_other_key_goes_to_specifications(places, tmp_path):
    specs, vault = places
    target = resolve("PRODUCT-7", {"SPECS_PATH": str(specs), "VAULT_PATH": str(vault)}, tmp_path)
    assert target.data_dir == specs / "specifications" / "PRODUCT-7" / "jira-import"


def test_without_specs_the_vault_takes_it(places, tmp_path):
    _, vault = places
    target = resolve("PRODUCT-7", {"VAULT_PATH": str(vault)}, tmp_path)
    assert target.data_dir == vault / "jira-products"
    assert (target.layout, target.links) == ("nested", "obsidian")


def test_a_specs_folder_that_is_not_a_repository_falls_back_to_the_vault(places, tmp_path):
    specs, vault = places
    (specs / ".git").rmdir()
    target = resolve("PRODUCT-7", {"SPECS_PATH": str(specs), "VAULT_PATH": str(vault)}, tmp_path)
    assert target.data_dir == vault / "jira-products"
    assert any("not the root of a git repository" in n for n in target.notices)


def test_neither_set_is_an_error(tmp_path):
    with pytest.raises(DestinationError):
        resolve("PRODUCT-7", {}, tmp_path)
