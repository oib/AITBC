#!/usr/bin/env python3
"""
Production Services Launcher
Launches AITBC production services from system locations
"""

import os
import sys
import subprocess
from pathlib import Path

def launch_service(service_name: str, script_path: str):
    """Launch a production service"""
    print(f"Launching {service_name}...")
    
    # Ensure log directory exists
    log_dir = Path(f"/var/log/aitbc/production/{service_name}")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Launch service
    try:
        subprocess.run([
            sys.executable, 
            str(Path("/opt/aitbc/services") / script_path)
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to launch {service_name}: {e}")
        return False
    except FileNotFoundError:
        print(f"Service script not found: {script_path}")
        return False
    
    return True

def main():
    """Main launcher"""
    print("=== AITBC Production Services Launcher ===")
    
    services = [
        ("blockchain", "blockchain.py"),
        ("marketplace", "marketplace.py"),
        ("unified_marketplace", "unified_marketplace.py"),
    ]
    
    for service_name, script_path in services:
        if not launch_service(service_name, script_path):
            print(f"Skipping {service_name} due to error")
            continue

if __name__ == "__main__":
    main()
