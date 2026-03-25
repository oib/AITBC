#!/bin/bash
#
# AITBC Comprehensive Planning Cleanup - Move ALL Completed Tasks
# Scans entire docs/10_plan subfolder structure, finds all completed tasks,
# and moves them to appropriate organized folders in docs/
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
ARCHIVE_DIR="$PROJECT_ROOT/docs/archive"
WORKSPACE_DIR="$PROJECT_ROOT/workspace/planning-analysis"
BACKUP_DIR="$WORKSPACE_DIR/backup"

# Main execution
main() {
    print_header "AITBC COMPREHENSIVE PLANNING CLEANUP - ALL SUBFOLDERS"
    echo ""
    echo "📋 Scanning entire docs/10_plan subfolder structure"
    echo "📚 Moving ALL completed tasks to appropriate docs/ folders"
    echo "📁 Organizing by category and completion status"
    echo ""
    
    # Step 1: Create organized destination folders
    print_header "Step 1: Creating Organized Destination Folders"
    create_organized_folders
    
    # Step 2: Scan all subfolders for completed tasks
    print_header "Step 2: Scanning All Subfolders for Completed Tasks"
    scan_all_subfolders
    
    # Step 3: Categorize and move completed content
    print_header "Step 3: Categorizing and Moving Completed Content"
    categorize_and_move_content
    
    # Step 4: Create comprehensive archive
    print_header "Step 4: Creating Comprehensive Archive"
    create_comprehensive_archive
    
    # Step 5: Clean up planning documents
    print_header "Step 5: Cleaning Up Planning Documents"
    cleanup_planning_documents
    
    # Step 6: Generate final reports
    print_header "Step 6: Generating Final Reports"
    generate_final_reports
    
    print_header "Comprehensive Planning Cleanup Complete! 🎉"
    echo ""
    echo "✅ All subfolders scanned and processed"
    echo "✅ Completed content categorized and moved"
    echo "✅ Comprehensive archive created"
    echo "✅ Planning documents cleaned"
    echo "✅ Final reports generated"
    echo ""
    echo "📊 docs/10_plan is now clean and focused"
    echo "📚 docs/ has organized completed content"
    echo "📁 Archive system fully operational"
    echo "🎯 Ready for new milestone planning"
}

# Create organized destination folders
create_organized_folders() {
    print_status "Creating organized destination folders in docs/"
    
    # Create main categories
    mkdir -p "$DOCS_DIR/completed/infrastructure"
    mkdir -p "$DOCS_DIR/completed/cli"
    mkdir -p "$DOCS_DIR/completed/backend"
    mkdir -p "$DOCS_DIR/completed/security"
    mkdir -p "$DOCS_DIR/completed/exchange"
    mkdir -p "$DOCS_DIR/completed/blockchain"
    mkdir -p "$DOCS_DIR/completed/analytics"
    mkdir -p "$DOCS_DIR/completed/marketplace"
    mkdir -p "$DOCS_DIR/completed/maintenance"
    mkdir -p "$DOCS_DIR/completed/ai"
    
    # Create archive structure
    mkdir -p "$ARCHIVE_DIR/by_category/infrastructure"
    mkdir -p "$ARCHIVE_DIR/by_category/cli"
    mkdir -p "$ARCHIVE_DIR/by_category/backend"
    mkdir -p "$ARCHIVE_DIR/by_category/security"
    mkdir -p "$ARCHIVE_DIR/by_category/exchange"
    mkdir -p "$ARCHIVE_DIR/by_category/blockchain"
    mkdir -p "$ARCHIVE_DIR/by_category/analytics"
    mkdir -p "$ARCHIVE_DIR/by_category/marketplace"
    mkdir -p "$ARCHIVE_DIR/by_category/maintenance"
    mkdir -p "$ARCHIVE_DIR/by_category/ai"
    
    print_status "Organized folders created"
}

