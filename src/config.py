"""
Configuration module for Jira workitem exporter.
Contains field mappings and constants.
"""

# Jira base URL
JIRA_BASE_URL = "https://dt-rnd.atlassian.net"

# Field mappings: Display Name -> Jira Field ID
FIELD_MAPPING = {
    "Architecture Assignee": "customfield_21107",
    "Assignee": "assignee",
    "Breaking Change": "customfield_19500",
    "Comments": "comment",
    "Description": "description",
    "Execution Assignee": "customfield_19400",
    "Fix versions": "fixVersions",
    "Issue Type": "issuetype",
    "Key": "key",
    "Labels": "labels",
    "Linked Issues": "issuelinks",
    "Parent": "parent",
    "Parent Link": "customfield_17801",
    "Project": "project",
    "Rank": "customfield_12800",
    "Release Notes Summary": "customfield_15000",
    "Release Notes Title": "customfield_19701",
    "Release Versions": "customfield_20300",
    "Relevant for release notes": "customfield_15900",
    "Reporter": "reporter",
    "Resolution": "resolution",
    "Sprint": "sprint",
    "Status": "status",
    "Status details": "customfield_19200",
    "Story Points": "customfield_10004",
    "Summary": "summary",
    "Team": "customfield_17800",
    "owning Program": "customfield_18700",
    "tracking Programs": "customfield_18701"
}

# Fields to include in export (ordered)
EXPORT_FIELDS = [
    "Key",
    "Issue Type",
    "Summary",
    "Status",
    "Assignee",
    "Reporter",
    "Architecture Assignee",
    "Execution Assignee",
    "Team",
    "Project",
    "Parent",
    "Parent Link",
    "Linked Issues",
    "Fix versions",
    "Sprint",
    "Rank",
    "owning Program",
    "tracking Programs",
    "Labels",
    "Resolution",
    "Status details",
    "Story Points",
    "Relevant for release notes",
    "Release Versions",
    "Breaking Change",
    "Release Notes Title",
    "Release Notes Summary",
]

# All Jira field IDs to fetch in a single API call
ALL_FIELD_IDS = ",".join(set(FIELD_MAPPING.values())) + ",attachment,comment"
