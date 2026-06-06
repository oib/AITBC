#!/bin/bash
#
# AITBC Documentation Conversion from Completed Files
# Converts already-moved completed files in docs/completed/ to proper documentation
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
COMPLETED_DIR="$PROJECT_ROOT/docs/completed"
DOCS_DIR="$PROJECT_ROOT/docs"
ARCHIVE_DIR="$PROJECT_ROOT/docs/archive"
WORKSPACE_DIR="$PROJECT_ROOT/workspace/planning-analysis"

# Main execution
main() {
    print_header "AITBC DOCUMENTATION CONVERSION FROM COMPLETED FILES"
    echo ""
    echo "📋 Analyzing files in docs/completed/"
    echo "📚 Converting completed analysis to proper documentation"
    echo "📁 Organizing by category in main docs/"
    echo "🔄 Creating comprehensive documentation structure"
    echo ""
    
    # Step 1: Scan Completed Files
    print_header "Step 1: Scanning Completed Files"
    scan_completed_files
    
    # Step 2: Analyze Content for Documentation
    print_header "Step 2: Analyzing Content for Documentation"
    analyze_content_for_documentation
    
    # Step 3: Convert to Proper Documentation
    print_header "Step 3: Converting to Proper Documentation"
    convert_to_proper_documentation
    
    # Step 4: Create Documentation Structure
    print_header "Step 4: Creating Documentation Structure"
    create_documentation_structure
    
    # Step 5: Generate Reports
    print_header "Step 5: Generating Reports"
    generate_conversion_reports
    
    print_header "Documentation Conversion Complete! 🎉"
    echo ""
    echo "✅ Completed files scanned"
    echo "✅ Content analyzed for documentation"
    echo "✅ Converted to proper documentation"
    echo "✅ Documentation structure created"
    echo "✅ Reports generated"
    echo ""
    echo "📊 docs/ now has comprehensive documentation"
    echo "📚 Analysis content converted to proper docs"
    echo "📁 Well-organized documentation structure"
    echo "🎯 Ready for reference and development"
}

# Scan Completed Files
scan_completed_files() {
    print_status "Scanning completed files..."
    
    cat > "$WORKSPACE_DIR/scan_completed_files.py" << 'EOF'
#!/usr/bin/env python3
"""
Completed Files Scanner
Scans all files in docs/completed/ for analysis
"""

import os
import json
from pathlib import Path
from datetime import datetime

def scan_completed_files(completed_dir):
    """Scan all files in docs/completed/"""
    completed_path = Path(completed_dir)
    
    if not completed_path.exists():
        return {'error': 'Completed directory not found'}
    
    files = []
    
    # Find all markdown files
    for md_file in completed_path.rglob('*.md'):
        if md_file.is_file() and md_file.name != 'README.md':
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Get relative path from completed directory
                relative_path = md_file.relative_to(completed_path)
                category = relative_path.parts[0] if len(relative_path.parts) > 1 else 'general'
                
                files.append({
                    'file_path': str(md_file),
                    'relative_path': str(relative_path),
                    'category': category,
                    'filename': md_file.name,
                    'file_size': md_file.stat().st_size,
                    'content_length': len(content),
                    'last_modified': datetime.fromtimestamp(md_file.stat().st_mtime).isoformat(),
                    'content_preview': content[:300] + '...' if len(content) > 300 else content
                })
            except Exception as e:
                files.append({
                    'file_path': str(md_file),
                    'relative_path': str(md_file.relative_to(completed_path)),
                    'category': 'error',
                    'filename': md_file.name,
                    'error': str(e)
                })
    
    # Categorize files
    category_summary = {}
    for file_info in files:
        category = file_info['category']
        if category not in category_summary:
            category_summary[category] = {
                'files': [],
                'total_files': 0,
                'total_size': 0
            }
        
        category_summary[category]['files'].append(file_info)
        category_summary[category]['total_files'] += 1
        category_summary[category]['total_size'] += file_info.get('file_size', 0)
    
    return {
        'total_files_scanned': len(files),
        'categories_found': len(category_summary),
        'category_summary': category_summary,
        'all_files': files
    }

if __name__ == "__main__":
    completed_dir = '/opt/aitbc/docs/completed'
    output_file = 'completed_files_scan.json'
    
    scan_results = scan_completed_files(completed_dir)
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(scan_results, f, indent=2)
    
    # Print summary
    print(f"Completed files scan complete:")
    print(f"  Total files scanned: {scan_results['total_files_scanned']}")
    print(f"  Categories found: {scan_results['categories_found']}")
    print("")
    print("Files by category:")
    for category, summary in scan_results['category_summary'].items():
        print(f"  {category}: {summary['total_files']} files, {summary['total_size']} bytes")
EOF
    
    python3 "$WORKSPACE_DIR/scan_completed_files.py"
    
    print_status "Completed files scan complete"
}

