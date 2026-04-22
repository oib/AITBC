"""
AITBC JSON Utilities
Centralized JSON loading, saving, and manipulation
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from .exceptions import ConfigurationError


def load_json(path: Path) -> Dict[str, Any]:
    """
    Load JSON data from a file.
    
    Args:
        path: Path to JSON file
        
    Returns:
        Parsed JSON data as dictionary
        
    Raises:
        ConfigurationError: If file cannot be read or parsed
    """
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise ConfigurationError(f"JSON file not found: {path}")
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in {path}: {e}")


def save_json(data: Dict[str, Any], path: Path, indent: int = 2) -> None:
    """
    Save JSON data to a file.
    
    Args:
        data: Dictionary to save as JSON
        path: Path to output file
        indent: JSON indentation level
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=indent)


def merge_json(*paths: Path) -> Dict[str, Any]:
    """
    Merge multiple JSON files, later files override earlier ones.
    
    Args:
        *paths: Variable number of JSON file paths
        
    Returns:
        Merged dictionary
    """
    merged = {}
    for path in paths:
        data = load_json(path)
        merged.update(data)
    return merged


def json_to_string(data: Dict[str, Any], indent: int = 2) -> str:
    """
    Convert dictionary to JSON string.
    
    Args:
        data: Dictionary to convert
        indent: JSON indentation level
        
    Returns:
        JSON string
    """
    return json.dumps(data, indent=indent)


def string_to_json(json_str: str) -> Dict[str, Any]:
    """
    Parse JSON string to dictionary.
    
    Args:
        json_str: JSON string
        
    Returns:
        Parsed dictionary
        
    Raises:
        ConfigurationError: If string cannot be parsed
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON string: {e}")


def get_nested_value(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    Get a nested value from a dictionary using dot notation or key chain.
    
    Args:
        data: Dictionary to search
        *keys: Keys to traverse (e.g., "a", "b", "c" for data["a"]["b"]["c"])
        default: Default value if key not found
        
    Returns:
        Nested value or default
    """
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def set_nested_value(data: Dict[str, Any], *keys: str, value: Any) -> None:
    """
    Set a nested value in a dictionary using key chain.
    
    Args:
        data: Dictionary to modify
        *keys: Keys to traverse (e.g., "a", "b", "c" for data["a"]["b"]["c"])
        value: Value to set
    """
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def flatten_json(data: Dict[str, Any], separator: str = ".") -> Dict[str, Any]:
    """
    Flatten a nested dictionary using dot notation.
    
    Args:
        data: Nested dictionary
        separator: Separator for flattened keys
        
    Returns:
        Flattened dictionary
    """
    def _flatten(obj: Any, parent_key: str = "") -> Dict[str, Any]:
        items = {}
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{parent_key}{separator}{key}" if parent_key else key
                items.update(_flatten(value, new_key))
        else:
            items[parent_key] = obj
        return items
    
    return _flatten(data)
