# Export destination resolution and GitHub-compatible link rendering

**Date:** 2026-09-28
**Status:** Approved

## Problem

Two problems, discovered together.

### 1. The export destination is wrong when `VAULT_PATH` is unset

`runme.sh:17` builds the destination unconditionally:

```bash
EXPORT_DIR="$VAULT_PATH/jira-products"
```

With `VAULT_PATH` unset or empty this expands to the absolute path
`/jira-products`, which is not writable for a non-root user. `main.py:39` then
calls `Path(os.getcwd()) / args.export_dir`; because the argument is absolute,
pathlib discards the cwd and the tool attempts to create `/jira-products`.

The failure is also *late*: `main.py:75` announces the destination only after
the graph walk completes, so a wrong pointer costs a full Jira round-trip
before it surfaces.

Meanwhile `main.py:21` declares `DEFAULT_EXPORT_DIR = ".data"` and the README
(line 50) documents that default — but `runme.sh` always passes `--export-dir`,
so the `.data` default is unreachable through the supported entry point. The
two entry points disagree, and the README documents the one that never runs.

### 2. Exports are Obsidian-only

Every link the tool emits is an Obsidian wikilink (`[[KEY]]`, `![[image]]`).
GitHub does not render these: in repo markdown `[[KEY]]` appears as literal
text and `![[image]]` does not render the image at all. An export written into
a git-hosted specs repository is therefore unreadable in the GitHub UI.

## Goal

Resolve the export destination from an explicit precedence chain, and render
exports that are readable both in Obsidian (vault) and in the GitHub UI (specs
repository).

## Decisions (from brainstorming)

- **Destination precedence:** `--export-dir` → `SPECS_PATH` → `VAULT_PATH` →
  error. No silent default.
- **Validate pointers, create children.** A host pointer that does not exist is
  an error; directories the tool owns are created. A mistyped pointer must stop
  the run, not build a tree somewhere useless.
- **Two independent axes.** Layout (flat vs nested) follows the *destination*;
  content rendering (links, comments, attachments) follows `--link-style`.
  Inferred from the destination, overridable by flag.
- **Backwards compatibility is the contract.** Every new parameter defaults to
  Obsidian behavior. The 28 existing tests must pass unmodified.
- **Specs mode needs no import registry.** Each ticket resolves to its own
  `specifications/<ID>-*/` directory, so each `jira-import/` holds exactly one
  import; a cross-import registry would list one row.

## Design

Two new modules and changes threaded through six existing ones.

### 1. Destination resolution (`src/export_paths.py`, new)

```python
@dataclass(frozen=True)
class ExportTarget:
    data_dir: Path      # export root
    layout: str         # "nested" | "flat"
    origin: str         # "explicit" | "specs" | "vault"

class ExportPathError(ValueError): ...

def resolve_export_target(
    jira_id: str,
    export_dir: str | None,
    env: Mapping[str, str],
) -> ExportTarget: ...
```

`env` is injected so tests never read the real environment.

Precedence:

| # | Condition | `data_dir` | `layout` |
|---|---|---|---|
| 1 | `export_dir` given | `Path(export_dir).expanduser()`, relative resolved against cwd | `nested` |
| 2 | `SPECS_PATH` non-empty | `<specs>/specifications/<VI-dir>/jira-import` | `flat` |
| 3 | `VAULT_PATH` non-empty | `<vault>/jira-products` | `nested` |
| 4 | neither set | — | raises `ExportPathError` |

An environment variable set to the empty string counts as unset and falls
through to the next rule. This is the exact shape of the reported bug.

**`<VI-dir>` resolution.** Under `<specs>/specifications/`, match directories
named exactly `<ID>` **or** matching `<ID>-*`:

- exactly one match → use it
- zero matches → create `specifications/<ID>/`
- two or more → raise, listing the candidates

Matching the bare `<ID>` form matters: it is what the zero-match branch
creates, so a second run of the same ticket reuses that directory instead of
creating a duplicate.

**Existence rules — validate what you were handed, create what you own:**

| Path | Behavior |
|---|---|
| `$VAULT_PATH` | must exist, else `ExportPathError` |
| `$VAULT_PATH/jira-products` | created |
| `$SPECS_PATH` | must exist, else `ExportPathError` |
| `$SPECS_PATH/specifications` | must exist, else `ExportPathError` |
| `$SPECS_PATH/specifications/<VI-dir>` | created when the glob finds nothing |
| `<VI-dir>/jira-import` | created |
| `<data_dir>/<ID>/` (nested layout) | created |

