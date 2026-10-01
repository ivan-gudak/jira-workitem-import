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

Extra arguments are forwarded, so `./runme.sh PRODUCT-12345 --link-style=github` works.

Alternatively, invoke Python directly after activating the venv:

```bash
source .venv/bin/activate
python src/main.py PRODUCT-12345 --export-dir=/path/to/output
SPECS_PATH=/path/to/specs-repo python src/main.py PRODUCT-12345
VAULT_PATH=/path/to/obsidian-vault python src/main.py PRODUCT-12345
```

### Where the export goes

The destination is resolved from the first rule that applies. There is no
default — with none of these set the run stops immediately with an error,
before contacting Jira.

| # | Given | Destination | Layout | Links |
|---|-------|-------------|--------|-------|
| 1 | `--export-dir=<path>` | `<path>` | nested | obsidian |
| 2 | `SPECS_PATH=<repo>` | `<repo>/<specifications\|ideas>/<ID>-<slug>/jira-import` | flat | github |
| 3 | `VAULT_PATH=<vault>` | `<vault>/jira-products` | nested | obsidian |
| 4 | none of the above | *error* | — | — |

An environment variable set to the empty string counts as unset.

Under rule 2, `PRODFB-` keys go to `ideas/` and every other key goes to
`specifications/`. The specs repo is used only when `SPECS_PATH` exists, the
target subfolder exists in it, and it is the root of a git repository (a `.git`
directory, or a `.git` file in a worktree). If any check fails, the run prints
a `Note:` with the reason and falls back to rule 3; with no usable `VAULT_PATH`
either, it stops with both reasons.

The `<ID>-<slug>` folder is matched case-insensitively, and an existing `<ID>`
or `<ID>-*` folder is used as it is, never renamed. If several match, the run
stops and asks you to pick one with `--export-dir`. If none exists, a new
folder is named from the root ticket's summary: people's names, emails and
mentions are scrubbed out, the rest is lowercased to ASCII letters, digits and
hyphens, and cut to at most 40 characters at a word boundary. *Export a
distributed trace* becomes `PRODUCT-14279-export-a-distributed-trace`. A
summary with nothing left after that gives a bare `<ID>` folder. Company names
are not scrubbed and stay in the slug.

`--link-style=obsidian|github` overrides the inferred link style.

## What gets exported

Starting from the root workitem, the tool:

1. **Fetches the root issue** with all fields, comments, and attachments
2. **Fetches all directly linked issues** (all link types: blocks, relates to, duplicates, etc.)
3. **Traverses all Epics** found in steps 1-2, recursively fetching children, grandchildren, etc. (stories, bugs, tasks, sub-tasks)
4. **Fetches pull request info** for every issue via Jira's dev-status API
5. **Anonymizes PII** — person names become `User-1`, `User-2` (consistent across the export), emails are scrubbed, @mentions are replaced

Each issue is exported exactly once (deduplicated).

## Output

**Nested** (`--export-dir` or `VAULT_PATH`) — the destination holds many
imports, so each gets its own subdirectory and a registry lists them:

```
<destination>/
├── export-index.md              # registry listing all imports
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

**Flat** (`SPECS_PATH`) — the destination already belongs to one Value
Increment, so there is no `<ID>` level and no registry. Comments are inlined
into the ticket page rather than written as separate files:

```
<repo>/specifications/PRODUCT-12345-some-slug/jira-import/
├── PRODUCT-12345-index.md
├── PRODUCT-12345/
│   ├── PRODUCT-12345.md         # comments inlined under "## Comments"
│   └── attachments/
├── EPIC-100/
│   └── EPIC-100.md
└── STORY-200/
    └── STORY-200.md
