#!/bin/bash
set -e
cd "$(dirname "$0")" || exit 1

if [ -z "$1" ]; then
  echo "Usage: $0 <JIRA-ID>  (e.g. $0 PRODUCT-12345)"
  exit 1
fi

JIRA_ID="$1"

# Expand the "P-" shorthand to the full "PRODUCT-" project key.
if [[ "$JIRA_ID" == P-* ]]; then
  JIRA_ID="PRODUCT-${JIRA_ID#P-}"
fi

EXPORT_DIR="$VAULT_PATH/jira-products"

# A venv is machine-specific, and this one lives inside the Obsidian vault, so a
# venv built on another machine can arrive here by vault sync. Re-running
# `python -m venv .venv` over it exits 0 and repairs NOTHING -- the stale
# symlinks survive, `set -e` never fires, and the run dies later at pip or at
# the interpreter itself (on macOS, as "Killed: 9"). Validate before reuse and
# rebuild with --clear when the interpreter is not executable here.
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c '' 2>/dev/null; then
  python -m venv --clear .venv
fi
source .venv/bin/activate
pip install -r requirements.txt -q

python src/main.py "$JIRA_ID" --export-dir="$EXPORT_DIR"
