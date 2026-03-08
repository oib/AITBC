#!/usr/bin/env python3
"""
Comprehensive Subfolder Scanner
Scans all subfolders in docs/10_plan for completed tasks
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime

def categorize_file_content(file_path):
    """Categorize file based on content and path"""
    path_parts = file_path.parts
    filename = file_path.name.lower()
    
    # Check path-based categorization
    if '01_core_planning' in path_parts:
        return 'core_planning'
    elif '02_implementation' in path_parts:
        return 'implementation'
    elif '03_testing' in path_parts:
        return 'testing'
    elif '04_infrastructure' in path_parts:
        return 'infrastructure'
    elif '05_security' in path_parts:
        return 'security'
    elif '06_cli' in path_parts:
        return 'cli'
    elif '07_backend' in path_parts:
        return 'backend'
    elif '08_marketplace' in path_parts:
        return 'marketplace'
    elif '09_maintenance' in path_parts:
        return 'maintenance'
    elif '10_summaries' in path_parts:
        return 'summaries'
    
    # Check filename-based categorization
    if any(word in filename for word in ['infrastructure', 'port', 'network', 'deployment']):
        return 'infrastructure'
    elif any(word in filename for word in ['cli', 'command', 'interface']):
        return 'cli'
    elif any(word in filename for word in ['api', 'backend', 'service']):
        return 'backend'
    elif any(word in filename for word in ['security', 'auth', 'firewall']):
        return 'security'
    elif any(word in filename for word in ['exchange', 'trading', 'market']):
        return 'exchange'
    elif any(word in filename for word in ['blockchain', 'wallet', 'transaction']):
        return 'blockchain'
    elif any(word in filename for word in ['analytics', 'monitoring', 'ai']):
        return 'analytics'
    elif any(word in filename for word in ['marketplace', 'pool', 'hub']):
        return 'marketplace'
    elif any(word in filename for word in ['maintenance', 'update', 'requirements']):
        return 'maintenance'
    
    return 'general'

def scan_file_for_completion(file_path):
    """Scan a file for completion indicators"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for completion indicators
        completion_patterns = [
            r'✅\s*\*\*COMPLETE\*\*',
            r'✅\s*\*\*IMPLEMENTED\*\*',
            r'✅\s*\*\*OPERATIONAL\*\*',
            r'✅\s*\*\*DEPLOYED\*\*',
            r'✅\s*\*\*WORKING\*\*',
            r'✅\s*\*\*FUNCTIONAL\*\*',
            r'✅\s*\*\*ACHIEVED\*\*',
            r'✅\s*COMPLETE\s*',
            r'✅\s*IMPLEMENTED\s*',
            r'✅\s*OPERATIONAL\s*',
            r'✅\s*DEPLOYED\s*',
            r'✅\s*WORKING\s*',
            r'✅\s*FUNCTIONAL\s*',
            r'✅\s*ACHIEVED\s*',
            r'✅\s*COMPLETE:',
            r'✅\s*IMPLEMENTED:',
            r'✅\s*OPERATIONAL:',
            r'✅\s*DEPLOYED:',
            r'✅\s*WORKING:',
            r'✅\s*FUNCTIONAL:',
            r'✅\s*ACHIEVED:',
            r'✅\s*\*\*COMPLETE\*\*:',
            r'✅\s*\*\*IMPLEMENTED\*\*:',
            r'✅\s*\*\*OPERATIONAL\*\*:',
            r'✅\s*\*\*DEPLOYED\*\*:',
            r'✅\s*\*\*WORKING\*\*:',
            r'✅\s*\*\*FUNCTIONAL\*\*:',
            r'✅\s*\*\*ACHIEVED\*\*:'
        ]
        
        has_completion = any(re.search(pattern, content, re.IGNORECASE) for pattern in completion_patterns)
        
        if has_completion:
            # Count completion markers
            completion_count = sum(len(re.findall(pattern, content, re.IGNORECASE)) for pattern in completion_patterns)
            
            return {
                'file_path': str(file_path),
                'relative_path': str(file_path.relative_to(Path('/opt/aitbc/docs/10_plan'))),
                'category': categorize_file_content(file_path),
                'has_completion': True,
                'completion_count': completion_count,
                'file_size': file_path.stat().st_size,
                'last_modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            }
        
        return {
            'file_path': str(file_path),
            'relative_path': str(file_path.relative_to(Path('/opt/aitbc/docs/10_plan'))),
            'category': categorize_file_content(file_path),
            'has_completion': False,
            'completion_count': 0,
            'file_size': file_path.stat().st_size,
            'last_modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
        }
    
    except Exception as e:
        return {
            'file_path': str(file_path),
            'relative_path': str(file_path.relative_to(Path('/opt/aitbc/docs/10_plan'))),
            'category': 'error',
            'has_completion': False,
            'completion_count': 0,
            'error': str(e)
        }

def scan_all_subfolders(planning_dir):
    """Scan all subfolders for completed tasks"""
    planning_path = Path(planning_dir)
    results = []
    
    # Find all markdown files in all subdirectories
    for md_file in planning_path.rglob('*.md'):
        if md_file.is_file():
            result = scan_file_for_completion(md_file)
            results.append(result)
    
    # Categorize results
    completed_files = [r for r in results if r.get('has_completion', False)]
    category_summary = {}
    
    for result in completed_files:
        category = result['category']
        if category not in category_summary:
            category_summary[category] = {
                'files': [],
                'total_completion_count': 0,
                'total_files': 0
            }
        
        category_summary[category]['files'].append(result)
        category_summary[category]['total_completion_count'] += result['completion_count']
        category_summary[category]['total_files'] += 1
    
    return {
        'total_files_scanned': len(results),
        'files_with_completion': len(completed_files),
        'files_without_completion': len(results) - len(completed_files),
        'total_completion_markers': sum(r.get('completion_count', 0) for r in completed_files),
        'category_summary': category_summary,
        'all_results': results
    }

if __name__ == "__main__":
    planning_dir = '/opt/aitbc/docs/10_plan'
    output_file = 'comprehensive_scan_results.json'
    
    scan_results = scan_all_subfolders(planning_dir)
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(scan_results, f, indent=2)
    
    # Print summary
    print(f"Comprehensive scan complete:")
    print(f"  Total files scanned: {scan_results['total_files_scanned']}")
    print(f"  Files with completion: {scan_results['files_with_completion']}")
    print(f"  Files without completion: {scan_results['files_without_completion']}")
    print(f"  Total completion markers: {scan_results['total_completion_markers']}")
    print("")
    print("Files with completion by category:")
    for category, summary in scan_results['category_summary'].items():
        print(f"  {category}: {summary['total_files']} files, {summary['total_completion_count']} markers")