```

### export-index.md (top-level)

A simple table listing all root imported tickets, linked to their per-import indexes. Written for nested layouts only — a flat destination holds exactly one import.

### PRODUCT-12345-index.md (per-import)

Contains:
- **Backlink** to the registry (nested layouts only — a flat destination writes no registry, so the backlink is omitted)
- **Summary table** — all exported issues with type, status, summary, and role (root/linked/epic_child)
- **Relationship map** — link types between issues with directional arrows
- **Epic hierarchy** — tree view of Epic → Story → Task chains
- **Statistics** — counts by role

### Per-issue markdown

Each `<KEY>.md` includes:
- Backlink to the per-import index for navigation
- YAML frontmatter (all Jira fields)
- Metadata section (type, status, assignee, team, parent)
- Status details and description (converted from Jira markup)
- Attachments (embedded images, plus a file list)
- Release notes (if present)
- Linked issues (grouped by link type)
- Pull requests (title, URL, repo, branch, status)
- Comments (transcluded from `<KEY>-comments.md`, or inlined — see below)

### Navigation

Two link styles, chosen by `--link-style` or inferred from the destination.
GitHub's file browser renders neither `[[KEY]]` nor `![[image]]`, so an export
meant to be read in a pull request needs plain relative markdown links.

| | `obsidian` | `github` |
|---|---|---|
| Issue in the export | `[[KEY]]` | `[KEY](../KEY/KEY.md)` |
| Issue outside it | Jira URL | Jira URL |
| Index backlink | `[[PRODUCT-12345-index]]` | `[PRODUCT-12345-index](../PRODUCT-12345-index.md)` |
| Image | `![[image.png]]` | `![image.png](attachments/image.png)` |
| Other attachment | `[[file.pdf]]` | `[file.pdf](attachments/file.pdf)` |
| Comments | `![[KEY-comments]]` transclusion | inlined into `<KEY>.md` |

Under either style, links inside markdown tables are pipe-escaped (`\\|`) so
they do not break the table, and issues outside the export fall back to Jira
URLs. GitHub link targets are percent-encoded, so spaces and parentheses in a
filename survive.

One deliberate asymmetry: a bare issue key mentioned in *body text* stays a
`[[KEY]]` wikilink under the obsidian style even when the key is outside this
export, because Obsidian resolves wikilinks by filename across the whole vault
and will reach a ticket exported by a different import. Structural links —
index rows, **Parent**, **Linked Issues** — fall back to a Jira URL in both
styles.

### Attachment downloads

Under the obsidian style every attachment is downloaded. Under the github
style only an allowlist is: images, documents (`pdf`, office formats, `csv`),
and text/data formats. Everything else — archives, dumps, binaries, and
extensionless blobs — is left in Jira and rendered as a sized link:

```markdown
- [SupportArchive3F642709.zip](https://…/attachment/98123) (11.2 MB)
```

In a 163 MB vault export, archives accounted for 45.9 MB across 46 files —
40% of the attachment weight in 4% of the files — which is not something to
commit to a specs repository.

An attachment whose download fails is rendered the same way, as a link back to
Jira. An attachment Jira no longer returns at all — deleted, or not visible to
your account — has no URL to fall back on, so references to it are rendered as
`*(attachment unavailable: <filename>)*` rather than as a link to a file that
was never written.

## PII Anonymization

- Person names → consistent `User-N` placeholders across the entire export
- Email addresses → `[email]`
- `@mentions` and `[~user]` references → anonymized
- Ticket summaries → scrubbed the same way wherever they appear: page titles,
  frontmatter, indexes, and the slug of a new specs folder. A name is replaced
  only when it belongs to a person on the exported tickets or is written as an
  `@Name Surname` mention
- Team names, project names, ticket IDs → **kept as-is** (not PII)

## Re-exporting

Running the tool again for the same ticket will delete and recreate each issue's folder within its import subdirectory. The registry `export-index.md` is rewritten on every run to reflect all current imports. No snapshot history is maintained.

Only the folders of issues in the *current* graph are recreated. If a link is
removed in Jira between runs, that issue's directory is left behind from the
previous export and has to be deleted by hand — the tool never removes a
directory it did not just write.
