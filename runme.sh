#!/bin/bash
set -e

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

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -q

python src/main.py "$JIRA_ID" --export-dir="$EXPORT_DIR"
