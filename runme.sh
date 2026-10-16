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

# A venv is machine-specific, and this one lives inside the Obsidian vault, so a
# venv built on another machine can arrive here by vault sync. Re-running
# `python3 -m venv .venv` over it exits 0 and repairs NOTHING -- the stale
# symlinks survive, `set -e` never fires, and the run dies later at pip or at
# the interpreter itself (on macOS, as "Killed: 9"). Validate before reuse and
# rebuild with --clear when the interpreter is not executable here.
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c '' 2>/dev/null; then
  python3 -m venv --clear .venv
fi
source .venv/bin/activate
# jiramd is pinned in requirements.txt (…@vX.Y.Z). Install it only when the
# installed version differs, so a run does not re-fetch it from GitHub.
PIN=$(sed -n 's/.*@v\([0-9][0-9.]*\).*/\1/p' requirements.txt)
if [ "$(python -c 'import jiramd; print(jiramd.__version__)' 2>/dev/null)" != "$PIN" ]; then
  pip install -q --upgrade -r requirements.txt
fi

python src/main.py "$JIRA_ID" "${@:2}"
