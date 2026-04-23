#!/bin/bash
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <JIRA-ID>  (e.g. $0 PRODUCT-12345)"
  exit 1
fi

JIRA_ID="$1"
EXPORT_DIR=/mnt/c/workspaces/obsidian_vault/_archive/jira-products

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -q

python src/main.py "$JIRA_ID" --export-dir="$EXPORT_DIR"
