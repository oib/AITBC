#!/usr/bin/env python3
"""
Enhanced Documentation Verifier
Checks if completed tasks have corresponding documentation
"""

import os
import json
import re
from pathlib import Path

def search_documentation(task_description, docs_dir):
    """Search for task in documentation"""
    docs_path = Path(docs_dir)
    
    # Extract keywords from task description
    keywords = re.findall(r'\b\w+\b', task_description.lower())
    keywords = [kw for kw in keywords if len(kw) > 3 and kw not in ['the', 'and', 'for', 'with', 'that', 'this']]
    
    if not keywords:
        return False, []
    
    # Search in documentation files
    matches = []
    for md_file in docs_path.rglob('*.md'):
        if md_file.is_file() and '10_plan' not in str(md_file):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                
                # Check for keyword matches
                keyword_matches = sum(1 for keyword in keywords if keyword in content)
                if keyword_matches >= len(keywords) * 0.5:  # At least 50% of keywords
                    matches.append(str(md_file))
            except:
                continue
    
    return len(matches) > 0, matches

def verify_documentation_status(analysis_file, docs_dir, output_file):
    """Verify documentation status for completed tasks"""
    
    with open(analysis_file, 'r') as f:
        analysis_results = json.load(f)
    
    verification_results = []
    
    for result in analysis_results:
        if 'error' in result:
            continue
        
        file_tasks = []
        for task in result.get('completed_tasks', []):
            documented, matches = search_documentation(task['task_description'], docs_dir)
            
            task_verification = {
                **task,
                'documented': documented,
                'documentation_matches': matches,
                'needs_documentation': not documented
            }
            
            file_tasks.append(task_verification)
        
        verification_results.append({
            'file_path': result['file_path'],
            'completed_tasks': file_tasks,
            'documented_count': sum(1 for t in file_tasks if t['documented']),
            'undocumented_count': sum(1 for t in file_tasks if not t['documented']),
            'needs_documentation_count': sum(1 for t in file_tasks if not t['documented'])
        })
    
    # Save verification results
    with open(output_file, 'w') as f:
        json.dump(verification_results, f, indent=2)
    
    # Print summary
    total_completed = sum(len(r['completed_tasks']) for r in verification_results)
    total_documented = sum(r['documented_count'] for r in verification_results)
    total_undocumented = sum(r['undocumented_count'] for r in verification_results)
    
    print(f"Documentation verification complete:")
    print(f"  Total completed tasks: {total_completed}")
    print(f"  Documented tasks: {total_documented}")
    print(f"  Undocumented tasks: {total_undocumented}")
    print(f"  Documentation coverage: {(total_documented/total_completed*100):.1f}%")

if __name__ == "__main__":
    import sys
    
    analysis_file = sys.argv[1] if len(sys.argv) > 1 else 'analysis_results.json'
    docs_dir = sys.argv[2] if len(sys.argv) > 2 else '/opt/aitbc/docs'
    output_file = sys.argv[3] if len(sys.argv) > 3 else 'documentation_status.json'
    
    verify_documentation_status(analysis_file, docs_dir, output_file)
