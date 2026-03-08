#!/usr/bin/env python3
"""
Content Categorizer and Mover
Categorizes completed content and moves to appropriate folders
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

def move_completed_content(scan_file, docs_dir, archive_dir):
    """Move completed content to organized folders"""
    
    with open(scan_file, 'r') as f:
        scan_results = json.load(f)
    
    category_mapping = {
        'core_planning': 'core_planning',
        'implementation': 'implementation',
        'testing': 'testing',
        'infrastructure': 'infrastructure',
        'security': 'security',
        'cli': 'cli',
        'backend': 'backend',
        'exchange': 'exchange',
        'blockchain': 'blockchain',
        'analytics': 'analytics',
        'marketplace': 'marketplace',
        'maintenance': 'maintenance',
        'summaries': 'summaries',
        'general': 'general'
    }
    
    moved_files = []
    category_summary = {}
    
    for result in scan_results['all_results']:
        if not result.get('has_completion', False):
            continue
        
        source_path = Path(result['file_path'])
        category = category_mapping.get(result['category'], 'general')
        
        # Create destination paths
        completed_dir = Path(docs_dir) / 'completed' / category
        archive_dir = Path(archive_dir) / 'by_category' / category
        
        # Ensure directories exist
        completed_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Destination file paths
        completed_dest = completed_dir / source_path.name
        archive_dest = archive_dir / source_path.name
        
        try:
            # Move to completed folder (remove from planning)
            shutil.move(source_path, completed_dest)
            
            # Create archive entry
            archive_content = f"""# Archived: {source_path.name}

**Source**: {result['relative_path']}
**Category**: {category}
**Archive Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Completion Markers**: {result['completion_count']}
**File Size**: {result['file_size']} bytes

## Archive Reason
This file contains completed tasks and has been moved to the completed documentation folder.

## Original Content
The original file content has been preserved in the completed folder and can be referenced there.

---
*Archived by AITBC Comprehensive Planning Cleanup*
"""
            
            with open(archive_dest, 'w') as f:
                f.write(archive_content)
            
            moved_files.append({
                'source': str(source_path),
                'completed_dest': str(completed_dest),
                'archive_dest': str(archive_dest),
                'category': category,
                'completion_count': result['completion_count']
            })
            
            if category not in category_summary:
                category_summary[category] = {
                    'files_moved': 0,
                    'total_completion_markers': 0
                }
            
            category_summary[category]['files_moved'] += 1
            category_summary[category]['total_completion_markers'] += result['completion_count']
            
            print(f"Moved {source_path.name} to completed/{category}/")
            
        except Exception as e:
            print(f"Error moving {source_path}: {e}")
    
    return moved_files, category_summary

if __name__ == "__main__":
    scan_file = 'comprehensive_scan_results.json'
    docs_dir = '/opt/aitbc/docs'
    archive_dir = '/opt/aitbc/docs/archive'
    
    moved_files, category_summary = move_completed_content(scan_file, docs_dir, archive_dir)
    
    # Save results
    with open('content_move_results.json', 'w') as f:
        json.dump({
            'moved_files': moved_files,
            'category_summary': category_summary,
            'total_files_moved': len(moved_files)
        }, f, indent=2)
    
    print(f"Content move complete:")
    print(f"  Total files moved: {len(moved_files)}")
    print("")
    print("Files moved by category:")
    for category, summary in category_summary.items():
        print(f"  {category}: {summary['files_moved']} files, {summary['total_completion_markers']} markers")
