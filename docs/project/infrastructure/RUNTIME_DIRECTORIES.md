# AITBC Runtime Directory Structure

This document outlines the standard Linux system directories used by AITBC for runtime data.

## Standard System Directories

### `/var/lib/aitbc/`
**Purpose**: Application data and databases
- `keystore/` - Blockchain private keys and certificates
- `data/` - Application databases (.db, .sqlite files)
- `logs/` - Application log files

### `/etc/aitbc/`
**Purpose**: Configuration files
- Environment files (.env)
- Service configuration
- Network settings

### `/var/log/aitbc/`
**Purpose**: System logging (symlinked from `/var/lib/aitbc/logs/`)

## Security & Permissions

- **Keystore**: Restricted permissions (600/700)
- **Config**: Read-only for services, writable for admin
- **Logs**: Writable by services, readable by admin

## Migration from Repo

Runtime data has been moved from `/opt/aitbc/data/` to system standard directories:
- Old: `/opt/aitbc/data/keystore/` → New: `/var/lib/aitbc/keystore/`
- Old: `/opt/aitbc/data/` → New: `/var/lib/aitbc/data/`

## SystemD Integration

Services should be updated to use these standard paths:
- `Environment=KEYSTORE_PATH=/var/lib/aitbc/keystore`
- `Environment=DB_PATH=/var/lib/aitbc/data`
- `Environment=LOG_PATH=/var/log/aitbc`
