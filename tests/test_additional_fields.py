from pathlib import Path

from markdown_exporter import MarkdownExporter
from pii_scrubber import PiiScrubber


def make_exporter(field_names=None):
    return MarkdownExporter(
        jira_client=None,
        data_dir=Path("/tmp/jira-test-out"),
        scrubber=PiiScrubber(),
        root_key="ROOT",
        field_names=field_names or {},
    )


def test_is_empty_description():
    assert MarkdownExporter._is_empty_description(None) is True
    assert MarkdownExporter._is_empty_description("") is True
    assert MarkdownExporter._is_empty_description("\n\n") is True
    assert MarkdownExporter._is_empty_description("   ") is True
    assert MarkdownExporter._is_empty_description("real text") is False


class FakeOption:
    def __init__(self, value):
        self.value = value


class FakeUser:
    def __init__(self, display_name):
        self.displayName = display_name


def test_format_prose_string_converts_and_scrubs():
    exp = make_exporter()
    out = exp._format_additional_value("h3. Risk\n\nReported by alice@dynatrace.com")
    assert "Risk" in out
    assert "[email]" in out
    assert "alice@dynatrace.com" not in out


def test_format_empty_string_returns_none():
    exp = make_exporter()
    assert exp._format_additional_value("   ") is None
    assert exp._format_additional_value("\n\n") is None


def test_format_single_option_returns_value():
    exp = make_exporter()
    assert exp._format_additional_value(FakeOption("Synthetic")) == "Synthetic"


def test_format_people_list_anonymizes_in_order():
    exp = make_exporter()
    out = exp._format_additional_value([FakeUser("Shari Gigliotti"), FakeUser("Sahil Verma")])
    assert out == "User-1, User-2"


def test_format_single_user_anonymizes():
    exp = make_exporter()
    assert exp._format_additional_value(FakeUser("Shari Gigliotti")) == "User-1"


def test_format_plain_url_string_passthrough():
    exp = make_exporter()
    url = "https://example.com/lightning/r/Account/001/view"
    out = exp._format_additional_value(url)
    assert "https://example.com/lightning/r/Account/001/view" in out


def test_format_option_list_joins_values():
    exp = make_exporter()
    out = exp._format_additional_value([FakeOption("A"), FakeOption("B")])
    assert out == "A, B"


class FakeFields:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeIssue:
    def __init__(self, **fields):
        self.fields = FakeFields(**fields)


def test_generate_additional_fields_renders_populated_unmapped():
    field_names = {
        "customfield_22091": "User pain point",
        "customfield_20795": "Product Area",
        "customfield_99999": "Empty Field",
        "description": "Description",   # mapped — must be excluded
    }
    exp = make_exporter(field_names)
    issue = FakeIssue(
        customfield_22091="Users cannot select a CAG in the UI.",
        customfield_20795=FakeOption("Synthetic"),
        customfield_99999=None,
    )
    out = exp._generate_additional_fields(issue)
    assert out.startswith("## Details")
    assert "### Product Area" in out
    assert "Synthetic" in out
    assert "### User pain point" in out
    assert "Users cannot select a CAG in the UI." in out
    assert "Empty Field" not in out


def test_generate_additional_fields_excludes_mapped_fields():
    field_names = {
        "customfield_17800": "Team",
        "description": "Description",
    }
    exp = make_exporter(field_names)
    issue = FakeIssue(customfield_17800=FakeOption("Synthetic Team"))
    assert exp._generate_additional_fields(issue) is None


def test_generate_additional_fields_returns_none_when_nothing():
    exp = make_exporter({"customfield_22091": "User pain point"})
    issue = FakeIssue(customfield_22091=None)
    assert exp._generate_additional_fields(issue) is None


def test_format_empty_brace_string_returns_none():
    exp = make_exporter()
    assert exp._format_additional_value("{}") is None
    assert exp._format_additional_value("  {}  ") is None
    assert exp._format_additional_value("[]") is None


