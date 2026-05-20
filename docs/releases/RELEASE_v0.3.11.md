# AITBC v0.3.11 Release Notes

**Date**: May 20, 2026  
**Status**: ✅ Released  
**Scope**: Code Quality & Refactoring - Package naming convention standardization

## 🎯 Overview

AITBC v0.3.11 is a **code quality and refactoring release** that standardizes internal package naming conventions across the AITBC ecosystem. This release ensures all internal packages follow the `aitbc-` prefix convention for better organization and consistency.

## 🔧 Package Renaming

### Internal Package Standardization
- **ai-service → aitbc-ai**
  - Updated pyproject.toml package name
  - Renamed directory: `examples/stubs/ai-service/` → `examples/stubs/aitbc-ai/`
  - Renamed package module: `ai_service/` → `aitbc_ai/`
  - Updated health check response to use new service name
  
- **edge-api → aitbc-edge**
  - Updated pyproject.toml package name
  - Renamed directory: `apps/edge-api/` → `apps/aitbc-edge/`
  - Renamed package module: `edge_api/` → `aitbc_edge/`
  - Updated wheel packages configuration in pyproject.toml
  - Updated systemd service file reference

### Package Naming Convention Benefits
- **Consistency**: All internal packages now follow `aitbc-` prefix convention
- **Clarity**: Easier to identify AITBC-specific packages vs external dependencies
- **Organization**: Better package management and dependency resolution
- **Standards**: Aligns with Python packaging best practices

## 📋 File Changes

### Directory Structure Changes
```
examples/stubs/
  ai-service/          → aitbc-ai/
    src/
      ai_service/      → aitbc_ai/

apps/
  edge-api/            → aitbc-edge/
    src/
      edge_api/        → aitbc_edge/
```

### Configuration Updates
- Updated pyproject.toml files with new package names
- Updated wheel packages configuration
- Updated package import references
- Updated systemd service file references

### Documentation Updates
- Updated examples/stubs/README.md with new package name
- Updated docs/infrastructure/SYSTEMD_SERVICES.md with new service name
- Updated docs/releases/RELEASE_v0.3.5.md with new package name
- Updated docs/scenarios/07_ai_job_submission.md with new package path
- Updated scripts/training/stage3_ai_operations.sh with new package path

## ⚠️ Breaking Changes

### Import Path Changes
If you have custom code that imports from these packages, update your imports:

```python
# Old imports
from ai_service import main
from edge_api import main

# New imports
from aitbc_ai import main
from aitbc_edge import main
```

### Service Name Changes
Systemd service references updated:
- `aitbc-ai.service` (new name for AI service)
- `aitbc-edge.service` (new name for edge API)

### Installation Changes
If installing these packages directly, use new package names:

```bash
# Old installation
pip install ai-service edge-api

# New installation  
pip install aitbc-ai aitbc-edge
```

## 🔧 Technical Details

### Package Naming Convention
All internal AITBC packages now follow the pattern:
- `aitbc` - Main package
- `aitbc-cli` - CLI tools
- `aitbc-crypto` - Cryptography library
- `aitbc-sdk` - SDK
- `aitbc-ai` - AI services
- `aitbc-edge` - Edge API services

### Migration Impact
- 38 files changed in this refactoring
- All changes are directory/package renames
- No functional code changes
- Import statements updated across codebase
- Documentation references updated

## 🚀 Upgrade Instructions

### For Existing Installations
```bash
cd /opt/aitbc
git pull origin main
# No additional steps required - changes are structural only
```

### For Custom Import Code
Update your import statements to use new package names as shown in Breaking Changes section.

### For Systemd Services
If you have custom systemd service files, update service names:
```bash
# Update service references
sed -i 's/ai-service/aitbc-ai/g' your-service-file.service
sed -i 's/edge-api/aitbc-edge/g' your-service-file.service
sudo systemctl daemon-reload
```

## 📝 Migration Notes

### Automated Migration
Most changes are structural and don't require manual intervention:
- Directory renames handled by git
- Package imports updated in codebase
- Documentation references updated

### Manual Migration Required
Only if you have:
- Custom code importing these packages
- Custom systemd service files
- External dependencies on package names

## 🔍 Known Issues

None - this is a clean refactoring release with no functional changes.

## 🎉 Code Quality Milestone

**Package Naming Standardization**: All internal AITBC packages now follow consistent naming convention, improving code organization and maintainability.

---

*Last updated: 2026-05-20*  
*Version: 0.3.11*  
*Status: Code Quality & Refactoring Release*
