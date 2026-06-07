# pyenv Migration Documentation

**Date**: June 7, 2026
**Migration**: System-linked venv → pyenv-independent venv → System venv (systemd compatibility)
**Python Version**: 3.13.5 → 3.13.13 → 3.13.5 (system)
**Status**: ✅ Complete - All services running, pyenv purged

## Overview

The AITBC project attempted migration from a system-linked virtual environment to an independent virtual environment managed by pyenv. However, due to systemd compatibility issues with pyenv symlinks, the project was reverted to a system-linked venv with updated dependencies. The security improvements from pnpm migration remain in place. **pyenv was subsequently purged from the system** as it cannot be used in production.

## Migration Summary

### Before Migration
- **Python Version**: 3.13.5 (system-linked)
- **Virtual Environment**: `/opt/aitbc/venv` (linked to `/usr/bin/python3`)
- **Dependency Management**: System package manager
- **Stability**: Affected by system updates

### After Migration (Final)
- **Python Version**: 3.13.5 (system-linked)
- **Virtual Environment**: `/opt/aitbc/venv` (system venv)
- **Dependency Management**: pip + updated dependencies
- **Stability**: System-linked but with updated security packages
- **Security**: 0 vulnerabilities (pnpm migration retained)

### Issues Encountered
- **Systemd Compatibility**: pyenv symlink structure caused systemd to fail with "Unable to locate executable"
- **Service Failures**: Multiple services (aitbc-blockchain-node, aitbc-api-gateway) failed to start
- **User Configuration**: aitbc-api-gateway.service referenced non-existent user 'aitbc'
- **Resolution**: Reverted to system venv, fixed user configuration, retained pnpm security improvements, purged pyenv

## Migration Steps Completed

### 1. Installed pyenv ✅
```bash
curl https://pyenv.run | bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"
```

### 2. Installed Python 3.13.13 via pyenv ✅
```bash
pyenv install 3.13.13
```

### 3. Created New Independent venv ✅ (Later reverted)
```bash
# Backed up old venv
mv /opt/aitbc/venv /opt/aitbc/venv.backup

# Created new venv with pyenv Python
$HOME/.pyenv/versions/3.13.13/bin/python -m venv /opt/aitbc/venv
```

### 4. Migrated Dependencies ✅
```bash
# Updated pip and installed poetry
/opt/aitbc/venv/bin/pip install --upgrade pip
/opt/aitbc/venv/bin/pip install poetry

# Updated pyproject.toml for Python 3.13.13 compatibility
# Fixed torchvision Python requirement
python = ">=3.13.5,<3.14.1 || >3.14.1,<3.15"

# Regenerated lock file and installed dependencies
cd /opt/aitbc
/opt/aitbc/venv/bin/poetry lock
/opt/aitbc/venv/bin/poetry install
```

### 5. Updated Project Configuration ✅
- Updated `pyproject.toml` Python version requirement
- Updated mypy Python version to 3.13.13
- Fixed torchvision compatibility issue

### 6. Tested New Setup ⚠️ (Systemd compatibility issues)
- Verified Python version: 3.13.13 ✅
- Tested key imports: fastapi, web3, cryptography, torch ✅
- Verified AITBC import with poetry ✅
- **Systemd services failed** with "Unable to locate executable" ❌

### 7. Reverted to System venv ✅
```bash
# Stopped all services
systemctl stop aitbc-*.service

# Recreated system venv
rm -rf /opt/aitbc/venv
/usr/bin/python3 -m venv /opt/aitbc/venv

# Reinstalled dependencies
/opt/aitbc/venv/bin/pip install --upgrade pip
cd /opt/aitbc
/opt/aitbc/venv/bin/pip install -e .

# Fixed service configuration
# Updated aitbc-api-gateway.service to use root user instead of non-existent aitbc user

# Restarted services
systemctl start aitbc-*.service
```

### 8. Final Verification ✅
- All systemd services running successfully
- Python 3.13.5 (system-linked)
- All dependencies installed
- pnpm security improvements retained

### 9. pyenv Cleanup ✅
```bash
# Stopped all services
systemctl stop aitbc-*.service

# Removed pyenv installation
rm -rf /root/.pyenv

# Removed pyenv configuration from .bashrc
sed -i '/PYENV_ROOT/d' ~/.bashrc
sed -i '/pyenv init/d' ~/.bashrc
sed -i '/pyenv virtualenv-init/d' ~/.bashrc

# Removed backup venv
rm -rf /opt/aitbc/venv.backup

# Restarted services
systemctl start aitbc-*.service
```

## Benefits Achieved

### Security Improvements (Retained)
- **0 vulnerabilities** in JavaScript/TypeScript dependencies (pnpm migration)
- **Updated Python dependencies** with security patches
- **Automated security scanning** in CI/CD workflows
- **pyjwt upgraded** from 2.8.0 to 2.9.0

