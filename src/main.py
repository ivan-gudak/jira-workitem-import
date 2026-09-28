"""
Jira Workitem Deep Exporter
Exports a single Jira workitem and its full dependency graph to markdown.
"""

import argparse
import os
import sys

# Add src directory to path
sys.path.insert(0, os.path.dirname(__file__))

from jira_auth import JiraAuth
from graph_walker import GraphWalker
from markdown_exporter import MarkdownExporter
from index_generator import generate_import_index, update_top_level_index
from pii_scrubber import PiiScrubber
from export_paths import ExportPathError, resolve_export_target


def main():
    parser = argparse.ArgumentParser(
        description="Export a Jira workitem and its full dependency graph to markdown."
    )
    parser.add_argument(
        "jira_id",
        help="Root Jira workitem ID (e.g., PRODUCT-12345)",
    )
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

    # Authenticate
    try:
        auth = JiraAuth()
        jira_client = auth.get_jira_client()
        print(f"Connected to: {auth.server}\n")
        # Map customfield ids to display names (one call) for the Details fallback
        field_names = {f["id"]: f["name"] for f in jira_client.fields()}
    except (FileNotFoundError, ValueError) as e:
        print(f"Auth error: {e}")
        sys.exit(1)

    # Walk the graph
    print("=" * 50)
    print(f"Walking issue graph from: {args.jira_id}")
    print("=" * 50)

    walker = GraphWalker(jira_client)
    try:
        nodes = walker.walk(args.jira_id)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not nodes:
        print("No issues found. Nothing to export.")
        sys.exit(0)

    # Flat layout: the destination is already import-specific, so no <ID> level.
    import_dir = data_dir if target.layout == "flat" else data_dir / args.jira_id
    import_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 50)
    print(f"Exporting {len(nodes)} issues to: {import_dir}")
    print("=" * 50)

    scrubber = PiiScrubber()
    exporter = MarkdownExporter(jira_client, import_dir, scrubber, root_key=args.jira_id, field_names=field_names)
    success, failed = exporter.export_all(nodes)

    # Generate per-import index
    index_content = generate_import_index(import_dir, nodes, args.jira_id)
    index_path = import_dir / f"{args.jira_id}-index.md"
    index_path.write_text(index_content, encoding="utf-8")
    print(f"\nImport index: {index_path}")

    # The registry lists sibling imports; a flat destination holds exactly one.
    if target.layout == "nested":
        update_top_level_index(data_dir)
        print(f"Top-level index: {data_dir / 'export-index.md'}")

    # Summary
    print()
    print("=" * 50)
    print(f"Done. {success}/{len(nodes)} exported.")
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for key, err in failed:
            print(f"  {key}: {err}")
    print("=" * 50)


if __name__ == "__main__":
    main()
