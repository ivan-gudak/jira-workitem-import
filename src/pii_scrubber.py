"""
PII scrubber module.
Anonymizes person names and email addresses across the entire export.
Maintains consistent User-N mapping per displayName.
"""

import re


# Matches email addresses
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# Matches @mentions (Jira style: [~accountid:...] or [~username] or plain @Name)
_MENTION_JIRA_RE = re.compile(r'\[~(?:accountid:)?[^\]]+\]')
_MENTION_AT_RE = re.compile(r'@([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)')


class PiiScrubber:
    """Builds a consistent name→User-N mapping and scrubs text."""

    def __init__(self):
        self._name_map: dict[str, str] = {}
        self._counter = 0

    def anonymize_name(self, display_name: str | None) -> str | None:
        """Map a displayName to a consistent User-N placeholder."""
        if not display_name:
            return None
        if display_name not in self._name_map:
            self._counter += 1
            self._name_map[display_name] = f"User-{self._counter}"
        return self._name_map[display_name]

    def scrub_text(self, text: str) -> str:
        """Scrub PII from free-form text (descriptions, comments, etc.)."""
        if not text:
            return text

        # Replace Jira [~user] mentions with placeholder
        text = _MENTION_JIRA_RE.sub('[mention]', text)

        # Replace known names (longest first to avoid partial matches)
        for name in sorted(self._name_map, key=len, reverse=True):
            if name in text:
                text = text.replace(name, self._name_map[name])

        # Replace @Name Surname mentions that weren't caught above
        def _replace_at_mention(m):
            full_name = m.group(1)
            return f"@{self.anonymize_name(full_name)}"
        text = _MENTION_AT_RE.sub(_replace_at_mention, text)

        # Replace email addresses
        text = _EMAIL_RE.sub('[email]', text)

        return text
