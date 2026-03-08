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