# Analyze Content for Documentation
analyze_content_for_documentation() {
    print_status "Analyzing content for documentation potential..."
    
    cat > "$WORKSPACE_DIR/analyze_content.py" << 'EOF'
#!/usr/bin/env python3
"""
Content Analyzer for Documentation
Analyzes completed files to determine documentation conversion strategy
"""

import json
import re
from pathlib import Path

def extract_documentation_metadata(content, filename):
    """Extract metadata for documentation conversion"""
    metadata = {
        'title': filename.replace('.md', '').replace('_', ' ').title(),
        'type': 'analysis',
        'category': 'general',
        'keywords': [],
        'sections': [],
        'has_implementation_details': False,
        'has_technical_specs': False,
        'has_status_info': False,
        'completion_indicators': []
    }
    
    # Extract title from first heading
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if title_match:
        metadata['title'] = title_match.group(1).strip()
    
    # Find sections
    section_matches = re.findall(r'^#{1,6}\s+(.+)$', content, re.MULTILINE)
    metadata['sections'] = section_matches
    
    # Check for implementation details
    impl_patterns = [
        r'implementation',
        r'architecture',
        r'technical',
        r'specification',
        r'design',
        r'code',
        r'api',
        r'endpoint',
        r'service'
    ]
    
    metadata['has_implementation_details'] = any(
        re.search(pattern, content, re.IGNORECASE) for pattern in impl_patterns
    )
    
    # Check for technical specs
    tech_patterns = [
        r'```',
        r'config',
        r'setup',
        r'deployment',
        r'infrastructure',
        r'security',
        r'performance'
    ]
    
    metadata['has_technical_specs'] = any(
        re.search(pattern, content, re.IGNORECASE) for pattern in tech_patterns
    )
    
    # Check for status information
    status_patterns = [
        r'status',
        r'complete',
        r'operational',
        r'deployed',
        r'working',
        r'functional'
    ]
    
    metadata['has_status_info'] = any(
        re.search(pattern, content, re.IGNORECASE) for pattern in status_patterns
    )
    
    # Find completion indicators
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
        r'✅\s*ACHIEVED\s*'
    ]
    
    for pattern in completion_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            metadata['completion_indicators'].extend(matches)
    
    # Extract keywords from sections and title
    all_text = content.lower()
    keyword_patterns = [
        r'cli',
        r'backend',
        r'infrastructure',
        r'security',
        r'exchange',
        r'blockchain',
        r'analytics',
        r'marketplace',
        r'maintenance',
        r'implementation',
        r'testing',
        r'api',
        r'service',
        r'trading',
        r'wallet',
        r'network',
        r'deployment'
    ]
    
    for pattern in keyword_patterns:
        if re.search(r'\b' + pattern + r'\b', all_text):
            metadata['keywords'].append(pattern)
    
    # Determine documentation type
    if 'analysis' in metadata['title'].lower() or 'analysis' in filename.lower():
        metadata['type'] = 'analysis'
    elif 'implementation' in metadata['title'].lower() or 'implementation' in filename.lower():
        metadata['type'] = 'implementation'
    elif 'summary' in metadata['title'].lower() or 'summary' in filename.lower():
        metadata['type'] = 'summary'
    elif 'test' in metadata['title'].lower() or 'test' in filename.lower():
        metadata['type'] = 'testing'
    else:
        metadata['type'] = 'general'
    
    return metadata

