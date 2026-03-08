#!/usr/bin/env python3
"""
Enhanced Planning Document Cleanup
Removes archived completed tasks from planning documents
"""

import json
import re
from pathlib import Path

def cleanup_document(file_path, archived_tasks, dry_run=True):
    """Clean up a planning document by removing archived tasks"""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Sort tasks by line number in reverse order (to avoid index shifting)
        tasks_to_remove = sorted(archived_tasks, key=lambda x: x['line_number'], reverse=True)
        
        removed_lines = []
        for task in tasks_to_remove:
            line_num = task['line_number'] - 1  # Convert to 0-based index
            if 0 <= line_num < len(lines):
                removed_lines.append(lines[line_num])
                lines.pop(line_num)
        
        if not dry_run:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        
        return {
            'file_path': file_path,
            'lines_removed': len(removed_lines),
            'removed_content': removed_lines
        }
    
    except Exception as e:
        return {
            'file_path': file_path,
            'error': str(e),
            'lines_removed': 0
        }

def perform_cleanup(archive_file, dry_run=True):
    """Perform cleanup of all archived tasks"""
    
    with open(archive_file, 'r') as f:
        archived_data = json.load(f)
    
    cleanup_results = []
    
    for archive_item in archived_data:
        result = cleanup_document(
            archive_item['original_file'],
            archive_item['tasks'],
            dry_run
        )
        cleanup_results.append(result)
    
    return cleanup_results

if __name__ == "__main__":
    import sys
    
    archive_file = sys.argv[1] if len(sys.argv) > 1 else 'archive_results.json'
    dry_run = sys.argv[2] if len(sys.argv) > 2 else 'true'
    
    dry_run = dry_run.lower() == 'true'
    
    results = perform_cleanup(archive_file, dry_run)
    
    # Save results
    with open('cleanup_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    total_removed = sum(r.get('lines_removed', 0) for r in results)
    mode = "DRY RUN" if dry_run else "ACTUAL"
    
    print(f"Cleanup {mode} complete:")
    print(f"  Files processed: {len(results)}")
    print(f"  Total lines removed: {total_removed}")
    
    for result in results:
        if result.get('lines_removed', 0) > 0:
            print(f"  {result['file_path']}: {result['lines_removed']} lines")
