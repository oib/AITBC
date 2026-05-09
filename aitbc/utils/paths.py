"""
AITBC Path Utilities
Centralized path resolution and directory management
"""

from pathlib import Path
from .constants import DATA_DIR, CONFIG_DIR, LOG_DIR, REPO_DIR
from .exceptions import ConfigurationError


def get_data_path(subpath: str = "") -> Path:
    """
    Get a path within the AITBC data directory.
    
    Args:
        subpath: Optional subpath relative to data directory
        
    Returns:
        Full path to data directory or subpath
    """
    if subpath:
        return DATA_DIR / subpath
    return DATA_DIR


def get_config_path(filename: str) -> Path:
    """
    Get a path within the AITBC configuration directory.
    
    Args:
        filename: Configuration filename
        
    Returns:
        Full path to configuration file
    """
    return CONFIG_DIR / filename


def get_log_path(filename: str) -> Path:
    """
    Get a path within the AITBC log directory.
    
    Args:
        filename: Log filename
        
    Returns:
        Full path to log file
    """
    return LOG_DIR / filename


def get_repo_path(subpath: str = "") -> Path:
    """
    Get a path within the AITBC repository.
    
    Args:
        subpath: Optional subpath relative to repository
        
    Returns:
        Full path to repository or subpath
    """
    if subpath:
        return REPO_DIR / subpath
    return REPO_DIR


def ensure_dir(path: Path) -> Path:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path
        
    Returns:
        The path (guaranteed to exist)
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_file_dir(filepath: Path) -> Path:
    """
    Ensure the parent directory of a file exists.
    
    Args:
        filepath: File path
        
    Returns:
        The parent directory path (guaranteed to exist)
    """
    return ensure_dir(filepath.parent)


def resolve_path(path: str, base: Path = REPO_DIR) -> Path:
    """
    Resolve a path relative to a base directory.
    
    Args:
        path: Path to resolve (can be absolute or relative)
        base: Base directory for relative paths
        
    Returns:
        Resolved absolute path
    """
    p = Path(path)
    if p.is_absolute():
        return p
    return base / p


def get_keystore_path(wallet_name: str = "") -> Path:
    """
    Get a path within the AITBC keystore directory.
    
    Args:
        wallet_name: Optional wallet name for specific keystore file
        
    Returns:
        Full path to keystore directory or specific wallet file
    """
    keystore_dir = DATA_DIR / "keystore"
    if wallet_name:
        return keystore_dir / f"{wallet_name}.json"
    return keystore_dir


def get_blockchain_data_path(chain_id: str = "ait-mainnet") -> Path:
    """
    Get a path within the blockchain data directory.
    
    Args:
        chain_id: Chain identifier
        
    Returns:
        Full path to blockchain data directory
    """
    return DATA_DIR / "data" / chain_id


def get_marketplace_data_path(subpath: str = "") -> Path:
    """
    Get a path within the marketplace data directory.
    
    Args:
        subpath: Optional subpath relative to marketplace directory
        
    Returns:
        Full path to marketplace data directory or subpath
    """
    marketplace_dir = DATA_DIR / "marketplace"
    if subpath:
        return marketplace_dir / subpath
    return marketplace_dir
