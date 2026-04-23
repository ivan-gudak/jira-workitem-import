"""
Attachment handler module (simplified for single-export).
Downloads Jira attachments into <ticket>/attachments/.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional


IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp', '.ico'}


class AttachmentHandler:
    """Downloads and manages Jira attachments for a single export."""

    def __init__(self, jira_client, attachments_dir: str):
        self.jira_client = jira_client
        self.attachments_dir = Path(attachments_dir)
        self.downloaded_files: Dict[str, str] = {}  # original_name -> local_filename

    def download_attachments(self, issue) -> Tuple[List[str], List[str]]:
        """Download all attachments. Returns (image_files, other_files)."""
        if not hasattr(issue.fields, 'attachment') or not issue.fields.attachment:
            return [], []

        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        images, others = [], []

        for attachment in issue.fields.attachment:
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
        """Replace Jira attachment references with Obsidian wikilinks."""
        if not text:
            return text
        for original, local in self.downloaded_files.items():
            if self._is_image(local):
                escaped = re.escape(original)
                for pat, repl in [
                    (rf'!\[\]\({escaped}[^\)]*\)', f'![[{local}]]'),
                    (rf'!\[\]\(\[\]\({escaped}[^\)]*\)\)', f'![[{local}]]'),
                    (rf'\)\]\({escaped}\)', f'![[{local}]]'),
                    (rf'!{escaped}[^!]*!', f'![[{local}]]'),
                ]:
                    text = re.sub(pat, repl, text)
            else:
                escaped = re.escape(original)
                escaped_caret = re.escape(f"^{original}")
                for pat, repl in [
                    (rf'(?<!\[)\[(\^{escaped}|{escaped})\]\((\^{escaped}|{escaped})\)', f'[[{local}]]'),
                    (rf'(?<!\[)\[(\^{escaped}|{escaped})\]\([^)]+/{escaped}\)', f'[[{local}]]'),
                    (rf'(?<!\[)\[(\^{escaped}|{escaped})\](?![\(\[])', f'[[{local}]]'),
                    (rf'(?<!\[\[){escaped_caret}(?!\]\])', f'[[{local}]]'),
                ]:
                    text = re.sub(pat, repl, text)
        return text

    def get_attachment_list_markdown(self, images: List[str], others: List[str]) -> str:
        if not images and not others:
            return ""
        lines = ["## Attachments", ""]
        if images:
            lines.append("### Images")
            lines.append("")
            for img in images:
                lines.append(f"![[{img}]]")
                lines.append("")
        if others:
            lines.append("### Files")
            lines.append("")
            for f in others:
                lines.append(f"- [[{f}]]")
            lines.append("")
        return '\n'.join(lines)

    @staticmethod
    def pipe_escape(wikilink: str) -> str:
        """Escape pipe in wikilink for use inside markdown tables.
        [[target|alias]] -> [[target\\|alias]]
        """
        return wikilink.replace("[[", "[[").replace("|", "\\|") if "|" in wikilink else wikilink
