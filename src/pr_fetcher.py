"""
Pull request fetcher module.
Uses Jira's dev-status REST API to get linked Bitbucket PRs.
"""

import requests
from typing import Any
from dataclasses import dataclass


@dataclass
class PullRequest:
    title: str
    url: str
    status: str
    repo: str
    source_branch: str
    target_branch: str
    author: str


def fetch_pull_requests(jira_client: Any, issue_id: str) -> list[PullRequest]:
    """
    Fetch PRs linked to a Jira issue via the dev-status API.

    Args:
        jira_client: Authenticated JIRA client (used for server URL and auth)
        issue_id: The internal Jira issue ID (numeric), not the key.

    Returns:
        List of PullRequest objects.
    """
    url = (
        f"{jira_client._options['server']}"
        f"/rest/dev-status/latest/issue/detail"
        f"?issueId={issue_id}&applicationType=stash&dataType=pullrequest"
    )

    try:
        resp = jira_client._session.get(url)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    Warning: Could not fetch PR info: {e}")
        return []

    prs = []
    for detail in data.get("detail", []):
        for pr_data in detail.get("pullRequests", []):
            prs.append(PullRequest(
                title=pr_data.get("name", ""),
                url=pr_data.get("url", ""),
                status=pr_data.get("status", ""),
                repo=pr_data.get("repositoryName", detail.get("repository", {}).get("name", "")),
                source_branch=pr_data.get("source", {}).get("branch", "") if isinstance(pr_data.get("source"), dict) else pr_data.get("source", ""),
                target_branch=pr_data.get("destination", {}).get("branch", "") if isinstance(pr_data.get("destination"), dict) else pr_data.get("destination", ""),
                author=pr_data.get("author", {}).get("name", "") if isinstance(pr_data.get("author"), dict) else "",
            ))
    return prs


def format_prs_markdown(prs: list[PullRequest]) -> str:
    """Format pull requests as a markdown section."""
    if not prs:
        return ""
    lines = ["## Pull Requests", ""]
    for pr in prs:
        status_badge = f"**{pr.status.upper()}**" if pr.status else ""
        lines.append(f"- [{pr.title}]({pr.url}) {status_badge}")
        details = []
        if pr.repo:
            details.append(f"Repo: `{pr.repo}`")
        if pr.source_branch:
            details.append(f"Branch: `{pr.source_branch}` → `{pr.target_branch}`")
        if details:
            lines.append(f"  - {' | '.join(details)}")
    lines.append("")
    return '\n'.join(lines)
