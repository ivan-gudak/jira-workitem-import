"""
Graph walker module.
Traverses Jira issue links and Epic hierarchies to collect the full workitem graph.
"""

from dataclasses import dataclass, field
from typing import Any

from config import ALL_FIELD_IDS


@dataclass
class IssueNode:
    """A node in the workitem graph."""
    key: str
    issue: Any  # jira.Issue object
    role: str   # "root", "linked", "epic_child"
    links: list[tuple[str, str, str]] = field(default_factory=list)  # (link_type, direction, target_key)


class GraphWalker:
    """Walks the Jira issue graph starting from a root workitem."""

    def __init__(self, jira_client: Any):
        self.jira = jira_client
        self.nodes: dict[str, IssueNode] = {}  # key -> IssueNode

    def walk(self, root_key: str) -> dict[str, IssueNode]:
        """
        Walk the full graph:
        1. Fetch root issue
        2. Fetch all directly linked issues (all link types, 1 level)
        3. For every Epic in the set, recursively fetch the full child tree
        """
        print(f"[1/3] Fetching root issue: {root_key}")
        root = self._fetch_issue(root_key)
        if not root:
            raise ValueError(f"Could not fetch issue {root_key}")
        self._add_node(root_key, root, "root")

        # Step 2: direct links of root (1 level, all link types)
        print(f"[2/3] Fetching directly linked issues...")
        for key in self._collect_links(root):
            if key not in self.nodes:
                issue = self._fetch_issue(key)
                if issue:
                    self._add_node(key, issue, "linked")

        # Step 2b: find children via legacy Parent Link field (cf[17801]).
        # Older Jira items store the hierarchy on the child issue, not in issuelinks.
        for issue in self._search_jql_safe(f'cf[17801] = {root_key}'):
            if issue.key not in self.nodes:
                self._add_node(issue.key, issue, "linked")

        # Step 3: for every Epic in the set, recursively fetch full child tree
        print(f"[3/3] Traversing Epic hierarchies...")
        epics = [k for k, n in self.nodes.items() if self._is_epic(n.issue)]
        for epic_key in epics:
            print(f"  Epic: {epic_key}")
            self._fetch_epic_children(epic_key)

        print(f"  Total issues collected: {len(self.nodes)}")
        return self.nodes

    def _fetch_issue(self, key: str) -> Any | None:
        try:
            issue = self.jira.issue(key, fields=ALL_FIELD_IDS)
            print(f"  Fetched: {issue.key} - {issue.fields.summary}")
            return issue
        except Exception as e:
            print(f"  Warning: Could not fetch {key}: {e}")
            return None

    def _add_node(self, key: str, issue: Any, role: str) -> IssueNode:
        links = self._extract_links(issue)
        node = IssueNode(key=key, issue=issue, role=role, links=links)
        self.nodes[key] = node
        return node

    def _extract_links(self, issue: Any) -> list[tuple[str, str, str]]:
        """Extract (link_type, direction, target_key) from issue links."""
        links = []
        issue_links = getattr(issue.fields, 'issuelinks', None) or []
        for link in issue_links:
            if hasattr(link, 'outwardIssue') and link.outwardIssue:
                link_type = getattr(link.type, 'outward', 'relates to')
                links.append((link_type, "outward", link.outwardIssue.key))
            elif hasattr(link, 'inwardIssue') and link.inwardIssue:
                link_type = getattr(link.type, 'inward', 'relates to')
                links.append((link_type, "inward", link.inwardIssue.key))
        return links

    def _collect_links(self, issue: Any) -> list[str]:
        """Collect all directly linked issue keys."""
        keys = []
        issue_links = getattr(issue.fields, 'issuelinks', None) or []
        for link in issue_links:
            if hasattr(link, 'outwardIssue') and link.outwardIssue:
                keys.append(link.outwardIssue.key)
            elif hasattr(link, 'inwardIssue') and link.inwardIssue:
                keys.append(link.inwardIssue.key)
        return keys

    @staticmethod
    def _is_epic(issue: Any) -> bool:
        issue_type = getattr(issue.fields, 'issuetype', None)
        return issue_type and getattr(issue_type, 'name', '').lower() == 'epic'

    def _fetch_epic_children(self, epic_key: str) -> None:
        """Recursively fetch all children of an Epic via JQL."""
        # Include cf[17801] for older Jira items that store the hierarchy via Parent Link
        jql = f'"Epic Link" = {epic_key} OR parent = {epic_key} OR cf[17801] = {epic_key}'
        children = self._search_jql(jql)

        for child in children:
            if child.key not in self.nodes:
                self._add_node(child.key, child, "epic_child")
                # Recurse: this child might have sub-tasks
                self._fetch_subtasks(child.key)

    def _fetch_subtasks(self, parent_key: str) -> None:
        """Recursively fetch sub-tasks (children) of a given issue."""
        jql = f'parent = {parent_key}'
        children = self._search_jql(jql)

        for child in children:
            if child.key not in self.nodes:
                self._add_node(child.key, child, "epic_child")
                self._fetch_subtasks(child.key)

    def _search_jql_safe(self, jql: str) -> list:
        """Run a JQL search, returning an empty list on error."""
        try:
            return self._search_jql(jql)
        except Exception as e:
            print(f"  Warning: JQL query failed ({jql[:80]}): {e}")
            return []

    def _search_jql(self, jql: str) -> list:
        """Run a JQL search and return all results."""
        results = []
        start = 0
        while True:
            batch = self.jira.search_issues(jql, fields=ALL_FIELD_IDS, startAt=start, maxResults=50)
            if not batch:
                break
            results.extend(batch)
            if len(results) >= batch.total:
                break
            start += len(batch)
        return results
