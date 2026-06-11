# Enrich Empty-Description Tickets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a Jira ticket's standard `description` is empty/missing (Product Discovery types like "Account", "Product Need"), render its populated custom fields as a `## Details` section so the content comes through.

**Architecture:** Fetch all fields (`*all`) instead of a curated subset; resolve `customfield_*` ids to display names via one `jira.fields()` call; in the exporter, when the description is empty, walk every populated custom field not already shown elsewhere and format it by type (prose / option / people / other), with people anonymized to `User-N`.

**Tech Stack:** Python 3, `jira` library, pytest (new dev dependency).

---

## File Structure

- `src/markdown_exporter.py` (modify) — owns rendering. New: `field_names` ctor arg, `_is_empty_description`, `_format_additional_value`, `_generate_additional_fields`, the empty-description branch, and a `_register_users` extension for PII consistency.
- `src/main.py` (modify) — builds the `{field_id: display_name}` map and passes it to the exporter.
- `src/graph_walker.py` (modify) — fetches `*all` fields so unmapped custom fields are retrieved.
- `pytest.ini` (create) — sets `pythonpath = src` so tests import the modules.
- `requirements-dev.txt` (create) — pins pytest.
- `tests/test_additional_fields.py` (create) — unit tests for the pure formatting/exclusion/trigger logic using fake field objects (no network).

**Reference interfaces (verified, do not re-derive):**
- `PiiScrubber.anonymize_name(displayName) -> "User-N"` (consistent per name); `scrubber.scrub_text(text)` replaces emails with `[email]`.
- `JiraMarkupConverter(base_url).convert(wiki_text) -> markdown` (pure, no network).
- `FieldFormatter.format_custom_field(value)` handles str/int/bool/list/`.name`/`.value`.
- Jira typed values via `issue.fields.<id>`: prose → `str`; single-select → object with `.value`; people → `list` of objects with `.displayName`.
- `jira_client.fields()` → list of `{"id": ..., "name": ...}` (one call, ~408 entries).

---

## Task 1: Test infrastructure + empty-description trigger

**Files:**
- Create: `pytest.ini`
- Create: `requirements-dev.txt`
- Create: `tests/test_additional_fields.py`
- Modify: `src/markdown_exporter.py` (add `_is_empty_description` static method)

- [ ] **Step 1: Create pytest config**

Create `pytest.ini`:

```ini
[pytest]
pythonpath = src
testpaths = tests
```

- [ ] **Step 2: Create dev requirements**

Create `requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0
```

- [ ] **Step 3: Install pytest into the venv**

Run: `source .venv/bin/activate && pip install -q -r requirements-dev.txt`
Expected: installs pytest with no errors.

- [ ] **Step 4: Write the failing test**

Create `tests/test_additional_fields.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_additional_fields.py -v`
Expected: FAIL — `MarkdownExporter.__init__() got an unexpected keyword argument 'field_names'` (and/or `_is_empty_description` missing).

- [ ] **Step 6: Add `field_names` ctor arg and the trigger helper**

In `src/markdown_exporter.py`, change `__init__` signature and body:

```python
    def __init__(self, jira_client: Any, data_dir: Path, scrubber: PiiScrubber, root_key: str = "", field_names: dict | None = None):
        self.jira = jira_client
        self.data_dir = data_dir
        self.scrubber = scrubber
        self.root_key = root_key
        self.field_names = field_names or {}
        self.converter = JiraMarkupConverter(JIRA_BASE_URL)
        self.formatter = FieldFormatter()
```

Add this static method to the class (e.g. just below `__init__`):

```python
    @staticmethod
    def _is_empty_description(description: Any) -> bool:
        """True when description is None, empty, or whitespace-only."""
        return not description or not str(description).strip()
```

