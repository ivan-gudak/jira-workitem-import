"""GraphWalker on sites that lack a field its JQL names.

The Epic query ORs together "Epic Link", parent and cf[17801] (one site's
Parent Link field). Jira rejects a whole query that names a field it does not
know, so on any other site the Epic's children were lost along with the field
that does not exist -- and the error ended the run.
"""

from jira.exceptions import JIRAError

from graph_walker import GraphWalker


class FakeNamed:
    def __init__(self, name):
        self.name = name


class FakeLinkType:
    outward = "relates to"
    inward = "relates to"


class FakeLink:
    def __init__(self, key):
        self.type = FakeLinkType()
        self.outwardIssue = FakeIssue(key, "Task")


class FakeFields:
    def __init__(self, summary, type_name, links):
        self.summary = summary
        self.issuetype = FakeNamed(type_name)
        self.issuelinks = links


class FakeIssue:
    def __init__(self, key, type_name, links=()):
        self.key = key
        self.fields = FakeFields(f"{key} summary", type_name, [FakeLink(k) for k in links])


class FakeResults(list):
    @property
    def total(self):
        return len(self)


class FakeJira:
    """Answers JQL clause by clause, and rejects a query naming an unknown field."""

    def __init__(self, issues, children, unknown_fields=()):
        self.issues = {i.key: i for i in issues}
        self.children = children
        self.unknown_fields = unknown_fields
        self.queries = []

    def issue(self, key, fields=None):
        return self.issues[key]

    def search_issues(self, jql, fields=None, startAt=0, maxResults=50):
        self.queries.append(jql)
        for field in self.unknown_fields:
            if field in jql:
                raise JIRAError(status_code=400, text=f"Field '{field}' does not exist")
        found = {}
        for clause in jql.split(" OR "):
            for child in self.children.get(clause, ()):
                found[child.key] = child
        return FakeResults(found.values())


def _site(unknown_fields=()):
    return FakeJira(
        issues=[FakeIssue("ROOT-1", "Feature", links=["EPIC-1"]), FakeIssue("EPIC-1", "Epic")],
        children={"parent = EPIC-1": [FakeIssue("STORY-1", "Story")]},
        unknown_fields=unknown_fields,
    )


def test_epic_children_are_found_when_the_site_lacks_the_parent_link_field():
    nodes = GraphWalker(_site(unknown_fields=("cf[17801]",))).walk("ROOT-1")
    assert "STORY-1" in nodes
    assert nodes["STORY-1"].role == "epic_child"


def test_a_site_with_every_field_asks_once_per_epic():
    jira = _site()
    nodes = GraphWalker(jira).walk("ROOT-1")
    assert nodes["STORY-1"].role == "epic_child"
    epic_queries = [q for q in jira.queries if "EPIC-1" in q]
    assert len(epic_queries) == 1
