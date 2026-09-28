from comments_handler import CommentsHandler
from link_renderer import GithubLinks, Location

BASE = "https://example.atlassian.net"

#: Exactly what fetch_and_format_comments produced before the split. Vault-mode
#: output must not change, and the join is easy to get wrong by one newline.
GOLDEN_DOCUMENT = (
    "# Comments for MGD-1\n"
    "\n"
    "**Ticket:** [[MGD-1]]\n"
    "\n"
    "Total comments: 2\n"
    "\n"
    "---\n"
    "\n"
    "## Comment #1\n"
    "\n"
    "**Author:** Jane Doe\n"
    "**Created:** 2026-03-04 10:00:00\n"
    "\n"
    "Looks good.\n"
    "\n"
    "---\n"
    "\n"
    "## Comment #2\n"
    "\n"
    "**Author:** Jane Doe\n"
    "**Created:** 2026-03-04 10:00:00\n"
    "\n"
    "Second.\n"
    "\n"
    "---\n"
)


class FakeComment:
    def __init__(self, body, author="Jane Doe", created="2026-03-04T10:00:00.000+0000"):
        self.body = body
        self.author = type("A", (), {"displayName": author})()
        self.created = created
        self.updated = created


class FakeCommentField:
    def __init__(self, comments):
        self.comments = comments


class FakeFields:
    def __init__(self, comments=None):
        if comments is not None:
            self.comment = FakeCommentField(comments)


class FakeIssue:
    def __init__(self, key="MGD-1", comments=None):
        self.key = key
        self.fields = FakeFields(comments)


def test_document_form_is_byte_identical_to_the_previous_output():
    issue = FakeIssue(comments=[FakeComment("Looks good."), FakeComment("Second.")])
    assert CommentsHandler(BASE).format_comments_document(issue) == GOLDEN_DOCUMENT


def test_document_form_keeps_the_title_and_backlink():
    issue = FakeIssue(comments=[FakeComment("Looks good.")])
    out = CommentsHandler(BASE).format_comments_document(issue)
    assert out.startswith("# Comments for MGD-1")
    assert "**Ticket:**" in out
    assert "## Comment #1" in out


def test_fragment_form_has_no_title_and_no_backlink():
    issue = FakeIssue(comments=[FakeComment("Looks good.")])
    out = CommentsHandler(BASE).format_comments_body(issue, level=3)
    assert "# Comments for" not in out
    assert "**Ticket:**" not in out
    assert "### Comment #1" in out


def test_fragment_demotes_headings_to_the_requested_level():
    issue = FakeIssue(comments=[FakeComment("a"), FakeComment("b")])
    out = CommentsHandler(BASE).format_comments_body(issue, level=4)
    assert "#### Comment #1" in out
    assert "#### Comment #2" in out
    # "#### Comment" contains "## Comment", so test line starts, not substrings.
    assert not any(line.startswith("## Comment") for line in out.splitlines())


def test_fragment_with_no_comments():
    issue = FakeIssue(comments=[])
    out = CommentsHandler(BASE).format_comments_body(issue, level=3)
    assert out.strip() == "*No comments*"


def test_fragment_when_the_comment_field_is_absent():
    issue = FakeIssue()
    out = CommentsHandler(BASE).format_comments_body(issue, level=3)
    assert out.strip() == "*No comments*"


def test_document_form_wraps_the_fragment():
    issue = FakeIssue(comments=[FakeComment("Looks good.")])
    handler = CommentsHandler(BASE)
    assert "Looks good." in handler.format_comments_body(issue, level=2)
    assert "Looks good." in handler.format_comments_document(issue)


def test_legacy_method_name_still_works():
    """fetch_and_format_comments is the name _export_one used; keep it."""
    issue = FakeIssue(comments=[FakeComment("Looks good.")])
    out = CommentsHandler(BASE).fetch_and_format_comments(issue)
    assert out.startswith("# Comments for MGD-1")


def test_github_renderer_reaches_the_backlink_and_the_body():
    at = GithubLinks(BASE, {"MGD-1", "MGD-2"}).at(Location.ticket("MGD-1"))
    issue = FakeIssue(comments=[FakeComment("Blocked by MGD-2")])
    handler = CommentsHandler(BASE, links=at)
    doc = handler.format_comments_document(issue)
    assert "**Ticket:** [MGD-1](../MGD-1/MGD-1.md)" in doc
    assert "[MGD-2](../MGD-2/MGD-2.md)" in doc
    assert "[[" not in doc
