#!/usr/bin/env python3
"""
API Key Generation Script for AITBC CLI

Generates cryptographically secure API keys for testing CLI commands
"""

import secrets
import json
import sys
from datetime import datetime, UTC, timedelta

def generate_api_key(length=32):
    """Generate a cryptographically secure API key"""
    return secrets.token_urlsafe(length)

def create_api_key_entry(name, permissions="client", environment="default"):
    """Create an API key entry with metadata"""
    api_key = generate_api_key()
    
    entry = {
        "name": name,
        "api_key": api_key,  # Stored in memory only, masked when printed
        "permissions": permissions.split(",") if isinstance(permissions, str) else permissions,
        "environment": environment,
        "created_at": datetime.now(datetime.UTC).isoformat(),
        "expires_at": (datetime.now(datetime.UTC) + timedelta(days=365)).isoformat(),
        "status": "active"
    }
    
    return entry

def main():
    """Main function to generate API keys"""
    print("🔑 AITBC API Key Generator")
    print("=" * 50)
    
    # Generate different types of API keys
    keys = []
    
    # Client API key (for job submission, agent operations)
    client_key = create_api_key_entry(
        name="client-test-key",
        permissions="client",
        environment="default"
    )
    keys.append(client_key)
    
    # Admin API key (for system administration)
    admin_key = create_api_key_entry(
        name="admin-test-key", 
        permissions="client,admin",
        environment="default"
    )
    keys.append(admin_key)
    
    # Miner API key (for mining operations)
    miner_key = create_api_key_entry(
        name="miner-test-key",
        permissions="client,miner",
        environment="default"
    )
    keys.append(miner_key)
    
    # Full access API key (for testing)
    full_key = create_api_key_entry(
        name="full-test-key",
        permissions="client,admin,miner",
        environment="default"
    )
    keys.append(full_key)
    
    # Display generated keys
    print(f"\n📋 Generated {len(keys)} API Keys:\n")
    
    for i, key in enumerate(keys, 1):
        print(f"{i}. {key['name']}")
        print(f"   API Key: {'*' * 32}")  # Mask API key for security
        print(f"   Permissions: {', '.join(key['permissions'])}")
        print(f"   Environment: {key['environment']}")
        print(f"   Created: {key['created_at']}")
        print()
    
    # Save to file
    output_file = "/tmp/aitbc-api-keys.json"
    with open(output_file, 'w') as f:
        json.dump(keys, f, indent=2)
    
    print(f"💾 API keys saved to: {output_file}")
    
    # Show usage instructions
    print("\n🚀 Usage Instructions:")
    print("=" * 50)
    
    for key in keys:
        if 'client' in key['permissions']:
            print(f"# For {key['name']}:")
            print(f"aitbc auth login {'*' * 32} --environment {key['environment']}")  # Mask API key
            print()
    
    print("# Test commands that require authentication:")
    print("aitbc client submit --prompt 'What is AITBC?' --model gemma3:1b")
    print("aitbc agent create --name test-agent --description 'Test agent'")
    print("aitbc marketplace gpu list")
    
    print("\n✅ API keys generated successfully!")

if __name__ == "__main__":
    main()
