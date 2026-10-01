import re
from pathlib import Path

import pytest

from export_paths import ExportPathError, resolve_export_target, slugify


def make_specs(tmp_path, *vi_dirs):
    """Build a specs repo skeleton; return its root."""
    specs = tmp_path / "specs"
    (specs / "specifications").mkdir(parents=True)
    (specs / ".git").mkdir()
    for name in vi_dirs:
        (specs / "specifications" / name).mkdir()
    return specs


def make_ideas(specs, *idea_dirs):
    """Add an ideas/ folder to a specs repo skeleton."""
    (specs / "ideas").mkdir()
    for name in idea_dirs:
        (specs / "ideas" / name).mkdir()
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


# --- Routing by key prefix ---------------------------------------------------

def test_prodfb_key_routes_to_ideas_with_the_name_pending(tmp_path):
    specs = make_ideas(make_specs(tmp_path))
    target = resolve_export_target("PRODFB-7", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "ideas" / "PRODFB-7" / "jira-import"
    assert target.layout == "flat"
    assert target.origin == "specs"
    assert target.pending_name is True
    assert target.notice is None


def test_prodfb_routing_ignores_case(tmp_path):
    specs = make_ideas(make_specs(tmp_path))
    target = resolve_export_target("prodfb-7", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir.parent.parent == specs / "ideas"


@pytest.mark.parametrize("key", ["PRODUCT-7", "MGD-7", "PRISM-7"])
def test_every_other_key_routes_to_specifications(tmp_path, key):
    specs = make_ideas(make_specs(tmp_path))
    target = resolve_export_target(key, None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "specifications" / key / "jira-import"
    assert target.pending_name is True


def test_existing_ideas_folder_is_used_as_is(tmp_path):
    specs = make_ideas(make_specs(tmp_path), "PRODFB-7-dark-mode")
    target = resolve_export_target("PRODFB-7", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "ideas" / "PRODFB-7-dark-mode" / "jira-import"
    assert target.pending_name is False


def test_existing_bare_folder_is_not_renamed(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-7")
    target = resolve_export_target("PRODUCT-7", None, {"SPECS_PATH": str(specs)})
    assert target.pending_name is False


def test_prodfb_key_does_not_match_a_specifications_folder(tmp_path):
    specs = make_ideas(make_specs(tmp_path, "PRODFB-7-old-home"))
    target = resolve_export_target("PRODFB-7", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "ideas" / "PRODFB-7" / "jira-import"


# --- An unusable SPECS_PATH falls back to VAULT_PATH -------------------------

def _missing_root(tmp_path):
    return tmp_path / "nope"


def _missing_ideas(tmp_path):
    return make_specs(tmp_path)


def _not_a_repo(tmp_path):
    specs = make_ideas(make_specs(tmp_path))
    (specs / ".git").rmdir()
    return specs


UNUSABLE_SPECS = [
    pytest.param(_missing_root, "that directory does not exist", id="missing-root"),
    pytest.param(_missing_ideas, "ideas does not exist", id="missing-ideas"),
    pytest.param(_not_a_repo, "not the root of a git repository", id="not-a-repo"),
]


@pytest.mark.parametrize("build, reason", UNUSABLE_SPECS)
def test_unusable_specs_falls_back_to_the_vault_with_a_notice(tmp_path, build, reason):
    specs = build(tmp_path)
    vault = make_vault(tmp_path)
    target = resolve_export_target(
        "PRODFB-7", None, {"SPECS_PATH": str(specs), "VAULT_PATH": str(vault)}
    )
    assert target.data_dir == vault / "jira-products"
    assert target.origin == "vault"
    assert target.layout == "nested"
    assert target.pending_name is False
    assert reason in target.notice


@pytest.mark.parametrize("build, reason", UNUSABLE_SPECS)
def test_unusable_specs_without_a_vault_raises_with_the_reason(tmp_path, build, reason):
    specs = build(tmp_path)
    with pytest.raises(ExportPathError) as exc:
        resolve_export_target("PRODFB-7", None, {"SPECS_PATH": str(specs)})
    assert reason in str(exc.value)
    assert "VAULT_PATH is not set" in str(exc.value)


def test_unusable_specs_and_missing_vault_raise_with_both_reasons(tmp_path):
    specs = make_specs(tmp_path)
    with pytest.raises(ExportPathError) as exc:
        resolve_export_target(
            "PRODFB-7", None,
            {"SPECS_PATH": str(specs), "VAULT_PATH": str(tmp_path / "no-vault")},
        )
    message = str(exc.value)
    assert "ideas does not exist" in message
    assert "VAULT_PATH is set to" in message


def test_git_file_counts_as_a_repository(tmp_path):
    """A git worktree has a .git file, not a directory."""
    specs = _not_a_repo(tmp_path)
    (specs / ".git").write_text("gitdir: /elsewhere/.git/worktrees/specs\n")
    target = resolve_export_target("PRODFB-7", None, {"SPECS_PATH": str(specs)})
    assert target.origin == "specs"


def test_several_matches_raise_even_with_a_vault_to_fall_back_to(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-7-a", "PRODUCT-7-b")
    vault = make_vault(tmp_path)
    with pytest.raises(ExportPathError, match="candidate directories"):
        resolve_export_target(
            "PRODUCT-7", None, {"SPECS_PATH": str(specs), "VAULT_PATH": str(vault)}
        )


# --- Naming a pending folder -------------------------------------------------

def test_named_appends_the_slug_to_the_feature_folder(tmp_path):
    specs = make_ideas(make_specs(tmp_path))
    target = resolve_export_target("PRODFB-7", None, {"SPECS_PATH": str(specs)})
    named = target.named("dark-mode")
    assert named.data_dir == specs / "ideas" / "PRODFB-7-dark-mode" / "jira-import"
    assert named.pending_name is False
    assert (named.layout, named.origin) == ("flat", "specs")


def test_named_with_an_empty_slug_keeps_the_bare_key(tmp_path):
    specs = make_ideas(make_specs(tmp_path))
    target = resolve_export_target("PRODFB-7", None, {"SPECS_PATH": str(specs)})
    named = target.named("")
    assert named.data_dir == specs / "ideas" / "PRODFB-7" / "jira-import"
    assert named.pending_name is False


def test_named_leaves_an_existing_folder_alone(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-7-chosen-by-hand")
    target = resolve_export_target("PRODUCT-7", None, {"SPECS_PATH": str(specs)})
    assert target.named("from-summary") == target


# --- slugify -----------------------------------------------------------------

SLUG_SHAPE = re.compile(r"^([a-z0-9]+(-[a-z0-9]+)*)?$")


def test_slug_from_a_plain_summary():
    assert slugify("Export a distributed trace") == "export-a-distributed-trace"


def test_slug_folds_accents_and_sharp_s_to_ascii():
    assert slugify("Café Straße") == "cafe-strasse"


def test_slug_drops_scrubber_placeholders():
    """A slug names the request, not who asked or how to reach them."""
    text = "User-3 asks @User-12 to email [email] about [mention] exports"
    assert slugify(text) == "asks-to-email-about-exports"


def test_slug_drops_punctuation_and_collapses_separators():
    assert slugify("  [RFE] Export -- traces (v2)!  ") == "rfe-export-traces-v2"


def test_slug_cut_exactly_on_a_word_boundary_keeps_the_last_word():
    # 40 characters end with a whole word and the 41st is the separator, so
    # cutting at the last "-" inside the first 40 would wrongly drop "abcdefg".
    head = "abcdefghij abcdefghij abcdefghij abcdefg"
    assert slugify(head + " tail") == "abcdefghij-abcdefghij-abcdefghij-abcdefg"


def test_slug_cut_inside_a_word_drops_the_partial_word():
    text = "alpha beta gamma delta epsilon zeta etaetaeta"
    slug = slugify(text)
    assert slug == "alpha-beta-gamma-delta-epsilon-zeta"
    assert len(slug) <= 40


def test_slug_of_one_long_word_is_cut_at_40():
    assert slugify("x" * 60) == "x" * 40


def test_slug_is_empty_when_nothing_survives():
    assert slugify("") == ""
    assert slugify("!!! ??? ---") == ""
    assert slugify("日本語のタイトル") == ""
    assert slugify("User-7 [email]") == ""


@pytest.mark.parametrize("hostile", [
    "../../etc/passwd",
    "a/b\\c",
    "..",
    "name\x00with\x00nul",
    'win: * ? " < > | chars',
    "tab\tnewline\ncarriage\rreturn",
    "emoji 🚀 rocket 🔥",
    "mixed עברית and english",
    "trailing dots...",
    "CON",
    "-leading and trailing-",
    "a" * 300,
])
def test_slug_only_ever_contains_lowercase_letters_digits_and_inner_hyphens(hostile):
    slug = slugify(hostile)
    assert SLUG_SHAPE.match(slug), slug
    assert len(slug) <= 40


def test_slug_turns_a_path_into_words():
    assert slugify("../../etc/passwd") == "etc-passwd"
