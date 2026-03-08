#!/usr/bin/env python3
"""
Cleanup Candidate Identifier
Identifies tasks that can be cleaned up (completed and documented)
"""

import json
from pathlib import Path

def identify_cleanup_candidates(verification_file, output_file):
    """Identify cleanup candidates from verification results"""
    
    with open(verification_file, 'r') as f:
        verification_results = json.load(f)
    
    cleanup_candidates = []
    summary = {
        'total_files_processed': len(verification_results),
        'files_with_cleanup_candidates': 0,
        'total_cleanup_candidates': 0,
        'files_affected': []
    }
    
    for result in verification_results:
        file_cleanup_tasks = [task for task in result.get('completed_tasks', []) if task.get('cleanup_candidate', False)]
        
        if file_cleanup_tasks:
            summary['files_with_cleanup_candidates'] += 1
            summary['total_cleanup_candidates'] += len(file_cleanup_tasks)
            summary['files_affected'].append(result['file_path'])
            
            cleanup_candidates.append({
                'file_path': result['file_path'],
                'cleanup_tasks': file_cleanup_tasks,
                'cleanup_count': len(file_cleanup_tasks)
            })
    
    # Save cleanup candidates
    with open(output_file, 'w') as f:
        json.dump({
            'summary': summary,
            'cleanup_candidates': cleanup_candidates
        }, f, indent=2)
    
    # Print summary
    print(f"Cleanup candidate identification complete:")
    print(f"  Files with cleanup candidates: {summary['files_with_cleanup_candidates']}")
    print(f"  Total cleanup candidates: {summary['total_cleanup_candidates']}")
    
    for candidate in cleanup_candidates:
        print(f"  {candidate['file_path']}: {candidate['cleanup_count']} tasks")

if __name__ == "__main__":
    import sys
    
    verification_file = sys.argv[1] if len(sys.argv) > 1 else 'documentation_status.json'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'cleanup_candidates.json'
    
    identify_cleanup_candidates(verification_file, output_file)
