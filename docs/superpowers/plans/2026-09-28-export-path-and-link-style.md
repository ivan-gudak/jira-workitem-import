# Export Path Resolution and GitHub Link Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the export destination from an explicit precedence chain (`--export-dir` → `SPECS_PATH` → `VAULT_PATH` → error) instead of expanding an unset `VAULT_PATH` into the unwritable `/jira-products`, and render exports that read correctly both in Obsidian and in the GitHub UI.

**Architecture:** Two new pure modules. `export_paths.py` decides *where* output goes and returns a frozen `ExportTarget`; it touches no global state and creates no directories. `link_renderer.py` decides *how* links are written, via two implementations of one interface bound to the file currently being written. Every existing module that hardcodes `[[...]]` is threaded with a renderer that defaults to Obsidian, so behavior is unchanged until the final wiring task flips the switch.

**Tech Stack:** Python 3, `jira` library, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-export-path-and-link-style-design.md`

## Global Constraints

- The 28 existing tests must pass **unmodified**. If `tests/test_additional_fields.py:8` or `tests/test_jira_markup_converter.py:11` needs editing, a new default is wrong.
- Every new parameter defaults to today's Obsidian behavior.
- Vault-mode output must be byte-for-byte identical to today.
- `resolve_export_target` creates no directories and reads no global environment — the environment is injected.
- An environment variable set to the empty string counts as unset.
- Relative paths in `GithubLinks` are derived structurally from the location, never with `os.path.relpath` over absolute paths.

## Review Focus

Five input classes the spec implies but which no task's happy path exercises. Each has a test assigned to the task owning the code.

1. **Attachment filenames containing `(` `)` or spaces** break markdown links — `attachments/SupportArchiveD2DFE639(1).zip` truncates at the paren. Real data: this exact filename exists in the vault export. Must be URL-encoded. *(Tasks 3 and 8)*
2. **A Jira ID whose case differs from the directory name** (`product-18742` vs `PRODUCT-18742-…`) must still match the glob, or the tool silently creates a second directory. *(Task 1)*
3. **Uppercase file extensions** (`.PNG`, `.PDF`) must match the allowlist. *(Task 8)*
4. **Extensionless attachments** (`binary_windows-x86-64`, UUID-named blobs — both present in the vault data) must default-deny, not crash on `suffix == ""`. *(Task 8)*
5. **`~` and trailing slashes in `SPECS_PATH` / `VAULT_PATH`** must normalize, or a trailing slash produces a doubled separator and `~` a literal directory named `~`. *(Task 1)*

---

## File Structure

- `src/export_paths.py` (create) — destination resolution only. `ExportTarget`, `ExportPathError`, `resolve_export_target`. Pure: no I/O beyond `is_dir()` checks, no directory creation.
- `src/link_renderer.py` (create) — `Location`, `ObsidianLinks`, `GithubLinks`, and `OutputProfile` (the bundle of renderer + content policy that `MarkdownExporter` consumes). No Jira imports, no filesystem.
- `src/main.py` (modify) — calls the resolver, builds the profile, prints the destination banner *before* the walk, honors `layout`.
- `src/jira_markup_converter.py` (modify) — `convert(text, links=None)`; `_format_issue_link` delegates to the bound renderer when given one.
- `src/index_generator.py` (modify) — render through a bound renderer; omit the "Main Index" backlink under flat layout; teach the registry parser the markdown-link row form.
- `src/markdown_exporter.py` (modify) — accept an `OutputProfile`, bind a renderer per issue, route parent/linked/index links through it.
- `src/field_formatter.py` (modify) — `format_issue_link` / `format_parent_link` accept an optional renderer.
- `src/comments_handler.py` (modify) — split document form from fragment form.
- `src/attachment_handler.py` (modify) — extension allowlist; sized Jira links for skipped files; renderer-driven reference rewriting.
- `runme.sh` (modify) — drop `EXPORT_DIR`, forward extra arguments.
- `README.md` (modify) — six corrections listed in the spec.
- `tests/test_export_paths.py`, `tests/test_link_renderer.py`, `tests/test_comments_inlining.py`, `tests/test_attachment_policy.py`, `tests/test_index_registry.py` (create).

**Refinement on the spec, flagged:** the spec describes passing a renderer to `MarkdownExporter` and `download_allowlist` to `AttachmentHandler` as separate parameters. This plan bundles the three style-driven decisions (renderer, comment inlining, download allowlist) into one `OutputProfile` value object, so the exporter constructor grows by one parameter instead of three and the three decisions cannot drift out of sync. Same behavior, same module names.

**Reference interfaces (verified against the code — do not re-derive):**
- `IssueNode` (`graph_walker.py:10`) has `.key`, `.issue`, `.role` (`"root"|"linked"|"epic_child"`), `.links` — a list of `(link_type, direction, target_key)` where direction is `"outward"|"inward"`.
- `nodes` throughout is `dict[str, IssueNode]` keyed by issue key.
- `JIRA_BASE_URL` comes from `config.py`.
- `AttachmentHandler.downloaded_files` is `dict[original_name, local_filename]`; `_unique_filename` appends `_1`, `_2` on collision, so the local name can differ from the original.
- `jira` attachment objects expose `.filename`, `.content` (download URL), `.size` (bytes), `.get()` (returns bytes).
- `JiraMarkupConverter._convert_links` (line 304) protects `[text](url)` spans, `[[wikilinks]]`, and bare URLs with `<<<LINKn>>>` placeholders before linkifying bare issue keys, then restores them.
- `PiiScrubber.scrub_text(text)` and `.anonymize_name(displayName) -> "User-N"`.
- Existing test suite: 28 tests across `tests/test_additional_fields.py` (17) and `tests/test_jira_markup_converter.py` (11).

---

## Task 1: Working baseline + the destination resolver

The bug fix proper. `export_paths.py` is pure, so it is fully testable before anything is wired.

**Files:**
- Create: `src/export_paths.py`
- Create: `tests/test_export_paths.py`

- [ ] **Step 1: Rebuild the virtualenv**

Both `.venv/bin/python` and `venv/bin/python` currently symlink to `/Users/ivan.gudak/.pyenv/versions/3.14.5/bin/python`. On a host where that path is real this is fine; if the interpreter is not executable, rebuild.

Run:
```bash
cd /workspace/jira-workitem-import
[ -x .venv/bin/python ] && .venv/bin/python -c '' || python3 -m venv --clear .venv
source .venv/bin/activate
pip install -q -r requirements-dev.txt
```
Expected: no errors; `python -c 'import pytest, jira'` succeeds.

- [ ] **Step 2: Record the green baseline**

Run: `python -m pytest -q`
Expected: **28 passed.** Write the number down. Every later task compares against it. If this is not green, stop and fix the environment before changing any source.

- [ ] **Step 3: Write the failing tests**

Create `tests/test_export_paths.py`:

```python
import pytest

from export_paths import ExportPathError, resolve_export_target


def make_specs(tmp_path, *vi_dirs):
    """Build a specs repo skeleton; return its root."""
    specs = tmp_path / "specs"
    (specs / "specifications").mkdir(parents=True)
    for name in vi_dirs:
        (specs / "specifications" / name).mkdir()
    return specs


def make_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


# --- Rule 1: explicit --export-dir wins -------------------------------------

