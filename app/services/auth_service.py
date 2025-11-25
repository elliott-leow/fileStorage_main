"""
Authentication and authorization service for folder protection.
"""
import os
import json
from typing import Dict, Optional, Set
from flask import session


class AuthService:
    """Handles folder key protection and session-based authorization."""
    
    def __init__(self, config_file: str):
        """
        Initialize the auth service.
        
        Args:
            config_file: Path to the folder keys configuration file
        """
        self.config_file = config_file
        self.protected_folders: Dict[str, str] = {}
        self.load_folder_keys()
    
    def load_folder_keys(self) -> None:
        """Load protected folder configurations from JSON file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    config_data = json.load(f)
                    raw_paths = config_data.get("protected_paths", [])
                    
                    # Sort by path length (longest first) for proper matching
                    sorted_paths = sorted(
                        raw_paths, 
                        key=lambda x: len(x.get("path", "")), 
                        reverse=True
                    )
                    
                    for item in sorted_paths:
                        path = item.get("path")
                        key = item.get("key")
                        if path and key:
                            norm_rel_path = os.path.normpath(path.strip("/"))
                            self.protected_folders[norm_rel_path] = key
                        else:
                            print(f"Warning: Invalid entry in {self.config_file}: {item}")
                    
                    print(f"Loaded {len(self.protected_folders)} protected folder configurations.")
            else:
                print(f"Info: {self.config_file} not found. No folder-specific keys loaded.")
                
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {self.config_file}.")
            self.protected_folders = {}
        except Exception as e:
            print(f"Error loading folder keys: {e}")
            self.protected_folders = {}
    
    def save_folder_keys(self) -> bool:
        """
        Save the current protected folder configurations to JSON file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            protected_paths_list = [
                {"path": path, "key": key} 
                for path, key in self.protected_folders.items()
            ]
            # Sort by path length for consistent output
            protected_paths_list.sort(
                key=lambda x: len(x.get("path", "")), 
                reverse=True
            )
            
            config_data = {"protected_paths": protected_paths_list}
            with open(self.config_file, "w") as f:
                json.dump(config_data, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving {self.config_file}: {e}")
            return False
    
    def get_required_key_for_path(self, relative_path: str) -> Optional[str]:
        """
        Find the required API key for a given relative path, if any.
        
        Args:
            relative_path: The relative path to check
            
        Returns:
            Required key or None if no key required
        """
        norm_req_path = os.path.normpath(relative_path.strip("/"))
        if norm_req_path == ".":
            norm_req_path = ""
        
        for protected_path, key in self.protected_folders.items():
            if (norm_req_path == protected_path or
                norm_req_path.startswith(protected_path + os.sep)):
                return key
        
        return None
    
    def is_path_protected(self, relative_path: str) -> bool:
        """
        Check if a path requires a key.
        
        Args:
            relative_path: The relative path to check
            
        Returns:
            True if protected
        """
        return self.get_required_key_for_path(relative_path) is not None
    
    def validate_key(self, path: str, key: str) -> bool:
        """
        Validate a key for a given path.
        
        Args:
            path: The path to validate
            key: The key to check
            
        Returns:
            True if key is valid
        """
        required_key = self.get_required_key_for_path(path)
        if not required_key:
            return True  # No key required
        return required_key == key
    
    def set_path_protection(self, path: str, password: str) -> bool:
        """
        Set password protection for a path.
        
        Args:
            path: The path to protect
            password: The protection password
            
        Returns:
            True if successful
        """
        norm_path = os.path.normpath(path.strip("/"))
        if norm_path == "." or norm_path == "":
            return False  # Cannot protect root
        
        self.protected_folders[norm_path] = password
        return self.save_folder_keys()
    
    def remove_path_protection(self, path: str) -> bool:
        """
        Remove password protection from a path.
        
        Args:
            path: The path to unprotect
            
        Returns:
            True if successful
        """
        norm_path = os.path.normpath(path.strip("/"))
        if norm_path in self.protected_folders:
            del self.protected_folders[norm_path]
            return self.save_folder_keys()
        return True
    
    @staticmethod
    def grant_session_access(path: str) -> None:
        """
        Grant session access to a path.
        
        Args:
            path: The path to grant access to
        """
        norm_path = os.path.normpath(path.strip("/"))
        if norm_path == ".":
            norm_path = ""
        
        authorized_paths = set(session.get("authorized_paths", []))
        authorized_paths.add(norm_path)
        session["authorized_paths"] = list(authorized_paths)
        session.modified = True
    
    @staticmethod
    def has_session_access(path: str, required_key: Optional[str]) -> bool:
        """
        Check if the current session has access to a path.
        
        Args:
            path: The path to check
            required_key: The required key for the path (None if not protected)
            
        Returns:
            True if access is granted
        """
        if not required_key:
            return True  # No key required
        
        norm_path = os.path.normpath(path.strip("/"))
        if norm_path == ".":
            norm_path = ""
        
        authorized_paths = set(session.get("authorized_paths", []))
        
        for authorized_path in authorized_paths:
            is_root_authorized = authorized_path == ""
            is_current_root = norm_path == ""
            
            if norm_path == authorized_path:
                return True
            elif is_root_authorized and not is_current_root:
                return True
            elif not is_root_authorized and norm_path.startswith(authorized_path + os.sep):
                return True
        
        return False


