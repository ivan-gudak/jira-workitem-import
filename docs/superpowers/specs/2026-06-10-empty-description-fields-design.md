# Enrich empty-description tickets with their populated custom fields

**Date:** 2026-06-10
**Status:** Approved

## Problem

Some Jira tickets export "almost empty." Reproduced with `PRODFB-759` (type
**Account**) and `PRODFB-929` (type **Product Need**) — both Jira Product
Discovery / "Product Feedback" issue types.

Root cause: the tool fetches only the ~30 fields listed in
`config.ALL_FIELD_IDS` (`graph_walker._fetch_issue` and `_search_jql` both pass
`fields=ALL_FIELD_IDS`). These issue types leave the standard `description`
field empty and store their real content in **unmapped custom fields**, which
are therefore never fetched and never rendered.

Confirmed via the raw API:

- **PRODFB-929** (`description` is `'\n\n'`) — real content lives in:
  - `customfield_22091` — User pain point (prose)
  - `customfield_22058` — Customer impact (prose)
  - `customfield_22060` — Business impact for Dynatrace (prose)
  - `customfield_20795` — Product Area (option)
  - `customfield_22059` — Product version (option)
  - `customfield_22025` — Workaround Possible (option)
- **PRODFB-759** (`description` is `None`) — content is:
  - `customfield_22191` — Salesforce Account Link (URL string)
  - `customfield_21926` / `21927` / `21928` — CSM / CSE / Relevant Stakeholders
    (people lists)

The export is faithful to what it fetches — it just isn't fetching the fields
that matter for these issue types.

## Goal

When a ticket's standard `description` is empty or missing, render its
populated custom fields so the content "comes through." Tickets that already
have a real description keep their current output unchanged.

## Decisions (from brainstorming)

- **Scope:** generic fallback (render all populated custom fields), not a
  hand-mapped list — so future Product Discovery types are covered without
  per-field config.
- **Trigger:** only when the standard `description` is empty/missing — surgical,
  no change to normal tickets.

## Design

Three parts.

### 1. Fetch all fields (`src/graph_walker.py`)

Change `fields=ALL_FIELD_IDS` → `fields="*all"` in:
- `_fetch_issue` (line ~67)
- `_search_jql` (line ~144)

Required so unmapped custom fields are actually retrieved. Payloads grow
modestly; acceptable for this single-workitem tool.

### 2. Resolve field display names (one API call)

Add a single `jira_client.fields()` call to build a
`{field_id: "Display Name"}` map (validated: 408 fields, e.g.
`customfield_22091 → "User pain point"`).

- Built once in `src/main.py` after authentication.
- Passed into `MarkdownExporter.__init__` as `field_names`.

### 3. Fallback "## Details" section (`src/markdown_exporter.py`)

In `_generate_markdown`, after the existing Description block, add: **if
`description` is empty/missing**, render a `## Details` section.

New method `_generate_additional_fields(issue)`:

1. Iterate custom fields present on the issue (`issue.raw['fields']` keys
   starting with `customfield_`, or iterate the `field_names` map).
2. Skip any field id in the **exclusion set** (see below).
3. Skip `None` / empty-string / empty-list values, and values that format to
   empty.
4. Format remaining values by type:
   - **prose `str`** → `JiraMarkupConverter.convert` + attachment-ref rewrite +
     `scrubber.scrub_text`
   - **`CustomFieldOption`** (has `.value`) → `.value`
   - **people list** (items have `.displayName`) → `scrubber.anonymize_name`
     each, join with `, `
   - **list** (options / strings) → `FieldFormatter.format_array`, join
   - **other** → `FieldFormatter.format_custom_field`
5. Render each as `### <Display Name>` followed by the formatted value.

**Heading:** `## Details` (the Description is absent, so this is the primary
content section for these tickets).

**Exclusion set:** every field id already present in `config.FIELD_MAPPING`
(these are rendered in frontmatter or specially handled: Status details,
Release notes title/summary, Team, Rank, Parent Link, issuelinks, description,
etc.). This keeps the section to genuinely-new content and prevents
double-rendering.

### PII consistency (`src/markdown_exporter.py`)

Extend `_register_users` (first pass) to also register people in custom fields,
so `User-N` numbering stays consistent across the whole export. Generic rule:
for each custom field value, if it is an object with `.displayName`, or a list
of such objects, register each `displayName`.

## What stays unchanged

Tickets with a non-empty `description` (normal DEV/EPIC stories) get **no**
Details section. Their markdown is byte-identical to today's output.

## Verification (success criteria)

Run the exporter for the root ticket and inspect output:

1. **PRODFB-929** — `## Details` shows User pain point, Customer impact,
   Business impact for Dynatrace, Product Area, Product version, Workaround
   Possible.
2. **PRODFB-759** — `## Details` shows Salesforce Account Link plus CSM / CSE /
   Relevant Stakeholders rendered as `User-N`.
3. **Regression check** — a ticket with a real description (e.g. `PRODFB-916`)
   shows **no** `## Details` section; diff against a pre-change export is empty
   for that file.

## Known limitations (v1)

- Any other populated, unmapped custom field on these issue types will also
  render. If a specific field is noisy, add its id to the exclusion set.
- A rare object-typed custom field with no `.value`/`.displayName`/`.name` will
  fall back to `str(value)` and may format plainly.

## Files touched

- `src/graph_walker.py` — `*all` fetch (2 lines)
- `src/main.py` — build field-name map, pass to exporter
- `src/markdown_exporter.py` — `field_names` ctor arg, `_generate_additional_fields`,
  empty-description trigger, extend `_register_users`
