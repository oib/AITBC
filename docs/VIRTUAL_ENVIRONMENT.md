# AITBC Central Virtual Environment Guide

**Last Updated**: 2026-03-29  
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
├── aitbc-env              # Environment wrapper script
└── apps/                   # AITBC applications
```

## 🚀 Quick Start

### Activate Virtual Environment
```bash
# Use the environment wrapper (recommended)
/opt/aitbc/aitbc-env

# Or activate directly
source /opt/aitbc/venv/bin/activate
```

### CLI Usage
```bash
# Start interactive shell with CLI access
/opt/aitbc/aitbc-env

# Use CLI commands directly
/opt/aitbc/aitbc-env aitbc --help

# Run Python scripts with venv
/opt/aitbc/aitbc-env python script.py
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
/opt/aitbc/aitbc-env

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
/opt/aitbc/aitbc-env

# Run development servers
cd /opt/aitbc/apps/coordinator-api
uvicorn app.main:app --reload

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
sudo systemctl status aitbc-service-name

# Check logs
sudo journalctl -u aitbc-service-name -n 20
```

**Missing Packages**
```bash
# Install missing package
/opt/aitbc/aitbc-env pip install package-name

# Update all services
sudo systemctl restart aitbc-*
```

**Import Errors**
```bash
# Check PYTHONPATH
echo $PYTHONPATH

# Verify package installation
/opt/aitbc/aitbc-env python -c "import package_name"
```

### Recreate Virtual Environment
```bash
# Backup current requirements
cp /opt/aitbc/requirements.txt /tmp/

# Remove and recreate
sudo rm -rf /opt/aitbc/venv
sudo python3 -m venv /opt/aitbc/venv
sudo chown -R root:root /opt/aitbc/venv

# Install packages
source /opt/aitbc/venv/bin/activate
pip install -r /opt/aitbc/requirements.txt
```

## 📋 Management Commands

### Virtual Environment
```bash
# Check Python version
/opt/aitbc/aitbc-env python --version

# List installed packages
/opt/aitbc/aitbc-env pip list

# Check package details
/opt/aitbc/aitbc-env pip show package-name
```

### Services
```bash
# Restart all services with venv
sudo systemctl restart aitbc-wallet aitbc-exchange-api

# Check service status
sudo systemctl status aitbc-*

# View service logs
sudo journalctl -u aitbc-service-name -f
```

## 🎯 Best Practices

1. **Always use the environment wrapper** (`/opt/aitbc/aitbc-env`) for consistency
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
- [AITBC Service Management](../infrastructure/SYSTEMD_SERVICES.md)

---

**Next Steps**: Use `/opt/aitbc/aitbc-env` for all AITBC development and operations.
