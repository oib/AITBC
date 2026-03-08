#!/usr/bin/env python3
"""
Enhanced Planning Document Analyzer
Analyzes planning documents to identify completed tasks
"""

import os
import re
import json
from pathlib import Path

def analyze_planning_document(file_path):
    """Analyze a single planning document"""
    tasks = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find completed task patterns
        completion_patterns = [
            r'✅\s*\*\*COMPLETE\*\*:?\s*(.+)',
            r'✅\s*\*\*IMPLEMENTED\*\*:?\s*(.+)',
            r'✅\s*\*\*OPERATIONAL\*\*:?\s*(.+)',
            r'✅\s*\*\*DEPLOYED\*\*:?\s*(.+)',
            r'✅\s*\*\*WORKING\*\*:?\s*(.+)',
            r'✅\s*\*\*FUNCTIONAL\*\*:?\s*(.+)',
            r'✅\s*\*\*ACHIEVED\*\*:?\s*(.+)',
            r'✅\s*COMPLETE\s*:?\s*(.+)',
            r'✅\s*IMPLEMENTED\s*:?\s*(.+)',
            r'✅\s*OPERATIONAL\s*:?\s*(.+)',
            r'✅\s*DEPLOYED\s*:?\s*(.+)',
            r'✅\s*WORKING\s*:?\s*(.+)',
            r'✅\s*FUNCTIONAL\s*:?\s*(.+)',
            r'✅\s*ACHIEVED\s*:?\s*(.+)',
            r'✅\s*COMPLETE:\s*(.+)',
            r'✅\s*IMPLEMENTED:\s*(.+)',
            r'✅\s*OPERATIONAL:\s*(.+)',
            r'✅\s*DEPLOYED:\s*(.+)',
            r'✅\s*WORKING:\s*(.+)',
            r'✅\s*FUNCTIONAL:\s*(.+)',
            r'✅\s*ACHIEVED:\s*(.+)',
            r'✅\s*\*\*COMPLETE\*\*:\s*(.+)',
            r'✅\s*\*\*IMPLEMENTED\*\*:\s*(.+)',
            r'✅\s*\*\*OPERATIONAL\*\*:\s*(.+)',
            r'✅\s*\*\*DEPLOYED\*\*:\s*(.+)',
            r'✅\s*\*\*WORKING\*\*:\s*(.+)',
            r'✅\s*\*\*FUNCTIONAL\*\*:\s*(.+)',
            r'✅\s*\*\*ACHIEVED\*\*:\s*(.+)'
        ]
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            for pattern in completion_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    task_description = match.group(1).strip()
                    tasks.append({
                        'line_number': i + 1,
                        'line_content': line.strip(),
                        'task_description': task_description,
                        'status': 'completed',
                        'file_path': str(file_path),
                        'pattern_used': pattern
                    })
        
        return {
            'file_path': str(file_path),
            'total_lines': len(lines),
            'completed_tasks': tasks,
            'completed_task_count': len(tasks)
        }
    
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return {
            'file_path': str(file_path),
            'error': str(e),
            'completed_tasks': [],
            'completed_task_count': 0
        }

def analyze_all_planning_documents(planning_dir):
    """Analyze all planning documents"""
    results = []
    
    planning_path = Path(planning_dir)
    
    # Find all markdown files
    for md_file in planning_path.rglob('*.md'):
        if md_file.is_file():
            result = analyze_planning_document(md_file)
            results.append(result)
    
    return results

if __name__ == "__main__":
    import sys
    
    planning_dir = sys.argv[1] if len(sys.argv) > 1 else '/opt/aitbc/docs/10_plan'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'analysis_results.json'
    
    results = analyze_all_planning_documents(planning_dir)
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    total_completed = sum(r.get('completed_task_count', 0) for r in results)
    print(f"Analyzed {len(results)} planning documents")
    print(f"Found {total_completed} completed tasks")
    
    for result in results:
        if result.get('completed_task_count', 0) > 0:
            print(f"  {result['file_path']}: {result['completed_task_count']} completed tasks")
