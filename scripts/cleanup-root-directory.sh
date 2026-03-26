#!/bin/bash

echo "=== AITBC Root Directory Cleanup ==="
echo "Organizing files before GitHub push..."
echo ""

# Create organized directories if they don't exist
mkdir -p temp/generated-files
mkdir -p temp/analysis-results
mkdir -p temp/workspace-files
mkdir -p temp/backup-files

echo "=== Moving Generated Files ==="
# Move generated analysis files
mv archive_results.json temp/generated-files/ 2>/dev/null || echo "archive_results.json not found"
mv cleanup_results.json temp/generated-files/ 2>/dev/null || echo "cleanup_results.json not found"
mv completed_files_scan.json temp/generated-files/ 2>/dev/null || echo "completed_files_scan.json not found"
mv comprehensive_final_report.json temp/generated-files/ 2>/dev/null || echo "comprehensive_final_report.json not found"
mv comprehensive_scan_results.json temp/generated-files/ 2>/dev/null || echo "comprehensive_scan_results.json not found"
mv content_analysis_results.json temp/generated-files/ 2>/dev/null || echo "content_analysis_results.json not found"
mv content_move_results.json temp/generated-files/ 2>/dev/null || echo "content_move_results.json not found"
mv documentation_conversion_final.json temp/generated-files/ 2>/dev/null || echo "documentation_conversion_final.json not found"
mv documentation_conversion_final_report.json temp/generated-files/ 2>/dev/null || echo "documentation_conversion_final_report.json not found"
mv documentation_status_check.json temp/generated-files/ 2>/dev/null || echo "documentation_status_check.json not found"
mv generated_documentation.json temp/generated-files/ 2>/dev/null || echo "generated_documentation.json not found"
mv specific_files_analysis.json temp/generated-files/ 2>/dev/null || echo "specific_files_analysis.json not found"

echo "=== Moving Genesis Files ==="
# Move genesis files to appropriate location
mv chain_enhanced_devnet.yaml data/ 2>/dev/null || echo "chain_enhanced_devnet.yaml not found"
mv genesis_ait_devnet.yaml data/ 2>/dev/null || echo "genesis_ait_devnet.yaml not found"
mv genesis_brother_chain_1773403269.yaml data/ 2>/dev/null || echo "genesis_brother_chain_1773403269.yaml not found"
mv genesis_enhanced_devnet.yaml data/ 2>/dev/null || echo "genesis_enhanced_devnet.yaml not found"
mv genesis_enhanced_local.yaml data/ 2>/dev/null || echo "genesis_enhanced_local.yaml not found"
mv genesis_enhanced_template.yaml data/ 2>/dev/null || echo "genesis_enhanced_template.yaml not found"
mv genesis_prod.yaml data/ 2>/dev/null || echo "genesis_prod.yaml not found"
mv test_multichain_genesis.yaml data/ 2>/dev/null || echo "test_multichain_genesis.yaml not found"
mv dummy.yaml data/ 2>/dev/null || echo "dummy.yaml not found"

echo "=== Moving Workspace Files ==="
# Move workspace files
mv workspace/* temp/workspace-files/ 2>/dev/null || echo "workspace files moved"
rmdir workspace 2>/dev/null || echo "workspace directory removed or not empty"

echo "=== Moving Backup Files ==="
# Move backup files
mv backup/* temp/backup-files/ 2>/dev/null || echo "backup files moved"
mv backups/* temp/backup-files/ 2>/dev/null || echo "backups files moved"
rmdir backup backups 2>/dev/null || echo "backup directories removed or not empty"

echo "=== Moving Temporary Files ==="
# Move temporary and log files
mv health temp/generated-files/ 2>/dev/null || echo "health file moved"
mv logs/* temp/generated-files/ 2>/dev/null || echo "log files moved"
rmdir logs 2>/dev/null || echo "logs directory removed or not empty"

echo "=== Moving Development Scripts ==="
# Move development scripts to dev/scripts if not already there
mv auto_review.py dev/scripts/ 2>/dev/null || echo "auto_review.py already in dev/scripts"
mv run_test.py dev/scripts/ 2>/dev/null || echo "run_test.py already in dev/scripts"

echo "=== Moving Virtual Environments ==="
# Move virtual environments to dev directory
mv agent-venv dev/ 2>/dev/null || echo "agent-venv already in dev"
mv ai-venv dev/ 2>/dev/null || echo "ai-venv already in dev"
mv concrete-env dev/ 2>/dev/null || echo "concrete-env already in dev"

echo "=== Moving Model Directories ==="
# Move models to appropriate location
mv models/* temp/backup-files/ 2>/dev/null || echo "models files moved"
rmdir models 2>/dev/null || echo "models directory removed or not empty"

echo "=== Cleanup Complete ==="
echo ""
echo "Files organized into:"
echo "- temp/generated-files/ (analysis results, generated JSON files)"
echo "- temp/workspace-files/ (workspace contents)"
echo "- temp/backup-files/ (backup and model files)"
echo "- data/ (genesis files)"
echo "- dev/ (virtual environments and scripts)"

echo ""
echo "Root directory is now clean and organized for GitHub push!"
