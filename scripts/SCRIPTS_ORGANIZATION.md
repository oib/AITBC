# Scripts Directory Organization

## Overview

The AITBC scripts directory has been reorganized into functional categories for better maintainability and navigation.

## Directory Structure

### 📁 github/
GitHub and Git-related operations
- `all-prs-merged-summary.md` - Summary of merged pull requests
- `gitea-changes-review.md` - Gitea repository changes review
- `github-push-ready-summary.md` - GitHub push readiness summary
- `pr40-resolution-complete.md` - PR #40 resolution documentation
- `solve-github-prs.sh` - GitHub PR resolution script
- `solve-prs-with-poetry.sh` - PR resolution with Poetry dependency management

### 📁 sync/
Synchronization and data replication
- `bulk_sync.sh` - Bulk synchronization operations
- `fast_bulk_sync.sh` - Fast bulk synchronization
- `sync_detector.sh` - Synchronization detection and monitoring
- `sync-systemd.sh` - SystemD service synchronization

### 📁 security/
Security and audit operations
- `security_audit.py` - Comprehensive security audit script
- `security_monitor.sh` - Security monitoring and alerting

### 📁 monitoring/
System and service monitoring
- `health_check.sh` - System health checks
- `log_monitor.sh` - Log file monitoring
- `network_monitor.sh` - Network monitoring
- `monitor-prs.py` - Pull request monitoring
- `nightly_health_check.sh` - Nightly health check automation
- `production_monitoring.sh` - Production environment monitoring

### 📁 maintenance/
System maintenance and cleanup
- `cleanup-root-directory.sh` - Root directory cleanup
- `final-cleanup.sh` - Final cleanup operations
- `performance_tune.sh` - Performance tuning
- `weekly_maintenance.sh` - Weekly maintenance tasks

### 📁 deployment/
Deployment and provisioning
- `build-release.sh` - Release building automation
- `deploy_openclaw_dao.py` - OpenClaw DAO deployment
- `provision_node.sh` - Node provisioning
- `complete-agent-protocols.sh` - Complete agent protocols deployment
- `deploy.sh` - General deployment script
- `production-deploy.sh` - Production deployment
- `implement-agent-protocols.sh` - Agent protocols implementation
- `implement-ai-trading-analytics.sh` - AI trading analytics implementation

### 📁 testing/
Testing and quality assurance
- `comprehensive_e2e_test_fixed.py` - Comprehensive E2E testing
- `test_workflow.sh` - Workflow testing
- `debug-services.sh` - Service debugging
- `drain_test.py` - Drain testing
- `qa-cycle.py` - QA cycle automation
- `quick_test.py` - Quick testing
- `run_all_tests.sh` - All tests runner
- `run_test.py` - Test runner
- `scalability_validation.py` - Scalability validation
- `simple-test.sh` - Simple testing
- `test-all-services.sh` - All services testing
- `test-permissions.sh` - Permission testing

### 📁 utils/
Utility scripts and helpers
- `link-systemd.sh` - SystemD linking
- `manage-services.sh` - Service management
- `requirements_migrator.py` - Requirements migration
- `setup.sh` - System setup
- `workspace-manager.sh` - Workspace management
- `check-aitbc-services.sh` - AITBC services checking
- `check-documentation-requirements.sh` - Documentation requirements checking
- `claim-task.py` - Task claiming
- `clean-sudoers-fix.sh` - Sudoers cleanup
- `cleanup_fake_gpus_db.py` - Fake GPU database cleanup
- `cleanup_fake_gpus.py` - Fake GPU cleanup
- `complete-permission-fix.sh` - Complete permission fixes
- `create_structured_issue.py` - Structured issue creation
- `deploy_enhanced_genesis.py` - Enhanced genesis deployment
- `detect-aitbc-user.sh` - AITBC user detection
- `end_to_end_workflow.py` - End-to-end workflow
- `final-sudoers-fix.sh` - Final sudoers fixes
- `fix_database_persistence.py` - Database persistence fixes
- `fix_gpu_release.py` - GPU release fixes
- `fix-permissions.sh` - Permission fixes
- `fix-startup-issues.sh` - Startup issue fixes
- `fix-sudoers-syntax.sh` - Sudoers syntax fixes
- `generate-api-keys.py` - API key generation
- `git_helper.sh` - Git helper functions
- `git-pre-commit-hook.sh` - Git pre-commit hook
- `init_production_genesis.py` - Production genesis initialization
- `keystore.py` - Keystore management
- `organize-dev-logs.sh` - Development logs organization
- `pr-conflict-resolution-summary.md` - PR conflict resolution summary
- `quick-fix.sh` - Quick fixes
- `run_comprehensive_planning_cleanup.py` - Comprehensive planning cleanup
- `run_documentation_conversion.sh` - Documentation conversion
- `run_enhanced_planning_analysis.py` - Enhanced planning analysis
- `run_enhanced_planning_cleanup.py` - Enhanced planning cleanup
- `run_master_planning_cleanup.py` - Master planning cleanup
- `run_planning_cleanup.py` - Planning cleanup
- `run_production_node.py` - Production node runner
- `security_hardening.sh` - Security hardening
- `setup-dev-permissions.sh` - Development permissions setup
- `setup_production.py` - Production setup
- `sync.sh` - Synchronization
- `update-docs.sh` - Documentation updates
- `validate-requirements.sh` - Requirements validation
- `verify-codebase-update.sh` - Codebase update verification
- `verify-production-advanced.sh` - Advanced production verification

## Usage

### Quick Reference
```bash
# GitHub operations
./scripts/github/solve-github-prs.sh

# System monitoring
./scripts/monitoring/health_check.sh

# Deployment
./scripts/deployment/build-release.sh

# Testing
./scripts/testing/comprehensive_e2e_test_fixed.py

# Security
./scripts/security/security_audit.py

# Maintenance
./scripts/maintenance/weekly_maintenance.sh
```

### Finding Scripts
Use this README to locate the appropriate script for your needs:
1. Identify the category (GitHub, sync, security, etc.)
2. Navigate to the relevant directory
3. Run the appropriate script

## Benefits

1. **Better Organization**: Scripts grouped by functionality
2. **Easier Navigation**: Clear directory structure
3. **Maintainability**: Related scripts grouped together
4. **Scalability**: Easy to add new scripts to appropriate categories
5. **Documentation**: Clear descriptions of each script's purpose

## Maintenance

- Add new scripts to appropriate functional directories
- Update this README when adding new categories or scripts
- Keep script descriptions current and accurate
