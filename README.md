# jira-workitem-import

Exports a single Jira workitem and its full dependency graph to markdown — including direct links, Epic children (recursively), comments, attachments, and pull request info. All person names and emails are anonymized.

**Use case:** You close a PRODUCT-XXXXX feature ticket and need to write release notes, documentation, or a blog post. This tool exports the full context — the PRODUCT ticket, linked Epics, all stories/bugs/tasks under those Epics, comments, and PR references — so you can write accurate docs even when the implementation diverged from the original plan.

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your config
cp .jira.config.example .jira.config   # then fill in your credentials
```

## Configuration

### `.jira.config`

Jira credentials. **Never commit this file.**

```
SERVER: https://your-org.atlassian.net
EMAIL: you@example.com
TOKEN: your_api_token_here
```

Generate an API token at: https://id.atlassian.com/manage-profile/security/api-tokens

Alternatively, set environment variables `JIRA_SERVER`, `JIRA_EMAIL`, `JIRA_TOKEN` (they take precedence).

## Usage

```bash
# Recommended: use the wrapper script (handles venv + install automatically)
./runme.sh PRODUCT-12345
```

The export directory is configured inside `runme.sh` (`EXPORT_DIR` variable). Edit it once to point at your Obsidian vault or preferred output location.

Alternatively, invoke Python directly after activating the venv:

```bash
source .venv/bin/activate
python src/main.py PRODUCT-12345
python src/main.py PRODUCT-12345 --export-dir=/path/to/output
```

## What gets exported

Starting from the root workitem, the tool:

1. **Fetches the root issue** with all fields, comments, and attachments
2. **Fetches all directly linked issues** (all link types: blocks, relates to, duplicates, etc.)
3. **Traverses all Epics** found in steps 1-2, recursively fetching children, grandchildren, etc. (stories, bugs, tasks, sub-tasks)
4. **Fetches pull request info** for every issue via Jira's dev-status API
5. **Anonymizes PII** — person names become `User-1`, `User-2` (consistent across the export), emails are scrubbed, @mentions are replaced

Each issue is exported exactly once (deduplicated).

## Output

Each import gets its own subdirectory, keeping multiple imports cleanly separated:

```
.data/
├── export-index.md              # top-level index listing all imports
├── PRODUCT-12345/               # one import = one subdirectory
│   ├── PRODUCT-12345-index.md   # per-import index (full detail, hierarchy, relationships)
│   ├── PRODUCT-12345/           # root ticket files
│   │   ├── PRODUCT-12345.md
│   │   ├── PRODUCT-12345-comments.md
│   │   └── attachments/
│   ├── EPIC-100/                # linked/epic_child ticket files
│   │   ├── EPIC-100.md
│   │   ├── EPIC-100-comments.md
│   │   └── attachments/
│   └── STORY-200/
│       └── ...
├── PRODUCT-67890/               # another import, fully separate
│   ├── PRODUCT-67890-index.md
│   └── ...
```

### export-index.md (top-level)

A simple table listing all root imported tickets with wikilinks to their per-import indexes.

### PRODUCT-12345-index.md (per-import)

Contains:
- **Backlink** to `[[export-index]]`
- **Summary table** — all exported issues with type, status, summary, and role (root/linked/epic_child)
- **Relationship map** — link types between issues with directional arrows
- **Epic hierarchy** — tree view of Epic → Story → Task chains
- **Statistics** — counts by role

### Per-issue markdown

Each `<KEY>.md` includes:
- Backlink to `[[PRODUCT-12345-index]]` (the per-import index) for navigation
- YAML frontmatter (all Jira fields)
- Metadata section (type, status, assignee, team, parent)
- Status details and description (converted from Jira markup)
- Attachments (downloaded, with `![[image]]` embeds)
- Release notes (if present)
- Linked issues (grouped by link type, as `[[KEY]]` wikilinks)
- Pull requests (title, URL, repo, branch, status)
- Comments (embedded via `![[KEY-comments]]` transclusion)

### Navigation

All internal links use **Obsidian wikilinks** (`[[KEY]]`):
- `export-index.md` links to each import via `[[PRODUCT-12345-index]]`
- Each per-import index links back to `[[export-index]]`
- Each ticket links back to its per-import index (e.g., `[[PRODUCT-12345-index]]`)
- Linked issues, parent tickets, and Epic children are all `[[KEY]]` wikilinks
- Comments are embedded via `![[KEY-comments]]` transclusion
- Issues not in the export (external links) fall back to Jira URLs
- Wikilinks inside markdown tables are pipe-escaped (`\\|`) to avoid breaking table structure

## PII Anonymization

- Person names → consistent `User-N` placeholders across the entire export
- Email addresses → `[email]`
- `@mentions` and `[~user]` references → anonymized
- Team names, project names, ticket IDs → **kept as-is** (not PII)

## Re-exporting

Running the tool again for the same ticket will delete and recreate each issue's folder within its import subdirectory. The top-level `export-index.md` is rewritten on every run to reflect all current imports. No snapshot history is maintained.
