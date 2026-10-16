"""
Export a Jira workitem and its dependency graph to markdown, with jiramd.

Keeps this tool's command line, credentials file and destinations, and runs
jiramd with the Dynatrace settings in jiramd.toml:

    python src/main.py PRODUCT-12345 [--export-dir=DIR] [--link-style=obsidian|github]

Credentials: JIRA_SERVER, JIRA_EMAIL and JIRA_TOKEN when all three are set,
otherwise .jira.config in the working directory.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Mapping, Optional

CONFIG = Path(__file__).resolve().parent.parent / "jiramd.toml"


def jiramd_argv(argv: list) -> list:
    """This tool's arguments as a jiramd command line."""
    parser = argparse.ArgumentParser(
        description="Export a Jira workitem and its full dependency graph to markdown.")
    parser.add_argument("jira_id", help="Root Jira workitem ID (e.g., PRODUCT-12345)")
    parser.add_argument("--export-dir", default=None, help="Output directory. Overrides SPECS_PATH and VAULT_PATH.")
    parser.add_argument("--link-style", choices=("obsidian", "github"), default=None,
                        help="Link rendering. Defaults to github for SPECS_PATH, obsidian otherwise.")
    args = parser.parse_args(argv)
    out = ["--config", str(CONFIG), "export", args.jira_id]
    if args.export_dir is not None:
        out += ["--export-dir", args.export_dir]
    if args.link_style is not None:
        out += ["--links", args.link_style]
    return out


def credentials(env: Mapping[str, str], cwd: Path) -> dict:
    """JIRA_URL / JIRA_USER / JIRA_TOKEN for jiramd, from this tool's sources."""
    if all(env.get(k) for k in ("JIRA_SERVER", "JIRA_EMAIL", "JIRA_TOKEN")):
        return {"JIRA_URL": env["JIRA_SERVER"], "JIRA_USER": env["JIRA_EMAIL"], "JIRA_TOKEN": env["JIRA_TOKEN"]}
    path = Path(cwd) / ".jira.config"
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in ("SERVER", "EMAIL", "TOKEN"):
            values[key.strip()] = value.strip()
    names = {"SERVER": "JIRA_URL", "EMAIL": "JIRA_USER", "TOKEN": "JIRA_TOKEN"}
    return {names[k]: v for k, v in values.items() if v}


def run(argv: Optional[list] = None, env: Optional[Mapping[str, str]] = None) -> int:
    try:
        from jiramd.cli import main as jiramd_main
    except ImportError:
        print("Error: jiramd is not installed in this environment. Run ./runme.sh once, "
              "or `pip install -r requirements.txt`.", file=sys.stderr)
        return 1
    env = dict(os.environ if env is None else env)
    cwd = Path.cwd()
    found = credentials(env, cwd)
    if not found:
        print(f"Note: no .jira.config in {cwd}, and JIRA_SERVER, JIRA_EMAIL, JIRA_TOKEN are not all set.",
              file=sys.stderr)
    return jiramd_main(jiramd_argv(sys.argv[1:] if argv is None else argv), env={**env, **found}, cwd=cwd)


if __name__ == "__main__":
    sys.exit(run())
