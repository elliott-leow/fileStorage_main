"""
File information and formatting utilities.
"""
import os
from datetime import datetime
from typing import Dict, Any, Optional
import urllib.parse

import humanize

from .path_utils import normalize_path_display


def format_file_info(
    entry_path: str, 
    rel_path: str,
    is_protected: bool = False,
    is_hidden: bool = False
) -> Dict[str, Any]:
    """
    Format file/directory information for the template.
    
    Args:
        entry_path: Absolute path to the entry
        rel_path: Relative path from public root
        is_protected: Whether the entry is password protected
        is_hidden: Whether the entry is hidden
        
    Returns:
        Dictionary with formatted file information
    """
    try:
        stat_result = os.stat(entry_path)
        is_dir = os.path.isdir(entry_path)
        size = "-" if is_dir else humanize.naturalsize(stat_result.st_size)
        mtime = datetime.fromtimestamp(stat_result.st_mtime).strftime("%Y-%m-%d %H:%M")
        
        rel_path_normalized = normalize_path_display(rel_path)
        rel_path_encoded = urllib.parse.quote(rel_path_normalized)
        
        return {
            "is_dir": is_dir,
            "size": size,
            "mtime": mtime,
            "rel_path": rel_path_normalized,
            "rel_path_encoded": rel_path_encoded,
            "is_protected": is_protected,
            "is_hidden": is_hidden,
            "error": False
        }
    except OSError as e:
        print(f"Warning: Could not stat {entry_path}: {e}")
        
        rel_path_normalized = normalize_path_display(rel_path)
        
        return {
            "is_dir": False,
            "size": "N/A",
            "mtime": "N/A",
            "rel_path": rel_path_normalized,
            "rel_path_encoded": urllib.parse.quote(rel_path_normalized),
            "is_protected": False,
            "is_hidden": is_hidden,
            "error": True
        }


def get_file_icon_type(filename: str) -> str:
    """
    Determine the icon type for a file based on its extension.
    
    Args:
        filename: The filename
        
    Returns:
        Icon type string (e.g., 'pdf', 'image', 'folder', 'file')
    """
    lower_name = filename.lower()
    
    if lower_name.endswith(".pdf"):
        return "pdf"
    elif lower_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif")):
        return "image"
    elif lower_name.endswith((".doc", ".docx")):
        return "document"
    elif lower_name.endswith((".xls", ".xlsx", ".csv")):
        return "spreadsheet"
    elif lower_name.endswith((".zip", ".rar", ".7z", ".tar", ".gz")):
        return "archive"
    elif lower_name.endswith((".mp3", ".wav", ".flac", ".ogg")):
        return "audio"
    elif lower_name.endswith((".mp4", ".avi", ".mov", ".mkv")):
        return "video"
    elif lower_name.endswith((".py", ".js", ".ts", ".java", ".cpp", ".c", ".h")):
        return "code"
    else:
        return "file"


def get_file_extension(filename: str) -> str:
    """
    Get the file extension.
    
    Args:
        filename: The filename
        
    Returns:
        File extension (lowercase, including dot) or empty string
    """
    _, ext = os.path.splitext(filename)
    return ext.lower()


def is_supported_for_indexing(filename: str, supported_extensions: list) -> bool:
    """
    Check if a file is supported for semantic indexing.
    
    Args:
        filename: The filename
        supported_extensions: List of supported extensions
        
    Returns:
        True if supported
    """
    ext = get_file_extension(filename)
    return ext in supported_extensions


