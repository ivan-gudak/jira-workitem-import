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
    # rstrip the separator so a trailing slash does not double up later,
    # but keep a bare "/" — stripping it leaves "", and Path("") is the CWD.
    return Path(raw.rstrip("/") or "/").expanduser()


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
            base = (Path(cwd) if cwd else Path.cwd()) / base
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
