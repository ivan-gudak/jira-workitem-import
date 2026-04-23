"""
Comments handler module.
Fetches and formats Jira comments as markdown.
"""

from datetime import datetime
from jira_markup_converter import JiraMarkupConverter
from field_formatter import FieldFormatter


class CommentsHandler:
    """Handles fetching and formatting of Jira comments."""

    def __init__(self, jira_base_url: str, attachment_handler=None):
        self.converter = JiraMarkupConverter(jira_base_url)
        self.formatter = FieldFormatter()
        self.attachment_handler = attachment_handler

    def fetch_and_format_comments(self, issue) -> str:
        """Fetch and format all comments from an issue."""
        if not hasattr(issue.fields, 'comment'):
            return f"# Comments for {issue.key}\n\n**Ticket:** [[{issue.key}]]\n\n*No comments*\n"

        comments = issue.fields.comment.comments if hasattr(issue.fields.comment, 'comments') else []
        if not comments:
            return f"# Comments for {issue.key}\n\n**Ticket:** [[{issue.key}]]\n\n*No comments*\n"

        lines = [f"# Comments for {issue.key}", "",
                 f"**Ticket:** [[{issue.key}]]", "",
                 f"Total comments: {len(comments)}", "", "---", ""]
        for i, comment in enumerate(comments, 1):
            lines.append(self._format_comment(i, comment))
            lines.append("")
        return '\n'.join(lines)

    def _format_comment(self, number: int, comment) -> str:
        lines = [f"## Comment #{number}", ""]

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
