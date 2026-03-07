#!/usr/bin/env python3
"""
Fix database persistence by switching to persistent SQLite
"""

import sys
import os
sys.path.insert(0, '/home/oib/windsurf/aitbc/apps/coordinator-api/src')

def fix_database_persistence():
    """Switch from in-memory to persistent SQLite database"""
    print("=== FIXING DATABASE PERSISTENCE ===")
    
    database_file = "/home/oib/windsurf/aitbc/apps/coordinator-api/aitbc_coordinator.db"
    
    # Read current database.py
    db_file = "/home/oib/windsurf/aitbc/apps/coordinator-api/src/app/database.py"
    
    with open(db_file, 'r') as f:
        content = f.read()
    
    # Replace in-memory SQLite with persistent file
    new_content = content.replace(
        '"sqlite:///:memory:"',
        f'"sqlite:///{database_file}"'
    )
    
    # Write back the fixed content
    with open(db_file, 'w') as f:
        f.write(new_content)
    
    print(f"✅ Database switched to persistent file: {database_file}")
    
    # Remove existing database file if it exists
    if os.path.exists(database_file):
        os.remove(database_file)
        print(f"🗑️  Removed old database file")
    
    return True

if __name__ == "__main__":
    if fix_database_persistence():
        print("🎉 Database persistence fix completed!")
    else:
        print("❌ Database persistence fix failed!")
        sys.exit(1)
