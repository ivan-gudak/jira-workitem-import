from jira_markup_converter import JiraMarkupConverter


def make_converter():
    return JiraMarkupConverter(jira_base_url="https://example.atlassian.net")


def test_bracketed_id_marker_is_not_wikilink_wrapped():
    conv = make_converter()
    out = conv.convert("### [US-1]: View OneAgent configuration state")
    assert out == "### [US-1]: View OneAgent configuration state"
    assert "[[US-1]]" not in out
    assert "[[[US-1]]]" not in out


def test_bare_issue_key_is_still_linkified():
    conv = make_converter()
    out = conv.convert("See PRODUCT-18503 for details")
    assert out == "See [[PRODUCT-18503]] for details"
