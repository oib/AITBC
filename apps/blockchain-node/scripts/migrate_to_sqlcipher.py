#!/usr/bin/env python3
"""
Migrate existing SQLite database to SQLCipher encrypted format.

This script converts an existing unencrypted SQLite database to SQLCipher
encrypted format using the built-in sqlcipher_export function.
"""

import sys
import os
from pathlib import Path

# Add repo root to path for imports
repo_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(repo_root))

try:
    import sqlcipher3 as sqlite3
except ImportError:
    print("ERROR: sqlcipher3-binary not installed")
    print("Run: pip install sqlcipher3-binary")
    sys.exit(1)


def migrate_to_sqlcipher(db_path: Path, key_path: Path) -> None:
    """Migrate database to SQLCipher encrypted format.
    
    Uses SQLCipher's built-in sqlcipher_export function to properly
    encrypt the database while maintaining SQLite's internal structure.
    
    Args:
        db_path: Path to the existing SQLite database
        key_path: Path to the encryption key file
    """
    if not db_path.exists():
        print(f"ERROR: Database file not found: {db_path}")
        sys.exit(1)
    
    if not key_path.exists():
        print(f"ERROR: Key file not found: {key_path}")
        sys.exit(1)
    
    # Read encryption key (stored as raw binary bytes)
    with open(key_path, 'rb') as f:
        key_bytes = f.read()
    
    # Convert raw bytes to hex for SQLCipher
    key_hex = key_bytes.hex()
    
    # Create backup
    backup_path = db_path.with_suffix('.db.backup')
    print(f"Creating backup: {backup_path}")
    import shutil
    shutil.copy2(db_path, backup_path)
    
    # Create temporary encrypted database
    temp_encrypted_path = db_path.with_suffix('.db.encrypted')
    
    # Open unencrypted database
    print(f"Opening unencrypted database: {db_path}")
    conn_unencrypted = sqlite3.connect(str(db_path))
    
    # Attach encrypted database
    print(f"Creating encrypted database: {temp_encrypted_path}")
    conn_unencrypted.execute(f"ATTACH DATABASE '{temp_encrypted_path}' AS encrypted KEY '{key_hex}'")
    
    # Export data to encrypted database
    print("Exporting data to encrypted database...")
    conn_unencrypted.execute("SELECT sqlcipher_export('encrypted')")
    conn_unencrypted.commit()
    
    # Detach encrypted database
    conn_unencrypted.execute("DETACH DATABASE encrypted")
    conn_unencrypted.close()
    
    # Replace original with encrypted
    print(f"Replacing original with encrypted database")
    temp_encrypted_path.replace(db_path)
    
    print(f"Database migrated successfully to SQLCipher format")
    print(f"Backup available at: {backup_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate SQLite database to SQLCipher encrypted format")
    parser.add_argument("--db-path", type=Path, required=True, help="Path to the SQLite database")
    parser.add_argument("--key-path", type=Path, default=Path("/etc/aitbc/secrets/db_encryption.key"), help="Path to the encryption key file")
    
    args = parser.parse_args()
    
    migrate_to_sqlcipher(args.db_path, args.key_path)
