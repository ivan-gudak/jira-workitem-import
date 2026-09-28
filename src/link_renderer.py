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

    def prose_issue(self, key: str) -> str:
        return self._r.prose_issue(key, self._loc)

    def index(self, name: str, alias: str = "") -> str:
        return self._r.index(name, self._loc, alias)

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

    def prose_issue(self, key: str, location: Location) -> str:
        """A key mentioned in body text. Same as a structural link by default;
        Obsidian overrides it, because a vault resolves beyond this export."""
        return self.issue(key, location)

    @staticmethod
    def table_cell(rendered: str) -> str:
        return rendered.replace("|", "\\|")


class ObsidianLinks(BaseLinks):
    """Wikilinks. Obsidian resolves by filename, so location is irrelevant."""

    style = "obsidian"

    def issue(self, key: str, location: Location) -> str:
        return f"[[{key}]]" if key in self.keys else self.external(key)

    def prose_issue(self, key: str, location: Location) -> str:
        """Always a wikilink. Obsidian resolves by filename across the whole
        vault, so a key outside *this* export still reaches a ticket exported
        by another import — a Jira URL would throw that away."""
        return f"[[{key}]]"

    def index(self, name: str, location: Location, alias: str = "") -> str:
        return f"[[{name}|{alias}]]" if alias else f"[[{name}]]"

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

    def index(self, name: str, location: Location, alias: str = "") -> str:
        if location.kind == "root":
            # export-index.md -> <ID>/<ID>-index.md
            stem = name[: -len("-index")] if name.endswith("-index") else name
            path = f"{stem}/{name}.md"
        else:
            # A ticket page or the per-import index links one level up.
            path = f"../{name}.md"
        return f"[{alias or name}]({_url_path(path)})"

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
