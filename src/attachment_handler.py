"""
Attachment handler module (simplified for single-export).
Downloads Jira attachments into <ticket>/attachments/.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from link_renderer import Location, ObsidianLinks


IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp', '.ico'}

#: A leftover reference to an attachment that was never written and has no
#: URL to fall back on. Requires a file extension, so markdown footnote
#: syntax ([^1]) and bare [^note] are left alone.
_NAME = r'[^\s\]\)/:]+\.[A-Za-z0-9]{1,10}'
UNRESOLVED_PATTERNS = (
    re.compile(rf'!\[\]\(({_NAME})\)'),      # Jira image, post-conversion
    re.compile(rf'(?<!\[)\[\^({_NAME})\]'),  # Jira attachment link
)


class AttachmentHandler:
    """Downloads and manages Jira attachments for a single export."""

    def __init__(self, jira_client, attachments_dir: str, download_allowlist=None, links=None):
        self.jira_client = jira_client
        self.attachments_dir = Path(attachments_dir)
        self.download_allowlist = download_allowlist
        self.links = links if links is not None else ObsidianLinks("", ()).at(Location.ticket(""))
        self.downloaded_files: Dict[str, str] = {}  # original_name -> local_filename
        self.skipped: List[Tuple[str, str, int]] = []  # (filename, url, size)
        self.failed: List[Tuple[str, str, int]] = []   # download raised; same shape

    def _should_download(self, filename: str) -> bool:
        """None means download everything (Obsidian). Otherwise allowlist by
        extension; no extension means no match, so it is skipped."""
        if self.download_allowlist is None:
            return True
        suffix = Path(filename).suffix.lower().lstrip(".")
        return bool(suffix) and suffix in self.download_allowlist

    def download_attachments(self, issue) -> Tuple[List[str], List[str]]:
        """Download allowlisted attachments. Returns (image_files, other_files)."""
        if not hasattr(issue.fields, 'attachment') or not issue.fields.attachment:
            return [], []

        images, others = [], []
        for attachment in issue.fields.attachment:
            if not self._should_download(attachment.filename):
                self.skipped.append((
                    attachment.filename,
                    getattr(attachment, 'content', ''),
                    getattr(attachment, 'size', 0),
                ))
                print(f"    Skipped (not downloaded): {attachment.filename}")
                continue
            # Created lazily so a ticket whose attachments are all skipped
            # leaves no empty attachments/ directory behind.
            self.attachments_dir.mkdir(parents=True, exist_ok=True)
            local = self._download(attachment)
            if local:
                self.downloaded_files[attachment.filename] = local
                (images if self._is_image(local) else others).append(local)
            else:
                # Nothing was written, so references must point at Jira
                # rather than at a file that is not there.
                self.failed.append((
                    attachment.filename,
                    getattr(attachment, 'content', ''),
                    getattr(attachment, 'size', 0),
                ))

        return images, others

    def _download(self, attachment) -> Optional[str]:
        try:
            content = attachment.get()
            filename = self._unique_filename(attachment.filename)
            (self.attachments_dir / filename).write_bytes(content)
            print(f"    Downloaded: {filename}")
            return filename
        except Exception as e:
            print(f"    Warning: Failed to download {attachment.filename}: {e}")
            return None

    def _unique_filename(self, filename: str) -> str:
        if not (self.attachments_dir / filename).exists():
            return filename
        name, ext = os.path.splitext(filename)
        counter = 1
        while (self.attachments_dir / f"{name}_{counter}{ext}").exists():
            counter += 1
        return f"{name}_{counter}{ext}"

    @staticmethod
    def _is_image(filename: str) -> bool:
        return Path(filename).suffix.lower() in IMAGE_EXTENSIONS

    @staticmethod
    def _image_patterns(f: str) -> tuple:
        """Jira image references, post-conversion. `f` is an escaped filename."""
        return (
            rf'!\[\]\({f}[^\)]*\)',
            rf'!\[\]\(\[\]\({f}[^\)]*\)\)',
            rf'!{f}[^!]*!',
        )

    @staticmethod
    def _link_patterns(f: str) -> tuple:
        """Jira attachment links, with and without the caret form."""
        return (
            rf'(?<!\[)\[(\^{f}|{f})\]\((\^{f}|{f})\)',
            rf'(?<!\[)\[(\^{f}|{f})\]\([^)]+/{f}\)',
            rf'(?<!\[)\[(\^{f}|{f})\](?![\(\[])',
        )

    def replace_attachment_references(self, text: str) -> str:
        """Rewrite Jira attachment references through the bound renderer.

        Each match becomes a placeholder and the rendered text is substituted
        back at the end. Without that, a later pattern re-matches a link an
        earlier one just wrote -- an external link ending in "/<filename>" is
        matched by the "[name](.../name)" pattern -- and the size suffix is
        appended twice. It also keeps the unresolved sweep off these links.
        """
        if not text:
            return text
        at = self.links
        rendered: Dict[str, str] = {}

        def stash(replacement: str):
            """A re.sub replacement that banks the text and leaves a token."""
            def substitute(_match):
                token = f"<<<ATT{len(rendered)}>>>"
                rendered[token] = replacement
                return token
            return substitute

        for original, local in self.downloaded_files.items():
            f = re.escape(original)
            if self._is_image(local):
                repl = at.image(local)
                patterns = self._image_patterns(f) + (rf'\)\]\({f}\)',)
            else:
                repl = at.attachment(local)
                patterns = self._link_patterns(f) + (rf'(?<!\[\[)\^{f}(?!\]\])',)
            for pat in patterns:
                text = re.sub(pat, stash(repl), text)

        # Skipped or failed: never written, but we have the Jira URL. Image
        # forms count too -- a failed image download leaves an ![](name)
        # reference behind exactly like a missing file does.
        for filename, url, size in self.elsewhere:
            f = re.escape(filename)
            repl = at.external_file(filename, url, size)
            for pat in self._image_patterns(f) + self._link_patterns(f):
                text = re.sub(pat, stash(repl), text)

        text = self._mark_unresolved(text)
        for token, replacement in rendered.items():
            text = text.replace(token, replacement)
        return text

    @property
    def elsewhere(self) -> List[Tuple[str, str, int]]:
        """Attachments that stayed in Jira, whether by policy or by failure."""
        return self.skipped + self.failed

    @staticmethod
    def _mark_unresolved(text: str) -> str:
        """Flag references to attachments Jira did not return at all.

        They were deleted, or are not visible to this account, so there is no
        URL to link to. Left alone they render as a broken image in GitHub and
        a dangling embed in Obsidian."""
        for pattern in UNRESOLVED_PATTERNS:
            text = pattern.sub(
                lambda m: f"*(attachment unavailable: {m.group(1)})*", text)
        return text

    def get_attachment_list_markdown(self, images: List[str], others: List[str]) -> str:
        if not images and not others and not self.elsewhere:
            return ""
        at = self.links
        lines = ["## Attachments", ""]
        if images:
            lines.append("### Images")
            lines.append("")
            for img in images:
                lines.append(at.image(img))
                lines.append("")
        if others or self.elsewhere:
            lines.append("### Files")
            lines.append("")
            for f in others:
                lines.append(f"- {at.attachment(f)}")
            for filename, url, size in self.elsewhere:
                lines.append(f"- {at.external_file(filename, url, size)}")
            lines.append("")
        return '\n'.join(lines)
