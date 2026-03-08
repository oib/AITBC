#!/usr/bin/env python3
"""
Documentation Status Checker
Checks if completed tasks are documented in docs/ (excluding docs/10_plan)
"""

import json
import os
import re
from pathlib import Path

def search_main_documentation(task_description, docs_dir):
    """Search for task in main documentation (excluding docs/10_plan)"""
    docs_path = Path(docs_dir)
    
    # Extract keywords from task description
    keywords = re.findall(r'\b\w+\b', task_description.lower())
    keywords = [kw for kw in keywords if len(kw) > 3 and kw not in ['the', 'and', 'for', 'with', 'that', 'this', 'from', 'were', 'been', 'have']]
    
    if not keywords:
        return False, []
    
    # Search in documentation files (excluding docs/10_plan)
    matches = []
    for md_file in docs_path.rglob('*.md'):
        if md_file.is_file() and '10_plan' not in str(md_file):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                
                # Check for keyword matches
                keyword_matches = sum(1 for keyword in keywords if keyword in content)
                if keyword_matches >= len(keywords) * 0.4:  # At least 40% of keywords
                    matches.append(str(md_file))
            except:
                continue
    
    return len(matches) > 0, matches

def check_documentation_status(analysis_file, docs_dir, output_file):
    """Check documentation status for completed tasks"""
    
    with open(analysis_file, 'r') as f:
        analysis_results = json.load(f)
    
    documentation_results = []
    
    for result in analysis_results['all_results']:
        if not result.get('has_completion', False) or 'error' in result:
            continue
        
        file_tasks = []
        for task in result.get('completed_tasks', []):
            documented, matches = search_main_documentation(task['task_description'], docs_dir)
            
            task_doc_status = {
                **task,
                'documented': documented,
                'documentation_matches': matches,
                'needs_documentation': not documented,
                'file_category': result['category'],
                'source_file': result['file_path']
            }
            
            file_tasks.append(task_doc_status)
        
        documentation_results.append({
            'file_path': result['file_path'],
            'category': result['category'],
            'completed_tasks': file_tasks,
            'documented_count': sum(1 for t in file_tasks if t['documented']),
            'undocumented_count': sum(1 for t in file_tasks if not t['documented']),
            'needs_documentation_count': sum(1 for t in file_tasks if not t['documented'])
        })
    
    # Save documentation status results
    with open(output_file, 'w') as f:
        json.dump(documentation_results, f, indent=2)
    
    # Print summary
    total_completed = sum(len(r['completed_tasks']) for r in documentation_results)
    total_documented = sum(r['documented_count'] for r in documentation_results)
    total_undocumented = sum(r['undocumented_count'] for r in documentation_results)
    
    print(f"Documentation status check complete:")
    print(f"  Total completed tasks: {total_completed}")
    print(f"  Documented tasks: {total_documented}")
    print(f"  Undocumented tasks: {total_undocumented}")
    print(f"  Documentation coverage: {(total_documented/total_completed*100):.1f}%")
    print("")
    print("Undocumented tasks by category:")
    category_undocumented = {}
    for result in documentation_results:
        category = result['category']
        if category not in category_undocumented:
            category_undocumented[category] = 0
        category_undocumented[category] += result['undocumented_count']
    
    for category, count in category_undocumented.items():
        if count > 0:
            print(f"  {category}: {count} undocumented tasks")

if __name__ == "__main__":
    analysis_file = 'specific_files_analysis.json'
    docs_dir = '/opt/aitbc/docs'
    output_file = 'documentation_status_check.json'
    
    check_documentation_status(analysis_file, docs_dir, output_file)
