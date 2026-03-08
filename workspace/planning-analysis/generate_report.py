#!/usr/bin/env python3
"""
Report Generator
Generates comprehensive cleanup reports
"""

import json
from datetime import datetime

def generate_cleanup_report():
    """Generate comprehensive cleanup report"""
    
    # Load all data files
    with open('analysis_results.json', 'r') as f:
        analysis_results = json.load(f)
    
    with open('documentation_status.json', 'r') as f:
        documentation_status = json.load(f)
    
    with open('cleanup_candidates.json', 'r') as f:
        cleanup_candidates = json.load(f)
    
    with open('cleanup_results.json', 'r') as f:
        cleanup_results = json.load(f)
    
    # Generate report
    report = {
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_planning_files': len(analysis_results),
            'total_completed_tasks': sum(r.get('completed_task_count', 0) for r in analysis_results),
            'total_documented_tasks': sum(r.get('documented_count', 0) for r in documentation_status),
            'total_undocumented_tasks': sum(r.get('undocumented_count', 0) for r in documentation_status),
            'total_cleanup_candidates': cleanup_candidates['summary']['total_cleanup_candidates'],
            'total_lines_removed': sum(r.get('lines_removed', 0) for r in cleanup_results)
        },
        'analysis_results': analysis_results,
        'documentation_status': documentation_status,
        'cleanup_candidates': cleanup_candidates,
        'cleanup_results': cleanup_results
    }
    
    # Save report
    with open('cleanup_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print summary
    summary = report['summary']
    print(f"Cleanup Report Generated:")
    print(f"  Planning files analyzed: {summary['total_planning_files']}")
    print(f"  Completed tasks found: {summary['total_completed_tasks']}")
    print(f"  Documented tasks: {summary['total_documented_tasks']}")
    print(f"  Undocumented tasks: {summary['total_undocumented_tasks']}")
    print(f"  Cleanup candidates: {summary['total_cleanup_candidates']}")
    print(f"  Lines removed: {summary['total_lines_removed']}")

if __name__ == "__main__":
    generate_cleanup_report()
