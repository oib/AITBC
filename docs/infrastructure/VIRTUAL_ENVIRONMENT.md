# AITBC Central Virtual Environment Guide

**Last Updated**: 2026-05-28
**Version**: 3.2 (Virtual Environment Standardization)

## Overview

AITBC now uses a central Python virtual environment to manage all dependencies consistently across services. This eliminates conflicts with system Python packages and provides a clean, isolated environment for all AITBC components.

## 🏗️ Virtual Environment Structure

```
/opt/aitbc/
├── venv/                    # Central virtual environment
│   ├── bin/                # Python executables and scripts
│   ├── lib/                # Installed packages
│   └── pyvenv.cfg          # Virtual environment configuration
├── requirements.txt        # Central dependency list
├── scripts/aitbc-cli      # CLI wrapper (sources venv, execs aitbc)
└── apps/                   # AITBC applications
```

## 🚀 Quick Start

### Activate Virtual Environment

```bash
# Activate directly
source /opt/aitbc/venv/bin/activate

# Or use the repo's CLI wrapper without activating
/opt/aitbc/scripts/aitbc-cli --help
```

### CLI Usage

```bash
# CLI commands directly (wrapper handles the venv)
/opt/aitbc/scripts/aitbc-cli --help

# Or after activating the venv
aitbc --help

# Run Python scripts with the venv interpreter
/opt/aitbc/venv/bin/python script.py
```

## 📦 Package Management

### Dependencies Included

- **Web Framework**: FastAPI, Uvicorn
- **Database**: SQLAlchemy, SQLModel, Alembic
- **Security**: Cryptography, PyNaCl
- **CLI Tools**: Click, Rich, Typer
- **AI/ML**: NumPy, Pandas, OpenCV
- **Monitoring**: Prometheus Client, Structlog

### Installing New Packages

```bash
# Activate environment first
source /opt/aitbc/venv/bin/activate

# Install packages
pip install package-name

# Update requirements.txt
pip freeze > /opt/aitbc/requirements.txt
```

## 🔧 Service Integration

### Updated Services

All major AITBC services now use the central virtual environment:

- ✅ **Wallet Service**: `/opt/aitbc/venv/bin/python`
- ✅ **Exchange API**: `/opt/aitbc/venv/bin/python`
- ✅ **Coordinator API**: `/opt/aitbc/venv/bin/python`
- ✅ **Blockchain Node**: `/opt/aitbc/venv/bin/python`

### SystemD Configuration

Services automatically use the central venv via updated ExecStart paths:

```ini
[Service]
ExecStart=/opt/aitbc/venv/bin/python service_script.py
```

## 🛠️ Development Workflow

### Development Environment

```bash
# Activate for development
source /opt/aitbc/venv/bin/activate

# Run development servers
cd /opt/aitbc/apps/coordinator-api
uvicorn coordinator_api.main:app --reload

# Run tests
pytest tests/
```

### Environment Variables

The environment wrapper sets up:

```bash
PYTHONPATH=/opt/aitbc/packages/py/aitbc-sdk/src:/opt/aitbc/packages/py/aitbc-crypto/src
AITBC_VENV=/opt/aitbc/venv
PATH=/opt/aitbc/venv/bin:$PATH
```

## 🔍 Troubleshooting

### Common Issues

**Service Not Starting**

```bash
# Check if venv exists
ls -la /opt/aitbc/venv/

# Check service status
systemctl status aitbc-service-name

# Check logs
journalctl -u aitbc-service-name -n 20
```

**Missing Packages**

```bash
# Install missing package
/opt/aitbc/venv/bin/python -m pip install package-name

# Update all services
systemctl restart aitbc-*
```

**Import Errors**

```bash
# Check PYTHONPATH
echo $PYTHONPATH

# Verify package installation
/opt/aitbc/venv/bin/python -c "import package_name"
```

### Recreate Virtual Environment

```bash
# Backup current requirements
cp /opt/aitbc/requirements.txt /tmp/

# Remove and recreate
rm -rf /opt/aitbc/venv
python3 -m venv /opt/aitbc/venv
chown -R root:root /opt/aitbc/venv

# Install packages
source /opt/aitbc/venv/bin/activate
pip install -r /opt/aitbc/requirements.txt
```

## 📋 Management Commands

### Virtual Environment

```bash
# Check Python version
/opt/aitbc/venv/bin/python --version

# List installed packages
/opt/aitbc/venv/bin/python -m pip list

# Check package details
/opt/aitbc/venv/bin/python -m pip show package-name
```

### Services

```bash
# Restart all services with venv
systemctl restart aitbc-wallet aitbc-exchange

# Check service status
systemctl status aitbc-*

# View service logs
journalctl -u aitbc-service-name -f
```

## 🎯 Best Practices

1. **Use `/opt/aitbc/venv/bin/python` or `scripts/aitbc-cli`** for consistency
2. **Update requirements.txt** when adding new packages
3. **Test services** after dependency updates
4. **Monitor disk space** - venv can grow with many packages
5. **Keep dependencies minimal** - only install what's needed

## 🔄 Migration Notes

### From System Python

- No more `--break-system-packages` needed
- Clean separation from OS packages
- Consistent package versions across services

### From Multiple Venvs

- Single source of truth for dependencies
- Easier maintenance and updates
- Reduced disk usage

## 📚 Additional Resources

- [Python Virtual Environments](https://docs.python.org/3/library/venv.html)
- [Pip Documentation](https://pip.pypa.io/)

---

**Next Steps**: Use `/opt/aitbc/venv/bin/python` (or `scripts/aitbc-cli` for CLI work) for all AITBC development and operations.

- [AITBC Service Management](../infrastructure/SYSTEMD_SERVICES.md)
