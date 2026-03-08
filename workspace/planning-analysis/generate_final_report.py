#!/usr/bin/env python3
"""
Final Report Generator
Generates comprehensive final report
"""

import json
from datetime import datetime

def generate_final_report():
    """Generate comprehensive final report"""
    
    # Load all data files
    with open('comprehensive_scan_results.json', 'r') as f:
        scan_results = json.load(f)
    
    with open('content_move_results.json', 'r') as f:
        move_results = json.load(f)
    
    # Generate report
    report = {
        'timestamp': datetime.now().isoformat(),
        'operation': 'comprehensive_planning_cleanup',
        'status': 'completed',
        'summary': {
            'total_files_scanned': scan_results['total_files_scanned'],
            'files_with_completion': scan_results['files_with_completion'],
            'files_without_completion': scan_results['files_without_completion'],
            'total_completion_markers': scan_results['total_completion_markers'],
            'files_moved': move_results['total_files_moved'],
            'categories_processed': len(move_results['category_summary'])
        },
        'scan_results': scan_results,
        'move_results': move_results
    }
    
    # Save report
    with open('comprehensive_final_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print summary
    summary = report['summary']
    print(f"Final Report Generated:")
    print(f"  Operation: {report['operation']}")
    print(f"  Status: {report['status']}")
    print(f"  Total files scanned: {summary['total_files_scanned']}")
    print(f"  Files with completion: {summary['files_with_completion']}")
    print(f"  Files moved: {summary['files_moved']}")
    print(f"  Total completion markers: {summary['total_completion_markers']}")
    print(f"  Categories processed: {summary['categories_processed']}")
    print("")
    print("Files moved by category:")
    for category, summary in move_results['category_summary'].items():
        print(f"  {category}: {summary['files_moved']} files")

if __name__ == "__main__":
    generate_final_report()
