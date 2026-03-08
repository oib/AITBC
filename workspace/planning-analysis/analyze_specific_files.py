#!/usr/bin/env python3
"""
Specific Files Analyzer
Analyzes the specific files listed by the user
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime

# List of specific files from user request
SPECIFIC_FILES = [
    "01_core_planning/advanced_analytics_analysis.md",
    "01_core_planning/analytics_service_analysis.md",
    "01_core_planning/compliance_regulation_analysis.md",
    "01_core_planning/exchange_implementation_strategy.md",
    "01_core_planning/genesis_protection_analysis.md",
    "01_core_planning/global_ai_agent_communication_analysis.md",
    "01_core_planning/market_making_infrastructure_analysis.md",
    "01_core_planning/multi_region_infrastructure_analysis.md",
    "01_core_planning/multisig_wallet_analysis.md",
    "01_core_planning/next-steps-plan.md",
    "01_core_planning/oracle_price_discovery_analysis.md",
    "01_core_planning/production_monitoring_analysis.md",
    "01_core_planning/README.md",
    "01_core_planning/real_exchange_integration_analysis.md",
    "01_core_planning/regulatory_reporting_analysis.md",
    "01_core_planning/security_testing_analysis.md",
    "01_core_planning/trading_engine_analysis.md",
    "01_core_planning/trading_surveillance_analysis.md",
    "01_core_planning/transfer_controls_analysis.md",
    "02_implementation/backend-implementation-roadmap.md",
    "02_implementation/backend-implementation-status.md",
    "02_implementation/enhanced-services-implementation-complete.md",
    "02_implementation/exchange-infrastructure-implementation.md",
    "03_testing/admin-test-scenarios.md",
    "04_infrastructure/geographic-load-balancer-0.0.0.0-binding.md",
    "04_infrastructure/geographic-load-balancer-migration.md",
    "04_infrastructure/infrastructure-documentation-update-summary.md",
    "04_infrastructure/localhost-port-logic-implementation-summary.md",
    "04_infrastructure/new-port-logic-implementation-summary.md",
    "04_infrastructure/nginx-configuration-update-summary.md",
    "04_infrastructure/port-chain-optimization-summary.md",
    "04_infrastructure/web-ui-port-8010-change-summary.md",
    "05_security/architecture-reorganization-summary.md",
    "05_security/firewall-clarification-summary.md",
    "06_cli/BLOCKCHAIN_BALANCE_MULTICHAIN_ENHANCEMENT.md",
    "06_cli/CLI_HELP_AVAILABILITY_UPDATE_SUMMARY.md",
    "06_cli/CLI_MULTICHAIN_ANALYSIS.md",
    "06_cli/cli-analytics-test-scenarios.md",
    "06_cli/cli-blockchain-test-scenarios.md",
    "06_cli/cli-checklist.md",
    "06_cli/cli-config-test-scenarios.md",
    "06_cli/cli-core-workflows-test-scenarios.md",
    "06_cli/cli-fixes-summary.md",
    "06_cli/cli-test-execution-results.md",
    "06_cli/cli-test-results.md",
    "06_cli/COMPLETE_MULTICHAIN_FIXES_NEEDED.md",
    "06_cli/PHASE1_MULTICHAIN_COMPLETION.md",
    "06_cli/PHASE2_MULTICHAIN_COMPLETION.md",
    "06_cli/PHASE3_MULTICHAIN_COMPLETION.md",
    "07_backend/api-endpoint-fixes-summary.md",
    "07_backend/api-key-setup-summary.md",
    "07_backend/coordinator-api-warnings-fix.md",
    "07_backend/swarm-network-endpoints-specification.md",
    "08_marketplace/06_global_marketplace_launch.md",
    "08_marketplace/07_cross_chain_integration.md",
    "09_maintenance/debian11-removal-summary.md",
    "09_maintenance/debian13-trixie-prioritization-summary.md",
    "09_maintenance/debian13-trixie-support-update.md",
    "09_maintenance/nodejs-22-requirement-update-summary.md",
    "09_maintenance/nodejs-requirements-update-summary.md",
    "09_maintenance/requirements-updates-comprehensive-summary.md",
    "09_maintenance/requirements-validation-implementation-summary.md",
    "09_maintenance/requirements-validation-system.md",
    "09_maintenance/ubuntu-removal-summary.md",
    "10_summaries/99_currentissue_exchange-gap.md",
    "10_summaries/99_currentissue.md",
    "10_summaries/priority-3-complete.md",
    "04_global_marketplace_launch.md",
    "05_cross_chain_integration.md",
    "ORGANIZATION_SUMMARY.md"
]

def categorize_file(file_path):
    """Categorize file based on path and content"""
    path_parts = file_path.split('/')
    folder = path_parts[0] if len(path_parts) > 1 else 'root'
    filename = path_parts[1] if len(path_parts) > 1 else file_path
    
    if 'core_planning' in folder:
        return 'core_planning'
    elif 'implementation' in folder:
        return 'implementation'
    elif 'testing' in folder:
        return 'testing'
    elif 'infrastructure' in folder:
        return 'infrastructure'
    elif 'security' in folder:
        return 'security'
    elif 'cli' in folder:
        return 'cli'
    elif 'backend' in folder:
        return 'backend'
    elif 'marketplace' in folder:
        return 'marketplace'
    elif 'maintenance' in folder:
        return 'maintenance'
    elif 'summaries' in folder:
        return 'summaries'
    
    # Filename-based categorization
    if any(word in filename.lower() for word in ['infrastructure', 'port', 'nginx']):
        return 'infrastructure'
    elif any(word in filename.lower() for word in ['cli', 'command']):
        return 'cli'
    elif any(word in filename.lower() for word in ['backend', 'api']):
        return 'backend'
    elif any(word in filename.lower() for word in ['security', 'firewall']):
        return 'security'
    elif any(word in filename.lower() for word in ['exchange', 'trading', 'marketplace']):
        return 'marketplace'
    elif any(word in filename.lower() for word in ['blockchain', 'wallet']):
        return 'blockchain'
    elif any(word in filename.lower() for word in ['analytics', 'monitoring']):
        return 'analytics'
    elif any(word in filename.lower() for word in ['maintenance', 'requirements']):
        return 'maintenance'
    
    return 'general'

def analyze_file_for_completion(file_path, planning_dir):
    """Analyze a specific file for completion indicators"""
    full_path = Path(planning_dir) / file_path
    
    if not full_path.exists():
        return {
            'file_path': file_path,
            'exists': False,
            'error': 'File not found'
        }
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
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
            
            # Extract completed tasks
            completed_tasks = []
            lines = content.split('\n')
            for i, line in enumerate(lines):
                for pattern in completion_patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        task_desc = line.strip()
                        completed_tasks.append({
                            'line_number': i + 1,
                            'task_description': task_desc,
                            'pattern_used': pattern
                        })
                        break
            
            return {
                'file_path': file_path,
                'exists': True,
                'category': categorize_file(file_path),
                'has_completion': True,
                'completion_count': completion_count,
                'completed_tasks': completed_tasks,
                'file_size': full_path.stat().st_size,
                'last_modified': datetime.fromtimestamp(full_path.stat().st_mtime).isoformat(),
                'content_preview': content[:500] + '...' if len(content) > 500 else content
            }
        
        return {
            'file_path': file_path,
            'exists': True,
            'category': categorize_file(file_path),
            'has_completion': False,
            'completion_count': 0,
            'completed_tasks': [],
            'file_size': full_path.stat().st_size,
            'last_modified': datetime.fromtimestamp(full_path.stat().st_mtime).isoformat(),
            'content_preview': content[:500] + '...' if len(content) > 500 else content
        }
    
    except Exception as e:
        return {
            'file_path': file_path,
            'exists': True,
            'error': str(e),
            'has_completion': False,
            'completion_count': 0
        }

def analyze_all_specific_files(planning_dir):
    """Analyze all specific files"""
    results = []
    
    for file_path in SPECIFIC_FILES:
        result = analyze_file_for_completion(file_path, planning_dir)
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
        'total_files_analyzed': len(results),
        'files_with_completion': len(completed_files),
        'files_without_completion': len(results) - len(completed_files),
        'total_completion_markers': sum(r.get('completion_count', 0) for r in completed_files),
        'category_summary': category_summary,
        'all_results': results
    }

if __name__ == "__main__":
    planning_dir = '/opt/aitbc/docs/10_plan'
    output_file = 'specific_files_analysis.json'
    
    analysis_results = analyze_all_specific_files(planning_dir)
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(analysis_results, f, indent=2)
    
    # Print summary
    print(f"Specific files analysis complete:")
    print(f"  Total files analyzed: {analysis_results['total_files_analyzed']}")
    print(f"  Files with completion: {analysis_results['files_with_completion']}")
    print(f"  Files without completion: {analysis_results['files_without_completion']}")
    print(f"  Total completion markers: {analysis_results['total_completion_markers']}")
    print("")
    print("Files with completion by category:")
    for category, summary in analysis_results['category_summary'].items():
        print(f"  {category}: {summary['total_files']} files, {summary['total_completion_count']} markers")