`specifications/` is not auto-created: it is the specs repo's structural
convention, and its absence means the pointer is wrong.

**Known cost of the create-if-missing branch:** exporting a non-VI key (for
example `MGD-11951` directly) creates `specifications/MGD-11951/` in the specs
repo. Accepted deliberately; use `--export-dir` to avoid it.

### 2. Link rendering (`src/link_renderer.py`, new)

Below the import directory both layouts are structurally identical —
`<ID>-index.md` at the top, `<KEY>/<KEY>.md` one level down,
`<KEY>/attachments/` below that. The renderer therefore never needs to know the
layout. It needs only the file currently being written, of which there are
three kinds:

- `AT_ROOT` — `export-index.md`, the registry (nested layouts only)
- `AT_INDEX` — the per-import `<ID>-index.md`
- `AT_TICKET(key)` — a ticket page `<KEY>/<KEY>.md`

`renderer.at(location)` returns a bound context. Relative paths are derived
structurally from the location, never with `os.path.relpath` over absolute
paths — deterministic and unit-testable without a filesystem.

| Method | `ObsidianLinks` | `GithubLinks` from `AT_TICKET("MGD-11951")` |
|---|---|---|
| `issue(key)` — exported | `[[PRODUCT-18742]]` | `[PRODUCT-18742](../PRODUCT-18742/PRODUCT-18742.md)` |
| `issue(key)` — not exported | `[FOO-1](<base>/browse/FOO-1)` | `[FOO-1](<base>/browse/FOO-1)` |
| `index(name)` | `[[PRODUCT-18742-index]]` | `[PRODUCT-18742-index](../PRODUCT-18742-index.md)` |
| `image(file)` | `![[flow.png]]` | `![flow.png](attachments/flow.png)` |
| `attachment(file)` | `[[spec.pdf]]` | `[spec.pdf](attachments/spec.pdf)` |
| `table_cell(link)` | pipe-escape | pipe-escape |

From `AT_INDEX` the same calls yield `[KEY](KEY/KEY.md)`, and
`index("export-index")` yields `[export-index](../export-index.md)`; from
`AT_ROOT`, `issue`-style calls yield `[<root>](<root>/<root>-index.md)`.

**Under flat layout there is no `export-index.md`**, so the "Main Index"
backlink that `index_generator.py:30` emits unconditionally
(`**Main Index:** [[export-index]]`) must be omitted — otherwise the per-import
index links to a file that is never written. This is a layout-driven decision,
not a style-driven one: it applies to flat layout in either link style.

Both implementations hold the node set. This is the core reason for the
abstraction: `jira_markup_converter.py:24` currently emits `[[KEY]]` for *any*
issue key found in prose, exported or not. Obsidian tolerates a dangling
wikilink; GitHub would render a link to a file that does not exist.

**This is not a corner case.** The walk is not transitive over links —
`graph_walker.py:41` collects links from the root only; Epic children are
fetched recursively but *their* links are not, while `_add_node` still records
them (line 73) for rendering. Four sources of unexported keys:

1. links belonging to non-root issues (the common case)
2. fetch failures — `_fetch_issue` returns `None` on any exception
   (`graph_walker.py:68-70`) but the key remains in the linking issue's list
3. arbitrary issue keys mentioned in prose, linkified by
   `jira_markup_converter.py:24`
4. parent links outside the walked set (`field_formatter.py:82`)

Measured across the existing vault export: **701 Jira-URL fallbacks against
1875 wikilinks in index files alone — 27%.** Routing through `ctx.issue(key)`
makes the fallback correct by construction in both styles.

**Threading the context.** The converter is built once per exporter but the
context changes per issue, so it is passed as an argument rather than held as
mutable state:

```python
JiraMarkupConverter(jira_base_url, links=None)   # None -> Obsidian, no node set
converter.convert(text, links=ctx)               # per-call override
```

Five call sites: `comments_handler.py:51`, `markdown_exporter.py:44,218,226,265`.
The `links=None` default is what keeps `test_jira_markup_converter.py` passing
unmodified.

`jira_markup_converter.py:350` already protects `[text](url)` spans from the key
linkifier (the fix in commit `5ddbd6d`), so emitting markdown links instead of
wikilinks does not reopen that class of bug.

### 3. Style and layout selection (`src/main.py`)

```
--export-dir DIR       explicit destination (rule 1)
--link-style STYLE     obsidian | github
```

