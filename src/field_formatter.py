"""
Field formatter for Jira fields.
Handles complex field types and formatting.
"""

from typing import Any, List, Optional
from datetime import datetime


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
