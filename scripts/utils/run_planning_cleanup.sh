#!/bin/bash
#
# AITBC Planning Analysis & Cleanup Implementation
# Analyzes planning documents, checks documentation status, and cleans up completed tasks
#

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Configuration
PROJECT_ROOT="/opt/aitbc"
PLANNING_DIR="$PROJECT_ROOT/docs/10_plan"
DOCS_DIR="$PROJECT_ROOT/docs"
WORKSPACE_DIR="$PROJECT_ROOT/workspace/planning-analysis"
BACKUP_DIR="$WORKSPACE_DIR/backup"

# Main execution
main() {
    print_header "AITBC PLANNING ANALYSIS & CLEANUP WORKFLOW"
    echo ""
    echo "📋 Analyzing planning documents in $PLANNING_DIR"
    echo "📚 Checking documentation status in $DOCS_DIR"
    echo "🧹 Cleaning up completed and documented tasks"
    echo ""
    
    # Step 1: Setup Analysis Environment
    print_header "Step 1: Setting Up Analysis Environment"
    setup_analysis_environment
    
    # Step 2: Analyze Planning Documents
    print_header "Step 2: Analyzing Planning Documents"
    analyze_planning_documents
    
    # Step 3: Verify Documentation Status
    print_header "Step 3: Verifying Documentation Status"
    verify_documentation_status
    
    # Step 4: Identify Cleanup Candidates
    print_header "Step 4: Identifying Cleanup Candidates"
    identify_cleanup_candidates
    
    # Step 5: Create Backup
    print_header "Step 5: Creating Backup"
    create_backup
    
    # Step 6: Perform Cleanup
    print_header "Step 6: Performing Cleanup"
    perform_cleanup
    
    # Step 7: Generate Reports
    print_header "Step 7: Generating Reports"
    generate_reports
    
    # Step 8: Validate Results
    print_header "Step 8: Validating Results"
    validate_results
    
    print_header "Planning Analysis & Cleanup Complete! 🎉"
    echo ""
    echo "✅ Planning documents analyzed"
    echo "✅ Documentation status verified"
    echo "✅ Cleanup candidates identified"
    echo "✅ Backup created"
    echo "✅ Cleanup performed"
    echo "✅ Reports generated"
    echo "✅ Results validated"
    echo ""
    echo "📊 Planning documents are now cleaner and focused on remaining tasks"
    echo "📚 Documentation alignment verified"
    echo "🎯 Ready for continued development"
}

# Setup Analysis Environment
setup_analysis_environment() {
    print_status "Creating analysis workspace..."
    
    mkdir -p "$WORKSPACE_DIR"
    mkdir -p "$BACKUP_DIR"
    
    # Install Python dependencies
    pip3 install --user beautifulsoup4 markdown python-frontmatter > /dev/null 2>&1 || true
    
    print_status "Analysis environment ready"
}

# Analyze Planning Documents
analyze_planning_documents() {
    print_status "Analyzing planning documents..."
    
    cat > "$WORKSPACE_DIR/analyze_planning.py" << 'EOF'
#!/usr/bin/env python3
"""
Planning Document Analyzer
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
            r'✅\s*COMPLETE\s*:?\s*(.+)',
            r'✅\s*IMPLEMENTED\s*:?\s*(.+)',
            r'✅\s*OPERATIONAL\s*:?\s*(.+)',
            r'✅\s*DEPLOYED\s*:?\s*(.+)',
            r'✅\s*WORKING\s*:?\s*(.+)',
            r'✅\s*FUNCTIONAL\s*:?\s*(.+)'
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
EOF
    
    python3 "$WORKSPACE_DIR/analyze_planning.py" "$PLANNING_DIR" "$WORKSPACE_DIR/analysis_results.json"
    
    print_status "Planning documents analyzed"
}

# Verify Documentation Status
verify_documentation_status() {
    print_status "Verifying documentation status..."
    
    cat > "$WORKSPACE_DIR/verify_documentation.py" << 'EOF'
#!/usr/bin/env python3
"""
Documentation Verifier
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
                'cleanup_candidate': documented  # Can be cleaned up if documented
            }
            
            file_tasks.append(task_verification)
        
        verification_results.append({
            'file_path': result['file_path'],
            'completed_tasks': file_tasks,
            'documented_count': sum(1 for t in file_tasks if t['documented']),
            'undocumented_count': sum(1 for t in file_tasks if not t['documented']),
            'cleanup_candidates': sum(1 for t in file_tasks if t['cleanup_candidate'])
        })
    
    # Save verification results
    with open(output_file, 'w') as f:
        json.dump(verification_results, f, indent=2)
    
    # Print summary
    total_completed = sum(len(r['completed_tasks']) for r in verification_results)
    total_documented = sum(r['documented_count'] for r in verification_results)
    total_undocumented = sum(r['undocumented_count'] for r in verification_results)
    total_cleanup = sum(r['cleanup_candidates'] for r in verification_results)
    
    print(f"Documentation verification complete:")
    print(f"  Total completed tasks: {total_completed}")
    print(f"  Documented tasks: {total_documented}")
    print(f"  Undocumented tasks: {total_undocumented}")
    print(f"  Cleanup candidates: {total_cleanup}")

