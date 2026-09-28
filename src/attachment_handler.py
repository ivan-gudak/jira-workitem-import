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


class AttachmentHandler:
    """Downloads and manages Jira attachments for a single export."""

    def __init__(self, jira_client, attachments_dir: str, download_allowlist=None, links=None):
        self.jira_client = jira_client
        self.attachments_dir = Path(attachments_dir)
        self.download_allowlist = download_allowlist
        self.links = links if links is not None else ObsidianLinks("", ()).at(Location.ticket(""))
        self.downloaded_files: Dict[str, str] = {}  # original_name -> local_filename
        self.skipped: List[Tuple[str, str, int]] = []  # (filename, url, size)

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

    def replace_attachment_references(self, text: str) -> str:
        """Rewrite Jira attachment references through the bound renderer."""
        if not text:
            return text
        at = self.links
        for original, local in self.downloaded_files.items():
            escaped = re.escape(original)
            if self._is_image(local):
                repl = at.image(local)
                patterns = [
                    rf'!\[\]\({escaped}[^\)]*\)',
                    rf'!\[\]\(\[\]\({escaped}[^\)]*\)\)',
                    rf'\)\]\({escaped}\)',
                    rf'!{escaped}[^!]*!',
                ]
            else:
                repl = at.attachment(local)
                escaped_caret = re.escape(f"^{original}")
                patterns = [
                    rf'(?<!\[)\[(\^{escaped}|{escaped})\]\((\^{escaped}|{escaped})\)',
                    rf'(?<!\[)\[(\^{escaped}|{escaped})\]\([^)]+/{escaped}\)',
                    rf'(?<!\[)\[(\^{escaped}|{escaped})\](?![\(\[])',
                    rf'(?<!\[\[){escaped_caret}(?!\]\])',
                ]
            for pat in patterns:
                # A lambda replacement, so a rendered link is inserted
                # literally rather than read for backreferences.
                text = re.sub(pat, lambda _m, r=repl: r, text)

        # A skipped file was never written, so its reference points at Jira.
        for filename, url, size in self.skipped:
            escaped = re.escape(filename)
            repl = at.external_file(filename, url, size)
            for pat in (
                rf'(?<!\[)\[(\^{escaped}|{escaped})\]\((\^{escaped}|{escaped})\)',
                rf'(?<!\[)\[(\^{escaped}|{escaped})\]\([^)]+/{escaped}\)',
                rf'(?<!\[)\[(\^{escaped}|{escaped})\](?![\(\[])',
            ):
                text = re.sub(pat, lambda _m, r=repl: r, text)
        return text

    def get_attachment_list_markdown(self, images: List[str], others: List[str]) -> str:
        if not images and not others and not self.skipped:
            return ""
        at = self.links
        lines = ["## Attachments", ""]
        if images:
            lines.append("### Images")
            lines.append("")
            for img in images:
                lines.append(at.image(img))
                lines.append("")
        if others or self.skipped:
            lines.append("### Files")
            lines.append("")
            for f in others:
                lines.append(f"- {at.attachment(f)}")
            for filename, url, size in self.skipped:
                lines.append(f"- {at.external_file(filename, url, size)}")
            lines.append("")
        return '\n'.join(lines)
