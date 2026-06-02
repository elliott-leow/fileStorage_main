"""
Path manipulation and safety utilities.
"""
import os
import urllib.parse


def check_path_safety(path_abs: str, public_dir: str) -> bool:
    """
    Check if the absolute path is safely within the public directory.
    
    Args:
        path_abs: Absolute path to check
        public_dir: The public directory root
        
    Returns:
        True if path is safe, False otherwise
    """
    public_dir_norm = os.path.normpath(public_dir)
    path_abs_norm = os.path.normpath(path_abs)
    
    return (path_abs_norm == public_dir_norm or 
            path_abs_norm.startswith(public_dir_norm + os.sep))


def normalize_path(path: str, strip_slashes: bool = True) -> str:
    """
    Normalize a path, optionally stripping leading/trailing slashes.
    
    Args:
        path: Path to normalize
        strip_slashes: Whether to strip leading/trailing slashes
        
    Returns:
        Normalized path
    """
    if strip_slashes:
        path = path.strip("/")
    
    normalized = os.path.normpath(path)
    
    # Handle root case
    if normalized == ".":
        return ""
    
    return normalized


def normalize_path_display(path: str) -> str:
    """
    Normalize path for display (use forward slashes).
    
    Args:
        path: Path to normalize
        
    Returns:
        Path with forward slashes
    """
    if os.sep != "/":
        return path.replace(os.sep, "/")
    return path


def url_encode_path(path: str) -> str:
    """
    URL encode a path, preserving slashes.
    
    Args:
        path: Path to encode
        
    Returns:
        URL encoded path
    """
    # Normalize to forward slashes first
    normalized = normalize_path_display(path)
    return urllib.parse.quote(normalized)


def url_decode_path(path: str) -> str:
    """
    URL decode a path.
    
    Args:
        path: Path to decode
        
    Returns:
        Decoded path
    """
    try:
        return urllib.parse.unquote(path)
    except Exception:
        return path


