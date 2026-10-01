# Route specs exports by ticket type and name new folders from the summary

**Date:** 2026-10-01
**Status:** Approved

## Problem

Two gaps in the `SPECS_PATH` destination (rule 2 of `src/export_paths.py`).

### 1. A new specs folder has no slug

When no `<ID>` or `<ID>-*` folder exists under `specifications/`, the export
goes to a bare `specifications/<ID>/`. Every other folder in the specs repo is
named `<ID>-<slug>`, and the dev-workflows commands name the folders they
create the same way. A bare folder has to be renamed by hand. If someone
creates a `<ID>-<slug>` folder next to it instead, the next import finds two
matches and stops.

### 2. Every key goes to `specifications/`

Product-feedback tickets (`PRODFB-`) are not product changes, but they are
exported into `specifications/` next to the `PRODUCT-` Value Increments. They
belong in a separate `ideas/` folder.

## Goal

Under `SPECS_PATH`, send `PRODFB-` keys to `ideas/` and every other key to
`specifications/`, and name a new folder `<ID>-<slug>`, with the slug built
from the root ticket's summary after PII scrubbing. The tool still uses no AI:
the slug comes from a fixed rule.

## Decisions (from brainstorming)

- **Routing by key prefix.** `PRODFB-` (any case) → `ideas/`. Everything else,
  including `PRISM-` and `MGD-`, → `specifications/`, as today.
- **Use the specs repo only when it is usable; otherwise fall back.** The specs
  route requires `SPECS_PATH` to exist, to be a git repository root, and to
  contain the target subfolder. If any check fails, the reason is printed and
  the tool falls back to `VAULT_PATH`. This replaces today's rule that a set
  but unusable `SPECS_PATH` stops the run.
- **Ambiguity still stops the run.** Several matching `<ID>-*` folders is an
  unclear choice, not an unusable path; falling back would hide it.
- **Existing folders are never renamed.** Matching is unchanged.
- **Slug from the scrubbed summary.** People's names, emails and mentions are
  scrubbed first, and the scrubber's placeholders are dropped. Company names are
  not PII to the scrubber and stay in the slug.
- **No retry with a bare name when creating the folder fails.** The slug cannot
  produce an invalid name (see §2), so a failure is about permissions, space or
  path length, and a bare name would fail the same way. The run stops with the
  OS error and the path.
- **`jira-bulk-import` is out of scope.** It has no `SPECS_PATH` support and
  scrubs no PII; it stays a private, dated archive in the vault.

## Design

### 1. Routing and fallback (`src/export_paths.py`)

Precedence is unchanged: `--export-dir` → `SPECS_PATH` → `VAULT_PATH` → error.
Rule 2 changes as follows.

**Subfolder.** `ideas` when `jira_id.casefold().startswith("prodfb-")`,
otherwise `specifications`.

**Usability checks**, in this order, first failure wins:

| # | Check | Reason recorded |
|---|-------|-----------------|
| a | `$SPECS_PATH` is a directory | `SPECS_PATH is set to <p> but that directory does not exist.` |
| b | `$SPECS_PATH/<subfolder>` is a directory | `SPECS_PATH is set to <p> but <p>/<subfolder> does not exist.` |
| c | `$SPECS_PATH/.git` exists (a directory, or a file in a worktree) | `SPECS_PATH is set to <p> but it is not the root of a git repository.` |

Check b comes before c so that the existing test for a missing
`specifications/` keeps its message.

**On failure** the reason is kept and resolution continues with `VAULT_PATH`:

- `VAULT_PATH` usable → the vault target, with the reason in `ExportTarget.notice`.
- `VAULT_PATH` unset → `ExportPathError(<reason> + " VAULT_PATH is not set, so there is nothing to fall back to.")`.
- `VAULT_PATH` set but missing → `ExportPathError` with both reasons, one per line.

**On success** matching is unchanged: case-insensitive, `<ID>` or `<ID>-*`,
directories only, several matches raise. Exactly one match → that folder.

**`ExportTarget`** gains two fields with defaults, so existing constructions
keep working:

```python
@dataclass(frozen=True)
class ExportTarget:
    data_dir: Path
    layout: str            # "nested" | "flat"
    origin: str            # "explicit" | "specs" | "vault"
    notice: Optional[str] = None   # why SPECS_PATH was not used
    pending_name: bool = False     # data_dir's feature folder is new; name it

    def named(self, slug: str) -> "ExportTarget": ...
```

With no match, the resolver returns `data_dir = <subfolder>/<ID>/jira-import`
and `pending_name=True`. `named(slug)` returns a copy with the feature folder
renamed to `<ID>-<slug>` and `pending_name=False`. With an empty slug, or when
`pending_name` is already false, it returns the target unchanged apart from
`pending_name=False`. The resolver stays pure: it still creates nothing.

### 2. The slug (`slugify` in `src/export_paths.py`)

`slugify(text: str) -> str`, applied to the already-scrubbed summary:

1. Replace the scrubber's placeholders with a space: `@User-N`, `User-N`,
   `[email]`, `[mention]`. The pattern is defined in `src/pii_scrubber.py` as
   `PLACEHOLDER_RE`, next to the code that produces the placeholders.
2. `casefold()`, then NFKD-normalize and drop non-ASCII bytes. `Straße` →
   `strasse`, `Café` → `cafe`.
