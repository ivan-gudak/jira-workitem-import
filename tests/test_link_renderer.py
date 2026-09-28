from link_renderer import GithubLinks, Location, ObsidianLinks, OutputProfile

BASE = "https://example.atlassian.net"
KEYS = {"PRODUCT-18742", "MGD-11951"}


def obsidian():
    return ObsidianLinks(BASE, KEYS)


def github():
    return GithubLinks(BASE, KEYS)


# --- Obsidian: location never matters ---------------------------------------

def test_obsidian_issue_link_is_a_wikilink():
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.issue("PRODUCT-18742") == "[[PRODUCT-18742]]"


def test_obsidian_unexported_key_falls_back_to_jira_url():
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.issue("FOO-1") == f"[FOO-1]({BASE}/browse/FOO-1)"


def test_obsidian_image_and_attachment():
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.image("flow.png") == "![[flow.png]]"
    assert at.attachment("spec.pdf") == "[[spec.pdf]]"


def test_obsidian_index_link():
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.index("PRODUCT-18742-index") == "[[PRODUCT-18742-index]]"


# --- GitHub: relative paths derived from the location ------------------------

def test_github_ticket_to_sibling_ticket():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.issue("PRODUCT-18742") == "[PRODUCT-18742](../PRODUCT-18742/PRODUCT-18742.md)"


def test_github_index_to_ticket():
    at = github().at(Location.index())
    assert at.issue("MGD-11951") == "[MGD-11951](MGD-11951/MGD-11951.md)"


def test_github_unexported_key_falls_back_to_jira_url():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.issue("FOO-1") == f"[FOO-1]({BASE}/browse/FOO-1)"


def test_github_ticket_to_index():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.index("PRODUCT-18742-index") == "[PRODUCT-18742-index](../PRODUCT-18742-index.md)"


def test_github_index_to_registry():
    at = github().at(Location.index())
    assert at.index("export-index") == "[export-index](../export-index.md)"


def test_github_registry_to_import_index():
    at = github().at(Location.root())
    assert at.index("PRODUCT-18742-index") == (
        "[PRODUCT-18742-index](PRODUCT-18742/PRODUCT-18742-index.md)"
    )


def test_github_image_is_relative_to_the_ticket():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.image("flow.png") == "![flow.png](attachments/flow.png)"


def test_github_attachment_link():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.attachment("spec.pdf") == "[spec.pdf](attachments/spec.pdf)"


def test_github_external_file_link_with_size():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.external_file("archive.zip", f"{BASE}/attachment/98123", 11_744_051) == (
        f"[archive.zip]({BASE}/attachment/98123) (11.2 MB)"
    )


# --- Prose mentions vs structural links --------------------------------------

def test_obsidian_prose_mention_stays_a_wikilink_when_unexported():
    """Obsidian resolves wikilinks by filename across the whole vault, so a key
    mentioned in prose links to a ticket exported by a *different* import."""
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.prose_issue("PRODUCT-18742") == "[[PRODUCT-18742]]"
    assert at.prose_issue("FOO-1") == "[[FOO-1]]"


def test_github_prose_mention_matches_structural_rendering():
    """GitHub has no vault-wide resolution, so prose and structure agree."""
    at = github().at(Location.ticket("MGD-11951"))
    assert at.prose_issue("PRODUCT-18742") == "[PRODUCT-18742](../PRODUCT-18742/PRODUCT-18742.md)"
    assert at.prose_issue("FOO-1") == f"[FOO-1]({BASE}/browse/FOO-1)"


# --- Review Focus 1: filenames that break markdown links ---------------------

def test_github_encodes_parentheses_in_filenames():
    """Real vault data contains SupportArchiveD2DFE639(1).zip."""
    at = github().at(Location.ticket("MGD-11951"))
    assert at.attachment("SupportArchiveD2DFE639(1).zip") == (
        "[SupportArchiveD2DFE639(1).zip](attachments/SupportArchiveD2DFE639%281%29.zip)"
    )


def test_github_encodes_spaces_in_filenames():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.image("my screenshot.png") == (
        "![my screenshot.png](attachments/my%20screenshot.png)"
    )


