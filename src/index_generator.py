"""
Index generator module.
Generates export-index.md with Obsidian wikilinks and pipe-escaped table cells.
"""

from pathlib import Path
from graph_walker import IssueNode
from config import JIRA_BASE_URL


def _pipe_escape(text: str) -> str:
    """Escape pipe characters for use inside markdown table cells."""
    return text.replace("|", "\\|")


def _wikilink(key: str, nodes: dict[str, IssueNode]) -> str:
    """[[KEY]] if in export, else Jira URL link."""
    if key in nodes:
        return f"[[{key}]]"
    return f"[{key}]({JIRA_BASE_URL}/browse/{key})"


def _wikilink_table(key: str, nodes: dict[str, IssueNode]) -> str:
    """Wikilink safe for table cells (pipe-escaped)."""
    return _pipe_escape(_wikilink(key, nodes))


def generate_import_index(data_dir: Path, nodes: dict[str, IssueNode], root_key: str) -> str:
    """Generate per-import index content (e.g., PRODUCT-12345-index.md)."""
    lines = [f"# Export Index: {root_key}", "", "**Main Index:** [[export-index]]", ""]

    # Summary table
    lines.append("## All Exported Work Items")
    lines.append("")
    lines.append("| Key | Type | Status | Summary | Role |")
    lines.append("| --- | --- | --- | --- | --- |")

    for key in _sorted_keys(nodes, root_key):
        node = nodes[key]
        issue = node.issue
        itype = getattr(issue.fields.issuetype, 'name', '') if issue.fields.issuetype else ''
        status = getattr(issue.fields.status, 'name', '') if issue.fields.status else ''
        summary = _pipe_escape(getattr(issue.fields, 'summary', '') or '')
        link = _wikilink_table(key, nodes)
        lines.append(f"| {link} | {itype} | {status} | {summary} | {node.role} |")

    lines.append("")

    # Relationship map
    lines.append("## Relationships")
    lines.append("")

    for key in _sorted_keys(nodes, root_key):
        node = nodes[key]
        if not node.links:
            continue
        lines.append(f"### {key}")
        lines.append("")
        for link_type, direction, target in node.links:
            arrow = "→" if direction == "outward" else "←"
            target_link = _wikilink(target, nodes)
            lines.append(f"- {arrow} **{link_type}** {target_link}")
        lines.append("")

    # Epic hierarchy
    epics = [k for k, n in nodes.items() if _is_epic(n.issue)]
    if epics:
        lines.append("## Epic Hierarchy")
        lines.append("")
        for epic_key in epics:
            epic_summary = getattr(nodes[epic_key].issue.fields, 'summary', '')
            lines.append(f"### [[{epic_key}]]: {epic_summary}")
            lines.append("")
            children = [k for k, n in nodes.items()
                        if n.role == "epic_child" and _parent_of(n.issue) == epic_key]
            if children:
                _render_tree(lines, nodes, children, indent=0)
            else:
                lines.append("_No children found in export._")
            lines.append("")

    # Stats
    lines.append("## Statistics")
    lines.append("")
    lines.append(f"- **Total issues exported:** {len(nodes)}")
    role_counts = {}
    for n in nodes.values():
        role_counts[n.role] = role_counts.get(n.role, 0) + 1
    for role, count in sorted(role_counts.items()):
        lines.append(f"- **{role}:** {count}")
    lines.append("")

    return '\n'.join(lines)


def _sorted_keys(nodes: dict[str, IssueNode], root_key: str) -> list[str]:
    """Root first, then linked, then epic children — alphabetical within each group."""
    order = {"root": 0, "linked": 1, "epic_child": 2}
    return sorted(nodes.keys(), key=lambda k: (order.get(nodes[k].role, 9), k))


def _is_epic(issue) -> bool:
    it = getattr(issue.fields, 'issuetype', None)
    return it and getattr(it, 'name', '').lower() == 'epic'


def _parent_of(issue) -> str | None:
    """Get the parent key of an issue (via parent field or Epic Link)."""
    parent = getattr(issue.fields, 'parent', None)
    if parent and hasattr(parent, 'key'):
        return parent.key
    epic_link = getattr(issue.fields, 'customfield_17801', None)
    if epic_link:
        return epic_link if isinstance(epic_link, str) else getattr(epic_link, 'key', None)
    return None


def _render_tree(lines: list, nodes: dict[str, IssueNode], keys: list[str], indent: int) -> None:
    """Render a tree of issues with indentation, using wikilinks."""
    for key in sorted(keys):
        node = nodes.get(key)
        if not node:
            continue
        prefix = "  " * indent + "- "
        summary = getattr(node.issue.fields, 'summary', '') or ''
        itype = getattr(node.issue.fields.issuetype, 'name', '') if node.issue.fields.issuetype else ''
        lines.append(f"{prefix}[[{key}]] ({itype}) — {summary}")
        children = [k for k, n in nodes.items()
                    if k != key and _parent_of(n.issue) == key]
        if children:
            _render_tree(lines, nodes, children, indent + 1)


def update_top_level_index(data_dir: Path) -> None:
    """Rewrite export-index.md listing all import subdirectories."""
    imports = []
    for subdir in sorted(data_dir.iterdir()):
        if not subdir.is_dir():
            continue
        index_files = list(subdir.glob("*-index.md"))
        if not index_files:
            continue
        root_key = subdir.name
        # Try to extract summary/type/status from the per-import index
        summary, itype, status = "", "", ""
        index_file = index_files[0]
        for line in index_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("| [[") or line.startswith("| \\[\\["):
                parts = [p.strip() for p in line.split("|")]
                # | link | type | status | summary | role |
                if len(parts) >= 6 and "root" in parts[5].lower():
                    itype = parts[2]
                    status = parts[3]
                    summary = parts[4]
                    break
        imports.append((root_key, itype, status, summary))

    lines = ["# Export Index", ""]
    if imports:
        lines.append("| Import | Type | Status | Summary |")
        lines.append("| --- | --- | --- | --- |")
        for root_key, itype, status, summary in imports:
            lines.append(f"| [[{root_key}-index\\|{root_key}]] | {itype} | {status} | {summary} |")
    else:
        lines.append("_No imports found._")
    lines.append("")

    (data_dir / "export-index.md").write_text("\n".join(lines), encoding="utf-8")
