"""Compatibility imports for scripts that used the former root-level settings module."""

from tech_arena.config import Settings, find_project_root, load_settings

__all__ = ["Settings", "find_project_root", "load_settings"]
