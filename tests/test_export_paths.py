from pathlib import Path

import pytest

from export_paths import ExportPathError, resolve_export_target


def make_specs(tmp_path, *vi_dirs):
    """Build a specs repo skeleton; return its root."""
    specs = tmp_path / "specs"
    (specs / "specifications").mkdir(parents=True)
    for name in vi_dirs:
        (specs / "specifications" / name).mkdir()
    return specs


def make_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


# --- Rule 1: explicit --export-dir wins -------------------------------------

def test_explicit_absolute_dir_wins_over_env(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    target = resolve_export_target(
        "PRODUCT-1", str(tmp_path / "out"), {"SPECS_PATH": str(specs)}
    )
    assert target.data_dir == tmp_path / "out"
    assert target.layout == "nested"
    assert target.origin == "explicit"


def test_explicit_relative_dir_resolves_against_cwd(tmp_path):
    target = resolve_export_target("PRODUCT-1", ".data", {}, cwd=tmp_path)
    assert target.data_dir == tmp_path / ".data"


def test_explicit_tilde_dir_expands(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = resolve_export_target("PRODUCT-1", "~/out", {})
    assert target.data_dir == tmp_path / "out"


# --- Rule 2: SPECS_PATH ------------------------------------------------------

def test_specs_single_glob_match(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-18742-managed-mcp-server-bundling")
    target = resolve_export_target("PRODUCT-18742", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == (
        specs / "specifications" / "PRODUCT-18742-managed-mcp-server-bundling" / "jira-import"
    )
    assert target.layout == "flat"
    assert target.origin == "specs"


def test_specs_no_match_uses_bare_id_dir(tmp_path):
    specs = make_specs(tmp_path)
    target = resolve_export_target("PRODUCT-99999", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "specifications" / "PRODUCT-99999" / "jira-import"
    assert target.layout == "flat"


def test_specs_reuses_bare_id_dir_on_second_run(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-99999")
    target = resolve_export_target("PRODUCT-99999", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "specifications" / "PRODUCT-99999" / "jira-import"


def test_specs_multiple_matches_raises_and_lists_them(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-18742", "PRODUCT-18742-managed-mcp")
    with pytest.raises(ExportPathError) as exc:
        resolve_export_target("PRODUCT-18742", None, {"SPECS_PATH": str(specs)})
    message = str(exc.value)
    assert "PRODUCT-18742-managed-mcp" in message
    assert "--export-dir" in message


def test_specs_ignores_files_that_look_like_matches(tmp_path):
    specs = make_specs(tmp_path)
    (specs / "specifications" / "PRODUCT-18742-notes.md").write_text("x")
    target = resolve_export_target("PRODUCT-18742", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "specifications" / "PRODUCT-18742" / "jira-import"


def test_specs_prefix_does_not_over_match(tmp_path):
    """PRODUCT-1 must not match PRODUCT-18742-slug."""
    specs = make_specs(tmp_path, "PRODUCT-18742-slug")
    target = resolve_export_target("PRODUCT-1", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "specifications" / "PRODUCT-1" / "jira-import"


def test_specs_missing_root_raises(tmp_path):
    with pytest.raises(ExportPathError, match="does not exist"):
        resolve_export_target("PRODUCT-1", None, {"SPECS_PATH": str(tmp_path / "nope")})


def test_specs_missing_specifications_dir_raises(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    with pytest.raises(ExportPathError, match="specifications"):
        resolve_export_target("PRODUCT-1", None, {"SPECS_PATH": str(specs)})


# --- Rule 3: VAULT_PATH ------------------------------------------------------

def test_vault_path_used_when_specs_absent(tmp_path):
    vault = make_vault(tmp_path)
    target = resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": str(vault)})
    assert target.data_dir == vault / "jira-products"
    assert target.layout == "nested"
    assert target.origin == "vault"


def test_specs_wins_over_vault(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    vault = make_vault(tmp_path)
    target = resolve_export_target(
        "PRODUCT-1", None, {"SPECS_PATH": str(specs), "VAULT_PATH": str(vault)}
    )
    assert target.origin == "specs"


def test_vault_missing_dir_raises(tmp_path):
    with pytest.raises(ExportPathError, match="VAULT_PATH"):
        resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": str(tmp_path / "nope")})


# --- Rule 4: nothing set -----------------------------------------------------

def test_no_destination_raises():
    with pytest.raises(ExportPathError, match="no export destination"):
        resolve_export_target("PRODUCT-1", None, {})


def test_empty_string_env_counts_as_unset():
    """The reported bug: VAULT_PATH='' must not yield /jira-products."""
    with pytest.raises(ExportPathError, match="no export destination"):
        resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": "", "SPECS_PATH": "   "})


def test_resolver_creates_no_directories(tmp_path):
    specs = make_specs(tmp_path)
    target = resolve_export_target("PRODUCT-99999", None, {"SPECS_PATH": str(specs)})
    assert not target.data_dir.exists()
    assert not (specs / "specifications" / "PRODUCT-99999").exists()


# --- Review Focus 2 and 5 ----------------------------------------------------

def test_jira_id_case_insensitive_glob_match(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-18742-managed-mcp")
    target = resolve_export_target("product-18742", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == (
        specs / "specifications" / "PRODUCT-18742-managed-mcp" / "jira-import"
    )


def test_trailing_slash_in_pointer_normalizes(tmp_path):
    vault = make_vault(tmp_path)
    target = resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": str(vault) + "/"})
    assert target.data_dir == vault / "jira-products"


def test_tilde_in_vault_path_expands(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "myvault").mkdir()
    target = resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": "~/myvault"})
    assert target.data_dir == tmp_path / "myvault" / "jira-products"


def test_root_pointer_is_not_collapsed_to_the_working_directory():
    """VAULT_PATH='/' rstrips to '', and Path('') is the CWD — which would
    silently write the export next to wherever the tool happened to run."""
    target = resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": "/"})
    assert target.data_dir.is_absolute()
    assert target.data_dir == Path("/jira-products")