### System venv Benefits
- **Systemd compatibility**: No symlink issues with systemd
- **Stable service execution**: All services running successfully
- **Simplified maintenance**: System-managed Python version
- **Production reliability**: Proven configuration

### Lessons Learned
- **Systemd and pyenv**: pyenv symlink structure incompatible with systemd ExecStart
- **Service configuration**: Always verify user accounts exist in service files
- **Migration testing**: Test systemd services before finalizing environment changes
- **Security vs. compatibility**: Balance security improvements with system stability

## Usage

### Using the Current venv (System-linked)

#### Direct Python
```bash
/opt/aitbc/venv/bin/python --version  # Python 3.13.5
/opt/aitbc/venv/bin/python -c "import sys; print(sys.version)"
/opt/aitbc/venv/bin/python -c "import aitbc; print('AITBC imported successfully')"
```

#### Development
```bash
cd /opt/aitbc
/opt/aitbc/venv/bin/pip install -e .
/opt/aitbc/venv/bin/pip install <package>
```

#### Systemd Services
```bash
systemctl status aitbc-*.service
systemctl restart aitbc-*.service
```

### Note on pyenv

**pyenv was installed but later purged** due to systemd compatibility issues. The system venv is used for production to ensure systemd compatibility. Future Python version upgrades should:

1. Test systemd compatibility before deployment
2. Consider using system Python packages or containerization
3. Avoid symlink-based Python management for systemd services

## Configuration Changes

### pyproject.toml
```toml
# Python version requirement (retained for future compatibility)
python = ">=3.13.5,<3.14.1 || >3.14.1,<3.15"

# mypy version (updated to system version)
[tool.mypy]
python_version = "3.13.5"
```

### Service Configuration
**aitbc-api-gateway.service** - Fixed user configuration:
```ini
# Before (incorrect)
User=aitbc

# After (correct)
User=root
Group=root
```

### Environment Setup
**Note**: pyenv configuration has been removed from `~/.bashrc` since pyenv was purged due to systemd incompatibility.

## Troubleshooting

### Systemd Services Not Starting
```bash
# Check service status
systemctl status aitbc-*.service

# Check logs
journalctl -u aitbc-*.service -n 50

# Common issues:
# 1. User does not exist - fix service file User/Group directives
# 2. Python executable not found - verify venv structure
# 3. Missing dependencies - install with pip install -e .
```

### Dependencies Not Found
```bash
cd /opt/aitbc
/opt/aitbc/venv/bin/pip install -e .
/opt/aitbc/venv/bin/pip install <missing-package>
```

### Python Version Issues
```bash
# Check current version
/opt/aitbc/venv/bin/python --version

# Recreate venv if needed
systemctl stop aitbc-*.service
rm -rf /opt/aitbc/venv
/usr/bin/python3 -m venv /opt/aitbc/venv
/opt/aitbc/venv/bin/pip install --upgrade pip
cd /opt/aitbc
/opt/aitbc/venv/bin/pip install -e .
systemctl start aitbc-*.service
```

## Rollback Plan

If issues arise, rollback to previous setup:

```bash
# Stop all services
systemctl stop aitbc-*.service

# Restore backup (if available)
rm -rf /opt/aitbc/venv
mv /opt/aitbc/venv.backup /opt/aitbc/venv

# Or recreate system venv
/usr/bin/python3 -m venv /opt/aitbc/venv
/opt/aitbc/venv/bin/pip install --upgrade pip
cd /opt/aitbc
/opt/aitbc/venv/bin/pip install -e .

# Restart services
systemctl start aitbc-*.service
```

## Future Python Upgrades

When new Python versions become available:

1. **Test new version**: Install and test in development environment
2. **Update pyproject.toml**: Adjust Python version requirements
3. **Test systemd compatibility**: Ensure new version works with systemd
4. **Recreate venv**: Create new venv with new Python version
5. **Test dependencies**: Ensure all packages work with new version
6. **Update documentation**: Document the upgrade process

**Note**: Consider systemd compatibility when planning Python version upgrades. System venv is recommended for production services.

## Monitoring

### Check Python Version
```bash
/opt/aitbc/venv/bin/python --version
```

### Check Dependencies
```bash
cd /opt/aitbc
/opt/aitbc/venv/bin/pip list
```

### Check Service Status
```bash
systemctl status aitbc-*.service
journalctl -u aitbc-*.service -f
```

## References

- [Poetry Documentation](https://python-poetry.org/docs/)
- [Python Version Management](https://docs.python.org/3/using/windows.html)
- [Systemd Service Management](https://www.freedesktop.org/software/systemd/man/systemd.service.html)

---

**Migration Status**: ✅ Complete (with adjustments)
**Backup Location**: Removed (purged)
**Current Python**: 3.13.5 (system-linked)
**Current venv**: `/opt/aitbc/venv` (system venv)
**Security Status**: 0 vulnerabilities (pnpm migration retained)
**Service Status**: All services running successfully
**pyenv Status**: Purged due to systemd incompatibility