`--link-style` defaults to the destination's inferred style: `specs` → `github`,
`vault` and `explicit` → `obsidian`. The flag overrides in any mode. The
`DEFAULT_EXPORT_DIR = ".data"` constant is removed and the argparse default
becomes `None`, so "not specified" is distinguishable.

A banner prints the resolved destination, mode and link style **before** the
Jira round-trip, so a wrong pointer is visible immediately.

### 4. Comments (`src/comments_handler.py`, `src/markdown_exporter.py`)

`fetch_and_format_comments` (`comments_handler.py:19`) currently returns a whole
document: `# Comments for KEY`, a `**Ticket:**` backlink, `Total comments: N`,
then `## Comment #N` sections. Inlining that verbatim under `## Comments` would
nest an `<h1>` inside an `<h2>` and add a backlink to the page being read. It
splits in two:

- `format_comments_body(issue, level)` — the fragment: comments only, headings
  at `level` (`### Comment #1` when inlined under `## Comments`)
- `format_comments_document(issue)` — today's standalone file, a title and
  backlink wrapped around the fragment

`markdown_exporter.py:291-295` emits the fragment under GitHub style and today's
`![[KEY-comments]]` transclusion under Obsidian style. Under GitHub style no
`<KEY>-comments.md` file is written. Empty comments inline as `*No comments*`.

### 5. Attachments (`src/attachment_handler.py`)

