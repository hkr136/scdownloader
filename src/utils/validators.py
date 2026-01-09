"""Validation utilities for URLs and filenames."""

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


def validate_url(url: str) -> bool:
    """
    Validate if a URL is a valid SoundCloud URL.
    
    Args:
        url: URL string to validate
        
    Returns:
        True if valid SoundCloud URL, False otherwise
    """
    if not url:
        return False
    
    try:
        parsed = urlparse(url)
        
        # Check if it's a SoundCloud domain
        valid_domains = ['soundcloud.com', 'www.soundcloud.com', 'm.soundcloud.com']
        
        if parsed.netloc.lower() not in valid_domains:
            return False
        
        # Check if URL has a path
        if not parsed.path or parsed.path == '/':
            return False
        
        return True
        
    except Exception:
        return False


def extract_track_info_from_url(url: str) -> Optional[dict]:
    """
    Extract basic information from SoundCloud URL.
    
    Args:
        url: SoundCloud URL
        
    Returns:
        Dictionary with extracted info or None
    """
    if not validate_url(url):
        return None
    
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]
    
    if len(path_parts) >= 2:
        return {
            'artist': path_parts[0],
            'track_slug': path_parts[1],
            'url': url
        }
    
    return None


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitize filename to be safe for file systems.
    
    Args:
        filename: Original filename
        max_length: Maximum filename length
        
    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, '_', filename)
    
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')
    
    # Limit length
    if len(sanitized) > max_length:
        name, ext = Path(sanitized).stem, Path(sanitized).suffix
        sanitized = name[:max_length - len(ext)] + ext
    
    # Ensure filename is not empty
    if not sanitized:
        sanitized = "untitled"
    
    return sanitized