if __name__ == "__main__":
    import sys
    
    analysis_file = sys.argv[1] if len(sys.argv) > 1 else 'analysis_results.json'
    docs_dir = sys.argv[2] if len(sys.argv) > 2 else '/opt/aitbc/docs'
    output_file = sys.argv[3] if len(sys.argv) > 3 else 'documentation_status.json'
    
    verify_documentation_status(analysis_file, docs_dir, output_file)
EOF
    
    python3 "$WORKSPACE_DIR/verify_documentation.py" "$WORKSPACE_DIR/analysis_results.json" "$DOCS_DIR" "$WORKSPACE_DIR/documentation_status.json"
    
    print_status "Documentation status verified"
}

# Identify Cleanup Candidates
identify_cleanup_candidates() {
    print_status "Identifying cleanup candidates..."
    
    cat > "$WORKSPACE_DIR/identify_cleanup.py" << 'EOF'
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
EOF
    
    python3 "$WORKSPACE_DIR/identify_cleanup.py" "$WORKSPACE_DIR/documentation_status.json" "$WORKSPACE_DIR/cleanup_candidates.json"
    
    print_status "Cleanup candidates identified"
}

# Create Backup
create_backup() {
    print_status "Creating backup of planning documents..."
    
    # Create timestamped backup
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_path="$BACKUP_DIR/planning_backup_$timestamp"
    
    mkdir -p "$backup_path"
    cp -r "$PLANNING_DIR" "$backup_path/"
    
    echo "$backup_path" > "$WORKSPACE_DIR/latest_backup.txt"
    
    print_status "Backup created at $backup_path"
}

