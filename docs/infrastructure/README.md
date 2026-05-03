# AITBC Infrastructure Documentation

**Last Updated**: 2026-03-29  
**Version**: 3.2 (Infrastructure Optimization)

## Overview

This section documents the AITBC infrastructure components, runtime architecture, and system management following the latest infrastructure optimization.

## 🏗️ Recent Infrastructure Updates (March 29, 2026)

### ✅ Completed Optimizations
- **Runtime Directories**: Implemented standard Linux directory structure
  - `/var/lib/aitbc/keystore/` - Secure blockchain key storage
  - `/var/lib/aitbc/data/` - Database files and application data
  - `/var/lib/aitbc/logs/` - Application logs
  - `/etc/aitbc/` - Configuration files

- **SystemD Services**: Fixed 34+ services with system Python3
  - Replaced non-existent venv paths with `/usr/bin/python3`
  - Updated WorkingDirectory paths to correct locations
  - Created missing environment files
  - Fixed PYTHONPATH configurations

- **Service Consolidation**: Standardized agent services
  - Consolidated into `/opt/aitbc/apps/agent-services/`
  - Consistent hyphenated naming (`agent-*`)
  - Removed duplicate services
  - Updated systemd service paths

### 🔧 Infrastructure Components

#### Core Services
- **Coordinator API**: Central orchestration (Port 8000) - **⚠️ LEGACY - DISABLED, use Agent Coordinator (9001)**
- **Blockchain Node**: Core blockchain (Port 8545) 
- **Exchange API**: Trading services (Port 8001)
- **Wallet Service**: Wallet management (Port 8003)

#### Agent Services
- **Agent Registry**: Service discovery and registration
- **Agent Coordinator**: Task coordination and management
- **Agent Protocols**: Communication and messaging
- **Agent Bridge**: Service integration layer
- **Agent Compliance**: Regulatory monitoring
- **Agent Trading**: Automated trading

#### Supporting Services
- **GPU Services**: Multimodal processing
- **Marketplace Services**: Enhanced marketplace
- **Load Balancer**: Geographic distribution
- **Explorer**: Blockchain explorer

## 📁 Documentation Structure

### Core Infrastructure Files
- [Runtime Directories Guide](../RUNTIME_DIRECTORIES.md) - Standard directory structure
- [SystemD Services Guide](SYSTEMD_SERVICES.md) - Service management
- [Security Hardening Guide](SECURITY_HARDENING.md) - Security best practices

### Analysis Documents
- [AITBC Requirements Updates](documented_AITBC_Requirements_Updates_-_Comprehensive_Summary.md)
- [Requirements Validation System](documented_AITBC_Requirements_Validation_System_-_Implementat.md)
- [Genesis Protection System](documented_Genesis_Protection_System_-_Technical_Implementati.md)

### Deployment Guides
- [Codebase Update Summary](codebase-update-summary.md) - Service standardization
- [Multimodal Services Deployment](multimodal-services-deployment.md) - GPU services

## 🔒 Security Architecture

### Keystore Security
- **Location**: `/var/lib/aitbc/keystore/`
- **Permissions**: 700 (root/aitbc user only)
- **Isolation**: Separate from application code
- **Backup**: Included in system backup strategy

### Service Security
- **User Isolation**: Services run with minimal privileges
- **Path Security**: Sensitive paths properly secured
- **Environment Security**: Configuration files protected

## 🚀 Setup and Deployment

### Automated Setup
```bash
# Complete infrastructure setup
sudo bash <(curl -sSL https://raw.githubusercontent.com/oib/aitbc/main/setup.sh)
```

### Manual Setup
```bash
# Clone and setup manually
sudo git clone https://github.com/aitbc/aitbc.git /opt/aitbc
cd /opt/aitbc
sudo ./setup.sh
```

## 📊 Service Management

### Health Monitoring
```bash
# Check all services
/opt/aitbc/health-check.sh

# View logs (new locations)
tail -f /var/lib/aitbc/logs/aitbc-*.log

# SystemD control
systemctl status aitbc-*
systemctl restart aitbc-coordinator-api
```

### Runtime Directory Access
```bash
# Check keystore
ls -la /var/lib/aitbc/keystore/

# Check data directory
ls -la /var/lib/aitbc/data/

# Check logs
ls -la /var/lib/aitbc/logs/
```

## 🔄 Maintenance Procedures

### Regular Tasks
- **Log Rotation**: Automatic via logrotate
- **Service Updates**: Controlled systemd updates
- **Security Patches**: Regular system updates
- **Backup Verification**: Validate keystore backups

### Troubleshooting
- **Service Failures**: Check journalctl logs
- **Path Issues**: Verify runtime directories exist
- **Permission Issues**: Check directory permissions
- **Dependency Issues**: Verify Python3 packages

---

**Next Steps**: Review individual service documentation for specific configuration details.


## Category Overview
This section contains all documentation related to infrastructure documentation. The documented files have been automatically converted from completed planning analysis files.

---
*Auto-generated index*
