#!/bin/bash

# ============================================================================
# Fix SQLAlchemy Index Issues - Simple Approach
# ============================================================================

echo "🔧 Fixing SQLAlchemy index issues..."

# Simple approach: comment out all indexes in __table_args__
for file in /opt/aitbc/apps/coordinator-api/src/app/domain/*.py; do
    echo "Processing $file..."
    
    # Comment out indexes blocks
    sed -i 's/"indexes": \[/# "indexes": [/g' "$file"
    sed -i 's/            Index(/#            Index(/g' "$file"
    sed -i 's/        \]/#        \]/g' "$file"
    
    # Fix tuple format to dict format
    sed -i 's/__table_args__ = (/__table_args__ = {/g' "$file"
    sed -i 's/        Index(/#        Index(/g' "$file"
    sed -i 's/    )/    }/g' "$file"
    
    # Fix bounty.py specific format
    sed -i 's/            {"name": "/#            {"name": "/g' "$file"
    sed -i 's/, "columns": \[/, "columns": [\/g' "$file"
done

echo "✅ SQLAlchemy index fixes completed!"