def test_obsidian_leaves_parentheses_alone():
    """Wikilinks are not URLs; encoding would break them."""
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.attachment("SupportArchiveD2DFE639(1).zip") == "[[SupportArchiveD2DFE639(1).zip]]"


# --- Table escaping ----------------------------------------------------------

def test_table_cell_escapes_pipes_in_both_styles():
    for renderer in (obsidian(), github()):
        at = renderer.at(Location.index())
        assert at.table_cell("[[a|b]]") == "[[a\\|b]]"


# --- Profiles ----------------------------------------------------------------

def test_obsidian_profile_defaults():
    profile = OutputProfile.for_style("obsidian", BASE, KEYS)
    assert profile.renderer.style == "obsidian"
    assert profile.inline_comments is False
    assert profile.download_allowlist is None


def test_github_profile_defaults():
    profile = OutputProfile.for_style("github", BASE, KEYS)
    assert profile.renderer.style == "github"
    assert profile.inline_comments is True
    assert "png" in profile.download_allowlist
    assert "zip" not in profile.download_allowlist


# --- Aliased index links (the registry's "<ID>-index shown as <ID>" rows) ----

def test_obsidian_index_alias_uses_wikilink_alias_syntax():
    at = obsidian().at(Location.root())
    assert at.index("PRODUCT-1-index", alias="PRODUCT-1") == "[[PRODUCT-1-index|PRODUCT-1]]"


def test_github_index_alias_becomes_the_link_text():
    at = github().at(Location.root())
    assert at.index("PRODUCT-1-index", alias="PRODUCT-1") == (
        "[PRODUCT-1](PRODUCT-1/PRODUCT-1-index.md)"
    )


# ---------------------------------------------------------------------------
# Regressions found in review (2026-09-28): only the path half of a markdown
# link was sanitised; the text half and external URLs were passed through raw.
# ---------------------------------------------------------------------------

def test_github_escapes_brackets_in_link_text():
    at = github().at(Location.ticket("MGD-2"))
    assert at.attachment("a]b.png") == "[a\\]b.png](attachments/a%5Db.png)"
    assert at.image("r[1].png") == "![r\\[1\\].png](attachments/r%5B1%5D.png)"


def test_external_file_escapes_brackets_in_link_text():
    at = github().at(Location.ticket("MGD-2"))
    out = at.external_file("r[v2].zip", "https://ex.net/a/1", 2048)
    assert out == "[r\\[v2\\].zip](https://ex.net/a/1) (2.0 KB)"


def test_external_file_escapes_link_breaking_chars_in_the_url():
    at = github().at(Location.ticket("MGD-2"))
    out = at.external_file("f.zip", "https://ex.net/a (1).zip")
    assert out == "[f.zip](https://ex.net/a%20%281%29.zip)"


def test_external_file_does_not_double_encode_a_percent():
    at = github().at(Location.ticket("MGD-2"))
    out = at.external_file("f.zip", "https://ex.net/a%20b.zip")
    assert out == "[f.zip](https://ex.net/a%20b.zip)"


def test_obsidian_wikilinks_are_left_alone():
    """Vault output must stay byte-identical; wikilinks cannot escape brackets."""
    at = obsidian().at(Location.ticket("MGD-2"))
    assert at.attachment("a]b.png") == "[[a]b.png]]"
    assert at.image("r[1].png") == "![[r[1].png]]"


# --- human_size boundaries and the unknown-style guard -----------------------

def test_human_size_boundaries():
    from link_renderer import human_size
    assert human_size(0) == "0 B"
    assert human_size(1023) == "1023 B"
    assert human_size(1024) == "1.0 KB"
    assert human_size(1024 ** 2) == "1.0 MB"
    assert human_size(1024 ** 3) == "1.0 GB"
    # Nothing above GB, so a huge file stays readable rather than wrapping.
    assert human_size(5 * 1024 ** 4) == "5120.0 GB"


def test_a_zero_byte_attachment_shows_no_size():
    at = github().at(Location.ticket("MGD-1"))
    assert at.external_file("empty.log", "https://ex.net/1", 0) == (
        "[empty.log](https://ex.net/1)"
    )


def test_unknown_style_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="unknown link style"):
        OutputProfile.for_style("markdown", BASE)
