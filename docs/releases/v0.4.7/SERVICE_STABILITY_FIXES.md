# Service Stability Fixes - v0.4.7

**Release**: v0.4.7
**Date**: June 5, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.7 resolves critical service startup issues across Coordinator API, AgentDaemon, Marketplace Service, and service dependencies.

## Issues Resolved

### 1. Coordinator API Import Errors

**Problem**: Coordinator API failed to start due to deprecated schema imports
```bash
ImportError: cannot import name 'MarketplaceBidRequest' from 'app.schemas'
```

**Solution**:
- Removed deprecated `MarketplaceBidRequest` and `MarketplaceBidView` imports from multiple files
- Updated `/opt/aitbc/apps/coordinator-api/src/app/contexts/marketplace/services/marketplace.py`
- Updated `/opt/aitbc/apps/coordinator-api/src/app/models/__init__.py`
- Service now starts successfully on port 8203

### 2. AgentDaemon Connection Issues

**Problem**: AgentDaemon unable to connect to Coordinator API
```bash
HTTPConnectionPool(host='localhost', port=8203): Max retries exceeded with url: /v1/hermes/messages/owl-hub
Connection refused
```

**Solution**:
- Fixed polling URL configuration in `/opt/aitbc/apps/agent-coordinator/scripts/hermes_polling_daemon.py`
- Updated coordinator URL from port 8107 to 8203 in `/etc/aitbc/node.env`
- Corrected endpoint path from `/api/v1/agent/messages/` to `/v1/hermes/messages/`
- AgentDaemon now successfully polls every 10 seconds

### 3. Marketplace Service Database Schema

**Problem**: Marketplace service crashed due to missing database columns
```bash
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such column: softwareservice.avg_rating
```

**Solution**:
- Added missing `avg_rating` and `rating_count` columns to `softwareservice` table
- Applied database migration: `ALTER TABLE softwareservice ADD COLUMN avg_rating FLOAT DEFAULT 0.0`
- Service now runs without database errors

### 4. Missing Dependencies

**Problem**: Coordinator API missing required Python packages
```bash
No module named 'ipfshttpclient'
```

**Solution**:
- Added `ipfshttpclient>=0.7.0` to `/opt/aitbc/requirements.txt`
- Installed dependency in virtual environment
- IPFS features now properly enabled

### 5. Service Management Issues

**Problem**: Marketplace service unit file missing from systemd
```bash
Failed to restart aitbc-marketplace.service: Unit aitbc-marketplace.service not found
```

**Solution**:
- Recreated systemd symlink: `ln -s /opt/aitbc/apps/marketplace/aitbc-marketplace.service /etc/systemd/system/`
- Reloaded systemd daemon
- Service now properly manageable with systemctl commands

## Current Service Status (2026-06-05)

- ✅ **aitbc-coordinator-api.service**: Running on port 8203, Hermes endpoints operational
- ✅ **aitbc-agent-daemon.service**: Running, polling successfully every 10 seconds
- ✅ **aitbc-marketplace.service**: Running, database schema updated and healthy
- ✅ **All dependencies**: Installed and functional

## Results

- ✅ **Coordinator API**: Fixed import errors and deprecated schema references
- ✅ **AgentDaemon**: Resolved polling URL configuration and endpoint connectivity
- ✅ **Marketplace Service**: Fixed database schema with missing rating columns
- ✅ **Service Dependencies**: Resolved missing ipfshttpclient and other dependencies
- ✅ **Service Management**: Fixed systemd service unit file linking
- ✅ **Database Migrations**: Applied schema updates for rating system functionality

---

*Last Updated: 2026-06-05*