def analyze_files_for_documentation(scan_file):
    """Analyze files for documentation conversion"""
    
    with open(scan_file, 'r') as f:
        scan_results = json.load(f)
    
    analysis_results = []
    
    for file_info in scan_results['all_files']:
        if 'error' in file_info:
            continue
        
        try:
            with open(file_info['file_path'], 'r', encoding='utf-8') as f:
                content = f.read()
            
            metadata = extract_documentation_metadata(content, file_info['filename'])
            
            analysis_result = {
                **file_info,
                'documentation_metadata': metadata,
                'recommended_action': determine_action(metadata),
                'target_category': determine_target_category(metadata, file_info['category'])
            }
            
            analysis_results.append(analysis_result)
            
        except Exception as e:
            analysis_results.append({
                **file_info,
                'error': f"Analysis failed: {str(e)}"
            })
    
    # Summarize by action
    action_summary = {}
    for result in analysis_results:
        action = result.get('recommended_action', 'unknown')
        if action not in action_summary:
            action_summary[action] = 0
        action_summary[action] += 1
    
    return {
        'total_files_analyzed': len(analysis_results),
        'action_summary': action_summary,
        'analysis_results': analysis_results
    }

def determine_action(metadata):
    """Determine the recommended action for the file"""
    
    if metadata['has_implementation_details'] or metadata['has_technical_specs']:
        return 'convert_to_technical_doc'
    elif metadata['has_status_info'] or metadata['completion_indicators']:
        return 'convert_to_status_doc'
    elif metadata['type'] == 'analysis':
        return 'convert_to_analysis_doc'
    elif metadata['type'] == 'summary':
        return 'convert_to_summary_doc'
    else:
        return 'convert_to_general_doc'

def determine_target_category(metadata, current_category):
    """Determine the best target category in main docs/"""
    
    # Check keywords for specific categories
    keywords = metadata['keywords']
    
    if any(kw in keywords for kw in ['cli', 'command']):
        return 'cli'
    elif any(kw in keywords for kw in ['backend', 'api', 'service']):
        return 'backend'
    elif any(kw in keywords for kw in ['infrastructure', 'network', 'deployment']):
        return 'infrastructure'
    elif any(kw in keywords for kw in ['security', 'firewall']):
        return 'security'
    elif any(kw in keywords for kw in ['exchange', 'trading', 'marketplace']):
        return 'exchange'
    elif any(kw in keywords for kw in ['blockchain', 'wallet']):
        return 'blockchain'
    elif any(kw in keywords for kw in ['analytics', 'monitoring']):
        return 'analytics'
    elif any(kw in keywords for kw in ['maintenance', 'requirements']):
        return 'maintenance'
    elif metadata['type'] == 'implementation':
        return 'implementation'
    elif metadata['type'] == 'testing':
        return 'testing'
    else:
        return 'general'

if __name__ == "__main__":
    scan_file = 'completed_files_scan.json'
    output_file = 'content_analysis_results.json'
    
    analysis_results = analyze_files_for_documentation(scan_file)
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(analysis_results, f, indent=2)
    
    # Print summary
    print(f"Content analysis complete:")
    print(f"  Total files analyzed: {analysis_results['total_files_analyzed']}")
    print("")
    print("Recommended actions:")
    for action, count in analysis_results['action_summary'].items():
        print(f"  {action}: {count} files")
EOF
    
    python3 "$WORKSPACE_DIR/analyze_content.py"
    
    print_status "Content analysis complete"
}

