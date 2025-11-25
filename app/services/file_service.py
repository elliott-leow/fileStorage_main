"""
File operations service.
"""
import os
import shutil
from typing import List, Dict, Any, Optional, Tuple
from werkzeug.utils import secure_filename

from ..utils.path_utils import check_path_safety, normalize_path, normalize_path_display
from ..utils.file_utils import format_file_info


class FileService:
    """Handles file and directory operations."""
    
    def __init__(self, public_dir: str, auth_service, visibility_service):
        """
        Initialize the file service.
        
        Args:
            public_dir: The public directory root
            auth_service: The authentication service instance
            visibility_service: The visibility service instance
        """
        self.public_dir = os.path.normpath(public_dir)
        self.auth_service = auth_service
        self.visibility_service = visibility_service
    
    def is_safe_path(self, path_abs: str) -> bool:
        """
        Check if an absolute path is safe.
        
        Args:
            path_abs: The absolute path to check
            
        Returns:
            True if safe
        """
        return check_path_safety(path_abs, self.public_dir)
    
    def get_absolute_path(self, relative_path: str) -> str:
        """
        Get the absolute path from a relative path.
        
        Args:
            relative_path: The relative path
            
        Returns:
            Absolute path
        """
        norm_rel = normalize_path(relative_path)
        return os.path.normpath(os.path.join(self.public_dir, norm_rel))
    
    def list_directory(
        self, 
        relative_path: str, 
        show_hidden: bool = False
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        List contents of a directory.
        
        Args:
            relative_path: The relative path to list
            show_hidden: Whether to show hidden files
            
        Returns:
            Tuple of (list of file info dicts, success boolean)
        """
        norm_path = normalize_path(relative_path)
        abs_path = self.get_absolute_path(norm_path)
        
        if not self.is_safe_path(abs_path) or not os.path.isdir(abs_path):
            return [], False
        
        entries = []
        try:
            for name in sorted(os.listdir(abs_path), key=lambda s: s.lower()):
                entry_abs = os.path.join(abs_path, name)
                
                if not self.is_safe_path(entry_abs):
                    continue
                if not os.path.lexists(entry_abs):
                    continue
                
                entry_rel = normalize_path(os.path.join(norm_path, name))
                
                # Check if hidden
                is_hidden = self.visibility_service.is_hidden(entry_rel)
                if not show_hidden and is_hidden:
                    continue
                
                # Check if protected
                is_protected = self.auth_service.is_path_protected(entry_rel)
                
                info = format_file_info(
                    entry_abs, 
                    entry_rel, 
                    is_protected=is_protected,
                    is_hidden=is_hidden
                )
                
                if not info["error"]:
                    info["display_name"] = name
                    entries.append(info)
        except OSError as e:
            print(f"Error listing directory {abs_path}: {e}")
            return [], False
        
        return entries, True
    
    def get_all_directories(
        self, 
        start_path: str = "", 
        show_hidden: bool = False
    ) -> List[str]:
        """
        Recursively get all directory paths within a start path.
        
        Args:
            start_path: Starting relative path (empty for root)
            show_hidden: Whether to include hidden directories
            
        Returns:
            List of relative directory paths
        """
        start_abs = self.get_absolute_path(start_path)
        dir_list = []
        
        try:
            for root, dirs, _ in os.walk(start_abs, topdown=True):
                if not self.is_safe_path(root):
                    dirs[:] = []
                    continue
                
                rel_root = os.path.relpath(root, self.public_dir)
                norm_rel_root = normalize_path(rel_root)
                
                # Check if hidden
                if not show_hidden and norm_rel_root and self.visibility_service.is_hidden(norm_rel_root):
                    dirs[:] = []
                    continue
                
                if rel_root != ".":
                    dir_list.append(normalize_path_display(rel_root))
                
                # Filter directories for safety
                safe_dirs = [
                    d for d in dirs 
                    if self.is_safe_path(os.path.join(root, d))
                ]
                dirs[:] = safe_dirs
                
        except OSError as e:
            print(f"Error walking directory {start_abs}: {e}")
        
        dir_list.sort()
        return dir_list
    
    def find_by_name(
        self, 
        query: str, 
        start_path: str = "",
        recursive: bool = False,
        show_hidden: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Find files/folders matching a query name substring.
        
        Args:
            query: Search query
            start_path: Starting relative path
            recursive: Whether to search recursively
            show_hidden: Whether to include hidden files
            
        Returns:
            List of matching file info dicts
        """
        start_abs = self.get_absolute_path(start_path)
        results = []
        query_lower = query.lower()
        
        if not self.is_safe_path(start_abs) or not os.path.isdir(start_abs):
            return []
        
        try:
            for root, dirs, files in os.walk(start_abs, topdown=True):
                if not self.is_safe_path(root):
                    dirs[:] = []
                    continue
                
                # Stop recursion if not recursive
                if not recursive and root != start_abs:
                    dirs[:] = []
                
                for name in sorted(dirs + files, key=lambda s: s.lower()):
                    if query_lower not in name.lower():
                        continue
                    
                    entry_abs = os.path.join(root, name)
                    if not self.is_safe_path(entry_abs):
                        continue
                    if not os.path.lexists(entry_abs):
                        continue
                    
                    entry_rel = os.path.relpath(entry_abs, self.public_dir)
                    norm_entry_rel = normalize_path(entry_rel)
                    
                    # Check if hidden
                    is_hidden = self.visibility_service.is_hidden(norm_entry_rel)
                    if not show_hidden and is_hidden:
                        continue
                    
                    is_protected = self.auth_service.is_path_protected(norm_entry_rel)
                    
                    results.append({
                        "rel_path": normalize_path_display(entry_rel),
                        "abs_path": entry_abs,
                        "name": name,
                        "is_protected": is_protected,
                        "is_hidden": is_hidden
                    })
                
                if not recursive and root == start_abs:
                    break
                    
        except OSError as e:
            print(f"Error during find_by_name in {start_abs}: {e}")
        
        return results
    
    def create_folder(self, parent_path: str, folder_name: str) -> Tuple[bool, str, Optional[str]]:
        """
        Create a new folder.
        
        Args:
            parent_path: Parent directory path
            folder_name: Name for the new folder
            
        Returns:
            Tuple of (success, message, new folder relative path or None)
        """
        safe_name = secure_filename(folder_name)
        if not safe_name:
            return False, "Invalid folder name.", None
        
        norm_parent = normalize_path(parent_path)
        new_folder_rel = normalize_path(os.path.join(norm_parent, safe_name)) if norm_parent else safe_name
        new_folder_abs = self.get_absolute_path(new_folder_rel)
        
        if not self.is_safe_path(new_folder_abs):
            return False, "Forbidden path.", None
        
        if os.path.exists(new_folder_abs):
            return False, "Folder already exists.", None
        
        try:
            os.makedirs(new_folder_abs)
            print(f"Created new folder: {new_folder_abs}")
            return True, "Folder created successfully.", new_folder_rel
        except OSError as e:
            print(f"Error creating folder {new_folder_abs}: {e}")
            return False, f"OS Error: {e.strerror}", None
    
    def delete_items(self, items: List[str]) -> Dict[str, Any]:
        """
        Delete files or folders.
        
        Args:
            items: List of relative paths to delete
            
        Returns:
            Dict with success_count, fail_count, and errors list
        """
        success_count = 0
        fail_count = 0
        errors = []
        
        for item_rel_path in items:
            if not isinstance(item_rel_path, str):
                fail_count += 1
                errors.append({"path": "(invalid)", "error": "Invalid item format"})
                continue
            
            norm_path = normalize_path(item_rel_path)
            item_abs = self.get_absolute_path(norm_path)
            
            # Safety checks
            if not self.is_safe_path(item_abs):
                fail_count += 1
                errors.append({"path": norm_path, "error": "Access forbidden"})
                continue
            
            if item_abs == self.public_dir:
                fail_count += 1
                errors.append({"path": "/", "error": "Cannot delete root directory"})
                continue
            
            if not os.path.lexists(item_abs):
                fail_count += 1
                errors.append({"path": norm_path, "error": "Item not found"})
                continue
            
            try:
                if os.path.isdir(item_abs) and not os.path.islink(item_abs):
                    shutil.rmtree(item_abs)
                else:
                    os.remove(item_abs)
                success_count += 1
                print(f"Deleted: {item_abs}")
            except OSError as e:
                fail_count += 1
                errors.append({"path": norm_path, "error": f"OS error: {e.strerror}"})
            except Exception as e:
                fail_count += 1
                errors.append({"path": norm_path, "error": str(e)})
        
        return {
            "success_count": success_count,
            "fail_count": fail_count,
            "errors": errors
        }
    
    def save_uploaded_file(
        self, 
        data: bytes, 
        destination_rel: str
    ) -> Tuple[bool, str]:
        """
        Save uploaded file data.
        
        Args:
            data: File data
            destination_rel: Relative destination path
            
        Returns:
            Tuple of (success, message)
        """
        dest_abs = self.get_absolute_path(destination_rel)
        
        if not self.is_safe_path(dest_abs):
            return False, "Forbidden path"
        
        try:
            dest_dir = os.path.dirname(dest_abs)
            os.makedirs(dest_dir, exist_ok=True)
            
            with open(dest_abs, "wb") as f:
                f.write(data)
            
            print(f"File uploaded: {dest_abs}")
            return True, "File uploaded successfully"
        except IOError as e:
            print(f"IOError writing file {dest_abs}: {e}")
            return False, f"IO Error: {e}"
        except Exception as e:
            print(f"Error during upload: {e}")
            return False, str(e)