- [ ] **Step 7: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_additional_fields.py -v`
Expected: PASS (1 passed).

- [ ] **Step 8: Commit**

```bash
git add pytest.ini requirements-dev.txt tests/test_additional_fields.py src/markdown_exporter.py
git commit -m "test: add pytest infra and empty-description trigger helper"
```

---

## Task 2: Format a single custom-field value by type

**Files:**
- Modify: `src/markdown_exporter.py` (add `_format_additional_value`)
- Test: `tests/test_additional_fields.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_additional_fields.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_additional_fields.py -v`
Expected: FAIL — `AttributeError: 'MarkdownExporter' object has no attribute '_format_additional_value'`.

- [ ] **Step 3: Implement `_format_additional_value`**

Add to `src/markdown_exporter.py` (in the class):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_additional_fields.py -v`
Expected: PASS (all tests pass).

- [ ] **Step 5: Commit**

```bash
git add src/markdown_exporter.py tests/test_additional_fields.py
git commit -m "feat: format custom-field values by type for Details section"
```

---

## Task 3: Assemble the Details section (iteration + exclusion)

**Files:**
- Modify: `src/markdown_exporter.py` (add `_generate_additional_fields`)
- Test: `tests/test_additional_fields.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_additional_fields.py`:

```python
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
    # null field is skipped
    assert "Empty Field" not in out


def test_generate_additional_fields_excludes_mapped_fields():
    # customfield_17800 (Team) and description are in FIELD_MAPPING -> excluded
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_additional_fields.py -v`
Expected: FAIL — `AttributeError: ... no attribute '_generate_additional_fields'`.

- [ ] **Step 3: Implement `_generate_additional_fields`**

Add to `src/markdown_exporter.py` (in the class). Note `FIELD_MAPPING` is already imported at the top of the file:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_additional_fields.py -v`
Expected: PASS (all tests pass).

- [ ] **Step 5: Commit**

```bash
git add src/markdown_exporter.py tests/test_additional_fields.py
git commit -m "feat: assemble Details section from populated unmapped custom fields"
```

---

## Task 4: Wire the fallback into rendering + PII pre-registration

**Files:**
- Modify: `src/markdown_exporter.py` (description branch in `_generate_markdown`; extend `_register_users`)

No new unit test: `_generate_markdown` performs network calls (`fetch_pull_requests`) and needs a live `att_handler`, so this branch is verified by the live-export checks in Task 6. The decision logic it relies on (`_is_empty_description`, `_generate_additional_fields`) is already unit-tested.

- [ ] **Step 1: Replace the Description block with the empty-aware branch**

In `src/markdown_exporter.py`, find the current Description block in `_generate_markdown`:

```python
        # Description
        description = getattr(issue.fields, 'description', None)
        if description:
            lines.append("## Description")
            lines.append("")
            converted = self.converter.convert(description)
            converted = att_handler.replace_attachment_references(converted)
            lines.append(self.scrubber.scrub_text(converted))
            lines.append("")
```

Replace it with:

```python
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
```

- [ ] **Step 2: Extend `_register_users` to pre-register people in custom fields**

In `src/markdown_exporter.py`, find the end of `_register_users` (after the comment-author loop) and append:

```python
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
```

- [ ] **Step 3: Run unit tests (no regression)**

Run: `source .venv/bin/activate && python -m pytest -v`
Expected: PASS (all previously-passing tests still pass).

- [ ] **Step 4: Commit**

```bash
git add src/markdown_exporter.py
git commit -m "feat: render Details fallback when description empty; pre-register custom-field people"
```

---

## Task 5: Fetch all fields and build the field-name map

**Files:**
- Modify: `src/graph_walker.py` (fetch `*all`; drop unused import)
- Modify: `src/main.py` (build `field_names`, pass to exporter)

- [ ] **Step 1: Fetch all fields in `graph_walker.py`**

In `src/graph_walker.py`, in `_fetch_issue`, change:

```python
            issue = self.jira.issue(key, fields=ALL_FIELD_IDS)
