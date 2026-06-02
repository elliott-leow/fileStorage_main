"""
Shortcut service for managing folder shortcuts/links.
"""
import os
import json


class ShortcutService:
    """Handles folder shortcut management."""

    def __init__(self, config_file: str):
        self.config_file = config_file
        self.shortcuts = []
        self.load_shortcuts()

    def load_shortcuts(self) -> None:
        """Load shortcuts from the config file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.shortcuts = data.get("shortcuts", [])
                    print(f"Loaded {len(self.shortcuts)} shortcuts.")
            else:
                self.shortcuts = []
                print(f"Info: {self.config_file} not found. No shortcuts configured.")
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Error loading {self.config_file}: {e}")
            self.shortcuts = []

    def save_shortcuts(self) -> bool:
        """Save shortcuts to the config file."""
        try:
            data = {"shortcuts": self.shortcuts}
            with open(self.config_file, "w") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving {self.config_file}: {e}")
            return False

    def get_shortcuts_for_path(self, path: str) -> list:
        """Return shortcuts whose location matches the given path."""
        norm_path = os.path.normpath(path.strip("/")) if path.strip("/") else ""
        if norm_path == ".":
            norm_path = ""
        return [
            s for s in self.shortcuts
            if self._normalize_location(s.get("location", "")) == norm_path
        ]

    def add_shortcut(self, name: str, location: str, target: str) -> bool:
        """Add a new shortcut and save."""
        self.shortcuts.append({
            "name": name,
            "location": location,
            "target": target
        })
        return self.save_shortcuts()

    def remove_shortcut(self, name: str, location: str) -> bool:
        """Remove a shortcut by name and location, then save."""
        norm_location = self._normalize_location(location)
        self.shortcuts = [
            s for s in self.shortcuts
            if not (s.get("name") == name and self._normalize_location(s.get("location", "")) == norm_location)
        ]
        return self.save_shortcuts()

    @staticmethod
    def _normalize_location(location: str) -> str:
        """Normalize a location path for comparison."""
        stripped = location.strip("/")
        if not stripped or stripped == ".":
            return ""
        return os.path.normpath(stripped)
