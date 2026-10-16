# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Set up environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # or requirements.txt, without pytest

# Run the tests
python -m pytest

# Run the exporter (from project root)
./runme.sh PRODUCT-12345                              # builds .venv, installs, runs
python src/main.py PRODUCT-12345 --export-dir=output  # explicit destination
```

The script must be run from the project root — `JiraAuth` reads `.jira.config` from `os.getcwd()`. `runme.sh` changes into its own directory first.

`test_converters_differ_only_in_known_hunks` compares `src/jira_markup_converter.py` against `../jira-bulk-import/src/`. It skips when that sibling is not checked out next to this repo.

Design specs and implementation plans live in `docs/superpowers/specs/` and `docs/superpowers/plans/`.

## Configuration

Credentials are read from `.jira.config` (`KEY: value` format) or env vars `JIRA_SERVER`, `JIRA_EMAIL`, `JIRA_TOKEN`. The env vars are used only when all three are set; otherwise the file is read and its values replace them. `.jira.config` is gitignored and must never be committed.

The destination comes from `--export-dir`, then `SPECS_PATH`, then `VAULT_PATH`; with none of them the run stops before contacting Jira. The rules are in `export_paths.py` and tabulated in the README.

### Values tied to one Jira site

`SERVER` in `.jira.config` is used only to connect. Every link written into the export is built from `JIRA_BASE_URL` in `src/config.py`, hard-coded to `https://dt-rnd.atlassian.net`. Custom field IDs belong to that site too, and not all of them live in `config.py`:

| Field | ID | Also hard-coded in |
|---|---|---|
| Parent Link | `customfield_17801` (`cf[17801]` in JQL) | `graph_walker.py`, `index_generator.py` |
| Team | `customfield_17800` | `markdown_exporter.py` |
| Status details | `customfield_19200` | `markdown_exporter.py` |
| Architecture / Execution Assignee | `customfield_21107`, `customfield_19400` | `markdown_exporter.py` (person fields) |
| Release-notes fields | `customfield_15900`, `_22157`, `_20300`, `_19502`, `_19701`, `_15000` | `markdown_exporter.py` |

Other site-specific behaviour: `pr_fetcher.py` asks the dev-status API for `applicationType=stash`, so only Bitbucket Server pull requests appear; `export_paths._specs_subfolder` sends `PRODFB-` keys to `ideas/`; `runme.sh` expands `P-123` to `PRODUCT-123`.

## Architecture

`main.py` runs one export in this order:

1. `resolve_export_target` (`export_paths.py`) decides the destination, its layout (`nested` or `flat`) and its origin (`explicit`, `specs` or `vault`). It runs before any Jira call and creates nothing, so a misconfigured run fails fast and leaves no folders behind.
2. `JiraAuth` connects. One `jira.fields()` call maps custom field IDs to display names for the Details fallback.
3. `GraphWalker.walk` collects `IssueNode`s: the root; its direct links (one level, every link type); issues whose Parent Link points at the root; then the full child tree of every Epic found so far (`"Epic Link"`, `parent` or Parent Link, recursing into sub-tasks). Each node has a role: `root`, `linked` or `epic_child`.
4. `register_people` then `scrub_summaries` (`markdown_exporter.py`) teach `PiiScrubber` every person on the tickets and scrub every summary in place, before anything is written or slugged. A new specs folder is then named by `slugify` from the scrubbed root summary.
5. `MarkdownExporter.export_all` writes one `<KEY>/` folder per node, deleting it first: `<KEY>.md`, `attachments/`, and `<KEY>-comments.md` unless comments are inlined. One failing ticket is recorded and the rest continue.
6. `index_generator` writes `<ROOT>-index.md`, and for a nested layout rewrites the `export-index.md` registry from the folders on disk.

**Module responsibilities:**

| Module | Role |
|---|---|
| `main.py` | CLI parsing and orchestration |
| `export_paths.py` | Destination rules, specs-repo checks and fallback, `slugify`. Pure: reads only the env mapping it is given |
| `jira_auth.py` | Reads credentials, returns a `JIRA` client |
| `graph_walker.py` | Graph traversal: `IssueNode`, `GraphWalker` |
| `pii_scrubber.py` | Consistent `User-N` mapping; email and mention scrubbing |
| `markdown_exporter.py` | Per-ticket page: frontmatter, sections, Details fallback, pull requests, comments |
| `link_renderer.py` | `ObsidianLinks` / `GithubLinks`, `Location`, and `OutputProfile` |
| `rendering_converter.py` | `JiraMarkupConverter` subclass that renders issue keys through a link renderer |
| `jira_markup_converter.py` | Jira wiki markup and ADF → markdown. Shared with jira-bulk-import (see below) |
| `attachment_handler.py` | Downloads attachments the profile allows; rewrites inline attachment references |
| `comments_handler.py` | Formats comments as a separate document or an inlined section |
| `field_formatter.py` | Formats users, arrays, parents, linked issues and generic custom values |
| `index_generator.py` | Per-import index and top-level registry |
| `pr_fetcher.py` | Pull requests from Jira's dev-status API |
| `config.py` | `JIRA_BASE_URL`, `FIELD_MAPPING` (display name → field ID), `EXPORT_FIELDS` (frontmatter order) |

**Link style.** Everything that writes a link goes through a renderer bound to a `Location` — the registry, an import index, or a ticket page — so the same code emits `[[KEY]]` or `[KEY](../KEY/KEY.md)`. `OutputProfile.for_style` bundles the renderer with the two decisions that follow from the style: whether comments are inlined, and the attachment download allowlist. Both are on for `github` and off for `obsidian`.

**The shared converter.** `jira_markup_converter.py` is a copy of the one in `../jira-bulk-import`. The two differ only in `_format_issue_link` and the comment describing it (a wikilink here, a Jira URL there); the sibling file also uses CRLF line endings. Make a converter change in both copies, or the drift test fails. Behaviour that only this repo needs belongs in `RenderingConverter`.

**PII.** Names are anonymized only once `PiiScrubber` has met them. Free text goes through `scrub_text`; person fields go through `anonymize_name`. Write any new text into the export through one of the two.

**Adding a Jira field:** add the display name → field ID mapping to `FIELD_MAPPING` in `config.py`, then add the display name to `EXPORT_FIELDS` in the desired position. If the field needs its own rendering, add a case in `MarkdownExporter._extract_field()` or `_generate_markdown()` and a helper in `FieldFormatter`. A field that holds a person must also join the person-field tuples in `_generate_frontmatter()` and `_extract_field()`, or its frontmatter value is written without anonymization.