class FakeNamed:
    def __init__(self, name):
        self.name = name


def test_format_fallback_scrubs_pii():
    exp = make_exporter()
    out = exp._format_additional_value(FakeNamed("contact john@dynatrace.com"))
    assert "[email]" in out
    assert "john@dynatrace.com" not in out


def test_generate_markdown_uses_details_when_description_empty(monkeypatch):
    import markdown_exporter as me
    monkeypatch.setattr(me, "fetch_pull_requests", lambda jira, issue_id: [])

    exp = make_exporter({"customfield_22091": "User pain point"})

    class FakeAtt:
        def replace_attachment_references(self, text):
            return text
        def get_attachment_list_markdown(self, images, others):
            return ""

    issue = FakeIssue(summary="S", description="", customfield_22091="Real pain content")
    issue.key = "PRODFB-929"
    issue.id = "1"

    class Node:
        pass
    node = Node()
    node.role = "linked"

    md = exp._generate_markdown(issue, node, FakeAtt(), [], [], {})
    assert "## Details" in md
    assert "### User pain point" in md
    assert "Real pain content" in md
    assert "## Description" not in md


def test_generate_markdown_uses_description_when_present(monkeypatch):
    import markdown_exporter as me
    monkeypatch.setattr(me, "fetch_pull_requests", lambda jira, issue_id: [])

    exp = make_exporter({"customfield_22091": "User pain point"})

    class FakeAtt:
        def replace_attachment_references(self, text):
            return text
        def get_attachment_list_markdown(self, images, others):
            return ""

    issue = FakeIssue(summary="S", description="A real description.", customfield_22091="Should not appear")
    issue.key = "PRODFB-916"
    issue.id = "2"

    class Node:
        pass
    node = Node()
    node.role = "root"

    md = exp._generate_markdown(issue, node, FakeAtt(), [], [], {})
    assert "## Description" in md
    assert "A real description." in md
    assert "## Details" not in md
    assert "Should not appear" not in md


def test_release_notes_section_includes_new_fields(monkeypatch):
    import markdown_exporter as me
    monkeypatch.setattr(me, "fetch_pull_requests", lambda jira, issue_id: [])

    exp = make_exporter()

    class FakeAtt:
        def replace_attachment_references(self, text):
            return text
        def get_attachment_list_markdown(self, images, others):
            return ""

    issue = FakeIssue(
        summary="S",
        description="d",
        customfield_15900=[FakeOption("Yes")],
        customfield_22157=FakeOption("New technology support"),
        customfield_20300="Managed (344), SaaS (344)",
        customfield_19502=FakeOption("Application Observability"),
        customfield_19701="Some Release Notes Title",
        customfield_15000="Some release notes summary text.",
    )
    issue.key = "PRODUCT-1"
    issue.id = "1"

    class Node:
        pass
    node = Node()
    node.role = "root"

    md = exp._generate_markdown(issue, node, FakeAtt(), [], [], {})
    assert "## Release Notes" in md
    assert "**Relevant for release notes:** Yes" in md
    assert "**Change type:** New technology support" in md
    assert "**Release versions:** Managed (344), SaaS (344)" in md
    assert "**Category:** Application Observability" in md
    assert "**Title:** Some Release Notes Title" in md
    assert "Some release notes summary text." in md


def test_release_notes_section_absent_when_all_empty(monkeypatch):
    import markdown_exporter as me
    monkeypatch.setattr(me, "fetch_pull_requests", lambda jira, issue_id: [])

    exp = make_exporter()

    class FakeAtt:
        def replace_attachment_references(self, text):
            return text
        def get_attachment_list_markdown(self, images, others):
            return ""

    issue = FakeIssue(summary="S", description="d")
    issue.key = "PRODUCT-2"
    issue.id = "2"

    class Node:
        pass
    node = Node()
    node.role = "root"

    md = exp._generate_markdown(issue, node, FakeAtt(), [], [], {})
    assert "## Release Notes" not in md