`AttachmentHandler` gains `download_allowlist: set[str] | None`. `None` means
download everything (today's behavior, used by Obsidian style). GitHub style
passes the allowlist below; anything not on it — including files with **no**
extension — is recorded as `(filename, url, size)` from `attachment.content`
and `attachment.size`, and rendered as a sized link instead of being fetched.

```
images      png jpg jpeg gif bmp svg webp ico
documents   pdf doc docx xls xlsx csv ppt pptx odt ods odp rtf
text        txt md json xml yaml yml diff patch
```

Everything else links to Jira: archives (`zip tar gz 7z rar`), dumps
(`har ppdump log`), binaries, media, unlisted extensions, and extensionless
files. No size cap.

Rationale from the existing 163 MB vault export: archives are 45.9 MB across 46
files — 40% of attachment weight in 4% of files — while every allowlisted
document format totals under 10 MB. Extensionless blobs
(`binary_windows-x86-64`, UUID-named files) exist in the data and are handled by
the allowlist's default-deny.

Rendered form:

```markdown
## Attachments

![flow-diagram.png](attachments/flow-diagram.png)

- [SupportArchive3F642709.zip](https://…/attachment/98123) (11.2 MB)
```

This also reaches `replace_attachment_references` (`attachment_handler.py:63-91`),
which rewrites inline Jira attachment references: image references route through
`ctx.image(local)`, and a reference to a non-downloaded file becomes a Jira URL
rather than a link to a file that was never written.

### 6. Index and registry (`src/index_generator.py`)

`generate_import_index` takes a bound context and renders through it. Under flat
layout `main.py` writes `<ID>-index.md` directly into `jira-import/` and skips
`update_top_level_index` entirely — no `export-index.md`.

**Latent break to fix:** `index_generator.py:148` identifies a table row by
`line.startswith("| [[")`. Under `--link-style=github` rows begin
`| [MGD-11951](MGD-11951/MGD-11951.md)`, so the parser matches nothing and every
import silently loses its type, status and summary. The parser must accept both
the wikilink and markdown-link row forms.

## Output layouts

**Flat (specs mode):**

```
$SPECS_PATH/specifications/PRODUCT-18742-managed-mcp-server-bundling/
└── jira-import/
    ├── PRODUCT-18742-index.md
    ├── PRODUCT-18742/
    │   ├── PRODUCT-18742.md          # comments inlined
    │   └── attachments/              # allowlisted files only
    └── MGD-11951/
        └── MGD-11951.md
```

**Nested (vault and explicit modes) — unchanged from today:**

```
$VAULT_PATH/jira-products/
├── export-index.md
└── PRODUCT-18742/
    ├── PRODUCT-18742-index.md
    ├── PRODUCT-18742/
    │   ├── PRODUCT-18742.md
    │   ├── PRODUCT-18742-comments.md
    │   └── attachments/
    └── MGD-11951/
        └── ...
```

## Error messages

```
Error: no export destination. Pass --export-dir=<path>, or set SPECS_PATH or VAULT_PATH.

Error: SPECS_PATH is set to /workspace/specs but /workspace/specs/specifications
       does not exist. Is SPECS_PATH pointing at the specs repo root?

Error: VAULT_PATH is set to /workspace/vaultt but that directory does not exist.

Error: 2 candidate directories for PRODUCT-18742 under /workspace/specs/specifications:
         PRODUCT-18742
         PRODUCT-18742-managed-mcp-server-bundling
       Pass --export-dir to choose one.
```

All raised as `ExportPathError`, caught in `main.py`, printed, `sys.exit(1)`.

## What stays unchanged

- Vault-mode output, byte for byte, including `export-index.md` maintenance
- The graph walk, PII scrubbing, PR fetching, frontmatter
- `runme.sh`'s `P-` shorthand expansion and its venv validation guard
- Re-export semantics (see Known limitations)

`runme.sh` drops the `EXPORT_DIR` line and forwards extra arguments:
`python src/main.py "$JIRA_ID" "${@:2}"`. Resolution lives in Python so the
wrapper and a direct invocation cannot disagree — which is how they diverged in
the first place.

## Verification (success criteria)

Step 0, before any change: build a working venv and record a green baseline.
Both `.venv/bin/python` and `venv/bin/python` currently symlink to
`/Users/ivan.gudak/.pyenv/versions/3.14.5/bin/python`, a macOS host path, and
are dead on Linux — the stale-venv case commit `d87bb29` hardened `runme.sh`
against. Rebuild with `python -m venv --clear .venv` and
`pip install -r requirements-dev.txt`.

1. All 28 existing tests pass **unmodified**. If `test_additional_fields.py:8`
   or `test_jira_markup_converter.py:11` needs editing, the new defaults are
   wrong.
2. `test_export_paths.py` — all four rules; empty-string env treated as unset;
   glob zero/one/many matches; bare `<ID>` reuse on a second run; missing
   `$SPECS_PATH`, missing `specifications/`, missing `$VAULT_PATH`; relative,
   absolute and `~` forms of `--export-dir`. Injected env dict and `tmp_path`.
3. `test_link_renderer.py` — both renderers × three locations × exported and
   unexported keys; images; attachments; table escaping.
4. `test_comments_inlining.py` — fragment versus document form; heading
   demotion; empty comments.
5. `test_attachment_policy.py` — allowlist decisions including uppercase
   extensions and extensionless files; asserts non-allowlisted files are never
   *downloaded*, not merely omitted from output.
6. `test_index_registry.py` — the `index_generator.py:148` parser reading both
   row forms; and that flat layout omits the "Main Index" backlink while nested
   layout keeps it.
7. Manual: a real export to each of the three destinations. The specs-mode
   output renders correctly in the GitHub UI — links resolve, images display,
   comments read inline.
8. Manual: with `VAULT_PATH` and `SPECS_PATH` both unset, the tool exits 1 with
   the no-destination message and creates nothing.

## Known limitations (v1)

- Re-export deletes and recreates each *issue* folder but does not clear the
  import directory. A second run over a smaller graph leaves folders from the
  larger run behind; in a git repo these surface as stale directories in
  `git status`. Pre-existing behavior, deliberately unchanged.
- A non-VI key exported in specs mode creates a `specifications/<ID>/`
  directory (see Design §1).
- Non-downloaded attachments link to Jira and therefore require Jira access to
  open; the specs-mode export is not fully self-contained.

## Documentation

`README.md` currently misdescribes behavior and would misdescribe it worse.
Six corrections:

1. Line 44 — "configured inside `runme.sh` (`EXPORT_DIR` variable)" → the
   resolution table
2. Line 50 — `python src/main.py PRODUCT-12345` now errors without a pointer;
   the example needs one
3. Lines 70-88 — the `.data/` tree matches neither mode; replace with both
   layouts
4. Lines 118-125 — "Navigation" presents wikilinks as universal; add the
   Obsidian/GitHub split
5. New — document `--link-style` and the attachment allowlist with its rationale
6. Lines 134-135 — add the stale-directory caveat to "Re-exporting"

## Files touched

**New:** `src/export_paths.py`, `src/link_renderer.py`, `tests/test_export_paths.py`,
`tests/test_link_renderer.py`, `tests/test_comments_inlining.py`,
`tests/test_attachment_policy.py`, `tests/test_index_registry.py`

**Modified:** `src/main.py`, `src/markdown_exporter.py`, `src/index_generator.py`,
`src/comments_handler.py`, `src/attachment_handler.py`, `src/field_formatter.py`,
`src/jira_markup_converter.py`, `runme.sh`, `README.md`
