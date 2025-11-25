"""
Visibility service for managing hidden folders.
"""
import os
import json
from typing import Set
from flask import session


class VisibilityService:
    """Handles folder visibility (hidden/shown) management."""
    
    def __init__(self, config_file: str):
        """
        Initialize the visibility service.
        
        Args:
            config_file: Path to the visibility configuration file
        """
        self.config_file = config_file
        self.hidden_paths: Set[str] = set()
        self.load_hidden_paths()
    
    def load_hidden_paths(self) -> None:
        """Load the set of hidden paths from the visibility config file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    raw_paths = data.get("hidden_paths", [])
                    self.hidden_paths = {
                        os.path.normpath(p.strip("/")) 
                        for p in raw_paths if p
                    }
                    print(f"Loaded {len(self.hidden_paths)} hidden folder paths.")
            else:
                self.hidden_paths = set()
                print(f"Info: {self.config_file} not found. No folders are hidden.")
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Error loading or parsing {self.config_file}: {e}")
            self.hidden_paths = set()
    
    def save_hidden_paths(self) -> bool:
        """
        Save the current set of hidden paths to the config file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            data = {"hidden_paths": sorted(list(self.hidden_paths))}
            with open(self.config_file, "w") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving {self.config_file}: {e}")
            return False
    
    def is_hidden(self, path: str) -> bool:
        """
        Check if a path is hidden.
        
        Args:
            path: The relative path to check
            
        Returns:
            True if hidden
        """
        norm_path = os.path.normpath(path.strip("/"))
        if norm_path == ".":
            return False  # Root cannot be hidden
        return norm_path in self.hidden_paths
    
    def hide_path(self, path: str) -> bool:
        """
        Hide a path.
        
        Args:
            path: The path to hide
            
        Returns:
            True if successful
        """
        norm_path = os.path.normpath(path.strip("/"))
        if norm_path == "." or norm_path == "":
            return False  # Cannot hide root
        
        self.hidden_paths.add(norm_path)
        return self.save_hidden_paths()
    
    def unhide_path(self, path: str) -> bool:
        """
        Unhide a path.
        
        Args:
            path: The path to unhide
            
        Returns:
            True if successful
        """
        norm_path = os.path.normpath(path.strip("/"))
        self.hidden_paths.discard(norm_path)
        return self.save_hidden_paths()
    
    def toggle_visibility(self, path: str, hide: bool) -> bool:
        """
        Toggle visibility of a path.
        
        Args:
            path: The path to toggle
            hide: True to hide, False to unhide
            
        Returns:
            True if successful
        """
        if hide:
            return self.hide_path(path)
        else:
            return self.unhide_path(path)
    
    @staticmethod
    def get_show_hidden_session() -> bool:
        """
        Get the show_hidden state from session.
        
        Returns:
            True if hidden files should be shown
        """
        return session.get("show_hidden", False)
    
    @staticmethod
    def set_show_hidden_session(show: bool) -> None:
        """
        Set the show_hidden state in session.
        
        Args:
            show: Whether to show hidden files
        """
        session["show_hidden"] = show
        session.modified = True
    
    @staticmethod
    def toggle_show_hidden_session() -> bool:
        """
        Toggle the show_hidden state in session.
        
        Returns:
            The new state
        """
        current = session.get("show_hidden", False)
        new_state = not current
        session["show_hidden"] = new_state
        session.modified = True
        return new_state


