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
