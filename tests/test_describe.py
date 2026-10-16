"""Errors are shown as Jira's status and message, never with response headers."""

from jira.exceptions import JIRAError

from jira_auth import describe


def test_describe_keeps_status_and_text_but_not_headers():
    class Response:
        headers = {"Set-Cookie": "JSESSIONID=SECRET-SESSION"}
        text = "x"

    error = JIRAError(status_code=403, text="Forbidden", url="https://example.atlassian.net/x", response=Response())
    assert "SECRET-SESSION" in str(error)          # what printing it used to leak
    assert describe(error) == "HTTP 403: Forbidden"
    assert describe(ValueError("plain")) == "plain"