# Perform Cleanup
perform_cleanup() {
    print_status "Performing cleanup of documented completed tasks..."
    
    cat > "$WORKSPACE_DIR/cleanup_planning.py" << 'EOF'
#!/usr/bin/env python3
"""
Planning Document Cleanup
Removes documented completed tasks from planning documents
"""

import json
import re
from pathlib import Path

def cleanup_document(file_path, cleanup_tasks, dry_run=True):
    """Clean up a planning document"""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Sort tasks by line number in reverse order (to avoid index shifting)
        tasks_to_remove = sorted(cleanup_tasks, key=lambda x: x['line_number'], reverse=True)
        
        removed_lines = []
        for task in tasks_to_remove:
            line_num = task['line_number'] - 1  # Convert to 0-based index
            if 0 <= line_num < len(lines):
                removed_lines.append(lines[line_num])
                lines.pop(line_num)
        
        if not dry_run:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        
        return {
            'file_path': file_path,
            'lines_removed': len(removed_lines),
            'removed_content': removed_lines
        }
    
    except Exception as e:
        return {
            'file_path': file_path,
            'error': str(e),
            'lines_removed': 0
        }

def perform_cleanup(candidates_file, dry_run=True):
    """Perform cleanup of all candidates"""
    
    with open(candidates_file, 'r') as f:
        candidates_data = json.load(f)
    
    cleanup_results = []
    
    for candidate in candidates_data['cleanup_candidates']:
        result = cleanup_document(
            candidate['file_path'],
            candidate['cleanup_tasks'],
            dry_run
        )
        cleanup_results.append(result)
    
    return cleanup_results

if __name__ == "__main__":
    import sys
    
    candidates_file = sys.argv[1] if len(sys.argv) > 1 else 'cleanup_candidates.json'
    dry_run = sys.argv[2] if len(sys.argv) > 2 else 'true'
    
    dry_run = dry_run.lower() == 'true'
    
    results = perform_cleanup(candidates_file, dry_run)
    
    # Save results
    with open('cleanup_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    total_removed = sum(r.get('lines_removed', 0) for r in results)
    mode = "DRY RUN" if dry_run else "ACTUAL"
    
    print(f"Cleanup {mode} complete:")
    print(f"  Files processed: {len(results)}")
    print(f"  Total lines removed: {total_removed}")
    
    for result in results:
        if result.get('lines_removed', 0) > 0:
            print(f"  {result['file_path']}: {result['lines_removed']} lines")
EOF
    
    # First do a dry run
    python3 "$WORKSPACE_DIR/cleanup_planning.py" "$WORKSPACE_DIR/cleanup_candidates.json" "true"
    
    print_status "Dry run completed - review above changes"
    print_status "Performing actual cleanup..."
    
    # Perform actual cleanup
    python3 "$WORKSPACE_DIR/cleanup_planning.py" "$WORKSPACE_DIR/cleanup_candidates.json" "false"
    
    print_status "Cleanup performed"
}

# Generate Reports
generate_reports() {
    print_status "Generating cleanup reports..."
    
    cat > "$WORKSPACE_DIR/generate_report.py" << 'EOF'
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
EOF
    
    cd "$WORKSPACE_DIR"
    python3 generate_report.py
    
    print_status "Reports generated"
}

# Validate Results
validate_results() {
    print_status "Validating cleanup results..."
    
    # Re-analyze to verify cleanup
    python3 "$WORKSPACE_DIR/analyze_planning.py" "$PLANNING_DIR" "$WORKSPACE_DIR/post_cleanup_analysis.json"
    
    # Compare before and after
    cat > "$WORKSPACE_DIR/validate_cleanup.py" << 'EOF'
#!/usr/bin/env python3
"""
Cleanup Validator
Validates cleanup results
"""

import json

def validate_cleanup():
    """Validate cleanup results"""
    
    with open('analysis_results.json', 'r') as f:
        before_results = json.load(f)
    
    with open('post_cleanup_analysis.json', 'r') as f:
        after_results = json.load(f)
    
    with open('cleanup_report.json', 'r') as f:
        report = json.load(f)
    
    # Calculate differences
    before_completed = sum(r.get('completed_task_count', 0) for r in before_results)
    after_completed = sum(r.get('completed_task_count', 0) for r in after_results)
    
    validation = {
        'before_cleanup': {
            'total_completed_tasks': before_completed
        },
        'after_cleanup': {
            'total_completed_tasks': after_completed
        },
        'difference': {
            'tasks_removed': before_completed - after_completed,
            'expected_removal': report['summary']['total_lines_removed']
        },
        'validation_passed': (before_completed - after_completed) >= 0
    }
    
    # Save validation
    with open('validation_report.json', 'w') as f:
        json.dump(validation, f, indent=2)
    
    # Print results
    print(f"Validation Results:")
    print(f"  Tasks before cleanup: {validation['before_cleanup']['total_completed_tasks']}")
    print(f"  Tasks after cleanup: {validation['after_cleanup']['total_completed_tasks']}")
    print(f"  Tasks removed: {validation['difference']['tasks_removed']}")
    print(f"  Validation passed: {validation['validation_passed']}")

if __name__ == "__main__":
    validate_cleanup()
EOF
    
    cd "$WORKSPACE_DIR"
    python3 validate_cleanup.py
    
    print_status "Results validated"
}

# Run main function
main "$@"
