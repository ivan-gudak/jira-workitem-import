# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

The Dynatrace wrapper around [jiramd](https://github.com/ihudak/jiramd), which does the export. This repository keeps:

| File | Role |
|---|---|
| `jiramd.toml` | dt-rnd settings: the `SPECS_PATH` / `VAULT_PATH` destinations, frontmatter and metadata fields (custom fields by ID where names are shared), the Status Details and Release Notes sections |
| `src/main.py` | Keeps this tool's command line (`PRODUCT-123 [--export-dir] [--link-style]`) and credentials (`JIRA_SERVER`/`JIRA_EMAIL`/`JIRA_TOKEN`, else `.jira.config` in the working directory), and runs `jiramd export` with `jiramd.toml` |
| `runme.sh` | Builds or repairs `.venv`, installs the jiramd version pinned in `requirements.txt` when it differs, expands `P-` to `PRODUCT-`, runs `src/main.py` |
| `requirements.txt` | `jiramd @ git+https://github.com/ihudak/jiramd@vX.Y.Z` |

Fix export behaviour in jiramd, not here; then bump the tag in `requirements.txt`.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest                       # runner and config tests; no network
./runme.sh PRODUCT-12345               # or P-12345
```

`.jira.config` is gitignored and must never be committed. The Obsidian vault holds a hand-synced copy of this repository whose `runme.sh` adds `unset SPECS_PATH`.
