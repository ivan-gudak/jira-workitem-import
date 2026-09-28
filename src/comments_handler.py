"""
Comments handler module.
Fetches and formats Jira comments as markdown.
"""

from datetime import datetime
from jira_markup_converter import JiraMarkupConverter
from rendering_converter import RenderingConverter
from field_formatter import FieldFormatter


class CommentsHandler:
    """Handles fetching and formatting of Jira comments."""

    def __init__(self, jira_base_url: str, attachment_handler=None, links=None):
        """`links` is a renderer bound to the file these comments land in."""
        self.converter = (RenderingConverter(jira_base_url, links) if links is not None
                          else JiraMarkupConverter(jira_base_url))
        self.formatter = FieldFormatter()
        self.attachment_handler = attachment_handler
        self.links = links

    def _comments_of(self, issue) -> list:
        field = getattr(issue.fields, 'comment', None)
        if field is None:
            return []
        return getattr(field, 'comments', []) or []

    def format_comments_body(self, issue, level: int = 2) -> str:
        """The comments themselves, headings at `level`. For inlining."""
        comments = self._comments_of(issue)
        if not comments:
            return "*No comments*\n"
        lines = []
        for i, comment in enumerate(comments, 1):
            lines.append(self._format_comment(i, comment, level))
            lines.append("")
        return '\n'.join(lines)

    def format_comments_document(self, issue) -> str:
        """The standalone <KEY>-comments.md file."""
        comments = self._comments_of(issue)
        ticket = self.links.issue(issue.key) if self.links is not None else f"[[{issue.key}]]"
        if not comments:
            return f"# Comments for {issue.key}\n\n**Ticket:** {ticket}\n\n*No comments*\n"
        header = [f"# Comments for {issue.key}", "",
                  f"**Ticket:** {ticket}", "",
                  f"Total comments: {len(comments)}", "", "---", ""]
        # join(header) stops at the trailing "", so the separator before the
        # first comment has to be added back explicitly.
        return '\n'.join(header) + "\n" + self.format_comments_body(issue, level=2)

    # Retained for callers that predate the split.
    fetch_and_format_comments = format_comments_document

    def _format_comment(self, number: int, comment, level: int = 2) -> str:
        lines = [f"{'#' * level} Comment #{number}", ""]

        author = self.formatter.format_user(comment.author) if hasattr(comment, 'author') else "Unknown"
        lines.append(f"**Author:** {author}")

        if hasattr(comment, 'created'):
            lines.append(f"**Created:** {self._format_dt(comment.created)}")

        if hasattr(comment, 'updated') and hasattr(comment, 'created') and comment.updated != comment.created:
            lines.append(f"**Updated:** {self._format_dt(comment.updated)}")

        lines.append("")

        if hasattr(comment, 'body') and comment.body:
            body = self.converter.convert(comment.body)
            if self.attachment_handler:
                body = self.attachment_handler.replace_attachment_references(body)
            lines.append(body)
        else:
            lines.append("*(Empty comment)*")

        lines.extend(["", "---"])
        return '\n'.join(lines)

    @staticmethod
    def _format_dt(dt_str: str) -> str:
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return dt_str
