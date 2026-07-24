"""
Jira markup to Markdown converter.
Handles Jira wiki syntax conversion and ADF (Atlassian Document Format).
"""

import re
import json


class JiraMarkupConverter:
    """Converts Jira wiki markup to Markdown."""
    
    def __init__(self, jira_base_url: str):
        """
        Initialize converter.
        
        Args:
            jira_base_url: Base URL for Jira instance
        """
        self.jira_base_url = jira_base_url

    def _format_issue_link(self, key: str) -> str:
        """Format a Jira issue key as an Obsidian wikilink."""
        return f"[[{key}]]"

    def _is_url_like(self, value: str) -> bool:
        """Return True when a bracketed Jira token should be treated as a URL link."""
        return bool(re.match(r'^(?:https?://|mailto:|ftp://|www\.)', value.strip(), flags=re.IGNORECASE))
    
    def convert(self, text: str) -> str:
        """
        Convert Jira markup to Markdown.
        
        Args:
            text: Jira wiki markup text or ADF
            
        Returns:
            str: Markdown formatted text
        """
        if not text:
            return ""
        
        # First, extract and convert ADF blocks (before other conversions)
        adf_blocks = {}
        text = self._extract_adf_blocks(text, adf_blocks)
        
        # Extract and convert Wiki tables early (before bold conversion changes || delimiters)
        table_blocks = {}
        text = self._extract_and_convert_tables(text, table_blocks)
        
        # Apply conversions in order (order matters!)
        text = self._convert_images(text)
        text = self._convert_headings(text)
        text = self._convert_lists(text)
        text = self._convert_bold_italic(text)
        text = self._convert_code_blocks(text)
        text = self._convert_inline_code(text)
        text = self._convert_links(text)
        text = self._convert_quotes(text)
        text = self._convert_line_breaks(text)
        text = self._convert_text_effects(text)
        
        # Restore converted tables
        text = self._restore_table_blocks(text, table_blocks)
        
        # Restore ADF blocks after all conversions
        text = self._restore_adf_blocks(text, adf_blocks)
        
        # Escape angle brackets in patterns like <key> to prevent HTML interpretation
        # But don't escape actual markdown/HTML constructs
        text = self._escape_angle_brackets(text)
        
        return text
    
    def _escape_angle_brackets(self, text: str) -> str:
        """Escape angle brackets that might be interpreted as HTML tags."""
        # Pattern: <word> that's not a valid HTML tag
        # Common placeholders in documentation: <key>, <value>, <token>, etc.
        text = re.sub(r'<([a-zA-Z][a-zA-Z0-9_\-]*)>', r'\\<\1\\>', text)
        return text
    
    def _extract_and_convert_tables(self, text: str, table_blocks: dict) -> str:
        """
        Extract Jira Wiki tables, convert them to Markdown, and replace with placeholders.
        This must happen before bold conversion because || delimiters contain *bold*.
        """
        lines = text.split('\n')
        result_lines = []
        table_buffer = []
        in_table = False
        block_id = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Check if this line starts a table or is a header row
            is_header = stripped.startswith('||')
            is_data_start = stripped.startswith('|') and not is_header
            
            if is_header or (is_data_start and not in_table):
                # Start of table
                if not in_table:
                    in_table = True
                table_buffer.append(line)
            elif in_table:
                # We're in a table - keep collecting until we hit a non-table line
                # A line is part of the table if:
                # 1. It starts with | (normal row)
                # 2. It ends with | (continuation that completes a row)
                # 3. Previous line didn't end with | (it's a continuation)
                if stripped.startswith('|') or stripped.endswith('|') or (table_buffer and not table_buffer[-1].strip().endswith('|')):
                    table_buffer.append(line)
                else:
                    # End of table
                    table_text = '\n'.join(table_buffer)
                    converted_table = self._convert_single_table(table_text)
                    placeholder = f'<<<TABLEBLOCK{block_id}>>>'
                    table_blocks[placeholder] = converted_table
                    result_lines.append(placeholder)
                    table_buffer = []
                    in_table = False
                    block_id += 1
                    result_lines.append(line)
            else:
                result_lines.append(line)
        
        # Handle table at end of text
        if in_table and table_buffer:
            table_text = '\n'.join(table_buffer)
            converted_table = self._convert_single_table(table_text)
            placeholder = f'<<<TABLEBLOCK{block_id}>>>'
            table_blocks[placeholder] = converted_table
            result_lines.append(placeholder)
        
        return '\n'.join(result_lines)
    
    def _convert_single_table(self, table_text: str) -> str:
        """Convert a single Jira Wiki table to Markdown."""
        # Parse the table using the existing logic
        lines = table_text.split('\n')
        table_rows = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            if not stripped:
                i += 1
                continue
            
            # Check if this is a table line
            is_header = '||' in stripped
            is_data = stripped.startswith('|') and not is_header
            
            if is_header:
                cells = self._smart_split(stripped, '||')
                # Convert Jira markup in header cells
                cells = [self._convert_cell_content(cell) for cell in cells]
                table_rows.append(('header', cells))
                i += 1
            elif is_data:
                # Data row - collect all lines until we have a complete row
                row_lines = [stripped]
                i += 1
                
                # Keep collecting lines until we find one that ends with |
                while i < len(lines) and not row_lines[-1].endswith('|'):
                    next_line = lines[i].strip()
                    if not next_line:
                        break
                    row_lines.append(next_line)
                    i += 1
                
                # Now parse the complete row
                full_row = ' '.join(row_lines)
                if full_row.startswith('|') and full_row.endswith('|'):
                    cells = self._smart_split(full_row[1:-1], '|')
                    # Convert Jira markup in data cells
                    cells = [self._convert_cell_content(cell) for cell in cells]
                    table_rows.append(('data', cells))
            else:
                i += 1
        
        # Format as Markdown table
        markdown_lines = self._format_markdown_table(table_rows)
        return '\n'.join(markdown_lines)
    
    def _convert_cell_content(self, cell: str) -> str:
        """Convert Jira markup within a table cell to Markdown."""
        # Remove color tags: {color:#xxxxxx}text{color} -> text
        cell = re.sub(r'\{color:[^}]+\}([^{]*)\{color\}', r'\1', cell)
        cell = re.sub(r'\{color\}', '', cell)  # Remove orphaned closing tags
        
        # Handle smart-links first (3-part format: [text|url|smart-link])
        # [KEY-1234|url|smart-link] -> [KEY-1234](url)
        def replace_smart_link(match):
            key = match.group(1)
            return self._format_issue_link(key)
        cell = re.sub(r'\[([A-Z]{2,10}-\d+)\|[^\|]+\|smart-link\]', replace_smart_link, cell)
        
        # [text|url|smart-link] -> [text](url) (for non-issue-key smart-links)
        cell = re.sub(r'\[([^\|]+)\|([^\|]+)\|smart-link\]', r'[\1](\2)', cell)
        
        # Convert links: [text|url] -> [text](url)
        cell = re.sub(r'\[([^\|]+)\|([^\]]+)\]', r'[\1](\2)', cell)
        # Convert bold: *text* -> **text**
        cell = re.sub(r'\*([^\*\n]+?)\*', r'**\1**', cell)
        # Convert italic: _text_ -> *text*
        cell = re.sub(r'_([^_\n]+)_', r'*\1*', cell)
        # Convert inline code: {{text}} -> `text`
        cell = re.sub(r'\{\{([^\}]+)\}\}', r'`\1`', cell)
        return cell
    
    def _restore_table_blocks(self, text: str, table_blocks: dict) -> str:
        """Restore converted table blocks."""
        for placeholder, table_content in table_blocks.items():
            text = text.replace(placeholder, table_content)
        return text
    
    def _convert_headings(self, text: str) -> str:
        """Convert h1-h6 headings."""
        # h1. -> #, h2. -> ##, etc.
        for i in range(6, 0, -1):
            pattern = rf'^h{i}\.\s+'
            replacement = '#' * i + ' '
            text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
        return text
    
    def _convert_bold_italic(self, text: str) -> str:
        """Convert bold and italic (must run before list processing)."""
        # Temporarily protect ** from list processing
        # *bold* -> **bold** (but not if it's a list marker at line start)
        # Use negative lookbehind to avoid matching list markers
        text = re.sub(r'(?<!\n)\*(?!\s)([^\*\n]+?)(?<!\s)\*(?!\*)', r'**\1**', text)
        
        # _italic_ -> *italic*
        text = re.sub(r'_([^_\n]+)_', r'*\1*', text)
        
        return text
    
    def _convert_lists(self, text: str) -> str:
        """Convert lists."""
        lines = text.split('\n')
        converted = []
        
        for line in lines:
            # Handle nested ordered lists: #*, #**, #***, etc.
            match = re.match(r'^(#\*+)\s+(.*)$', line)
            if match:
                depth = len(match.group(1)) - 1  # -1 because # is the first level
                indent = '   ' * depth
                line = f"{indent}1. {match.group(2)}"
            # Handle nested unordered lists: **, ***, ****, etc.
            elif re.match(r'^\*{2,}\s+', line):
                depth = len(re.match(r'^(\*+)', line).group(1)) - 1
                indent = '   ' * depth
                line = re.sub(r'^\*+\s+', f'{indent}- ', line)
            # Ordered list: # item -> 1. item
            elif re.match(r'^#\s+', line):
                line = re.sub(r'^#\s+', '1. ', line)
            # Unordered list: * item -> - item
            elif re.match(r'^\*\s+', line):
                line = re.sub(r'^\*\s+', '- ', line)
            
            converted.append(line)
        
        return '\n'.join(converted)
    
    def _convert_code_blocks(self, text: str) -> str:
        """Convert code blocks with proper newlines."""
        # Process closing tags first to avoid interference
        
        # content{code} -> content\n```
        text = re.sub(r'([^\n])\{code\}', r'\1\n```', text)
        # \n{code} -> \n``` (already has newline)
        text = re.sub(r'(\n)\{code\}', r'\1```', text)
        
        # content{noformat} -> content\n```
        text = re.sub(r'([^\n])\{noformat\}', r'\1\n```', text)
        # \n{noformat} -> \n``` (already has newline)
        text = re.sub(r'(\n)\{noformat\}', r'\1```', text)
        
        # Now process opening tags
        
        # {code:language}content -> ```language\ncontent
        text = re.sub(r'\{code:([^\}]+)\}([^\n])', r'```\1\n\2', text)
        # {code:language}\n -> ```language\n (already has newline)
        text = re.sub(r'\{code:([^\}]+)\}(\n)', r'```\1\2', text)
        
        # {noformat}content -> ```\ncontent
        text = re.sub(r'\{noformat\}([^\n])', r'```\n\1', text)
        # {noformat}\n -> ```\n (already has newline)
        text = re.sub(r'\{noformat\}(\n)', r'```\1', text)
        
        return text
    
    def _convert_inline_code(self, text: str) -> str:
        """Convert inline code."""
        # {{text}} -> `text`
        text = re.sub(r'\{\{([^\}]+)\}\}', r'`\1`', text)
        return text
    
    def _convert_links(self, text: str) -> str:
        """Convert links."""
        # First, handle special Jira smart-links with issue keys: [KEY-1234|smart-link] -> markdown link
        def replace_smart_link(match):
            key = match.group(1)
            return self._format_issue_link(key)
        
        text = re.sub(r'\[([A-Z]{2,10}-\d+)\|smart-link\]', replace_smart_link, text)
        
        # Handle smart-links with 3-part format: [text|url|smart-link] -> [text](url)
        text = re.sub(r'\[([^\|]+)\|([^\|]+)\|smart-link\]', r'[\1](\2)', text)
        
        # [text|url] -> [text](url)
        text = re.sub(r'\[([^\|]+)\|([^\]]+)\]', r'[\1](\2)', text)
        # [url] -> [url](url) only for URL-like content, not for arbitrary bracketed text
        def replace_plain_link(match):
            value = match.group(1)
            if self._is_url_like(value):
                return f'[{value}]({value})'
            return match.group(0)

        text = re.sub(r'\[([^\]]+)\](?!\()', replace_plain_link, text)
        
        # Convert remaining Jira issue keys to Markdown links (not inside links)
        # KEY-1234 -> [KEY-1234](url)
        def replace_issue_key(match):
            key = match.group(0)
            return self._format_issue_link(key)
        
        # Match typical Jira keys (2-10 uppercase letters, dash, numbers)
        # But not if they're inside markdown link syntax [...](...) or [[...]]
        # We need to avoid matching keys that are:
        # - Inside []() markdown links (in the text or URL part)
        # - Inside [[]] wikilinks
        # Strategy: temporarily protect already-converted links with placeholders
        link_placeholders = {}
        placeholder_id = 0
        
        # Protect markdown links [text](url)
        def protect_markdown_link(match):
            nonlocal placeholder_id
            placeholder = f"<<<LINK{placeholder_id}>>>"
            link_placeholders[placeholder] = match.group(0)
            placeholder_id += 1
            return placeholder
        
        text = re.sub(r'\[[^\]]+\]\([^\)]+\)', protect_markdown_link, text)
        
        # Protect wikilinks [[text]]
        def protect_wikilink(match):
            nonlocal placeholder_id
            placeholder = f"<<<LINK{placeholder_id}>>>"
            link_placeholders[placeholder] = match.group(0)
            placeholder_id += 1
            return placeholder
        
        text = re.sub(r'\[\[[^\]]+\]\]', protect_wikilink, text)

        # Protect bare http(s) URLs so an issue key embedded in a URL path
        # (e.g. https://…/browse/MGD-8605) is not rewritten into a broken link.
        # Runs after markdown-link protection, so URLs already inside [text](url)
        # are shielded by that placeholder and won't be matched again here. The
        # pattern stops at whitespace and bracket/paren boundaries.
        def protect_bare_url(match):
            nonlocal placeholder_id
            placeholder = f"<<<LINK{placeholder_id}>>>"
            link_placeholders[placeholder] = match.group(0)
            placeholder_id += 1
            return placeholder

        text = re.sub(r'https?://[^\s<>()\[\]]+', protect_bare_url, text)

        # Now convert remaining issue keys, but not ones already sitting inside
        # a literal [bracket] pair (e.g. a VI's [US-1] ID marker) — otherwise
        # the untouched outer brackets plus this replacement's own [[key]]
        # nest into a corrupted [[[key]]].
        text = re.sub(r'(?<!\[)\b([A-Z]{2,10}-\d+)\b(?!\])', replace_issue_key, text)
        
        # Restore protected links
        for placeholder, original in link_placeholders.items():
            text = text.replace(placeholder, original)
        
        return text
    
    def _convert_quotes(self, text: str) -> str:
        """Convert quotes."""
        # {quote} -> > (blockquote)
        lines = text.split('\n')
        in_quote = False
        converted = []
        
        for line in lines:
            if line.strip() == '{quote}':
                in_quote = not in_quote
                continue
            if in_quote:
                converted.append('> ' + line)
            else:
                converted.append(line)
        
        return '\n'.join(converted)
    
    def _convert_tables(self, text: str) -> str:
        """Convert Jira wiki markup tables to Markdown."""
        lines = text.split('\n')
        converted = []
        in_table = False
        table_rows = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check if this is a table line
            is_header = '||' in stripped
            is_data = stripped.startswith('|') and not is_header
            
            if is_header:
                # Header row - parse it carefully
                if not in_table:
                    in_table = True
                cells = self._smart_split(stripped, '||')
                table_rows.append(('header', cells))
                i += 1
            elif is_data and in_table:
                # Data row - collect all lines until we have a complete row
                row_lines = [stripped]
                i += 1
                
                # Keep collecting lines until we find one that ends with |
                while i < len(lines) and not row_lines[-1].endswith('|'):
                    next_line = lines[i].strip()
                    if not next_line or next_line.startswith('#') or next_line.startswith('||'):
                        # End of table content
                        break
                    row_lines.append(next_line)
                    i += 1
                
                # Now parse the complete row
                full_row = ' '.join(row_lines)
                if full_row.endswith('|'):
                    cells = self._smart_split(full_row[1:-1], '|')
                    table_rows.append(('data', cells))
                else:
                    # Incomplete row, skip it
                    pass
            elif is_data and not in_table:
                # Start of table with data row (no header)
                in_table = True
                row_lines = [stripped]
                i += 1
                
                # Collect complete row
                while i < len(lines) and not row_lines[-1].endswith('|'):
                    next_line = lines[i].strip()
                    if not next_line or next_line.startswith('#'):
                        break
                    row_lines.append(next_line)
                    i += 1
                
                full_row = ' '.join(row_lines)
                if full_row.endswith('|'):
                    cells = self._smart_split(full_row[1:-1], '|')
                    table_rows.append(('data', cells))
            else:
                # Not a table line
                if in_table and table_rows:
                    # End of table - convert and output
                    converted.extend(self._format_markdown_table(table_rows))
                    table_rows = []
                    in_table = False
                
                converted.append(line)
                i += 1
        
        # Handle table at end of file
        if in_table and table_rows:
            converted.extend(self._format_markdown_table(table_rows))
        
        return '\n'.join(converted)
    
    def _smart_split(self, text: str, delimiter: str) -> list:
        """
        Split text on delimiter, but not when delimiter is inside brackets.
        This handles Jira link syntax [text|url] which shouldn't be split.
        """
        cells = []
        current_cell = []
        bracket_depth = 0
        
        i = 0
        while i < len(text):
            char = text[i]
            
            if char == '[':
                bracket_depth += 1
                current_cell.append(char)
                i += 1
            elif char == ']':
                bracket_depth -= 1
                current_cell.append(char)
                i += 1
            elif bracket_depth == 0 and text[i:i+len(delimiter)] == delimiter:
                # Found delimiter outside brackets - split here
                cell_text = ''.join(current_cell).strip()
                if cell_text:  # Only add non-empty cells
                    cells.append(cell_text)
                current_cell = []
                i += len(delimiter)
            else:
                current_cell.append(char)
                i += 1
        
        # Add final cell
        cell_text = ''.join(current_cell).strip()
        if cell_text:
            cells.append(cell_text)
        
        return cells
    
    def _format_markdown_table(self, rows: list) -> list:
        """Format table rows as Markdown."""
        if not rows:
            return []
        
        markdown_lines = []
        has_header = False
        max_cells = 0
        all_cleaned_rows = []
        
        # First pass: clean all rows and determine max cell count
        for i, (row_type, cells) in enumerate(rows):
            cleaned_cells = []
            for cell in cells:
                # Replace newlines with spaces, collapse multiple spaces
                cleaned = ' '.join(cell.split())
                # Remove specific malformed artifacts (but preserve valid markdown links)
                # Only remove if it's JUST punctuation, not part of a valid link
                cleaned = re.sub(r'^\]\(\s*', '', cleaned)  # Remove '](' at start
                cleaned = re.sub(r'^\)\[\s*', '', cleaned)  # Remove ')[' at start
                cleaned = cleaned.strip()
                # Only add non-empty cells
                if cleaned:
                    cleaned_cells.append(cleaned)
            
            # Skip rows with no valid cells
            if cleaned_cells:
                all_cleaned_rows.append((row_type, cleaned_cells))
                if len(cleaned_cells) > max_cells:
                    max_cells = len(cleaned_cells)
        
        # Second pass: normalize all rows to have the same number of cells
        for i, (row_type, cells) in enumerate(all_cleaned_rows):
            # Pad rows with fewer cells
            while len(cells) < max_cells:
                cells.append('')
            
            # Format row
            markdown_lines.append('| ' + ' | '.join(cells) + ' |')
            
            # Add separator after first row if it's a header
            if i == 0 and row_type == 'header':
                markdown_lines.append('| ' + ' | '.join(['---'] * max_cells) + ' |')
                has_header = True
        
        # If no header was found, treat first row as header and add separator
        if not has_header and len(markdown_lines) > 0:
            separator = '| ' + ' | '.join(['---'] * max_cells) + ' |'
            markdown_lines.insert(1, separator)
        
        return markdown_lines
    
    def _convert_line_breaks(self, text: str) -> str:
        """Convert line breaks."""
        # \\ -> <br> (or just double newline for Markdown)
        text = re.sub(r'\\\\', '\n\n', text)
        return text
    
    def _convert_images(self, text: str) -> str:
        """Convert image attachments."""
        # !image.png|width=100,height=50,alt="text"! -> ![](image.png)
        # Use non-greedy match and explicitly stop at !
        # Handle multiline by matching any char except !
        text = re.sub(r'!([^!\|\n]+?)\|([^!]+?)!', r'![](\1)', text)
        # !image.png! -> ![](image.png)  
        text = re.sub(r'!([^!\n]+?)!', r'![](\1)', text)
        return text
    
    def _convert_text_effects(self, text: str) -> str:
        """Convert text effects like +inserted+ and -deleted-."""
        # Remove {color} tags - {color:#xxxxxx}text{color} -> text
        text = re.sub(r'\{color:[^\}]+\}([^\{]*)\{color\}', r'\1', text)
        
        # Remove {panel} tags - {panel:bgColor=#xxxxxx}text{panel} -> text (in blockquote)
        text = re.sub(r'\{panel:[^\}]+\}([^\{]*)\{panel\}', r'> \1', text)
        
        # +inserted+ -> **bold** (emphasize inserted text)
        text = re.sub(r'\+([^\+\n]+)\+', r'**\1**', text)
        # -deleted- -> ~~strikethrough~~ (only when surrounded by non-word chars or spaces)
        # But NOT when it's a table separator (multiple dashes)
        text = re.sub(r'(?<!\w)(?<!-)(?<!|)-([^-\n]+)-(?!-)(?!\w)', r'~~\1~~', text)
        return text
    
    def _extract_adf_blocks(self, text: str, adf_blocks: dict) -> str:
        """
        Extract ADF blocks and replace with placeholders.
        Returns text with placeholders, stores converted ADF in adf_blocks dict.
        """
        adf_pattern = r'\{adf:display=block\}\s*(\{.*?\})\s*\{adf\}'
        counter = 0
        
        def replace_adf(match):
            nonlocal counter
            adf_json = match.group(1)
            # Use a placeholder that won't be touched by any converters
            placeholder = f"<<<ADFBLOCK{counter}>>>"
            
            try:
                adf_data = json.loads(adf_json)
                converted = self._parse_adf_node(adf_data)
                adf_blocks[placeholder] = converted
            except json.JSONDecodeError:
                # If JSON parsing fails, keep original
                adf_blocks[placeholder] = match.group(0)
            
            counter += 1
            return placeholder
        
        return re.sub(adf_pattern, replace_adf, text, flags=re.DOTALL)
    
    def _restore_adf_blocks(self, text: str, adf_blocks: dict) -> str:
        """Restore ADF blocks from placeholders."""
        for placeholder, content in adf_blocks.items():
            text = text.replace(placeholder, content)
        return text
    
    def _convert_adf(self, text: str) -> str:
        """
        Convert Atlassian Document Format (ADF) to Markdown.
        ADF is used in newer Jira instances for rich text.
        """
        # Check for ADF block pattern: {adf:display=block} ... {adf}
        adf_pattern = r'\{adf:display=block\}\s*(\{.*?\})\s*\{adf\}'
        
        def replace_adf(match):
            adf_json = match.group(1)
            try:
                adf_data = json.loads(adf_json)
                return self._parse_adf_node(adf_data)
            except json.JSONDecodeError:
                # If JSON parsing fails, return the original text
                return match.group(0)
        
        text = re.sub(adf_pattern, replace_adf, text, flags=re.DOTALL)
        return text
    
    def _parse_adf_node(self, node: dict, inline: bool = False) -> str:
        """
        Parse an ADF node recursively.
        
        Args:
            node: ADF node dictionary
            inline: If True, omit block-level formatting (for table cells)
        """
        if not isinstance(node, dict):
            return ""
        
        node_type = node.get('type', '')
        content = node.get('content', [])
        
        # Handle different node types
        if node_type == 'table':
            return self._parse_adf_table(node)
        elif node_type == 'paragraph':
            result = self._parse_adf_content(content, inline=inline)
            # Only add newlines if not in inline mode
            return result if inline else result + '\n\n'
        elif node_type == 'heading':
            level = node.get('attrs', {}).get('level', 1)
            heading_text = self._parse_adf_content(content, inline=True)
            return f"{'#' * level} {heading_text}\n\n"
        elif node_type == 'bulletList':
            items = []
            for item in content:
                if item.get('type') == 'listItem':
                    item_content = self._parse_adf_content(item.get('content', []), inline=True)
                    items.append(f"- {item_content}")
            result = '\n'.join(items)
            return result if inline else result + '\n\n'
        elif node_type == 'text':
            text = node.get('text', '')
            marks = node.get('marks', [])
            for mark in marks:
                mark_type = mark.get('type')
                if mark_type == 'strong':
                    text = f"**{text}**"
                elif mark_type == 'em':
                    text = f"*{text}*"
                elif mark_type == 'code':
                    text = f"`{text}`"
            return text
        else:
            # For unknown types, process content if available
            return self._parse_adf_content(content, inline=inline)
    
    def _parse_adf_content(self, content: list, inline: bool = False) -> str:
        """
        Parse ADF content array.
        
        Args:
            content: List of ADF nodes
            inline: If True, format for inline context (e.g., table cells)
        """
        if not content:
            return ""
        
        result = []
        for node in content:
            if isinstance(node, dict):
                result.append(self._parse_adf_node(node, inline=inline))
        
        text = ''.join(result)
        return text.strip() if inline else text
    
    def _parse_adf_table(self, table_node: dict) -> str:
        """Parse ADF table to Markdown table."""
        content = table_node.get('content', [])
        if not content:
            return ""
        
        rows = []
        has_header = False
        
        for row_node in content:
            if row_node.get('type') != 'tableRow':
                continue
            
            cells = []
            is_header_row = False
            
            for cell_node in row_node.get('content', []):
                cell_type = cell_node.get('type')
                if cell_type == 'tableHeader':
                    is_header_row = True
                    has_header = True
                
                # Parse cell content in inline mode
                cell_content = self._parse_adf_content(cell_node.get('content', []), inline=True)
                # Clean up: remove all newlines and extra spaces
                cell_content = ' '.join(cell_content.split())
                cells.append(cell_content if cell_content else ' ')
            
            if cells:
                rows.append((cells, is_header_row))
        
        if not rows:
            return ""
        
        # Build Markdown table
        lines = []
        for i, (cells, is_header_row) in enumerate(rows):
            # Add table row
            lines.append('| ' + ' | '.join(cells) + ' |')
            
            # Add separator after first row if it's a header
            if i == 0 and is_header_row:
                lines.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
        
        return '\n'.join(lines) + '\n\n'
