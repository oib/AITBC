#!/usr/bin/env python3
"""
Completed Files Scanner
Scans all files in docs/completed/ for analysis
"""

import os
import json
from pathlib import Path
from datetime import datetime

def scan_completed_files(completed_dir):
    """Scan all files in docs/completed/"""
    completed_path = Path(completed_dir)
    
    if not completed_path.exists():
        return {'error': 'Completed directory not found'}
    
    files = []
    
    # Find all markdown files
    for md_file in completed_path.rglob('*.md'):
        if md_file.is_file() and md_file.name != 'README.md':
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Get relative path from completed directory
                relative_path = md_file.relative_to(completed_path)
                category = relative_path.parts[0] if len(relative_path.parts) > 1 else 'general'
                
                files.append({
                    'file_path': str(md_file),
                    'relative_path': str(relative_path),
                    'category': category,
                    'filename': md_file.name,
                    'file_size': md_file.stat().st_size,
                    'content_length': len(content),
                    'last_modified': datetime.fromtimestamp(md_file.stat().st_mtime).isoformat(),
                    'content_preview': content[:300] + '...' if len(content) > 300 else content
                })
            except Exception as e:
                files.append({
                    'file_path': str(md_file),
                    'relative_path': str(md_file.relative_to(completed_path)),
                    'category': 'error',
                    'filename': md_file.name,
                    'error': str(e)
                })
    
    # Categorize files
    category_summary = {}
    for file_info in files:
        category = file_info['category']
        if category not in category_summary:
            category_summary[category] = {
                'files': [],
                'total_files': 0,
                'total_size': 0
            }
        
        category_summary[category]['files'].append(file_info)
        category_summary[category]['total_files'] += 1
        category_summary[category]['total_size'] += file_info.get('file_size', 0)
    
    return {
        'total_files_scanned': len(files),
        'categories_found': len(category_summary),
        'category_summary': category_summary,
        'all_files': files
    }

if __name__ == "__main__":
    completed_dir = '/opt/aitbc/docs/completed'
    output_file = 'completed_files_scan.json'
    
    scan_results = scan_completed_files(completed_dir)
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(scan_results, f, indent=2)
    
    # Print summary
    print(f"Completed files scan complete:")
    print(f"  Total files scanned: {scan_results['total_files_scanned']}")
    print(f"  Categories found: {scan_results['categories_found']}")
    print("")
    print("Files by category:")
    for category, summary in scan_results['category_summary'].items():
        print(f"  {category}: {summary['total_files']} files, {summary['total_size']} bytes")