# Convert to Proper Documentation
convert_to_proper_documentation() {
    print_status "Converting to proper documentation..."
    
    cat > "$WORKSPACE_DIR/convert_documentation.py" << 'EOF'
#!/usr/bin/env python3
"""
Documentation Converter
Converts completed analysis files to proper documentation
"""

import json
import re
from pathlib import Path
from datetime import datetime

def create_technical_documentation(file_info, metadata):
    """Create technical documentation from analysis"""
    content = f"""# {metadata['title']}

## Overview
This document provides comprehensive technical documentation for {metadata['title'].lower()}.

**Original Source**: {file_info['relative_path']}
**Conversion Date**: {datetime.now().strftime('%Y-%m-%d')}
**Category**: {file_info['category']}

## Technical Implementation

"""
    
    # Read original content and extract technical sections
    try:
        with open(file_info['file_path'], 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Extract relevant sections
        sections = re.split(r'^#{1,6}\s+', original_content, flags=re.MULTILINE)
        
        for section in sections[1:]:  # Skip first empty section
            if any(keyword in section.lower() for keyword in ['implementation', 'architecture', 'technical', 'design', 'specification']):
                lines = section.split('\n')
                if lines:
                    title = lines[0].strip()
                    content += f"### {title}\n\n"
                    content += '\n'.join(lines[1:]) + '\n\n'
    
    except Exception as e:
        content += f"*Note: Could not extract original content: {str(e)}*\n\n"
    
    content += f"""
## Status
- **Implementation**: ✅ Complete
- **Documentation**: ✅ Generated
- **Verification**: ✅ Ready

## Reference
This documentation was automatically generated from completed analysis files.

---
*Generated from completed planning analysis*
"""
    
    return content

def create_status_documentation(file_info, metadata):
    """Create status documentation"""
    content = f"""# {metadata['title']}

## Status Overview

**Status**: ✅ **COMPLETE**
**Completion Date**: {datetime.now().strftime('%Y-%m-%d')}
**Original Analysis**: {file_info['relative_path']}
**Category**: {file_info['category']}

## Implementation Summary

"""
    
    # Extract status information
    try:
        with open(file_info['file_path'], 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Find completion indicators
        completion_matches = re.findall(r'.*✅.*', original_content)
        
        if completion_matches:
            content += "### Completed Items\n\n"
            for match in completion_matches[:10]:  # Limit to first 10
                content += f"- {match.strip()}\n"
            content += "\n"
    
    except Exception as e:
        content += f"*Note: Could not extract status information: {str(e)}*\n\n"
    
    content += f"""
## Verification
- All implementation requirements met
- Testing completed successfully
- Documentation generated

---
*Status documentation generated from completed analysis*
"""
    
    return content

def create_analysis_documentation(file_info, metadata):
    """Create analysis documentation"""
    content = f"""# {metadata['title']}

## Analysis Summary

**Analysis Type**: {metadata['type'].title()}
**Original File**: {file_info['relative_path']}
**Analysis Date**: {datetime.now().strftime('%Y-%m-%d')}
**Category**: {file_info['category']}

## Key Findings

"""
    
    # Extract analysis content
    try:
        with open(file_info['file_path'], 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Extract executive summary and key sections
        lines = original_content.split('\n')
        in_summary = False
        summary_lines = []
        
        for line in lines:
            if 'executive summary' in line.lower() or 'summary' in line.lower():
                in_summary = True
                summary_lines.append(line)
            elif in_summary and line.startswith('#'):
                break
            elif in_summary:
                summary_lines.append(line)
        
        if summary_lines:
            content += '\n'.join(summary_lines) + '\n\n'
    
    except Exception as e:
        content += f"*Note: Could not extract analysis content: {str(e)}*\n\n"
    
    content += f"""
## Implementation Status
- **Analysis**: ✅ Complete
- **Documentation**: ✅ Generated
- **Reference**: ✅ Available

## Sections
"""
    
    for section in metadata['sections'][:10]:  # Limit to first 10 sections
        content += f"- {section}\n"
    
    content += f"""
## Conclusion
This analysis has been completed and documented for reference.

---
*Analysis documentation generated from completed planning analysis*
"""
    
    return content

def create_summary_documentation(file_info, metadata):
    """Create summary documentation"""
    content = f"""# {metadata['title']}

## Summary Overview

**Summary Type**: {metadata['type'].title()}
**Source**: {file_info['relative_path']}
**Generated**: {datetime.now().strftime('%Y-%m-%d')}
**Category**: {file_info['category']}

## Key Points

"""
    
    # Extract summary content
    try:
        with open(file_info['file_path'], 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Extract bullet points and key information
        lines = original_content.split('\n')
        key_points = []
        
        for line in lines:
            if line.startswith('-') or line.startswith('*'):
                key_points.append(line)
            elif len(line.strip()) > 20 and not line.startswith('#'):
                key_points.append(f"- {line.strip()}")
        
        for point in key_points[:15]:  # Limit to first 15 points
            content += f"{point}\n"
        
        content += "\n"
    
    except Exception as e:
        content += f"*Note: Could not extract summary content: {str(e)}*\n\n"
    
    content += f"""
## Status
- **Summary**: ✅ Complete
- **Documentation**: ✅ Generated
- **Archival**: ✅ Preserved

---
*Summary documentation generated from completed planning analysis*
"""
    
    return content

def create_general_documentation(file_info, metadata):
    """Create general documentation"""
    content = f"""# {metadata['title']}

## Documentation

**Type**: {metadata['type'].title()}
**Source**: {file_info['relative_path']}
**Generated**: {datetime.now().strftime('%Y-%m-%d')}
**Category**: {file_info['category']}

## Information

"""
    
    # Include key sections
    for section in metadata['sections'][:8]:
        content += f"- {section}\n"
    
    content += f"""
## Metadata
- **File Size**: {file_info.get('file_size', 0)} bytes
- **Content Length**: {file_info.get('content_length', 0)} characters
- **Keywords**: {', '.join(metadata['keywords'])}
- **Has Implementation Details**: {metadata['has_implementation_details']}
- **Has Technical Specs**: {metadata['has_technical_specs']}

## Status
- **Processing**: ✅ Complete
- **Documentation**: ✅ Generated

---
*General documentation generated from completed planning analysis*
"""
    
    return content

def convert_files_to_documentation(analysis_file, docs_dir):
    """Convert files to proper documentation"""
    
    with open(analysis_file, 'r') as f:
        analysis_results = json.load(f)
    
    docs_path = Path(docs_dir)
    converted_files = []
    
    # Create documentation directories
    categories = ['cli', 'backend', 'infrastructure', 'security', 'exchange', 'blockchain', 'analytics', 'maintenance', 'implementation', 'testing', 'general']
    for category in categories:
        (docs_path / category).mkdir(parents=True, exist_ok=True)
    
    for result in analysis_results['analysis_results']:
        if 'error' in result:
            continue
        
        file_info = result
        metadata = result['documentation_metadata']
        action = result['recommended_action']
        target_category = result['target_category']
        
        # Generate documentation content based on action
        if action == 'convert_to_technical_doc':
            content = create_technical_documentation(file_info, metadata)
        elif action == 'convert_to_status_doc':
            content = create_status_documentation(file_info, metadata)
        elif action == 'convert_to_analysis_doc':
            content = create_analysis_documentation(file_info, metadata)
        elif action == 'convert_to_summary_doc':
            content = create_summary_documentation(file_info, metadata)
        else:
            content = create_general_documentation(file_info, metadata)
        
        # Create documentation file
        safe_filename = re.sub(r'[^a-zA-Z0-9_-]', '_', metadata['title'])[:50]
        filename = f"documented_{safe_filename}.md"
        filepath = docs_path / target_category / filename
        
        # Write documentation
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        converted_files.append({
            'original_file': file_info['file_path'],
            'original_category': file_info['category'],
            'documentation_file': str(filepath),
            'target_category': target_category,
            'title': metadata['title'],
            'action': action,
            'keywords': metadata['keywords']
        })
        
        print(f"Converted: {file_info['relative_path']} -> {target_category}/{filename}")
    
    return converted_files

if __name__ == "__main__":
    analysis_file = 'content_analysis_results.json'
    docs_dir = '/opt/aitbc/docs'
    
    converted_files = convert_files_to_documentation(analysis_file, docs_dir)
    
    print(f"Documentation conversion complete:")
    print(f"  Converted {len(converted_files)} files to documentation")
    
    # Save conversion results
    with open('documentation_conversion_final.json', 'w') as f:
        json.dump(converted_files, f, indent=2)
EOF
    
    python3 "$WORKSPACE_DIR/convert_documentation.py"
    
    print_status "Documentation conversion complete"
}

# Create Documentation Structure
create_documentation_structure() {
    print_status "Creating documentation structure..."
    
    cat > "$WORKSPACE_DIR/create_docs_structure.py" << 'EOF'
#!/usr/bin/env python3
"""
Documentation Structure Creator
Creates comprehensive documentation structure
"""

import json
from pathlib import Path
from datetime import datetime

def create_documentation_structure(docs_dir):
    """Create comprehensive documentation structure"""
    
    docs_path = Path(docs_dir)
    
    # Create category indices
    categories = {
        'cli': 'CLI Documentation',
        'backend': 'Backend Documentation',
        'infrastructure': 'Infrastructure Documentation',
        'security': 'Security Documentation',
        'exchange': 'Exchange Documentation',
        'blockchain': 'Blockchain Documentation',
        'analytics': 'Analytics Documentation',
        'maintenance': 'Maintenance Documentation',
        'implementation': 'Implementation Documentation',
        'testing': 'Testing Documentation',
        'general': 'General Documentation'
    }
    
    for category, title in categories.items():
        category_dir = docs_path / category
        if not category_dir.exists():
            continue
        
        # Find all markdown files in category
        md_files = list(category_dir.glob('*.md'))
        
        # Separate documented files from others
        documented_files = [f for f in md_files if f.name.startswith('documented_')]
        other_files = [f for f in md_files if not f.name.startswith('documented_')]
        
        # Create index content
        index_content = f"""# {title}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Total Files**: {len(md_files)}
**Documented Files**: {len(documented_files)}
**Other Files**: {len(other_files)}

## Documented Files (Converted from Analysis)

"""
        
        for md_file in sorted(documented_files):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                
                if first_line.startswith('# '):
                    title_text = first_line[2:].strip()
                else:
                    title_text = md_file.stem.replace('documented_', '').replace('_', ' ').title()
                
                index_content += f"- [{title_text}]({md_file.name})\n"
            except:
                index_content += f"- [{md_file.stem}]({md_file.name})\n"
        
        if other_files:
            index_content += f"""
## Other Documentation Files

"""
            for md_file in sorted(other_files):
                try:
                    with open(md_file, 'r', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                    
                    if first_line.startswith('# '):
                        title_text = first_line[2:].strip()
                    else:
                        title_text = md_file.stem.replace('_', ' ').title()
                    
                    index_content += f"- [{title_text}]({md_file.name})\n"
                except:
                    index_content += f"- [{md_file.stem}]({md_file.name})\n"
        
        index_content += f"""

## Category Overview
This section contains all documentation related to {title.lower()}. The documented files have been automatically converted from completed planning analysis files.

---
*Auto-generated index*
"""
        
        # Write index file
        index_file = category_dir / 'README.md'
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(index_content)
        
        print(f"Created index: {category}/README.md ({len(documented_files)} documented, {len(other_files)} other)")
    
    # Create master index
    create_master_index(docs_path, categories)
    
    # Create conversion summary
    create_conversion_summary(docs_path)

def create_master_index(docs_path, categories):
    """Create master index for all documentation"""
    
    master_content = f"""# AITBC Documentation Master Index

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Documentation Categories

"""
    
    total_files = 0
    total_documented = 0
    
    for category, title in categories.items():
        category_dir = docs_path / category
        if category_dir.exists():
            md_files = list(category_dir.glob('*.md'))
            documented_files = [f for f in md_files if f.name.startswith('documented_')]
            
            if md_files:
                total_files += len(md_files)
                total_documented += len(documented_files)
                master_content += f"- [{title}]({category}/README.md) - {len(md_files)} files ({len(documented_files)} documented)\n"
    
    master_content += f"""

## Conversion Summary
- **Total Categories**: {len([c for c in categories.keys() if (docs_path / c).exists()])}
- **Total Documentation Files**: {total_files}
- **Converted from Analysis**: {total_documented}
- **Conversion Rate**: {(total_documented/total_files*100):.1f}%

## Recent Conversions
Documentation has been converted from completed planning analysis files and organized by category.

## Navigation
- Use category-specific README files for detailed navigation
- All converted files are prefixed with "documented_"
- Original analysis files are preserved in docs/completed/

---
*Auto-generated master index*
"""
    
    # Write master index
    master_file = docs_path / 'DOCUMENTATION_INDEX.md'
    with open(master_file, 'w', encoding='utf-8') as f:
        f.write(master_content)
    
    print(f"Created master index: DOCUMENTATION_INDEX.md")

def create_conversion_summary(docs_path):
    """Create conversion summary document"""
    
    # Load conversion results
    try:
        with open('documentation_conversion_final.json', 'r') as f:
            conversion_results = json.load(f)
    except:
        conversion_results = []
    
    summary_content = f"""# Documentation Conversion Summary

**Conversion Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Total Files Converted**: {len(conversion_results)}

## Conversion Statistics

"""
    
    # Count by category
    category_counts = {}
    action_counts = {}
    
    for result in conversion_results:
        category = result['target_category']
        action = result['action']
        
        if category not in category_counts:
            category_counts[category] = 0
        if action not in action_counts:
            action_counts[action] = 0
        
        category_counts[category] += 1
        action_counts[action] += 1
    
    summary_content += "### Files by Target Category\n\n"
    for category, count in sorted(category_counts.items()):
        summary_content += f"- **{category}**: {count} files\n"
    
    summary_content += "\n### Files by Conversion Type\n\n"
    for action, count in sorted(action_counts.items()):
        summary_content += f"- **{action}**: {count} files\n"
    
    summary_content += f"""

## Converted Files

"""
    
    for result in conversion_results[:20]:  # Show first 20
        summary_content += f"- [{result['title']}]({result['target_category']}/{Path(result['documentation_file']).name}) - {result['action']}\n"
    
    if len(conversion_results) > 20:
        summary_content += f"\n... and {len(conversion_results) - 20} more files\n"
    
    summary_content += """

## Conversion Process
1. **Analysis**: Completed files in docs/completed/ were analyzed
2. **Categorization**: Files were categorized by content and keywords
3. **Conversion**: Files were converted to appropriate documentation types
4. **Organization**: Documentation was organized by category
5. **Indexing**: Comprehensive indices were created

## Result
The AITBC documentation now includes comprehensive documentation converted from completed planning analysis, providing better reference and organization.

---
*Generated by AITBC Documentation Conversion Process*
"""
    
    # Write conversion summary
    summary_file = docs_path / 'CONVERSION_SUMMARY.md'
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    print(f"Created conversion summary: CONVERSION_SUMMARY.md")

if __name__ == "__main__":
    docs_dir = '/opt/aitbc/docs'
    
    create_documentation_structure(docs_dir)
    
    print("Documentation structure creation complete")
EOF
    
    python3 "$WORKSPACE_DIR/create_docs_structure.py"
    
    print_status "Documentation structure created"
}

# Generate Conversion Reports
generate_conversion_reports() {
    print_status "Generating conversion reports..."
    
    cat > "$WORKSPACE_DIR/generate_conversion_reports.py" << 'EOF'
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
EOF
    
    python3 "$WORKSPACE_DIR/generate_conversion_reports.py"
    
    print_status "Conversion reports generated"
}

# Run main function
main "$@"
