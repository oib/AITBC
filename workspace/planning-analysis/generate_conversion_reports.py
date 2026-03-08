#!/usr/bin/env python3
"""
Conversion Report Generator
Generates comprehensive reports for the documentation conversion
"""

import json
from datetime import datetime

def generate_conversion_report():
    """Generate comprehensive conversion report"""
    
    # Load all data files
    try:
        with open('completed_files_scan.json', 'r') as f:
            scan_results = json.load(f)
    except:
        scan_results = {'total_files_scanned': 0}
    
    try:
        with open('content_analysis_results.json', 'r') as f:
            analysis_results = json.load(f)
    except:
        analysis_results = {'total_files_analyzed': 0, 'action_summary': {}}
    
    try:
        with open('documentation_conversion_final.json', 'r') as f:
            conversion_results = json.load(f)
    except:
        conversion_results = []
    
    # Generate report
    report = {
        'timestamp': datetime.now().isoformat(),
        'operation': 'documentation_conversion_from_completed_files',
        'status': 'completed',
        'summary': {
            'total_files_scanned': scan_results.get('total_files_scanned', 0),
            'total_files_analyzed': analysis_results.get('total_files_analyzed', 0),
            'total_files_converted': len(conversion_results),
            'conversion_actions': analysis_results.get('action_summary', {}),
            'target_categories': {}
        }
    }
    
    # Count target categories
    for result in conversion_results:
        category = result['target_category']
        if category not in report['summary']['target_categories']:
            report['summary']['target_categories'][category] = 0
        report['summary']['target_categories'][category] += 1
    
    # Include detailed data
    report['scan_results'] = scan_results
    report['analysis_results'] = analysis_results
    report['conversion_results'] = conversion_results
    
    # Save report
    with open('documentation_conversion_final_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print summary
    summary = report['summary']
    print(f"Documentation Conversion - Final Report:")
    print(f"  Operation: {report['operation']}")
    print(f"  Status: {report['status']}")
    print(f"  Files scanned: {summary['total_files_scanned']}")
    print(f"  Files analyzed: {summary['total_files_analyzed']}")
    print(f"  Files converted: {summary['total_files_converted']}")
    print("")
    print("Conversion actions:")
    for action, count in summary['conversion_actions'].items():
        print(f"  {action}: {count}")
    print("")
    print("Target categories:")
    for category, count in summary['target_categories'].items():
        print(f"  {category}: {count} files")

if __name__ == "__main__":
    generate_conversion_report()