# Scan all subfolders for completed tasks
scan_all_subfolders() {
    print_status "Scanning entire docs/10_plan subfolder structure..."
    
    cat > "$WORKSPACE_DIR/scan_all_subfolders.py" << 'EOF'
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
EOF
    
    python3 "$WORKSPACE_DIR/scan_all_subfolders.py"
    
    print_status "All subfolders scanned"
}

# Categorize and move completed content
categorize_and_move_content() {
    print_status "Categorizing and moving completed content..."
    
    cat > "$WORKSPACE_DIR/categorize_and_move.py" << 'EOF'
#!/usr/bin/env python3
"""
Content Categorizer and Mover
Categorizes completed content and moves to appropriate folders
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

def move_completed_content(scan_file, docs_dir, archive_dir):
    """Move completed content to organized folders"""
    
    with open(scan_file, 'r') as f:
        scan_results = json.load(f)
    
    category_mapping = {
        'core_planning': 'core_planning',
        'implementation': 'implementation',
        'testing': 'testing',
        'infrastructure': 'infrastructure',
        'security': 'security',
        'cli': 'cli',
        'backend': 'backend',
        'exchange': 'exchange',
        'blockchain': 'blockchain',
        'analytics': 'analytics',
        'marketplace': 'marketplace',
        'maintenance': 'maintenance',
        'summaries': 'summaries',
        'general': 'general'
    }
    
    moved_files = []
    category_summary = {}
    
    for result in scan_results['all_results']:
        if not result.get('has_completion', False):
            continue
        
        source_path = Path(result['file_path'])
        category = category_mapping.get(result['category'], 'general')
        
        # Create destination paths
        completed_dir = Path(docs_dir) / 'completed' / category
        archive_dir = Path(archive_dir) / 'by_category' / category
        
        # Ensure directories exist
        completed_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Destination file paths
        completed_dest = completed_dir / source_path.name
        archive_dest = archive_dir / source_path.name
        
        try:
            # Move to completed folder (remove from planning)
            shutil.move(source_path, completed_dest)
            
            # Create archive entry
            archive_content = f"""# Archived: {source_path.name}

**Source**: {result['relative_path']}
**Category**: {category}
**Archive Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Completion Markers**: {result['completion_count']}
**File Size**: {result['file_size']} bytes

## Archive Reason
This file contains completed tasks and has been moved to the completed documentation folder.

## Original Content
The original file content has been preserved in the completed folder and can be referenced there.

---
*Archived by AITBC Comprehensive Planning Cleanup*
"""
            
            with open(archive_dest, 'w') as f:
                f.write(archive_content)
            
            moved_files.append({
                'source': str(source_path),
                'completed_dest': str(completed_dest),
                'archive_dest': str(archive_dest),
                'category': category,
                'completion_count': result['completion_count']
            })
            
            if category not in category_summary:
                category_summary[category] = {
                    'files_moved': 0,
                    'total_completion_markers': 0
                }
            
            category_summary[category]['files_moved'] += 1
            category_summary[category]['total_completion_markers'] += result['completion_count']
            
            print(f"Moved {source_path.name} to completed/{category}/")
            
        except Exception as e:
            print(f"Error moving {source_path}: {e}")
    
    return moved_files, category_summary

if __name__ == "__main__":
    scan_file = 'comprehensive_scan_results.json'
    docs_dir = '/opt/aitbc/docs'
    archive_dir = '/opt/aitbc/docs/archive'
    
    moved_files, category_summary = move_completed_content(scan_file, docs_dir, archive_dir)
    
    # Save results
    with open('content_move_results.json', 'w') as f:
        json.dump({
            'moved_files': moved_files,
            'category_summary': category_summary,
            'total_files_moved': len(moved_files)
        }, f, indent=2)
    
    print(f"Content move complete:")
    print(f"  Total files moved: {len(moved_files)}")
    print("")
    print("Files moved by category:")
    for category, summary in category_summary.items():
        print(f"  {category}: {summary['files_moved']} files, {summary['total_completion_markers']} markers")
EOF
    
    python3 "$WORKSPACE_DIR/categorize_and_move.py"
    
    print_status "Completed content categorized and moved"
}

# Create comprehensive archive
create_comprehensive_archive() {
    print_status "Creating comprehensive archive..."
    
    cat > "$WORKSPACE_DIR/create_comprehensive_archive.py" << 'EOF'
#!/usr/bin/env python3
"""
Comprehensive Archive Creator
Creates a comprehensive archive of all completed work
"""

import json
from pathlib import Path
from datetime import datetime

def create_comprehensive_archive(scan_file, archive_dir):
    """Create comprehensive archive of all completed work"""
    
    with open(scan_file, 'r') as f:
        scan_results = json.load(f)
    
    archive_path = Path(archive_dir)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create main archive file
    main_archive = archive_path / f"comprehensive_archive_{timestamp}.md"
    
    archive_content = f"""# AITBC Comprehensive Planning Archive

**Archive Created**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Archive ID**: {timestamp}
**Total Files Processed**: {scan_results['total_files_scanned']}
**Files with Completion**: {scan_results['files_with_completion']}
**Total Completion Markers**: {scan_results['total_completion_markers']}

## Archive Summary

### Files with Completion Markers
"""
    
    for category, summary in scan_results['category_summary'].items():
        archive_content += f"""
#### {category.title()}
- **Files**: {summary['total_files']}
- **Completion Markers**: {summary['total_completion_count']}
"""
    
    archive_content += """

### Files Moved to Completed Documentation
"""
    
    for category, summary in scan_results['category_summary'].items():
        archive_content += f"""
#### {category.title()} Documentation
- **Location**: docs/completed/{category}/
- **Files**: {summary['total_files']}
"""
    
    archive_content += """

## Archive Structure

### Completed Documentation
```
docs/completed/
├── infrastructure/ - Infrastructure completed tasks
├── cli/ - CLI completed tasks
├── backend/ - Backend completed tasks
├── security/ - Security completed tasks
├── exchange/ - Exchange completed tasks
├── blockchain/ - Blockchain completed tasks
├── analytics/ - Analytics completed tasks
├── marketplace/ - Marketplace completed tasks
├── maintenance/ - Maintenance completed tasks
└── general/ - General completed tasks
```

### Archive by Category
```
docs/archive/by_category/
├── infrastructure/ - Infrastructure archive files
├── cli/ - CLI archive files
├── backend/ - Backend archive files
├── security/ - Security archive files
├── exchange/ - Exchange archive files
├── blockchain/ - Blockchain archive files
├── analytics/ - Analytics archive files
├── marketplace/ - Marketplace archive files
├── maintenance/ - Maintenance archive files
└── general/ - General archive files
```

## Next Steps

1. **New Milestone Planning**: docs/10_plan is now clean and ready for new content
2. **Reference Completed Work**: Use docs/completed/ for reference
3. **Archive Access**: Use docs/archive/ for historical information
4. **Template Usage**: Use completed documentation as templates

---
*Generated by AITBC Comprehensive Planning Cleanup*
"""
    
    with open(main_archive, 'w') as f:
        f.write(archive_content)
    
    return str(main_archive)

if __name__ == "__main__":
    scan_file = 'comprehensive_scan_results.json'
    archive_dir = '/opt/aitbc/docs/archive'
    
    archive_file = create_comprehensive_archive(scan_file, archive_dir)
    
    print(f"Comprehensive archive created: {archive_file}")
EOF
    
    python3 "$WORKSPACE_DIR/create_comprehensive_archive.py"
    
    print_status "Comprehensive archive created"
}

# Clean up planning documents
cleanup_planning_documents() {
    print_status "Cleaning up planning documents..."
    
    # Remove all completion markers from all files
    find "$PLANNING_DIR" -name "*.md" -exec sed -i '/✅/d' {} \;
    
    print_status "Planning documents cleaned"
}

# Generate final reports
generate_final_reports() {
    print_status "Generating final reports..."
    
    cat > "$WORKSPACE_DIR/generate_final_report.py" << 'EOF'
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
EOF
    
    python3 "$WORKSPACE_DIR/generate_final_report.py"
    
    print_status "Final reports generated"
}

# Run main function
main "$@"
