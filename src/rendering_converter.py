"""
A markup converter that renders issue keys through a link renderer.

`jira_markup_converter.py` is vendored — a byte-identical copy lives in the
sibling jira-bulk-import project, and tests/test_jira_markup_converter.py
guards the two against drifting apart. So the renderer hook lives here, in a
subclass, rather than as a parameter threaded through the shared file.

Overriding `_format_issue_link` covers every site that renders a key: the bare
key pass, both smart-link forms, and wiki-table cells (which are converted
before the main link pass and so never reach it).
"""

from jira_markup_converter import JiraMarkupConverter


class RenderingConverter(JiraMarkupConverter):
    """Converts Jira markup, rendering issue keys through a bound renderer."""

    def __init__(self, jira_base_url: str, links):
        """`links` is a renderer already bound to the file being written."""
        super().__init__(jira_base_url)
        self.links = links

    def _format_issue_link(self, key: str) -> str:
        """A key in body text is a mention, not a structural link — under
        Obsidian it stays a wikilink even for keys outside this export."""
        return self.links.prose_issue(key)
