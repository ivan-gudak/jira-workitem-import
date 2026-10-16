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


# --- Found in the review of the open-source port ------------------------------

class CloudLikeJira(FakeJira):
    """Like jira 3.10 on Jira Cloud: an int maxResults returns ONE page whose
    total is that page's length; maxResults=False fetches every page."""

    def search_issues(self, jql, fields=None, startAt=0, maxResults=50):
        found = super().search_issues(jql, fields)
        if maxResults is False:
            return found
        return FakeResults(list(found)[startAt:startAt + maxResults])


def test_an_epic_with_more_than_a_page_of_children_is_walked_completely():
    """Verified on the live site: the manual loop returned 50 of 196."""
    children = [FakeIssue(f"STORY-{i}", "Story") for i in range(120)]
    jira = CloudLikeJira(issues=[FakeIssue("ROOT-1", "Feature", links=["EPIC-1"]), FakeIssue("EPIC-1", "Epic")],
                         children={"parent = EPIC-1": children})
    nodes = GraphWalker(jira).walk("ROOT-1")
    assert sum(1 for key in nodes if key.startswith("STORY-")) == 120


def test_the_root_is_keyed_as_jira_spells_it():
    class CaseInsensitive(FakeJira):
        def issue(self, key, fields=None):
            return self.issues[key.upper()]

    nodes = GraphWalker(CaseInsensitive(issues=[FakeIssue("ROOT-1", "Feature")], children={})).walk("root-1")
    assert list(nodes) == ["ROOT-1"]


def test_a_failing_sub_task_query_is_a_warning_not_the_end(capsys):
    class FlakySubtasks(FakeJira):
        def search_issues(self, jql, fields=None, startAt=0, maxResults=50):
            if jql == "parent = STORY-1":
                raise JIRAError(status_code=502, text="Bad gateway")
            return super().search_issues(jql, fields, startAt, maxResults)

    jira = FlakySubtasks(issues=[FakeIssue("ROOT-1", "Feature", links=["EPIC-1"]), FakeIssue("EPIC-1", "Epic")],
                         children={"parent = EPIC-1": [FakeIssue("STORY-1", "Story")]})
    nodes = GraphWalker(jira).walk("ROOT-1")
    assert "STORY-1" in nodes and "Bad gateway" in capsys.readouterr().out


def test_warnings_do_not_carry_response_headers(capsys):
    class Response:
        headers = {"Set-Cookie": "JSESSIONID=SECRET-SESSION"}
        text = "no"

    class Failing(FakeJira):
        def search_issues(self, jql, fields=None, startAt=0, maxResults=50):
            raise JIRAError(status_code=500, text="boom", url="https://example.atlassian.net/x", response=Response())

    GraphWalker(Failing(issues=[FakeIssue("ROOT-1", "Feature")], children={})).walk("ROOT-1")
    out = capsys.readouterr().out
    assert "boom" in out and "SECRET-SESSION" not in out
