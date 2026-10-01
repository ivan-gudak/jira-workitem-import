"""
Export destination resolution.

Decides where an export is written, from --export-dir, SPECS_PATH, or
VAULT_PATH, in that order. A SPECS_PATH that cannot take the export falls back
to VAULT_PATH, and the reason travels with the target. Pure: reads only the
environment mapping it is given, and creates no directories — the caller owns
creation.
"""

import re
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Optional

from pii_scrubber import PLACEHOLDER_RE

SLUG_MAX = 40


class ExportPathError(ValueError):
    """Raised when the export destination cannot be resolved."""


@dataclass(frozen=True)
class ExportTarget:
    """Where an export goes, and how it is laid out."""
    data_dir: Path
    layout: str   # "nested" | "flat"
    origin: str   # "explicit" | "specs" | "vault"
    notice: Optional[str] = None   # why SPECS_PATH was not used
    pending_name: bool = False     # the feature folder is new; name it from the summary

    def named(self, slug: str) -> "ExportTarget":
        """Name a pending feature folder <ID>-<slug>; an empty slug keeps <ID>."""
        if not self.pending_name:
            return self
        feature_dir = self.data_dir.parent
        if slug:
            feature_dir = feature_dir.with_name(f"{feature_dir.name}-{slug}")
        return replace(self, data_dir=feature_dir / self.data_dir.name, pending_name=False)


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

    notice = None
    specs_root = _pointer(env, "SPECS_PATH")
    if specs_root is not None:
        subfolder = _specs_subfolder(jira_id)
        notice = _specs_unusable(specs_root, subfolder)
        if notice is None:
            return _resolve_specs(jira_id, specs_root / subfolder)

    vault_root = _pointer(env, "VAULT_PATH")
    if vault_root is not None:
        if not vault_root.is_dir():
            reasons = [notice] if notice else []
            reasons.append(
                f"VAULT_PATH is set to {vault_root} but that directory does not exist."
            )
            raise ExportPathError("\n".join(reasons))
        return ExportTarget(
            data_dir=vault_root / "jira-products", layout="nested", origin="vault",
            notice=notice,
        )

    if notice:
        raise ExportPathError(
            f"{notice} VAULT_PATH is not set, so there is nothing to fall back to."
        )
    raise ExportPathError(
        "no export destination. Pass --export-dir=<path>, or set SPECS_PATH or VAULT_PATH."
    )


def _specs_subfolder(jira_id: str) -> str:
    """Product feedback goes to ideas/; every other key is a product change."""
    return "ideas" if jira_id.casefold().startswith("prodfb-") else "specifications"


def _specs_unusable(specs_root: Path, subfolder: str) -> Optional[str]:
    """Why the specs repo cannot take this export, or None when it can."""
    if not specs_root.is_dir():
        return f"SPECS_PATH is set to {specs_root} but that directory does not exist."
    if not (specs_root / subfolder).is_dir():
        return f"SPECS_PATH is set to {specs_root} but {specs_root / subfolder} does not exist."
    # exists(), not is_dir(): in a git worktree .git is a file.
    if not (specs_root / ".git").exists():
        return f"SPECS_PATH is set to {specs_root} but it is not the root of a git repository."
    return None


def _resolve_specs(jira_id: str, parent: Path) -> ExportTarget:
    """Find the ticket's folder under ideas/ or specifications/."""
    wanted = jira_id.casefold()
    matches = sorted(
        (d for d in parent.iterdir()
         if d.is_dir() and (d.name.casefold() == wanted
                            or d.name.casefold().startswith(f"{wanted}-"))),
        key=lambda d: d.name,
    )

    if len(matches) > 1:
        listed = "\n".join(f"         {d.name}" for d in matches)
        raise ExportPathError(
            f"{len(matches)} candidate directories for {jira_id} under {parent}:\n"
            f"{listed}\n"
            "       Pass --export-dir to choose one."
        )

    if matches:
        return ExportTarget(data_dir=matches[0] / "jira-import", layout="flat", origin="specs")
    # No folder yet: main names it from the ticket summary once it has one.
    return ExportTarget(data_dir=parent / jira_id / "jira-import", layout="flat",
                        origin="specs", pending_name=True)


def slugify(text: str) -> str:
    """Kebab-case a scrubbed summary for a folder name. May return "".

    The result only ever holds [a-z0-9] runs joined by single hyphens, so it
    cannot carry a path separator, a dot, or any character a filesystem
    rejects.
    """
    # A slug names the request, not who asked or how to reach them.
    text = PLACEHOLDER_RE.sub(" ", text or "")
    # casefold before NFKD so "ß" becomes "ss" rather than being dropped.
    text = unicodedata.normalize("NFKD", text.casefold())
    text = text.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(slug) > SLUG_MAX:
        head = slug[:SLUG_MAX]
        if slug[SLUG_MAX] != "-":
            # Drop the partial last word; one long word is cut where it stands.
            head = head.rpartition("-")[0] or head
        slug = head.strip("-")
    return slug