def test_explicit_absolute_dir_wins_over_env(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    target = resolve_export_target(
        "PRODUCT-1", str(tmp_path / "out"), {"SPECS_PATH": str(specs)}
    )
    assert target.data_dir == tmp_path / "out"
    assert target.layout == "nested"
    assert target.origin == "explicit"


def test_explicit_relative_dir_resolves_against_cwd(tmp_path):
    target = resolve_export_target("PRODUCT-1", ".data", {}, cwd=tmp_path)
    assert target.data_dir == tmp_path / ".data"


def test_explicit_tilde_dir_expands(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = resolve_export_target("PRODUCT-1", "~/out", {})
    assert target.data_dir == tmp_path / "out"


# --- Rule 2: SPECS_PATH ------------------------------------------------------

def test_specs_single_glob_match(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-18742-managed-mcp-server-bundling")
    target = resolve_export_target("PRODUCT-18742", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == (
        specs / "specifications" / "PRODUCT-18742-managed-mcp-server-bundling" / "jira-import"
    )
    assert target.layout == "flat"
    assert target.origin == "specs"


def test_specs_no_match_uses_bare_id_dir(tmp_path):
    specs = make_specs(tmp_path)
    target = resolve_export_target("PRODUCT-99999", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "specifications" / "PRODUCT-99999" / "jira-import"
    assert target.layout == "flat"


def test_specs_reuses_bare_id_dir_on_second_run(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-99999")
    target = resolve_export_target("PRODUCT-99999", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "specifications" / "PRODUCT-99999" / "jira-import"


def test_specs_multiple_matches_raises_and_lists_them(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-18742", "PRODUCT-18742-managed-mcp")
    with pytest.raises(ExportPathError) as exc:
        resolve_export_target("PRODUCT-18742", None, {"SPECS_PATH": str(specs)})
    message = str(exc.value)
    assert "PRODUCT-18742-managed-mcp" in message
    assert "--export-dir" in message


def test_specs_ignores_files_that_look_like_matches(tmp_path):
    specs = make_specs(tmp_path)
    (specs / "specifications" / "PRODUCT-18742-notes.md").write_text("x")
    target = resolve_export_target("PRODUCT-18742", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "specifications" / "PRODUCT-18742" / "jira-import"


def test_specs_prefix_does_not_over_match(tmp_path):
    """PRODUCT-1 must not match PRODUCT-18742-slug."""
    specs = make_specs(tmp_path, "PRODUCT-18742-slug")
    target = resolve_export_target("PRODUCT-1", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == specs / "specifications" / "PRODUCT-1" / "jira-import"


def test_specs_missing_root_raises(tmp_path):
    with pytest.raises(ExportPathError, match="does not exist"):
        resolve_export_target("PRODUCT-1", None, {"SPECS_PATH": str(tmp_path / "nope")})


def test_specs_missing_specifications_dir_raises(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    with pytest.raises(ExportPathError, match="specifications"):
        resolve_export_target("PRODUCT-1", None, {"SPECS_PATH": str(specs)})


# --- Rule 3: VAULT_PATH ------------------------------------------------------

def test_vault_path_used_when_specs_absent(tmp_path):
    vault = make_vault(tmp_path)
    target = resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": str(vault)})
    assert target.data_dir == vault / "jira-products"
    assert target.layout == "nested"
    assert target.origin == "vault"


def test_specs_wins_over_vault(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-1-slug")
    vault = make_vault(tmp_path)
    target = resolve_export_target(
        "PRODUCT-1", None, {"SPECS_PATH": str(specs), "VAULT_PATH": str(vault)}
    )
    assert target.origin == "specs"


def test_vault_missing_dir_raises(tmp_path):
    with pytest.raises(ExportPathError, match="VAULT_PATH"):
        resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": str(tmp_path / "nope")})


# --- Rule 4: nothing set -----------------------------------------------------

def test_no_destination_raises(tmp_path):
    with pytest.raises(ExportPathError, match="no export destination"):
        resolve_export_target("PRODUCT-1", None, {})


def test_empty_string_env_counts_as_unset(tmp_path):
    """The reported bug: VAULT_PATH='' must not yield /jira-products."""
    with pytest.raises(ExportPathError, match="no export destination"):
        resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": "", "SPECS_PATH": "   "})


def test_resolver_creates_no_directories(tmp_path):
    specs = make_specs(tmp_path)
    target = resolve_export_target("PRODUCT-99999", None, {"SPECS_PATH": str(specs)})
    assert not target.data_dir.exists()
    assert not (specs / "specifications" / "PRODUCT-99999").exists()


# --- Review Focus 2 and 5 ----------------------------------------------------

def test_jira_id_case_insensitive_glob_match(tmp_path):
    specs = make_specs(tmp_path, "PRODUCT-18742-managed-mcp")
    target = resolve_export_target("product-18742", None, {"SPECS_PATH": str(specs)})
    assert target.data_dir == (
        specs / "specifications" / "PRODUCT-18742-managed-mcp" / "jira-import"
    )


def test_trailing_slash_in_pointer_normalizes(tmp_path):
    vault = make_vault(tmp_path)
    target = resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": str(vault) + "/"})
    assert target.data_dir == vault / "jira-products"


def test_tilde_in_vault_path_expands(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "myvault").mkdir()
    target = resolve_export_target("PRODUCT-1", None, {"VAULT_PATH": "~/myvault"})
    assert target.data_dir == tmp_path / "myvault" / "jira-products"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_export_paths.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'export_paths'`.

- [ ] **Step 5: Implement the resolver**

Create `src/export_paths.py`:

```python
"""
Export destination resolution.

Decides where an export is written, from --export-dir, SPECS_PATH, or
VAULT_PATH, in that order. Pure: reads only the environment mapping it is
given, and creates no directories — the caller owns creation.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


class ExportPathError(ValueError):
    """Raised when the export destination cannot be resolved."""


@dataclass(frozen=True)
class ExportTarget:
    """Where an export goes, and how it is laid out."""
    data_dir: Path
    layout: str   # "nested" | "flat"
    origin: str   # "explicit" | "specs" | "vault"


def _pointer(env: Mapping[str, str], name: str) -> Optional[Path]:
    """Read an env pointer. Empty or whitespace-only counts as unset."""
    raw = (env.get(name) or "").strip()
    if not raw:
        return None
    # rstrip the separator so a trailing slash does not doubled-up later
    return Path(raw.rstrip("/")).expanduser()


def resolve_export_target(
    jira_id: str,
    export_dir: Optional[str],
    env: Mapping[str, str],
    cwd: Optional[Path] = None,
) -> ExportTarget:
    """Resolve the export destination. Raises ExportPathError with guidance."""
    if export_dir:
        base = Path(export_dir).expanduser()
        if not base.is_absolute():
            base = Path(cwd) if cwd else Path.cwd()
            base = base / Path(export_dir).expanduser()
        return ExportTarget(data_dir=base, layout="nested", origin="explicit")

    specs_root = _pointer(env, "SPECS_PATH")
    if specs_root is not None:
        return _resolve_specs(jira_id, specs_root)

    vault_root = _pointer(env, "VAULT_PATH")
    if vault_root is not None:
        if not vault_root.is_dir():
            raise ExportPathError(
                f"VAULT_PATH is set to {vault_root} but that directory does not exist."
            )
        return ExportTarget(
            data_dir=vault_root / "jira-products", layout="nested", origin="vault"
        )

    raise ExportPathError(
        "no export destination. Pass --export-dir=<path>, or set SPECS_PATH or VAULT_PATH."
    )


def _resolve_specs(jira_id: str, specs_root: Path) -> ExportTarget:
    if not specs_root.is_dir():
        raise ExportPathError(
            f"SPECS_PATH is set to {specs_root} but that directory does not exist."
        )

    specifications = specs_root / "specifications"
    if not specifications.is_dir():
        raise ExportPathError(
            f"SPECS_PATH is set to {specs_root} but {specifications} does not exist. "
            "Is SPECS_PATH pointing at the specs repo root?"
        )

    wanted = jira_id.casefold()
    matches = sorted(
        (d for d in specifications.iterdir()
         if d.is_dir() and (d.name.casefold() == wanted
                            or d.name.casefold().startswith(f"{wanted}-"))),
        key=lambda d: d.name,
    )

    if len(matches) > 1:
        listed = "\n".join(f"         {d.name}" for d in matches)
        raise ExportPathError(
            f"{len(matches)} candidate directories for {jira_id} under {specifications}:\n"
            f"{listed}\n"
            "       Pass --export-dir to choose one."
        )

    vi_dir = matches[0] if matches else specifications / jira_id
    return ExportTarget(data_dir=vi_dir / "jira-import", layout="flat", origin="specs")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_export_paths.py -q`
Expected: all pass.

- [ ] **Step 7: Confirm no regression**

Run: `python -m pytest -q`
Expected: 28 + the new tests, all passing.

- [ ] **Step 8: Commit**

```bash
git add src/export_paths.py tests/test_export_paths.py
git commit -m "feat: add export destination resolver with explicit precedence"
```

---

## Task 2: Wire the resolver into main.py and runme.sh

Makes the bug fix reachable. Link style is still Obsidian everywhere; only the destination and layout change.

**Files:**
- Modify: `src/main.py:21-40` (argparse + resolution), `src/main.py:69-90` (layout)
- Modify: `runme.sh:17,31`

- [ ] **Step 1: Replace the destination block in `main.py`**

Delete `DEFAULT_EXPORT_DIR = ".data"` (line 21). Add the import:

```python
from export_paths import ExportPathError, resolve_export_target
```

Replace the `--export-dir` argument (lines 32-36) and the `data_dir` assignment (lines 39-40) with:

```python
    parser.add_argument(
        "--export-dir",
        default=None,
        help="Output directory. Overrides SPECS_PATH and VAULT_PATH.",
    )
    args = parser.parse_args()

    try:
        target = resolve_export_target(args.jira_id, args.export_dir, os.environ)
    except ExportPathError as e:
        print(f"Error: {e}")
        sys.exit(1)

    data_dir = target.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print(f"Destination: {data_dir}")
    print(f"Source:      {target.origin}    Layout: {target.layout}")
    print("=" * 50)
```

The banner prints before authentication, so a wrong pointer surfaces immediately rather than after the graph walk.

- [ ] **Step 2: Honor the layout**

Replace lines 69-71 (`import_dir = data_dir / args.jira_id`) with:

```python
    # Flat layout: the destination is already import-specific, so no <ID> level.
    import_dir = data_dir if target.layout == "flat" else data_dir / args.jira_id
    import_dir.mkdir(parents=True, exist_ok=True)
```

Replace lines 88-90 (the top-level index update) with:

```python
    # The registry lists sibling imports; a flat destination holds exactly one.
    if target.layout == "nested":
        update_top_level_index(data_dir)
        print(f"Top-level index: {data_dir / 'export-index.md'}")
```

- [ ] **Step 3: Simplify `runme.sh`**

Delete line 17 (`EXPORT_DIR="$VAULT_PATH/jira-products"`) and its preceding blank line. Change the final line from

```bash
python src/main.py "$JIRA_ID" --export-dir="$EXPORT_DIR"
```

to

```bash
python src/main.py "$JIRA_ID" "${@:2}"
```

Extra arguments now pass through, and resolution lives in one place.

- [ ] **Step 4: Verify the no-destination error**

Run: `env -u VAULT_PATH -u SPECS_PATH python src/main.py PRODUCT-1; echo "exit=$?"`
Expected:
```
Error: no export destination. Pass --export-dir=<path>, or set SPECS_PATH or VAULT_PATH.
exit=1
```
Confirm nothing was created: `ls /jira-products` → No such file or directory.

- [ ] **Step 5: Verify the banner prints before the Jira call**

Run: `env -u SPECS_PATH VAULT_PATH=/nonexistent python src/main.py PRODUCT-1; echo "exit=$?"`
Expected: the `VAULT_PATH is set to /nonexistent but that directory does not exist.` error and `exit=1`, with no "Connected to:" line — proving the check precedes authentication.

- [ ] **Step 6: Confirm no regression**

Run: `python -m pytest -q`
Expected: same count as Task 1, all passing.

- [ ] **Step 7: Commit**

```bash
git add src/main.py runme.sh
git commit -m "fix: resolve export destination explicitly instead of defaulting to /jira-products"
```

---

## Task 3: The link renderer

Pure module, no wiring. Both styles, three locations.

**Files:**
- Create: `src/link_renderer.py`
- Create: `tests/test_link_renderer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_link_renderer.py`:

```python
from link_renderer import GithubLinks, Location, ObsidianLinks, OutputProfile

BASE = "https://example.atlassian.net"
KEYS = {"PRODUCT-18742", "MGD-11951"}


def obsidian():
    return ObsidianLinks(BASE, KEYS)


def github():
    return GithubLinks(BASE, KEYS)


# --- Obsidian: location never matters ---------------------------------------

def test_obsidian_issue_link_is_a_wikilink():
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.issue("PRODUCT-18742") == "[[PRODUCT-18742]]"


def test_obsidian_unexported_key_falls_back_to_jira_url():
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.issue("FOO-1") == f"[FOO-1]({BASE}/browse/FOO-1)"


def test_obsidian_image_and_attachment():
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.image("flow.png") == "![[flow.png]]"
    assert at.attachment("spec.pdf") == "[[spec.pdf]]"


def test_obsidian_index_link():
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.index("PRODUCT-18742-index") == "[[PRODUCT-18742-index]]"


# --- GitHub: relative paths derived from the location ------------------------

def test_github_ticket_to_sibling_ticket():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.issue("PRODUCT-18742") == "[PRODUCT-18742](../PRODUCT-18742/PRODUCT-18742.md)"


def test_github_index_to_ticket():
    at = github().at(Location.index())
    assert at.issue("MGD-11951") == "[MGD-11951](MGD-11951/MGD-11951.md)"


def test_github_unexported_key_falls_back_to_jira_url():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.issue("FOO-1") == f"[FOO-1]({BASE}/browse/FOO-1)"


def test_github_ticket_to_index():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.index("PRODUCT-18742-index") == "[PRODUCT-18742-index](../PRODUCT-18742-index.md)"


def test_github_index_to_registry():
    at = github().at(Location.index())
    assert at.index("export-index") == "[export-index](../export-index.md)"


def test_github_registry_to_import_index():
    at = github().at(Location.root())
    assert at.index("PRODUCT-18742-index") == (
        "[PRODUCT-18742-index](PRODUCT-18742/PRODUCT-18742-index.md)"
    )


def test_github_image_is_relative_to_the_ticket():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.image("flow.png") == "![flow.png](attachments/flow.png)"


def test_github_attachment_link():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.attachment("spec.pdf") == "[spec.pdf](attachments/spec.pdf)"


def test_github_external_file_link_with_size():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.external_file("archive.zip", f"{BASE}/attachment/98123", 11_744_051) == (
        f"[archive.zip]({BASE}/attachment/98123) (11.2 MB)"
    )


# --- Review Focus 1: filenames that break markdown links ---------------------

def test_github_encodes_parentheses_in_filenames():
    """Real vault data contains SupportArchiveD2DFE639(1).zip."""
    at = github().at(Location.ticket("MGD-11951"))
    assert at.attachment("SupportArchiveD2DFE639(1).zip") == (
        "[SupportArchiveD2DFE639(1).zip](attachments/SupportArchiveD2DFE639%281%29.zip)"
    )


def test_github_encodes_spaces_in_filenames():
    at = github().at(Location.ticket("MGD-11951"))
    assert at.image("my screenshot.png") == (
        "![my screenshot.png](attachments/my%20screenshot.png)"
    )


def test_obsidian_leaves_parentheses_alone():
    """Wikilinks are not URLs; encoding would break them."""
    at = obsidian().at(Location.ticket("MGD-11951"))
    assert at.attachment("SupportArchiveD2DFE639(1).zip") == "[[SupportArchiveD2DFE639(1).zip]]"


# --- Table escaping ----------------------------------------------------------

def test_table_cell_escapes_pipes_in_both_styles():
    for renderer in (obsidian(), github()):
        at = renderer.at(Location.index())
        assert at.table_cell("[[a|b]]") == "[[a\\|b]]"


# --- Profiles ----------------------------------------------------------------

def test_obsidian_profile_defaults():
    profile = OutputProfile.for_style("obsidian", BASE, KEYS)
    assert profile.renderer.style == "obsidian"
    assert profile.inline_comments is False
    assert profile.download_allowlist is None


def test_github_profile_defaults():
    profile = OutputProfile.for_style("github", BASE, KEYS)
    assert profile.renderer.style == "github"
    assert profile.inline_comments is True
    assert "png" in profile.download_allowlist
    assert "zip" not in profile.download_allowlist
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_link_renderer.py -q`
Expected: `ModuleNotFoundError: No module named 'link_renderer'`.

- [ ] **Step 3: Implement the renderer**

Create `src/link_renderer.py`:

```python
"""
Link rendering for exported markdown.

Two styles: Obsidian wikilinks (for a vault) and relative markdown links (for
the GitHub UI, which renders neither [[KEY]] nor ![[image]]).

Below the import directory both layouts are structurally identical:

    <ID>-index.md
    <KEY>/<KEY>.md
    <KEY>/attachments/<file>

so a renderer needs only to know which of three kinds of file it is currently
writing. Relative paths are derived from that, never from absolute paths.
"""

from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import quote

#: Downloaded in GitHub style. Everything else links to Jira.
GITHUB_DOWNLOAD_ALLOWLIST = frozenset({
    # images
    "png", "jpg", "jpeg", "gif", "bmp", "svg", "webp", "ico",
    # documents
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "ppt", "pptx",
    "odt", "ods", "odp", "rtf",
    # text
    "txt", "md", "json", "xml", "yaml", "yml", "diff", "patch",
})


@dataclass(frozen=True)
class Location:
    """Which file is being written."""
    kind: str        # "root" | "index" | "ticket"
    key: str = ""

    @staticmethod
    def root() -> "Location":
        """export-index.md, the registry (nested layouts only)."""
        return Location("root")

    @staticmethod
    def index() -> "Location":
        """The per-import <ID>-index.md."""
        return Location("index")

    @staticmethod
    def ticket(key: str) -> "Location":
        """A ticket page <KEY>/<KEY>.md."""
        return Location("ticket", key)


def human_size(num_bytes: int) -> str:
    """Render a byte count as e.g. '11.2 MB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class _Bound:
    """A renderer bound to the file currently being written."""

    def __init__(self, renderer: "BaseLinks", location: Location):
        self._r = renderer
        self._loc = location

    def issue(self, key: str) -> str:
        return self._r.issue(key, self._loc)

    def index(self, name: str) -> str:
        return self._r.index(name, self._loc)

    def image(self, filename: str) -> str:
        return self._r.image(filename, self._loc)

    def attachment(self, filename: str) -> str:
        return self._r.attachment(filename, self._loc)

    def external_file(self, filename: str, url: str, size: Optional[int] = None) -> str:
        return self._r.external_file(filename, url, size)

    def table_cell(self, rendered: str) -> str:
        return self._r.table_cell(rendered)


class BaseLinks:
    """Shared behavior: the node set and the Jira fallback."""

    style = ""

    def __init__(self, jira_base_url: str, keys: Iterable[str] = ()):
        self.jira_base_url = jira_base_url.rstrip("/")
        self.keys = set(keys)

    def at(self, location: Location) -> _Bound:
        return _Bound(self, location)

    def external(self, key: str) -> str:
        """A key outside the export: always a Jira URL, in both styles."""
        return f"[{key}]({self.jira_base_url}/browse/{key})"

    def external_file(self, filename: str, url: str, size: Optional[int] = None) -> str:
        suffix = f" ({human_size(size)})" if size else ""
        return f"[{filename}]({url}){suffix}"

    @staticmethod
    def table_cell(rendered: str) -> str:
        return rendered.replace("|", "\\|")


class ObsidianLinks(BaseLinks):
    """Wikilinks. Obsidian resolves by filename, so location is irrelevant."""

    style = "obsidian"

    def issue(self, key: str, location: Location) -> str:
        return f"[[{key}]]" if key in self.keys else self.external(key)

    def index(self, name: str, location: Location) -> str:
        return f"[[{name}]]"

    def image(self, filename: str, location: Location) -> str:
        return f"![[{filename}]]"

    def attachment(self, filename: str, location: Location) -> str:
        return f"[[{filename}]]"


class GithubLinks(BaseLinks):
    """Relative markdown links that resolve in the GitHub file browser."""

    style = "github"

    def issue(self, key: str, location: Location) -> str:
        if key not in self.keys:
            return self.external(key)
        if location.kind == "ticket":
            path = f"../{key}/{key}.md"
        else:
            path = f"{key}/{key}.md"
        return f"[{key}]({_url_path(path)})"

    def index(self, name: str, location: Location) -> str:
        if location.kind == "root":
            # export-index.md -> <ID>/<ID>-index.md
            stem = name[: -len("-index")] if name.endswith("-index") else name
            path = f"{stem}/{name}.md"
        else:
            # A ticket page or the per-import index links one level up.
            path = f"../{name}.md"
        return f"[{name}]({_url_path(path)})"

    def image(self, filename: str, location: Location) -> str:
        return f"![{filename}]({_url_path(f'attachments/{filename}')})"

    def attachment(self, filename: str, location: Location) -> str:
        return f"[{filename}]({_url_path(f'attachments/{filename}')})"


def _url_path(path: str) -> str:
    """Percent-encode a relative path so spaces and parens survive markdown."""
    return quote(path, safe="/._-")


@dataclass(frozen=True)
class OutputProfile:
    """The three style-driven output decisions, bundled so they cannot drift."""
    renderer: BaseLinks
    inline_comments: bool
    download_allowlist: Optional[frozenset]

    @staticmethod
    def for_style(style: str, jira_base_url: str, keys: Iterable[str] = ()) -> "OutputProfile":
        if style == "github":
            return OutputProfile(
                renderer=GithubLinks(jira_base_url, keys),
                inline_comments=True,
                download_allowlist=GITHUB_DOWNLOAD_ALLOWLIST,
            )
        if style == "obsidian":
            return OutputProfile(
                renderer=ObsidianLinks(jira_base_url, keys),
                inline_comments=False,
                download_allowlist=None,
            )
        raise ValueError(f"unknown link style: {style!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_link_renderer.py -q`
Expected: all pass.

- [ ] **Step 5: Confirm no regression**

Run: `python -m pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/link_renderer.py tests/test_link_renderer.py
git commit -m "feat: add Obsidian and GitHub link renderers"
```

---

## Task 4: Thread the renderer through the markup converter

The most delicate change: this is the code that three of the last five commits fixed. Behavior must be identical when `links` is not supplied.

**Files:**
- Modify: `src/jira_markup_converter.py:22-24` (`_format_issue_link`), the `convert` signature (line 31), `_convert_links` (line 304)
- Test: `tests/test_jira_markup_converter.py` (append; do not edit existing tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_jira_markup_converter.py`:

```python
from link_renderer import GithubLinks, Location, ObsidianLinks

BASE_URL = "https://example.atlassian.net"


def test_convert_without_links_is_unchanged():
    """The default path must stay byte-identical — 11 existing tests rely on it."""
    conv = make_converter()
    assert conv.convert("See PRODUCT-18503 for details") == "See [[PRODUCT-18503]] for details"


def test_convert_with_github_links_uses_relative_path_for_exported_key():
    conv = make_converter()
    ctx = GithubLinks(BASE_URL, {"PRODUCT-18503"}).at(Location.ticket("MGD-1"))
    out = conv.convert("See PRODUCT-18503 for details", links=ctx)
    assert out == "See [PRODUCT-18503](../PRODUCT-18503/PRODUCT-18503.md) for details"


def test_convert_with_github_links_falls_back_for_unexported_key():
    conv = make_converter()
    ctx = GithubLinks(BASE_URL, set()).at(Location.ticket("MGD-1"))
    out = conv.convert("See PRODUCT-18503 for details", links=ctx)
    assert out == f"See [PRODUCT-18503]({BASE_URL}/browse/PRODUCT-18503) for details"


def test_convert_with_obsidian_links_falls_back_for_unexported_key():
    """Even in Obsidian style, an unexported key becomes a Jira URL once the
    node set is known — a dangling wikilink helps nobody."""
    conv = make_converter()
    ctx = ObsidianLinks(BASE_URL, {"OTHER-1"}).at(Location.ticket("MGD-1"))
    out = conv.convert("See PRODUCT-18503 for details", links=ctx)
    assert out == f"See [PRODUCT-18503]({BASE_URL}/browse/PRODUCT-18503) for details"


def test_github_links_do_not_reopen_the_bare_url_bug():
    """Regression guard for commit 5ddbd6d under the new style."""
    conv = make_converter()
    ctx = GithubLinks(BASE_URL, {"MGD-8605"}).at(Location.ticket("MGD-1"))
    out = conv.convert(f"See {BASE_URL}/browse/MGD-8605 for details", links=ctx)
    assert out == f"See {BASE_URL}/browse/MGD-8605 for details"


def test_github_links_do_not_reopen_the_bracketed_marker_bug():
    """Regression guard for commit 1874c4d under the new style."""
    conv = make_converter()
    ctx = GithubLinks(BASE_URL, {"US-1"}).at(Location.ticket("MGD-1"))
    out = conv.convert("### [US-1]: View OneAgent configuration state", links=ctx)
    assert out == "### [US-1]: View OneAgent configuration state"


def test_github_smart_link_uses_the_renderer():
    conv = make_converter()
    ctx = GithubLinks(BASE_URL, {"MGD-8605"}).at(Location.ticket("MGD-1"))
    out = conv.convert("[MGD-8605|smart-link]", links=ctx)
    assert out == "[MGD-8605](../MGD-8605/MGD-8605.md)"


def test_generated_markdown_links_are_protected_from_relinkification():
    """A rendered link contains a key; it must not be linkified again."""
    conv = make_converter()
    ctx = GithubLinks(BASE_URL, {"MGD-8605"}).at(Location.ticket("MGD-1"))
    out = conv.convert("MGD-8605 and MGD-8605", links=ctx)
    assert out.count("](../MGD-8605/MGD-8605.md)") == 2
    assert "[[" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_jira_markup_converter.py -q`
Expected: the new tests fail with `TypeError: convert() got an unexpected keyword argument 'links'`.

- [ ] **Step 3: Add the optional renderer**

In `src/jira_markup_converter.py`, replace `_format_issue_link` (lines 22-24) with:

```python
    def _format_issue_link(self, key: str, links=None) -> str:
        """Render a Jira issue key. Falls back to a wikilink when no renderer
        is supplied, which keeps the no-argument call path unchanged."""
        if links is not None:
            return links.issue(key)
        return f"[[{key}]]"
```

Change the `convert` signature from `def convert(self, text: str) -> str:` to:

```python
    def convert(self, text: str, links=None) -> str:
```

and thread `links` down to the `_convert_links` call inside `convert` (find the line reading `text = self._convert_links(text)` and change it to `text = self._convert_links(text, links)`).

- [ ] **Step 4: Thread it through `_convert_links`**

Change the signature at line 304 to `def _convert_links(self, text: str, links=None) -> str:` and update the two closures that call `_format_issue_link`:

```python
        def replace_smart_link(match):
            key = match.group(1)
            return self._format_issue_link(key, links)
```

```python
        def replace_issue_key(match):
            key = match.group(0)
            return self._format_issue_link(key, links)
```

The existing placeholder machinery needs no change: `protect_markdown_link` (line 350) already shields `[text](url)` spans, so links this renderer emits are protected from the bare-key pass that follows.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_jira_markup_converter.py -q`
Expected: all pass, **including the 11 original tests unmodified**.

- [ ] **Step 6: Confirm no regression**

Run: `python -m pytest -q`

- [ ] **Step 7: Commit**

```bash
git add src/jira_markup_converter.py tests/test_jira_markup_converter.py
git commit -m "feat: let the markup converter render issue links through a renderer"
```

---

## Task 5: Thread the renderer through the index generator

Also fixes the registry parser and the flat-layout backlink.

**Files:**
- Modify: `src/index_generator.py` (lines 16-25, 28-30, 44, 61, 72, 127, 148, 163)
- Create: `tests/test_index_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_index_registry.py`:

```python
from dataclasses import dataclass
from typing import Any

from index_generator import generate_import_index, update_top_level_index
from link_renderer import GithubLinks, Location, ObsidianLinks

BASE = "https://example.atlassian.net"


class FakeNamed:
    def __init__(self, name):
        self.name = name


class FakeFields:
    def __init__(self, summary, itype, status):
        self.summary = summary
        self.issuetype = FakeNamed(itype)
        self.status = FakeNamed(status)
        self.parent = None


class FakeIssue:
    def __init__(self, key, summary="A summary", itype="Story", status="Open"):
        self.key = key
        self.fields = FakeFields(summary, itype, status)


@dataclass
class FakeNode:
    key: str
    issue: Any
    role: str
    links: list


def make_nodes():
    return {
        "PRODUCT-1": FakeNode("PRODUCT-1", FakeIssue("PRODUCT-1", itype="Epic"), "root",
                              [("blocks", "outward", "MGD-2")]),
        "MGD-2": FakeNode("MGD-2", FakeIssue("MGD-2"), "linked", []),
    }


def test_obsidian_index_keeps_wikilinks_and_backlink():
    nodes = make_nodes()
    links = ObsidianLinks(BASE, nodes.keys())
    out = generate_import_index(None, nodes, "PRODUCT-1", links=links, layout="nested")
    assert "**Main Index:** [[export-index]]" in out
    assert "[[MGD-2]]" in out


def test_github_index_uses_relative_links():
    nodes = make_nodes()
    links = GithubLinks(BASE, nodes.keys())
    out = generate_import_index(None, nodes, "PRODUCT-1", links=links, layout="nested")
    assert "[MGD-2](MGD-2/MGD-2.md)" in out
    assert "[[" not in out


def test_flat_layout_omits_the_main_index_backlink():
    """Flat layout writes no export-index.md, so the backlink would 404."""
    nodes = make_nodes()
    links = GithubLinks(BASE, nodes.keys())
    out = generate_import_index(None, nodes, "PRODUCT-1", links=links, layout="flat")
    assert "Main Index" not in out
    assert "export-index" not in out


def test_unexported_link_target_falls_back_to_jira_url():
    nodes = make_nodes()
    nodes["PRODUCT-1"].links = [("blocks", "outward", "FOO-99")]
    links = GithubLinks(BASE, nodes.keys())
    out = generate_import_index(None, nodes, "PRODUCT-1", links=links, layout="flat")
    assert f"[FOO-99]({BASE}/browse/FOO-99)" in out


def test_registry_parses_wikilink_rows(tmp_path):
    sub = tmp_path / "PRODUCT-1"
    sub.mkdir()
    (sub / "PRODUCT-1-index.md").write_text(
        "| Key | Type | Status | Summary | Role |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| [[PRODUCT-1]] | Epic | Open | A summary | root |\n",
        encoding="utf-8",
    )
    update_top_level_index(tmp_path)
    out = (tmp_path / "export-index.md").read_text(encoding="utf-8")
    assert "Epic" in out and "A summary" in out


def test_registry_parses_markdown_link_rows(tmp_path):
    """Regression: the parser only knew '| [[' and silently lost every field."""
    sub = tmp_path / "PRODUCT-1"
    sub.mkdir()
    (sub / "PRODUCT-1-index.md").write_text(
        "| Key | Type | Status | Summary | Role |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| [PRODUCT-1](PRODUCT-1/PRODUCT-1.md) | Epic | Open | A summary | root |\n",
        encoding="utf-8",
    )
    update_top_level_index(tmp_path)
    out = (tmp_path / "export-index.md").read_text(encoding="utf-8")
    assert "Epic" in out and "A summary" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_index_registry.py -q`
Expected: `TypeError: generate_import_index() got an unexpected keyword argument 'links'`, and the markdown-row registry test fails with empty type/summary.

- [ ] **Step 3: Rewrite the link helpers**

In `src/index_generator.py`, replace `_wikilink` and `_wikilink_table` (lines 16-25) with:

```python
def _default_links(nodes: dict[str, IssueNode]):
    """Obsidian rendering, used when no renderer is supplied."""
    from link_renderer import Location, ObsidianLinks
    return ObsidianLinks(JIRA_BASE_URL, nodes.keys()).at(Location.index())


def _link_table(at, key: str) -> str:
    """An issue link safe for a table cell."""
    return at.table_cell(at.issue(key))
```

- [ ] **Step 4: Thread the renderer through `generate_import_index`**

Change the signature (line 28) and opening lines (line 30) to:

```python
def generate_import_index(data_dir: Path, nodes: dict[str, IssueNode], root_key: str,
                          links=None, layout: str = "nested") -> str:
    """Generate per-import index content (e.g., PRODUCT-12345-index.md)."""
    at = links.at(Location.index()) if links is not None else _default_links(nodes)

    lines = [f"# Export Index: {root_key}", ""]
    # A flat destination holds one import and writes no export-index.md,
    # so the registry backlink would point at a file that is never created.
    if layout == "nested":
        lines.extend([f"**Main Index:** {at.index('export-index')}", ""])
```

Add `from link_renderer import Location` to the imports at the top of the file.

Then replace the four remaining hardcoded link sites:

- line 44: `link = _wikilink_table(key, nodes)` → `link = _link_table(at, key)`
- line 61: `target_link = _wikilink(target, nodes)` → `target_link = at.issue(target)`
- line 72: `lines.append(f"### [[{epic_key}]]: {epic_summary}")` → `lines.append(f"### {at.issue(epic_key)}: {epic_summary}")`
- `_render_tree` needs the context: change its signature to `def _render_tree(lines, nodes, keys, indent, at)`, change line 127 to `lines.append(f"{prefix}{at.issue(key)} ({itype}) — {summary}")`, and update both call sites (line 77 `_render_tree(lines, nodes, children, indent=0, at=at)` and the recursive call at line 131 `_render_tree(lines, nodes, children, indent + 1, at)`).

- [ ] **Step 5: Fix the registry parser**

In `update_top_level_index`, replace the row test at line 148:

```python
            if line.startswith("| [[") or line.startswith("| \\[\\[") or line.startswith("| ["):
```

`| [` also matches the two earlier forms, but all three are listed so the intent survives a future reader.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_index_registry.py -q`
Expected: all pass.

- [ ] **Step 7: Confirm no regression**

Run: `python -m pytest -q`

- [ ] **Step 8: Commit**

```bash
git add src/index_generator.py tests/test_index_registry.py
git commit -m "feat: render indexes through a link renderer; fix registry row parsing"
```

---

## Task 6: Thread the renderer through the exporter and field formatter

**Files:**
- Modify: `src/field_formatter.py:56-58, 80-97`
- Modify: `src/markdown_exporter.py:24-31` (ctor), `:128-158` (`_export_one`), `:175` (index backlink), `:210` (parent), `:300-323` (link helpers), and the five `converter.convert` calls at `:44, 218, 226, 265`

- [ ] **Step 1: Make the field formatter renderer-aware**

In `src/field_formatter.py`, replace `format_issue_link` (lines 56-58):

```python
    @staticmethod
    def format_issue_link(key: str, links=None) -> str:
        """Format an issue link. Wikilink when no renderer is supplied."""
        if links is not None:
            return links.issue(key)
        return f"[[{key}]]"
```

and `format_parent_link` (the `return` at line 97):

```python
    @staticmethod
    def format_parent_link(parent: Any, links=None) -> Optional[str]:
        if not parent:
            return None
        key = getattr(parent, 'key', None)
        if not key:
            return None
        return FieldFormatter.format_issue_link(key, links)
```

- [ ] **Step 2: Accept a profile in the exporter**

In `src/markdown_exporter.py`, add to the imports:

```python
from link_renderer import Location, OutputProfile
```

Change the constructor (lines 24-31) to take a profile:

```python
    def __init__(self, jira_client: Any, data_dir: Path, scrubber: PiiScrubber,
                 root_key: str = "", field_names: dict | None = None,
                 profile: OutputProfile | None = None):
        self.jira = jira_client
        self.data_dir = data_dir
        self.scrubber = scrubber
        self.root_key = root_key
        self.field_names = field_names or {}
        self.profile = profile or OutputProfile.for_style("obsidian", JIRA_BASE_URL)
        self.converter = JiraMarkupConverter(JIRA_BASE_URL)
        self.formatter = FieldFormatter()
```

`tests/test_additional_fields.py:8` passes no profile, so the Obsidian default keeps it green.

- [ ] **Step 3: Bind a renderer per issue**

`_generate_markdown` (line 159) gains a bound context. Add as its first statement:

```python
        at = self.profile.renderer.at(Location.ticket(issue.key))
```

Then replace the link sites:

- line 175: `lines.append(f"**Index:** [[{index_name}]]")` → `lines.append(f"**Index:** {at.index(index_name)}")`
- line 210: `lines.append(f"**Parent:** {self._wikilink(parent_key, all_nodes)}")` → `lines.append(f"**Parent:** {at.issue(parent_key)}")`
- lines 218, 226, 265: add the context to each `self.converter.convert(...)` call, e.g. `self.converter.convert(description, links=at)`
- `_format_additional_value` (line 37) gains an optional context. Change its signature and the two lines that use it:

```python
    def _format_additional_value(self, value: Any, att_handler: Any = None, at=None) -> str | None:
        """Format one custom-field value for the Details section. Returns None if empty."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped or stripped in ("{}", "[]"):
                return None
            converted = self.converter.convert(value, links=at)
            if att_handler is not None:
                converted = att_handler.replace_attachment_references(converted, at)
            return self.scrubber.scrub_text(converted).strip() or None
```

The rest of the method is unchanged. `at` defaults to `None` so `tests/test_additional_fields.py` keeps calling it with one argument. Pass `at` from its call site inside `_generate_additional_fields`, which itself gains an `at=None` parameter, and call it as `self._generate_additional_fields(issue, att_handler, at)` from `_generate_markdown`.

Replace `_wikilink` (lines 300-304) and `_group_links_as_wikilinks` (line 306) so they take the bound context instead of the node dict:

```python
    @staticmethod
    def _group_links(links, at) -> dict[str, list[str]] | None:
        """Group linked issues by type, rendered through the bound renderer."""
        if not links:
            return None
        grouped = {}
        for link in links:
            if hasattr(link, 'outwardIssue') and link.outwardIssue:
                issue = link.outwardIssue
                link_type = getattr(link.type, 'outward', 'relates to')
            elif hasattr(link, 'inwardIssue') and link.inwardIssue:
                issue = link.inwardIssue
                link_type = getattr(link.type, 'inward', 'relates to')
            else:
                continue
            key = getattr(issue, 'key', None)
            if key:
                grouped.setdefault(link_type, []).append(at.issue(key))
        return grouped if grouped else None
```

Update the call at line 271 to `grouped = self._group_links(issue_links, at)`. Delete the now-unused `_wikilink` static method.

- [ ] **Step 4: Populate the renderer's node set**

The renderer needs every exported key. In `export_all` (around line 95), before the loop:

```python
        self.profile.renderer.keys = set(nodes.keys())
```

- [ ] **Step 5: Run the suite**

Run: `python -m pytest -q`
Expected: all green, `tests/test_additional_fields.py` **unmodified**.

- [ ] **Step 6: Commit**

```bash
git add src/markdown_exporter.py src/field_formatter.py
git commit -m "feat: render exporter links through the output profile"
```

---

## Task 7: Comments — document form and inline fragment

**Files:**
- Modify: `src/comments_handler.py:19-37`
- Modify: `src/markdown_exporter.py:151-157` (`_export_one`), `:291-295` (the transclusion)
- Create: `tests/test_comments_inlining.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_comments_inlining.py`:

```python
from comments_handler import CommentsHandler

BASE = "https://example.atlassian.net"


class FakeComment:
    def __init__(self, body, author="Jane Doe", created="2026-03-04T10:00:00.000+0000"):
        self.body = body
        self.author = type("A", (), {"displayName": author})()
        self.created = created
        self.updated = created


class FakeCommentField:
    def __init__(self, comments):
        self.comments = comments


class FakeFields:
    def __init__(self, comments=None):
        if comments is not None:
            self.comment = FakeCommentField(comments)


class FakeIssue:
    def __init__(self, key="MGD-1", comments=None):
        self.key = key
        self.fields = FakeFields(comments)


def test_document_form_keeps_the_title_and_backlink():
    issue = FakeIssue(comments=[FakeComment("Looks good.")])
    out = CommentsHandler(BASE).format_comments_document(issue)
    assert out.startswith("# Comments for MGD-1")
    assert "**Ticket:**" in out
    assert "## Comment #1" in out


def test_fragment_form_has_no_title_and_no_backlink():
    issue = FakeIssue(comments=[FakeComment("Looks good.")])
    out = CommentsHandler(BASE).format_comments_body(issue, level=3)
    assert "# Comments for" not in out
    assert "**Ticket:**" not in out
    assert "### Comment #1" in out


def test_fragment_demotes_headings_to_the_requested_level():
    issue = FakeIssue(comments=[FakeComment("a"), FakeComment("b")])
    out = CommentsHandler(BASE).format_comments_body(issue, level=4)
    assert "#### Comment #1" in out
    assert "#### Comment #2" in out
    assert "## Comment" not in out


def test_fragment_with_no_comments():
    issue = FakeIssue(comments=[])
    out = CommentsHandler(BASE).format_comments_body(issue, level=3)
    assert out.strip() == "*No comments*"


def test_fragment_when_the_comment_field_is_absent():
    issue = FakeIssue()
    out = CommentsHandler(BASE).format_comments_body(issue, level=3)
    assert out.strip() == "*No comments*"


def test_document_form_wraps_the_fragment():
    issue = FakeIssue(comments=[FakeComment("Looks good.")])
    handler = CommentsHandler(BASE)
    assert "Looks good." in handler.format_comments_body(issue, level=2)
    assert "Looks good." in handler.format_comments_document(issue)


def test_legacy_method_name_still_works():
    """fetch_and_format_comments is the name _export_one used; keep it."""
    issue = FakeIssue(comments=[FakeComment("Looks good.")])
    out = CommentsHandler(BASE).fetch_and_format_comments(issue)
    assert out.startswith("# Comments for MGD-1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_comments_inlining.py -q`
Expected: `AttributeError: 'CommentsHandler' object has no attribute 'format_comments_document'`.

- [ ] **Step 3: Split the two forms**

In `src/comments_handler.py`, replace `fetch_and_format_comments` (lines 19-34) with:

```python
    def _comments_of(self, issue) -> list:
        field = getattr(issue.fields, 'comment', None)
        if field is None:
            return []
        return getattr(field, 'comments', []) or []

    def format_comments_body(self, issue, level: int = 2, links=None) -> str:
        """The comments themselves, headings at `level`. For inlining."""
        comments = self._comments_of(issue)
        if not comments:
            return "*No comments*\n"
        lines = []
        for i, comment in enumerate(comments, 1):
            lines.append(self._format_comment(i, comment, level, links))
            lines.append("")
        return '\n'.join(lines)

    def format_comments_document(self, issue, links=None) -> str:
        """The standalone <KEY>-comments.md file."""
        comments = self._comments_of(issue)
        ticket = links.issue(issue.key) if links is not None else f"[[{issue.key}]]"
        if not comments:
            return f"# Comments for {issue.key}\n\n**Ticket:** {ticket}\n\n*No comments*\n"
        header = [f"# Comments for {issue.key}", "",
                  f"**Ticket:** {ticket}", "",
                  f"Total comments: {len(comments)}", "", "---", ""]
        return '\n'.join(header) + self.format_comments_body(issue, level=2, links=links)

    # Retained for callers that predate the split.
    fetch_and_format_comments = format_comments_document
```

Change `_format_comment` (line 36) to take the level and the renderer:

```python
    def _format_comment(self, number: int, comment, level: int = 2, links=None) -> str:
        lines = [f"{'#' * level} Comment #{number}", ""]
```

and its body conversion (line 51) to `body = self.converter.convert(comment.body, links=links)`.

- [ ] **Step 4: Inline comments in the exporter**

In `src/markdown_exporter.py`, replace the comments block at lines 291-295:

```python
        # Comments: inlined for GitHub (no transclusion there), transcluded for Obsidian.
        lines.append("## Comments")
        lines.append("")
        if self.profile.inline_comments:
            handler = CommentsHandler(JIRA_BASE_URL, att_handler)
            body = handler.format_comments_body(issue, level=3, links=at)
            lines.append(self.scrubber.scrub_text(body))
        else:
            lines.append(f"![[{issue.key}-comments]]")
        lines.append("")
```

and make the separate file conditional in `_export_one` (lines 151-157):

```python
        # Under GitHub style the comments live inside <KEY>.md.
        if not self.profile.inline_comments:
            comments_handler = CommentsHandler(JIRA_BASE_URL, att_handler)
            comments_md = comments_handler.format_comments_document(
                issue, links=self.profile.renderer.at(Location.ticket(key))
            )
            comments_md = self.scrubber.scrub_text(comments_md)
            (item_dir / f"{key}-comments.md").write_text(comments_md, encoding="utf-8")
            print(f"  Written: {key}-comments.md")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/comments_handler.py src/markdown_exporter.py tests/test_comments_inlining.py
git commit -m "feat: inline comments under GitHub style, keep transclusion for Obsidian"
```

---

## Task 8: Attachment allowlist

**Files:**
- Modify: `src/attachment_handler.py:15` (constants), `:18-46` (ctor and download), `:63-112` (rewriting and listing)
- Modify: `src/markdown_exporter.py:141-145` (handler construction)
- Create: `tests/test_attachment_policy.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_attachment_policy.py`:

```python
import pytest

from attachment_handler import AttachmentHandler
from link_renderer import GITHUB_DOWNLOAD_ALLOWLIST, GithubLinks, Location, ObsidianLinks

BASE = "https://example.atlassian.net"


class FakeAttachment:
    def __init__(self, filename, size=1024, payload=b"x"):
        self.filename = filename
        self.size = size
        self.content = f"{BASE}/attachment/{filename}"
        self._payload = payload
        self.fetched = False

    def get(self):
        self.fetched = True
        return self._payload


class FakeFields:
    def __init__(self, attachments):
        self.attachment = attachments


class FakeIssue:
    def __init__(self, attachments):
        self.fields = FakeFields(attachments)


def handler(tmp_path, allowlist):
    return AttachmentHandler(None, str(tmp_path / "attachments"),
                             download_allowlist=allowlist)


def test_allowlist_downloads_images_and_documents(tmp_path):
    atts = [FakeAttachment("flow.png"), FakeAttachment("spec.pdf"),
            FakeAttachment("data.xlsx"), FakeAttachment("rows.csv")]
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue(atts))
    assert all(a.fetched for a in atts)


def test_allowlist_skips_archives_without_fetching(tmp_path):
    """Assert the bytes are never requested, not merely omitted from output."""
    zip_att = FakeAttachment("SupportArchive.zip", size=11_744_051)
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue([zip_att]))
    assert zip_att.fetched is False
    assert h.skipped == [("SupportArchive.zip", zip_att.content, 11_744_051)]


def test_none_allowlist_downloads_everything(tmp_path):
    """Obsidian style: unchanged behavior."""
    zip_att = FakeAttachment("SupportArchive.zip")
    h = handler(tmp_path, None)
    h.download_attachments(FakeIssue([zip_att]))
    assert zip_att.fetched is True
    assert h.skipped == []


# --- Review Focus 3 and 4 ----------------------------------------------------

def test_uppercase_extensions_match_the_allowlist(tmp_path):
    att = FakeAttachment("SCREENSHOT.PNG")
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue([att]))
    assert att.fetched is True


def test_extensionless_files_are_skipped_not_crashed(tmp_path):
    """Real vault data: binary_windows-x86-64 and UUID-named blobs."""
    atts = [FakeAttachment("binary_windows-x86-64"),
            FakeAttachment("6457c0a4-01c0-4ace-aa09-c4ed86107eb2")]
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue(atts))
    assert not any(a.fetched for a in atts)
    assert len(h.skipped) == 2


def test_skipped_files_render_as_sized_jira_links(tmp_path):
    att = FakeAttachment("SupportArchive.zip", size=11_744_051)
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    images, others = h.download_attachments(FakeIssue([att]))
    at = GithubLinks(BASE, set()).at(Location.ticket("MGD-1"))
    md = h.get_attachment_list_markdown(images, others, at)
    assert f"[SupportArchive.zip]({BASE}/attachment/SupportArchive.zip) (11.2 MB)" in md


def test_github_listing_uses_relative_image_links(tmp_path):
    att = FakeAttachment("flow.png")
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    images, others = h.download_attachments(FakeIssue([att]))
    at = GithubLinks(BASE, set()).at(Location.ticket("MGD-1"))
    md = h.get_attachment_list_markdown(images, others, at)
    assert "![flow.png](attachments/flow.png)" in md


def test_obsidian_listing_is_unchanged(tmp_path):
    att = FakeAttachment("flow.png")
    h = handler(tmp_path, None)
    images, others = h.download_attachments(FakeIssue([att]))
    at = ObsidianLinks(BASE, set()).at(Location.ticket("MGD-1"))
    md = h.get_attachment_list_markdown(images, others, at)
    assert "![[flow.png]]" in md


def test_reference_to_a_skipped_file_becomes_a_jira_link(tmp_path):
    att = FakeAttachment("SupportArchive.zip", size=2048)
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue([att]))
    at = GithubLinks(BASE, set()).at(Location.ticket("MGD-1"))
    out = h.replace_attachment_references("see [^SupportArchive.zip]", at)
    assert f"({BASE}/attachment/SupportArchive.zip)" in out
    assert "attachments/SupportArchive.zip" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_attachment_policy.py -q`
Expected: `TypeError: __init__() got an unexpected keyword argument 'download_allowlist'`.

- [ ] **Step 3: Add the allowlist to the handler**

In `src/attachment_handler.py`, change the constructor (lines 18-21):

```python
    def __init__(self, jira_client, attachments_dir: str, download_allowlist=None):
        self.jira_client = jira_client
        self.attachments_dir = Path(attachments_dir)
        self.download_allowlist = download_allowlist
        self.downloaded_files: Dict[str, str] = {}   # original_name -> local_filename
        self.skipped: List[Tuple[str, str, int]] = []  # (filename, url, size)
```

Add the policy check and rewrite `download_attachments` (lines 23-36):

```python
    def _should_download(self, filename: str) -> bool:
        """None means download everything (Obsidian). Otherwise allowlist by
        extension; no extension means no match, so it is skipped."""
        if self.download_allowlist is None:
            return True
        suffix = Path(filename).suffix.lower().lstrip(".")
        return bool(suffix) and suffix in self.download_allowlist

    def download_attachments(self, issue) -> Tuple[List[str], List[str]]:
        """Download allowlisted attachments. Returns (image_files, other_files)."""
        if not hasattr(issue.fields, 'attachment') or not issue.fields.attachment:
            return [], []

        images, others = [], []
        for attachment in issue.fields.attachment:
            if not self._should_download(attachment.filename):
                self.skipped.append((
                    attachment.filename,
                    getattr(attachment, 'content', ''),
                    getattr(attachment, 'size', 0),
                ))
                print(f"    Skipped (not downloaded): {attachment.filename}")
                continue
            self.attachments_dir.mkdir(parents=True, exist_ok=True)
            local = self._download(attachment)
            if local:
                self.downloaded_files[attachment.filename] = local
                (images if self._is_image(local) else others).append(local)

        return images, others
```

Note the `mkdir` moved inside the loop so an issue whose attachments are all skipped leaves no empty `attachments/` directory behind.

- [ ] **Step 4: Render through the renderer**

Replace `get_attachment_list_markdown` (lines 92-107):

```python
    def get_attachment_list_markdown(self, images: List[str], others: List[str], at=None) -> str:
        if not images and not others and not self.skipped:
            return ""
        if at is None:
            from link_renderer import Location, ObsidianLinks
            at = ObsidianLinks("", set()).at(Location.ticket(""))

        lines = ["## Attachments", ""]
        if images:
            lines.extend(["### Images", ""])
            for img in images:
                lines.extend([at.image(img), ""])
        if others or self.skipped:
            lines.extend(["### Files", ""])
            for f in others:
                lines.append(f"- {at.attachment(f)}")
            for filename, url, size in self.skipped:
                lines.append(f"- {at.external_file(filename, url, size)}")
            lines.append("")
        return '\n'.join(lines)
```

Give `replace_attachment_references` the context, and map skipped files to their Jira URL. Change its signature (line 63) to `def replace_attachment_references(self, text: str, at=None) -> str:`, resolve a default the same way, then replace each `f'![[{local}]]'` with `at.image(local)` and each `f'[[{local}]]'` with `at.attachment(local)`. After the existing loop over `downloaded_files`, add:

```python
        for filename, url, size in self.skipped:
            escaped = re.escape(filename)
            replacement = at.external_file(filename, url, size)
            for pat in (
                rf'(?<!\[)\[(\^{escaped}|{escaped})\]\((\^{escaped}|{escaped})\)',
                rf'(?<!\[)\[(\^{escaped}|{escaped})\]\([^)]+/{escaped}\)',
                rf'(?<!\[)\[(\^{escaped}|{escaped})\](?![\(\[])',
            ):
                text = re.sub(pat, replacement.replace('\\', '\\\\'), text)
        return text
```

Delete the now-unused `pipe_escape` static method (lines 108-112); `table_cell` on the renderer replaces it.

- [ ] **Step 5: Pass the allowlist from the exporter**

In `src/markdown_exporter.py`, change the handler construction (line 142):

```python
        att_handler = AttachmentHandler(
            self.jira, str(attachments_dir),
            download_allowlist=self.profile.download_allowlist,
        )
```

and pass `at` to both `att_handler.replace_attachment_references(...)` calls (lines 46 and 227).

The attachments block (lines 236-238) needs both the context **and** a wider guard — a ticket whose attachments were all skipped has empty `images` and `others`, so today's condition would suppress the section entirely and the Jira links would never render:

```python
        # Attachments
        if images or others or att_handler.skipped:
            lines.append(att_handler.get_attachment_list_markdown(images, others, at))
```

Add a test for exactly this to `tests/test_attachment_policy.py`:

```python
def test_a_ticket_with_only_skipped_attachments_still_lists_them(tmp_path):
    att = FakeAttachment("SupportArchive.zip", size=2048)
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    images, others = h.download_attachments(FakeIssue([att]))
    assert images == [] and others == []
    at = GithubLinks(BASE, set()).at(Location.ticket("MGD-1"))
    md = h.get_attachment_list_markdown(images, others, at)
    assert "## Attachments" in md
    assert "SupportArchive.zip" in md
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/attachment_handler.py src/markdown_exporter.py tests/test_attachment_policy.py
git commit -m "feat: allowlist attachment downloads under GitHub style"
```

---

## Task 9: Wire `--link-style` end to end

Everything is in place; this turns it on.

**Files:**
- Modify: `src/main.py` (argparse, profile construction, index call)

- [ ] **Step 1: Add the flag**

In `src/main.py`, after the `--export-dir` argument:

```python
    parser.add_argument(
        "--link-style",
        choices=("obsidian", "github"),
        default=None,
        help="Link rendering. Defaults to github for SPECS_PATH, obsidian otherwise.",
    )
```

- [ ] **Step 2: Build the profile**

After the target is resolved and before the banner:

```python
    from link_renderer import Location, OutputProfile

    style = args.link_style or ("github" if target.origin == "specs" else "obsidian")
    profile = OutputProfile.for_style(style, JIRA_BASE_URL)
```

Add `from config import JIRA_BASE_URL` to the imports. Extend the banner line to:

```python
    print(f"Source:      {target.origin}    Layout: {target.layout}    Links: {style}")
```

- [ ] **Step 3: Pass the profile through**

Change the exporter construction (line 79):

```python
    exporter = MarkdownExporter(jira_client, import_dir, scrubber, root_key=args.jira_id,
                                field_names=field_names, profile=profile)
```

and the index call (line 83):

```python
    profile.renderer.keys = set(nodes.keys())
    index_content = generate_import_index(import_dir, nodes, args.jira_id,
                                          links=profile.renderer, layout=target.layout)
```

- [ ] **Step 4: Verify the flag resolves as specified**

Run:
```bash
python - <<'PY'
import sys; sys.path.insert(0, "src")
from export_paths import resolve_export_target
for env, expected in [
    ({"SPECS_PATH": "/workspace/specs"}, "github"),
    ({"VAULT_PATH": "/workspace/vault"}, "obsidian"),
]:
    t = resolve_export_target("PRODUCT-18742", None, env)
    style = "github" if t.origin == "specs" else "obsidian"
    print(t.origin, style, "OK" if style == expected else "WRONG")
PY
```
Expected: `specs github OK` then `vault obsidian OK`.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/main.py
git commit -m "feat: add --link-style, inferred from the destination"
```

---

## Task 10: Live verification and README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Export to an explicit directory (Obsidian, nested — the regression check)**

Run: `python src/main.py PRODUCT-17742 --export-dir=/tmp/jira-verify-obsidian`
Expected: banner shows `explicit / nested / obsidian`. Output contains `export-index.md`, `PRODUCT-17742/PRODUCT-17742-index.md`, per-ticket `<KEY>-comments.md` files, and `[[...]]` wikilinks.

Compare against the existing vault copy to prove vault-mode output is unchanged:
```bash
diff -r /workspace/vault/jira-products/PRODUCT-17742 /tmp/jira-verify-obsidian/PRODUCT-17742 | head -40
```
Expected: differences only where Jira data itself has changed since the last export. No structural or link-format differences.

- [ ] **Step 2: Export to specs (GitHub, flat)**

Run: `SPECS_PATH=/workspace/specs python src/main.py PRODUCT-17742`
Expected: banner shows `specs / flat / github`. Verify:
```bash
ls /workspace/specs/specifications/PRODUCT-17742*/jira-import/
grep -rc '\[\[' /workspace/specs/specifications/PRODUCT-17742*/jira-import/ | grep -v ':0' || echo "no wikilinks: OK"
find /workspace/specs/specifications/PRODUCT-17742*/jira-import/ -name '*-comments.md' | wc -l   # expect 0
find /workspace/specs/specifications/PRODUCT-17742*/jira-import/ -name '*.zip' | wc -l           # expect 0
test -e /workspace/specs/specifications/PRODUCT-17742*/jira-import/export-index.md && echo "UNEXPECTED registry" || echo "no registry: OK"
```

- [ ] **Step 3: Check the links resolve**

For each relative link in a generated ticket page, confirm the target exists:
```bash
cd /workspace/specs/specifications/PRODUCT-17742*/jira-import
for f in */*.md; do
  d=$(dirname "$f")
  grep -o ']([^)h][^)]*\.md)' "$f" | tr -d ']()' | while read -r link; do
    [ -e "$d/$link" ] || echo "BROKEN: $f -> $link"
  done
done
echo "link check done"
```
Expected: no `BROKEN` lines.

- [ ] **Step 4: Confirm in the GitHub UI**

Push the specs branch and open one ticket page in GitHub. Confirm links navigate, images display, and comments read inline. This is the requirement that motivated the work, and only a browser can confirm it.

- [ ] **Step 5: Clean up the verification output**

```bash
rm -rf /tmp/jira-verify-obsidian
git -C /workspace/specs status --short   # decide whether to keep or discard the specs export
```

- [ ] **Step 6: Rewrite the README sections**

Apply the six corrections from the spec:

1. Replace line 44 ("The export directory is configured inside `runme.sh`…") with the precedence table: `--export-dir`, then `SPECS_PATH` → `<specs>/specifications/<ID>-<slug>/jira-import`, then `VAULT_PATH` → `<vault>/jira-products`, else an error.
2. Fix the bare `python src/main.py PRODUCT-12345` example at line 50 — it now errors without a pointer.
3. Replace the `.data/` tree (lines 70-88) with both layouts, flat and nested, copied from the spec's "Output layouts" section.
4. Update "Navigation" (lines 118-125) to distinguish Obsidian wikilinks from GitHub relative links.
5. Add `--link-style` and the attachment allowlist, with the reason: archives were 40% of export weight.
6. Add the stale-directory caveat to "Re-exporting" (lines 134-135).

- [ ] **Step 7: Final full run**

Run: `python -m pytest -q`
Expected: all green — the 28 original tests plus roughly 60 new ones.

- [ ] **Step 8: Commit**

```bash
git add README.md
git commit -m "docs: document destination resolution, link styles, attachment policy"
```
