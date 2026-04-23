"""
Field formatter for Jira fields.
Handles complex field types and formatting.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from config import JIRA_BASE_URL


class FieldFormatter:
    """Formats Jira field values for Markdown output."""
    
    @staticmethod
    def format_user(user: Any) -> Optional[str]:
        """Format user field."""
        if not user:
            return None
        if hasattr(user, 'displayName'):
            return user.displayName
        if hasattr(user, 'name'):
            return user.name
        return str(user)
    
    @staticmethod
    def format_datetime(dt: Any) -> Optional[str]:
        """Format datetime field."""
        if not dt:
            return None
        if isinstance(dt, str):
            # Parse ISO format and convert to readable format
            try:
                parsed = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                return parsed.strftime('%Y-%m-%d %H:%M:%S')
            except:
                return dt
        return str(dt)
    
    @staticmethod
    def format_array(arr: Any) -> Optional[List[str]]:
        """Format array/list field."""
        if not arr:
            return None
        
        result = []
        for item in arr:
            if hasattr(item, 'name'):
                result.append(item.name)
            elif hasattr(item, 'value'):
                result.append(item.value)
            else:
                result.append(str(item))
        
        return result if result else None
    
    @staticmethod
    def format_issue_link(key: str) -> str:
        """Format issue link as an Obsidian wikilink."""
        return f"[[{key}]]"
    
    @staticmethod
    def format_parent(parent: Any) -> Optional[str]:
        """
        Format parent issue field for frontmatter (key only).
        
        Args:
            parent: Parent issue object
            
        Returns:
            str: Just the issue key (e.g., "PRODUCT-15245")
        """
        if not parent:
            return None
        
        key = getattr(parent, 'key', None)
        if not key:
            return None
        
        return key
    
    @staticmethod
    def format_parent_link(parent: Any) -> Optional[str]:
        """
        Format parent issue field for document body.
        
        Args:
            parent: Parent issue object
            
        Returns:
            str: Formatted issue link
        """
        if not parent:
            return None
        
        key = getattr(parent, 'key', None)
        if not key:
            return None
        
        return FieldFormatter.format_issue_link(key)
    
    @staticmethod
    def format_linked_issues(links: Any) -> Optional[List[str]]:
        """Format linked issues."""
        if not links:
            return None
        
        result = []
        for link in links:
            # Get the linked issue key
            if hasattr(link, 'outwardIssue'):
                issue = link.outwardIssue
                link_type = getattr(link.type, 'outward', 'relates to')
            elif hasattr(link, 'inwardIssue'):
                issue = link.inwardIssue
                link_type = getattr(link.type, 'inward', 'relates to')
            else:
                continue
            
            key = getattr(issue, 'key', None)
            if key:
                formatted = f"{link_type}: {FieldFormatter.format_issue_link(key)}"
                result.append(formatted)
        
        return result if result else None
    
    @staticmethod
    def format_linked_issues_grouped(links: Any) -> Optional[Dict[str, List[str]]]:
        """
        Format linked issues grouped by relationship type.
        
        Returns:
            Dict mapping relationship type to list of issue links
        """
        if not links:
            return None
        
        grouped = {}
        for link in links:
            # Get the linked issue key
            if hasattr(link, 'outwardIssue'):
                issue = link.outwardIssue
                link_type = getattr(link.type, 'outward', 'relates to')
            elif hasattr(link, 'inwardIssue'):
                issue = link.inwardIssue
                link_type = getattr(link.type, 'inward', 'relates to')
            else:
                continue
            
            key = getattr(issue, 'key', None)
            if key:
                if link_type not in grouped:
                    grouped[link_type] = []
                grouped[link_type].append(FieldFormatter.format_issue_link(key))
        
        return grouped if grouped else None
    
    @staticmethod
    def format_custom_field(value: Any) -> Optional[str]:
        """Format custom field (generic handler)."""
        if value is None:
            return None
        
        if isinstance(value, str):
            return value
        
        if isinstance(value, (int, float)):
            return str(value)
        
        if isinstance(value, bool):
            return 'Yes' if value else 'No'
        
        if isinstance(value, list):
            formatted = FieldFormatter.format_array(value)
            return ', '.join(formatted) if formatted else None
        
        # Object with name
        if hasattr(value, 'name'):
            return value.name
        
        # Object with value
        if hasattr(value, 'value'):
            return value.value
        
        return str(value)