```

to:

```python
            issue = self.jira.issue(key, fields="*all")
```

In `_search_jql`, change:

```python
            batch = self.jira.search_issues(jql, fields=ALL_FIELD_IDS, startAt=start, maxResults=50)
```

to:

```python
            batch = self.jira.search_issues(jql, fields="*all", startAt=start, maxResults=50)
```

- [ ] **Step 2: Remove the now-unused import**

In `src/graph_walker.py`, delete the line:

```python
from config import ALL_FIELD_IDS
```

(`ALL_FIELD_IDS` is no longer referenced anywhere in this file; it stays defined in `config.py` for now — do not delete it from config.)

- [ ] **Step 3: Build and pass the field-name map in `main.py`**

In `src/main.py`, just after the auth block that sets `jira_client` (after the `print(f"Connected to: {auth.server}\n")` line), add:

```python
    # Map customfield ids to display names (one call) for the Details fallback
    field_names = {f["id"]: f["name"] for f in jira_client.fields()}
```

Then find the exporter construction:

```python
    exporter = MarkdownExporter(jira_client, import_dir, scrubber, root_key=args.jira_id)
```

and change it to:

```python
    exporter = MarkdownExporter(jira_client, import_dir, scrubber, root_key=args.jira_id, field_names=field_names)
```

- [ ] **Step 4: Smoke-check imports and unit tests**

Run: `source .venv/bin/activate && python -c "import sys; sys.path.insert(0,'src'); import graph_walker, main, markdown_exporter; print('imports ok')" && python -m pytest -q`
Expected: `imports ok` then all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/graph_walker.py src/main.py
git commit -m "feat: fetch all fields and pass field-name map to exporter"
```

---

## Task 6: Live-export verification (spec success criteria)

**Files:** none (verification only)

These checks require the configured Jira credentials and network access. Export to a temp dir to avoid touching the real vault.

- [ ] **Step 1: Run the export for the root ticket**

Run: `source .venv/bin/activate && python src/main.py PRODFB-759 --export-dir=/tmp/jira-verify`
Expected: completes with `Done. N/N exported.` and no errors.

- [ ] **Step 2: Verify PRODFB-929 now has content**

Run: `cat /tmp/jira-verify/PRODFB-759/PRODFB-929/PRODFB-929.md`
Expected: contains `## Details`, `### User pain point`, `### Customer impact`, `### Business impact for Dynatrace`, `### Product Area`. There is no empty `## Description` heading.

- [ ] **Step 3: Verify PRODFB-759 (Account) now has content**

Run: `cat /tmp/jira-verify/PRODFB-759/PRODFB-759/PRODFB-759.md`
Expected: contains `## Details`, `### Salesforce Account Link` (with the URL), and `### CSM` / `### CSE` / `### Relevant Stakeholders (Account team, SEs, Sales)` rendered as `User-N` placeholders (no real names/emails).

- [ ] **Step 4: Regression check — a ticket with a real description is unchanged**

Run: `grep -c "## Details" /tmp/jira-verify/PRODFB-759/PRODFB-916/PRODFB-916.md; grep -c "## Description" /tmp/jira-verify/PRODFB-759/PRODFB-916/PRODFB-916.md`
Expected: first count `0` (no Details section), second count `1` (still has its real Description).

- [ ] **Step 5: Final full test run**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: all tests pass.

---

## Notes for the implementer

- Do not delete `ALL_FIELD_IDS` from `config.py` — only its import in `graph_walker.py` becomes unused.
- `field_names` keys include non-custom ids (e.g. `summary`, `status`); `_generate_additional_fields` filters to `customfield_*` and skips anything in `FIELD_MAPPING`, so those never leak into Details.
- Minor noise is acceptable per the spec: any other populated, unmapped custom field will also render. If a specific field is noisy in the live output, add its id to the `excluded` set in `_generate_additional_fields`.
