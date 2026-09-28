from jira_markup_converter import JiraMarkupConverter
from link_renderer import GithubLinks, Location, ObsidianLinks
from rendering_converter import RenderingConverter

BASE_URL = "https://example.atlassian.net"


def plain():
    return JiraMarkupConverter(jira_base_url=BASE_URL)


def rendering(renderer_cls, keys):
    ctx = renderer_cls(BASE_URL, keys).at(Location.ticket("MGD-1"))
    return RenderingConverter(BASE_URL, ctx)


def test_plain_converter_is_unchanged():
    """The base class must stay byte-identical — 11 existing tests rely on it."""
    assert plain().convert("See PRODUCT-18503 for details") == "See [[PRODUCT-18503]] for details"


def test_github_uses_relative_path_for_exported_key():
    conv = rendering(GithubLinks, {"PRODUCT-18503"})
    out = conv.convert("See PRODUCT-18503 for details")
    assert out == "See [PRODUCT-18503](../PRODUCT-18503/PRODUCT-18503.md) for details"


def test_github_falls_back_for_unexported_key():
    conv = rendering(GithubLinks, set())
    out = conv.convert("See PRODUCT-18503 for details")
    assert out == f"See [PRODUCT-18503]({BASE_URL}/browse/PRODUCT-18503) for details"


def test_obsidian_keeps_wikilink_for_unexported_key():
    """A key in prose is a *mention*, not a structural link. Obsidian resolves
    wikilinks by filename across the whole vault, so [[KEY]] still reaches a
    ticket exported by another import — vault output stays as it is today."""
    conv = rendering(ObsidianLinks, {"OTHER-1"})
    out = conv.convert("See PRODUCT-18503 for details")
    assert out == "See [[PRODUCT-18503]] for details"


def test_github_does_not_reopen_the_bare_url_bug():
    """Regression guard for commit 5ddbd6d under the new style."""
    conv = rendering(GithubLinks, {"MGD-8605"})
    out = conv.convert(f"See {BASE_URL}/browse/MGD-8605 for details")
    assert out == f"See {BASE_URL}/browse/MGD-8605 for details"


def test_github_does_not_reopen_the_bracketed_marker_bug():
    """Regression guard for commit 1874c4d under the new style."""
    conv = rendering(GithubLinks, {"US-1"})
    out = conv.convert("### [US-1]: View OneAgent configuration state")
    assert out == "### [US-1]: View OneAgent configuration state"


def test_github_smart_link_uses_the_renderer():
    conv = rendering(GithubLinks, {"MGD-8605"})
    assert conv.convert("[MGD-8605|smart-link]") == "[MGD-8605](../MGD-8605/MGD-8605.md)"


def test_github_table_cell_smart_link_uses_the_renderer():
    """Wiki tables are converted before the main link pass and restored after,
    so cell content never reaches it — the override has to cover them too."""
    conv = rendering(GithubLinks, {"MGD-8605"})
    out = conv.convert(f"||Key||Note||\n|[MGD-8605|{BASE_URL}/browse/MGD-8605|smart-link]|hi|\n")
    assert "[MGD-8605](../MGD-8605/MGD-8605.md)" in out
    assert "[[" not in out


def test_generated_markdown_links_are_protected_from_relinkification():
    """A rendered link contains a key; it must not be linkified again."""
    conv = rendering(GithubLinks, {"MGD-8605"})
    out = conv.convert("MGD-8605 and MGD-8605")
    assert out.count("](../MGD-8605/MGD-8605.md)") == 2
    assert "[[" not in out
