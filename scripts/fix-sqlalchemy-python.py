#!/usr/bin/env python3

import os
import re

def fix_sqlalchemy_indexes():
    """Fix SQLAlchemy index syntax issues in domain models"""
    
    domain_dir = "/opt/aitbc/apps/coordinator-api/src/app/domain"
    
    for filename in os.listdir(domain_dir):
        if filename.endswith('.py'):
            filepath = os.path.join(domain_dir, filename)
            print(f"Processing {filename}...")
            
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Fix "indexes": [...] pattern
            content = re.sub(r'"indexes": \[', r'# "indexes": [', content)
            content = re.sub(r'            Index\([^)]*\),', r'            # Index(\g<0>)', content)
            content = re.sub(r'        \]', r'#        ]', content)
            
            # Fix tuple format __table_args__ = (Index(...),)
            content = re.sub(r'__table_args__ = \(', r'__table_args__ = {', content)
            content = re.sub(r'        Index\([^)]*\),', r'        # Index(\g<0>)', content)
            content = re.sub(r'    \)', r'    }', content)
            
            # Fix bounty.py specific format
            content = re.sub(r'            \{"name": "[^"]*", "columns": \[[^]]*\]\},', r'            # {"name": "...", "columns": [...]},', content)
            
            with open(filepath, 'w') as f:
                f.write(content)
    
    print("✅ SQLAlchemy index fixes completed!")

if __name__ == "__main__":
    fix_sqlalchemy_indexes()
