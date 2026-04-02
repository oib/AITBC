# Project Root Directory Organization

## Changes Made

### Files Moved from Root to Subdirectories:

#### 📁 project-config/
- `pyproject.toml` - Python project configuration
- `requirements.txt` - Python dependencies  
- `poetry.lock` - Dependency lock file
- `.gitignore` - Git ignore rules
- `.deployment_progress` - Deployment tracking
- `=26.0` - Version marker

#### 📁 documentation/
- `README.md` - Main project documentation
- `SETUP.md` - Setup instructions
- `PYTHON_VERSION_STATUS.md` - Python compatibility
- `AITBC1_TEST_COMMANDS.md` - Testing commands
- `AITBC1_UPDATED_COMMANDS.md` - Updated commands

#### 📁 security/
- `SECURITY_VULNERABILITY_REPORT.md` - Security analysis
- `SECURITY_FIXES_SUMMARY.md` - Security fixes summary

#### 📁 backup-config/
- `aitbc-cli.backup` - Backup of old CLI wrapper

### Files Remaining in Root:
- `LICENSE` - Project license (essential)
- `README.md` - New root README with structure guide
- `aitbc-cli` - CLI symlink (essential)
- All directories (apps/, cli/, scripts/, etc.)

### Scripts Updated:
- `scripts/setup.sh` - Updated requirements.txt path
- `scripts/dependency-management/update-dependencies.sh` - Updated pyproject.toml path
- All scripts updated via `scripts/maintenance/update-file-references.sh`

## Benefits:
1. **Cleaner Root**: Only essential files at root level
2. **Better Organization**: Logical grouping of configuration files
3. **Easier Maintenance**: Related files grouped together
4. **Clearer Structure**: New README explains organization
5. **Preserved Functionality**: All references updated

## Root Directory Structure:
```
/opt/aitbc/
├── LICENSE                    # Essential
├── README.md                  # Essential (new)
├── aitbc-cli                  # Essential (symlink)
├── aitbc/                     # Core package
├── apps/                      # Applications
├── cli/                       # CLI implementation
├── scripts/                   # Automation scripts
├── project-config/            # Configuration files
├── documentation/             # User docs
├── security/                  # Security reports
├── backup-config/             # Backups
└── [other directories...]     # Unchanged
```

---
**Status**: Root directory organized ✅