3. Replace every run of characters outside `[a-z0-9]` with `-`; strip leading
   and trailing `-`.
4. Cap at 40 characters. If the 41st character is `-`, cut there. Otherwise cut
   at the last `-` within the first 40; if there is none (one long word), cut
   at 40. Strip a trailing `-`.
5. Return the result, which may be empty.

**Invariant:** the result matches `^([a-z0-9]+(-[a-z0-9]+)*)?$`. It therefore
never contains a path separator, `..`, a dot, a space, a control character, or
a character invalid in a Windows filename. A folder name is at most the key
plus 41 characters, far under the 255-byte name limit, and always starts with
the key, so it can never be a Windows reserved name.

Example: `Export a distributed trace` → `PRODUCT-14279-export-a-distributed-trace`.

### 3. Scrubbing before naming (`src/markdown_exporter.py`)

`MarkdownExporter._register_users` becomes a module-level function:

```python
def register_people(nodes: dict[str, IssueNode], scrubber: PiiScrubber,
                    field_names: dict) -> None
```

It registers the same fields in the same node order. `export_all` keeps calling
it. A second call is a no-op because `anonymize_name` returns the existing
mapping, so `User-N` numbering in the export is unchanged.

### 4. Wiring (`src/main.py`)

1. Resolve the target, as today. If `target.notice` is set, print
   `Note: <notice> Falling back to VAULT_PATH.` before the header.
2. The header prints the destination. While `pending_name` is set it prints
   `<subfolder>/<ID>-<slug>/jira-import` followed by
   `(new folder, named from the ticket summary)`.
3. After the graph walk, create the `PiiScrubber`, call `register_people`, and
   if `pending_name` is set:
   `target = target.named(slugify(scrubber.scrub_text(root_summary)))`, where
   `root_summary` is the summary of the node whose role is `"root"`.
4. Create the import directory. On `OSError`, print
   `Error: cannot create <path>: <os error>` and exit 1.
5. Pass the same scrubber to `MarkdownExporter`, as today.

The link style is still inferred from `target.origin`, so a fallback to the
vault renders Obsidian links.

## Output

```
$SPECS_PATH/
├── specifications/
│   └── PRODUCT-14279-export-a-distributed-trace/
│       └── jira-import/          # flat layout, unchanged
└── ideas/
    └── PRODFB-1234-<slug>/
        └── jira-import/          # flat layout, same as specifications/
```

## What stays unchanged

- `--export-dir`, the `VAULT_PATH` destination and the nested layout.
- Folder matching under the specs subfolder, and the error for several matches.
- The flat layout below `jira-import/`, link styles, comments and attachments.
- `User-N` numbering in exported files.
- `runme.sh`.
- `jira-bulk-import`.

## Verification (success criteria)

`tests/test_export_paths.py`:

- `PRODFB-1` → `ideas/PRODFB-1/jira-import` with `pending_name`; `prodfb-1`
  routes the same way; `PRODUCT-1` and `MGD-1` → `specifications/`.
- An existing `ideas/PRODFB-1-x` folder is used, not pending.
- Each failed check (a, b, c) with `VAULT_PATH` set → vault target with the
  matching notice; with `VAULT_PATH` unset → `ExportPathError` naming the reason.
- `.git` as a file counts as a repository.
- Several matches still raise when `VAULT_PATH` is set.
- `named()`: renames the feature folder; empty slug keeps the bare `<ID>`;
  a target that is not pending is returned unchanged.
- `slugify`: the example above; accents and `ß`; placeholders removed;
  the 40-character cap on a boundary, mid-text, and for one long word; the
  invariant holds for hostile input (`/`, `\`, `..`, NUL, `:*?"<>|`, emoji,
  right-to-left text, only punctuation → `""`).

`make_specs` in both test files also creates `.git`. No other existing test
changes.

`tests/test_main_wiring.py`:

- No matching folder → the export lands in `<ID>-<slug from summary>`.
- A summary containing the assignee's display name produces a slug without it.
- An existing folder is used and no new one appears.
- A missing `ideas/` with `VAULT_PATH` set → `Note:` printed, export in the
  vault, Obsidian links.
- Failing to create the import directory exits 1 with the path in the message.

The full suite passes.

## Known limitations

- Company names in a summary end up in the slug.
- A person's name in the summary is scrubbed only when it appears as an
  `@Name Surname` mention, or the person is a user on one of the exported
  tickets (assignee, reporter, comment author, or a person-type custom field).
- A slug is cut at 40 characters, so long summaries lose their tail. The folder
  can be renamed afterwards; matching finds it by key.
- The specs repo has no `ideas/` folder yet, so `PRODFB-` exports go to the
  vault until someone creates it.

## Documentation

README, "Where the export goes": rule 2 becomes
`<repo>/<specifications|ideas>/<ID>-<slug>/jira-import`, with a paragraph on
routing, the three checks and the fallback, and on how a new folder is named.

## Files touched

- `src/export_paths.py` — routing, checks, fallback, `ExportTarget` fields, `named()`, `slugify()`
- `src/pii_scrubber.py` — `PLACEHOLDER_RE`
- `src/markdown_exporter.py` — `register_people()`
- `src/main.py` — notice, header, naming after the walk, `mkdir` error
- `tests/test_export_paths.py`, `tests/test_main_wiring.py`
- `README.md`
