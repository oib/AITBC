#!/usr/bin/env python3
"""Database encryption migration tool for AITBC blockchain node.

This CLI tool provides commands to encrypt and decrypt SQLite database files
for the Phase 2 database encryption implementation.
"""

import argparse
import sys
import shutil
from pathlib import Path

# Add the src directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
# Add the repo root to the path for aitbc module
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from aitbc_chain.database_encryption import (
    KeyManager,
    DatabaseEncryptor,
    is_database_encrypted,
    get_encryption_key,
)


def encrypt_database(
    db_path: Path,
    key_path: Path,
    backup: bool = True,
    dry_run: bool = False,
) -> None:
    """Encrypt a database file.
    
    Args:
        db_path: Path to the database file.
        key_path: Path to the encryption key file.
        backup: Whether to create a backup before encryption.
        dry_run: If True, only print what would be done without executing.
    """
    print(f"Encrypting database: {db_path}")
    print(f"Using key file: {key_path}")
    
    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)
    
    if is_database_encrypted(db_path):
        print("Error: Database is already encrypted")
        sys.exit(1)
    
    if backup:
        backup_path = db_path.with_suffix('.db.backup')
        if dry_run:
            print(f"[DRY RUN] Would create backup: {backup_path}")
        else:
            print(f"Creating backup: {backup_path}")
            shutil.copy2(db_path, backup_path)
    
    key_manager = KeyManager(key_path)
    key = key_manager.get_or_generate_key()
    
    if dry_run:
        print(f"[DRY RUN] Would encrypt {db_path}")
        print(f"[DRY RUN] Key file exists: {key_path.exists()}")
    else:
        encryptor = DatabaseEncryptor(key)
        encrypted_path = db_path.with_suffix('.db.encrypted')
        encryptor.encrypt_file(db_path, encrypted_path)
        
        # Replace original with encrypted
        encrypted_path.replace(db_path)
        print(f"Database encrypted successfully: {db_path}")
        print(f"Backup created at: {backup_path if backup else 'None'}")


def decrypt_database(
    db_path: Path,
    key_path: Path,
    output_path: Path = None,
    backup: bool = True,
    dry_run: bool = False,
) -> None:
    """Decrypt an encrypted database file.
    
    Args:
        db_path: Path to the encrypted database file.
        key_path: Path to the encryption key file.
        output_path: Optional output path for decrypted database.
        backup: Whether to create a backup before decryption.
        dry_run: If True, only print what would be done without executing.
    """
    print(f"Decrypting database: {db_path}")
    print(f"Using key file: {key_path}")
    
    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)
    
    if not is_database_encrypted(db_path):
        print("Error: Database is not encrypted")
        sys.exit(1)
    
    if not key_path.exists():
        print(f"Error: Key file not found: {key_path}")
        sys.exit(1)
    
    if backup:
        backup_path = db_path.with_suffix('.db.encrypted.backup')
        if dry_run:
            print(f"[DRY RUN] Would create backup: {backup_path}")
        else:
            print(f"Creating backup: {backup_path}")
            shutil.copy2(db_path, backup_path)
    
    key_manager = KeyManager(key_path)
    key = key_manager.load_key()
    
    if key is None:
        print(f"Error: Failed to load key from: {key_path}")
        sys.exit(1)
    
    if output_path is None:
        output_path = db_path.with_suffix('').with_suffix('.db')
    
    if dry_run:
        print(f"[DRY RUN] Would decrypt {db_path} to {output_path}")
    else:
        encryptor = DatabaseEncryptor(key)
        encryptor.decrypt_file(db_path, output_path)
        
        # Replace original with decrypted if output_path is derived from db_path
        if str(output_path) == str(db_path.with_suffix('').with_suffix('.db')):
            output_path.replace(db_path)
            print(f"Database decrypted successfully: {db_path}")
        else:
            print(f"Database decrypted to: {output_path}")
        print(f"Backup created at: {backup_path if backup else 'None'}")


def generate_key(key_path: Path, dry_run: bool = False) -> None:
    """Generate a new encryption key.
    
    Args:
        key_path: Path where the key should be saved.
        dry_run: If True, only print what would be done without executing.
    """
    print(f"Generating encryption key: {key_path}")
    
    if dry_run:
        print(f"[DRY RUN] Would generate new key at: {key_path}")
    else:
        key_manager = KeyManager(key_path)
        key = key_manager.get_or_generate_key()
        print(f"Key generated successfully: {key_path}")
        print(f"Key length: {len(key)} bytes")


def check_encryption(db_path: Path) -> None:
    """Check if a database is encrypted.
    
    Args:
        db_path: Path to the database file.
    """
    print(f"Checking encryption status: {db_path}")
    
    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)
    
    if is_database_encrypted(db_path):
        print("Status: ENCRYPTED")
    else:
        print("Status: NOT ENCRYPTED")


def main():
    parser = argparse.ArgumentParser(
        description="Database encryption migration tool for AITBC blockchain node"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Encrypt command
    encrypt_parser = subparsers.add_parser("encrypt", help="Encrypt a database file")
    encrypt_parser.add_argument(
        "--db-path",
        type=Path,
        required=True,
        help="Path to the database file"
    )
    encrypt_parser.add_argument(
        "--key-path",
        type=Path,
        default=Path("/etc/aitbc/secrets/db_encryption.key"),
        help="Path to the encryption key file (default: /etc/aitbc/secrets/db_encryption.key)"
    )
    encrypt_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a backup before encryption"
    )
    encrypt_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without executing"
    )
    
    # Decrypt command
    decrypt_parser = subparsers.add_parser("decrypt", help="Decrypt an encrypted database file")
    decrypt_parser.add_argument(
        "--db-path",
        type=Path,
        required=True,
        help="Path to the encrypted database file"
    )
    decrypt_parser.add_argument(
        "--key-path",
        type=Path,
        default=Path("/etc/aitbc/secrets/db_encryption.key"),
        help="Path to the encryption key file (default: /etc/aitbc/secrets/db_encryption.key)"
    )
    decrypt_parser.add_argument(
        "--output-path",
        type=Path,
        help="Output path for decrypted database (default: replaces original)"
    )
    decrypt_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a backup before decryption"
    )
    decrypt_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without executing"
    )
    
    # Generate key command
    generate_parser = subparsers.add_parser("generate-key", help="Generate a new encryption key")
    generate_parser.add_argument(
        "--key-path",
        type=Path,
        default=Path("/etc/aitbc/secrets/db_encryption.key"),
        help="Path where the key should be saved (default: /etc/aitbc/secrets/db_encryption.key)"
    )
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without executing"
    )
    
    # Check command
    check_parser = subparsers.add_parser("check", help="Check if a database is encrypted")
    check_parser.add_argument(
        "--db-path",
        type=Path,
        required=True,
        help="Path to the database file"
    )
    
    args = parser.parse_args()
    
    if args.command == "encrypt":
        encrypt_database(
            db_path=args.db_path,
            key_path=args.key_path,
            backup=not args.no_backup,
            dry_run=args.dry_run,
        )
    elif args.command == "decrypt":
        decrypt_database(
            db_path=args.db_path,
            key_path=args.key_path,
            output_path=args.output_path,
            backup=not args.no_backup,
            dry_run=args.dry_run,
        )
    elif args.command == "generate-key":
        generate_key(
            key_path=args.key_path,
            dry_run=args.dry_run,
        )
    elif args.command == "check":
        check_encryption(
            db_path=args.db_path,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
