# Prerequisites

This guide covers the system and software requirements for installing AITBC.

## System Requirements

- **Operating System**: Ubuntu Linux (20.04 LTS or later recommended)
- **Python**: 3.13.5 or higher
- **pip3**: Latest version
- **git**: Latest version
- **systemd**: For service management
- **Root privileges**: Required for installation

## Software Dependencies

### Core Requirements
- Python 3.13.5+
- pip3
- git
- systemd

### Optional Requirements
- PostgreSQL (for production databases)
- Redis (for caching and pub/sub)
- nginx (for reverse proxy)

## Verification

Check your system meets the prerequisites:

```bash
# Check Python version
python3 --version

# Check pip3
pip3 --version

# Check git
git --version

# Check systemd
systemctl --version

# Check root privileges
whoami
```

## See Also

- [Quick Start](quick-start.md)
- [Requirements Management](requirements-management.md)
