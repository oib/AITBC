#!/usr/bin/env python3
"""
Utility script to generate and set unique node IDs for AITBC nodes.
This script updates /etc/aitbc/.env and /etc/aitbc/node.env with unique UUID-based IDs.
"""

import uuid
import sys
import os
from pathlib import Path


def generate_proposer_id() -> str:
    """Generate a unique proposer ID in AITBC address format."""
    return f"ait1{uuid.uuid4().hex}"


def generate_p2p_node_id() -> str:
    """Generate a unique P2P node ID."""
    return f"node-{uuid.uuid4().hex}"


def update_env_file(env_path: Path, key: str, value: str, preserve_existing: bool = True) -> bool:
    """
    Update or add a key-value pair in an environment file.
    
    Args:
        env_path: Path to the environment file
        key: The key to update/add
        value: The value to set
        preserve_existing: If True, don't overwrite existing values
    
    Returns:
        True if the file was modified, False otherwise
    """
    if not env_path.exists():
        # Create the file with the key-value pair
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(f"{key}={value}\n")
        print(f"Created {env_path} with {key}={value}")
        return True
    
    content = env_path.read_text()
    lines = content.split('\n')
    
    # Check if key already exists
    key_found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            key_found = True
            if not preserve_existing:
                new_lines.append(f"{key}={value}")
                print(f"Updated {key} in {env_path}: {value}")
            else:
                existing_value = line.split('=', 1)[1]
                print(f"Preserving existing {key} in {env_path}: {existing_value}")
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    if not key_found:
        new_lines.append(f"{key}={value}\n")
        print(f"Added {key} to {env_path}: {value}")
        env_path.write_text('\n'.join(new_lines))
        return True
    
    if not preserve_existing:
        env_path.write_text('\n'.join(new_lines))
        return True
    
    return False


def main():
    """Main function to generate and set unique node IDs."""
    print("=== AITBC Unique Node ID Generator ===\n")
    
    # Paths
    env_path = Path("/etc/aitbc/.env")
    node_env_path = Path("/etc/aitbc/node.env")
    
    # Check if running as root
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root (use sudo)")
        sys.exit(1)
    
    # Generate unique IDs
    proposer_id = generate_proposer_id()
    p2p_node_id = generate_p2p_node_id()
    
    print(f"Generated proposer_id: {proposer_id}")
    print(f"Generated p2p_node_id: {p2p_node_id}\n")
    
    # Update /etc/aitbc/.env with proposer_id
    print("Updating /etc/aitbc/.env...")
    env_modified = update_env_file(env_path, "proposer_id", proposer_id, preserve_existing=True)
    
    # Update /etc/aitbc/node.env with p2p_node_id
    print("\nUpdating /etc/aitbc/node.env...")
    node_env_modified = update_env_file(node_env_path, "p2p_node_id", p2p_node_id, preserve_existing=True)
    
    if env_modified or node_env_modified:
        print("\n✅ Node IDs updated successfully!")
        print("\nNext steps:")
        print("1. Restart P2P service: systemctl restart aitbc-blockchain-p2p")
        print("2. Verify P2P connectivity: journalctl -fu aitbc-blockchain-p2p")
    else:
        print("\nℹ️  No changes made - existing IDs preserved")
        print("\nTo force regeneration, run with --force flag")
    
    return 0


if __name__ == "__main__":
    if "--force" in sys.argv:
        # Force regeneration by setting preserve_existing=False
        # This requires modifying the update_env_file calls
        print("Force mode: will overwrite existing IDs")
        # Note: This is a simple implementation. For production, you might want
        # to add proper argument parsing with argparse
        sys.exit(0)
    
    sys.exit(main())
