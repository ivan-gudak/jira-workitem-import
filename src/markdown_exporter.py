"""
Markdown exporter module.
Exports each workitem as <KEY>.md + comments.md + attachments/, with PII scrubbing.
All links use Obsidian wikilinks. Each file links back to the index.
"""

import shutil
from pathlib import Path
from typing import Any

from config import FIELD_MAPPING, EXPORT_FIELDS, JIRA_BASE_URL
from jira_markup_converter import JiraMarkupConverter
from field_formatter import FieldFormatter
from attachment_handler import AttachmentHandler
from comments_handler import CommentsHandler
from pii_scrubber import PiiScrubber
from pr_fetcher import fetch_pull_requests, format_prs_markdown
from graph_walker import IssueNode


class MarkdownExporter:
    """Exports workitems to markdown with PII scrubbing and Obsidian wikilinks."""

    def __init__(self, jira_client: Any, data_dir: Path, scrubber: PiiScrubber, root_key: str = "", field_names: dict | None = None):
        self.jira = jira_client
        self.data_dir = data_dir
        self.scrubber = scrubber
        self.root_key = root_key
        self.field_names = field_names or {}
        self.converter = JiraMarkupConverter(JIRA_BASE_URL)
        self.formatter = FieldFormatter()

    @staticmethod
    def _is_empty_description(description: Any) -> bool:
        """True when description is None, empty, or whitespace-only."""
        return not description or not str(description).strip()

    def _format_additional_value(self, value: Any, att_handler: Any = None) -> str | None:
        """Format one custom-field value for the Details section. Returns None if empty."""
        if isinstance(value, str):
            if not value.strip():
                return None
            converted = self.converter.convert(value)
            if att_handler is not None:
                converted = att_handler.replace_attachment_references(converted)
            return self.scrubber.scrub_text(converted).strip() or None
        if isinstance(value, list):
            parts = []
            for item in value:
                if hasattr(item, 'displayName'):
                    parts.append(self.scrubber.anonymize_name(item.displayName))
                else:
                    parts.append(self.formatter.format_custom_field(item))
            parts = [p for p in parts if p]
            return ', '.join(parts) if parts else None
        if hasattr(value, 'displayName'):
            return self.scrubber.anonymize_name(value.displayName)
        return self.formatter.format_custom_field(value)

    def _generate_additional_fields(self, issue: Any, att_handler: Any = None) -> str | None:
        """Render populated custom fields not already shown elsewhere, as a Details section.

        Used as a fallback when the standard description is empty/missing.
        """
        excluded = set(FIELD_MAPPING.values())
        lines = []
        for field_id, display_name in sorted(self.field_names.items(), key=lambda kv: kv[1]):
            if not field_id.startswith('customfield_'):
                continue
            if field_id in excluded:
                continue
            value = getattr(issue.fields, field_id, None)
            if value is None:
                continue
            formatted = self._format_additional_value(value, att_handler)
            if not formatted:
                continue
            lines.append(f"### {display_name}")
            lines.append("")
            lines.append(formatted)
            lines.append("")
        if not lines:
            return None
        return "## Details\n\n" + "\n".join(lines).rstrip()

    def export_all(self, nodes: dict[str, IssueNode]) -> tuple[int, list[tuple[str, str]]]:
        """Export all nodes. Returns (success_count, [(key, error), ...])."""
        # First pass: register all user names for consistent PII mapping
        for node in nodes.values():
            self._register_users(node.issue)

        success, failed = 0, []
        for key, node in nodes.items():
            print(f"[{key}] Exporting...")
            try:
                self._export_one(node, nodes)
                success += 1
            except Exception as e:
                print(f"  ERROR: {e}")
                failed.append((key, str(e)))
        return success, failed

    def _register_users(self, issue: Any) -> None:
        """Pre-register all user displayNames for consistent anonymization."""
        for field_id in ("assignee", "reporter", "customfield_21107", "customfield_19400"):
            user = getattr(issue.fields, field_id, None)
            if user and hasattr(user, 'displayName'):
                self.scrubber.anonymize_name(user.displayName)

        comments = getattr(issue.fields, 'comment', None)
        if comments and hasattr(comments, 'comments'):
            for c in comments.comments:
                if hasattr(c, 'author') and hasattr(c.author, 'displayName'):
                    self.scrubber.anonymize_name(c.author.displayName)

        # Register people referenced in any custom field, for consistent User-N numbering
        for field_id in self.field_names:
            if not field_id.startswith('customfield_'):
                continue
            val = getattr(issue.fields, field_id, None)
            if val is None:
                continue
            items = val if isinstance(val, list) else [val]
            for item in items:
                if hasattr(item, 'displayName'):
                    self.scrubber.anonymize_name(item.displayName)

    def _export_one(self, node: IssueNode, all_nodes: dict[str, IssueNode]) -> None:
        """Export a single workitem."""
        issue = node.issue
        key = node.key
        item_dir = self.data_dir / key

        # Wipe previous export
        if item_dir.exists():
            shutil.rmtree(item_dir)
        item_dir.mkdir(parents=True)

        attachments_dir = item_dir / "attachments"
        att_handler = AttachmentHandler(self.jira, str(attachments_dir))

        # Download attachments
        print(f"  Downloading attachments...")
        images, others = att_handler.download_attachments(issue)

        # Generate main markdown
        md = self._generate_markdown(issue, node, att_handler, images, others, all_nodes)
        (item_dir / f"{key}.md").write_text(md, encoding="utf-8")
        print(f"  Written: {key}.md")

        # Generate comments
        comments_handler = CommentsHandler(JIRA_BASE_URL, att_handler)
        comments_md = comments_handler.fetch_and_format_comments(issue)
        comments_md = self.scrubber.scrub_text(comments_md)
        (item_dir / f"{key}-comments.md").write_text(comments_md, encoding="utf-8")
        print(f"  Written: {key}-comments.md")

    def _generate_markdown(self, issue: Any, node: IssueNode,
                           att_handler: AttachmentHandler,
                           images: list, others: list,
                           all_nodes: dict[str, IssueNode]) -> str:
        lines = []

        # Frontmatter
        lines.append(self._generate_frontmatter(issue))

        # Title
        summary = getattr(issue.fields, 'summary', 'Untitled')
        lines.append(f"# {issue.key}: {summary}")
        lines.append("")

        # Navigation: index backlink
        index_name = f"{self.root_key}-index" if self.root_key else "export-index"
        lines.append(f"**Index:** [[{index_name}]]")
        lines.append("")

        # Metadata
        lines.append("## Metadata")
        lines.append("")

        jira_url = f"{JIRA_BASE_URL}/browse/{issue.key}"
        lines.append(f"**Jira Link:** [{issue.key}]({jira_url})")

        issue_type = getattr(issue.fields, 'issuetype', None)
        if issue_type and hasattr(issue_type, 'name'):
            lines.append(f"**Type:** {issue_type.name}")

        status = getattr(issue.fields, 'status', None)
        if status and hasattr(status, 'name'):
            lines.append(f"**Status:** {status.name}")

        assignee = getattr(issue.fields, 'assignee', None)
        if assignee and hasattr(assignee, 'displayName'):
            lines.append(f"**Assignee:** {self.scrubber.anonymize_name(assignee.displayName)}")

        team = getattr(issue.fields, 'customfield_17800', None)
        if team:
            team_name = team.name if hasattr(team, 'name') else str(team)
            lines.append(f"**Team:** {team_name}")

        lines.append(f"**Role in export:** {node.role}")
        lines.append("")

        # Parent (wikilink if in export, Jira URL otherwise)
        parent = getattr(issue.fields, 'parent', None)
        if parent:
            parent_key = getattr(parent, 'key', None)
            if parent_key:
                lines.append(f"**Parent:** {self._wikilink(parent_key, all_nodes)}")
                lines.append("")

        # Status details
        status_details = getattr(issue.fields, 'customfield_19200', None)
        if status_details:
            lines.append("## Status Details")
            lines.append("")
            lines.append(self.scrubber.scrub_text(self.converter.convert(status_details)))
            lines.append("")

        # Description — or a Details fallback built from custom fields when empty
        description = getattr(issue.fields, 'description', None)
        if not self._is_empty_description(description):
            lines.append("## Description")
            lines.append("")
            converted = self.converter.convert(description)
            converted = att_handler.replace_attachment_references(converted)
            lines.append(self.scrubber.scrub_text(converted))
            lines.append("")
        else:
            details = self._generate_additional_fields(issue, att_handler)
            if details:
                lines.append(details)
                lines.append("")

        # Attachments
        if images or others:
            lines.append(att_handler.get_attachment_list_markdown(images, others))

        # Release notes
        release_title = getattr(issue.fields, 'customfield_19701', None)
        release_summary = getattr(issue.fields, 'customfield_15000', None)
        if release_title or release_summary:
            lines.append("## Release Notes")
            lines.append("")
            if release_title:
                lines.append(f"**Title:** {release_title}")
                lines.append("")
            if release_summary:
                lines.append("**Summary:**")
                lines.append("")
                lines.append(self.scrubber.scrub_text(self.converter.convert(release_summary)))
                lines.append("")

        # Linked issues (wikilinks for issues in export, Jira URLs for external)
        issue_links = getattr(issue.fields, 'issuelinks', None)
        if issue_links:
            grouped = self._group_links_as_wikilinks(issue_links, all_nodes)
            if grouped:
                lines.append("## Linked Issues")
                lines.append("")
                for link_type, wikilinks in sorted(grouped.items()):
                    lines.append(f"### {link_type}")
                    lines.append("")
                    for wl in wikilinks:
                        lines.append(f"- {wl}")
                    lines.append("")

        # Pull requests
        print(f"  Fetching pull requests...")
        prs = fetch_pull_requests(self.jira, issue.id)
        if prs:
            for pr in prs:
                if pr.author:
                    pr.author = self.scrubber.anonymize_name(pr.author) or pr.author
            lines.append(format_prs_markdown(prs))

        # Comments (embedded via Obsidian transclusion)
        lines.append("## Comments")
        lines.append("")
        lines.append(f"![[{issue.key}-comments]]")
        lines.append("")

        return '\n'.join(lines)

    @staticmethod
    def _wikilink(key: str, all_nodes: dict[str, IssueNode]) -> str:
        """Return [[KEY]] wikilink if key is in export, else Jira URL."""
        if key in all_nodes:
            return f"[[{key}]]"
        return f"[{key}]({JIRA_BASE_URL}/browse/{key})"

    def _group_links_as_wikilinks(self, links, all_nodes: dict[str, IssueNode]) -> dict[str, list[str]] | None:
        """Group linked issues by type, using wikilinks for exported issues."""
        if not links:
            return None
        grouped = {}
        for link in links:
            if hasattr(link, 'outwardIssue') and link.outwardIssue:
                issue = link.outwardIssue
                link_type = getattr(link.type, 'outward', 'relates to')
            elif hasattr(link, 'inwardIssue') and link.inwardIssue:
                issue = link.inwardIssue
                link_type = getattr(link.type, 'inward', 'relates to')
            else:
                continue
            key = getattr(issue, 'key', None)
            if key:
                grouped.setdefault(link_type, []).append(self._wikilink(key, all_nodes))
        return grouped if grouped else None

    def _generate_frontmatter(self, issue: Any) -> str:
        lines = ["---"]
        for field_name in EXPORT_FIELDS:
            field_id = FIELD_MAPPING.get(field_name)
            if not field_id:
                continue
            value = self._extract_field(issue, field_id)
            if value is not None:
                yaml_key = field_name.lower().replace(" ", "_")
                if field_id in ("assignee", "reporter", "customfield_21107", "customfield_19400"):
                    value = self.scrubber.anonymize_name(value) if isinstance(value, str) else value
                lines.append(f"{yaml_key}: {self._yaml_val(value)}")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _extract_field(self, issue: Any, field_id: str) -> Any:
        if field_id == "key":
            return issue.key
        try:
            value = getattr(issue.fields, field_id, None)
            if field_id == "parent":
                return self.formatter.format_parent(value)
            elif field_id in ("issuelinks", "customfield_19701", "customfield_15000", "customfield_19200"):
                return None
            elif field_id in ("assignee", "reporter", "customfield_21107", "customfield_19400"):
                return self.formatter.format_user(value)
            elif field_id in ("fixVersions", "labels"):
                return self.formatter.format_array(value)
            elif field_id in ("issuetype", "status", "project", "resolution"):
                return value.name if value and hasattr(value, "name") else None
            elif field_id.startswith("customfield_"):
                return self.formatter.format_custom_field(value)
            return value
        except AttributeError:
            return None

    @staticmethod
    def _yaml_val(value: Any) -> str:
        if value is None:
            return '""'
        if isinstance(value, str):
            return f'"{value.replace(chr(34), chr(92)+chr(34)).replace(chr(10), " ")}"'
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            if not value:
                return "[]"
            items = [f'"{i}"' if isinstance(i, str) else str(i) for i in value]
            return f"[{', '.join(items)}]"
        return f'"{str(value).replace(chr(34), chr(92)+chr(34)).replace(chr(10), " ")}"'
