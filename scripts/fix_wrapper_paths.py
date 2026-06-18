#!/usr/bin/env python3
"""Script to update wrapper files to use AITBC_HOME environment variable"""

import re
from pathlib import Path

def update_wrapper_file(file_path):
    """Update a wrapper file to use AITBC_HOME environment variable"""
    content = file_path.read_text()
    
    # Check if already updated
    if "AITBC_HOME" in content:
        print(f"Skipping {file_path} - already updated")
        return False
    
    # Replace hardcoded paths with AITBC_HOME pattern
    patterns = [
        (r'REPO_DIR = Path\("/opt/aitbc"\)', 
         'AITBC_HOME = Path(os.environ.get("AITBC_HOME", "/opt/aitbc"))\nREPO_DIR = AITBC_HOME'),
        (r'SERVICE_DIR = Path\("/opt/aitbc/([^"]+)"\)', 
         r'SERVICE_DIR = AITBC_HOME / "\1"'),
        (r'SDK_DIR = Path\("/opt/aitbc/([^"]+)"\)', 
         r'SDK_DIR = AITBC_HOME / "\1"'),
        (r'CRYPTO_DIR = Path\("/opt/aitbc/([^"]+)"\)', 
         r'CRYPTO_DIR = AITBC_HOME / "\1"'),
        (r'env\["PYTHONPATH"\] = "/opt/aitbc:([^"]+)"', 
         lambda m: f'env["PYTHONPATH"] = ":".join([str(REPO_DIR), {m.group(1).replace(":", '", "').replace("/opt/aitbc/", 'str(AITBC_HOME / "')}])'),
    ]
    
    updated_content = content
    for pattern, replacement in patterns:
        if callable(replacement):
            updated_content = re.sub(pattern, replacement, updated_content)
        else:
            updated_content = re.sub(pattern, replacement, updated_content)
    
    if updated_content != content:
        file_path.write_text(updated_content)
        print(f"Updated {file_path}")
        return True
    else:
        print(f"No changes needed for {file_path}")
        return False

def main():
    """Find and update all wrapper files"""
    base_dir = Path("/opt/aitbc")
    
    # Find all wrapper files
    wrapper_files = []
    wrapper_files.extend(base_dir.glob("apps/*/*wrapper.py"))
    wrapper_files.extend(base_dir.glob("scripts/services/*wrapper.py"))
    wrapper_files.extend(base_dir.glob("scripts/monitoring/*wrapper.py"))
    wrapper_files.extend(base_dir.glob("scripts/utils/*wrapper.py"))
    
    print(f"Found {len(wrapper_files)} wrapper files")
    
    updated_count = 0
    for wrapper_file in wrapper_files:
        if update_wrapper_file(wrapper_file):
            updated_count += 1
    
    print(f"\nUpdated {updated_count} wrapper files")

if __name__ == "__main__":
    main()