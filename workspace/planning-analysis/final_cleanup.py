#!/usr/bin/env python3
"""
Final Cleanup Script
Handles remaining completed task patterns
"""

import re
from pathlib import Path

def final_cleanup(file_path):
    """Final cleanup of remaining completed task patterns"""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find patterns with ✅ at the end of lines
        end_of_line_patterns = [
            r'^(.+)\s*✅\s*COMPLETE\s*$',
            r'^(.+)\s*✅\s*IMPLEMENTED\s*$',
            r'^(.+)\s*✅\s*OPERATIONAL\s*$',
            r'^(.+)\s*✅\s*DEPLOYED\s*$',
            r'^(.+)\s*✅\s*WORKING\s*$',
            r'^(.+)\s*✅\s*FUNCTIONAL\s*$'
        ]
        
        lines = content.split('\n')
        lines_to_remove = []
        
        for i, line in enumerate(lines):
            for pattern in end_of_line_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    lines_to_remove.append(i)
                    break
        
        # Remove lines (in reverse order to maintain indices)
        for line_num in sorted(lines_to_remove, reverse=True):
            del lines[line_num]
        
        # Write back
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return len(lines_to_remove)
    
    except Exception as e:
        print(f"Error: {e}")
        return 0

if __name__ == "__main__":
    file_path = "/opt/aitbc/docs/10_plan/01_core_planning/00_nextMileston.md"
    removed = final_cleanup(file_path)
    print(f"Final cleanup: Removed {removed} additional completed task lines")
    
    # Verify
    with open(file_path, 'r') as f:
        content = f.read()
    
    remaining = len(re.findall(r'', content))
    print(f"Remaining completed task markers: {remaining}")
