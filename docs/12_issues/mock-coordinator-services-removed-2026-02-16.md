# Mock Coordinator Services Removal - RESOLVED

**Date:** February 16, 2026  
**Status:** Resolved  
**Severity:** Low  

## Issue Description
Mock coordinator services were running on both localhost and AITBC server environments, creating potential confusion between development and production deployments. This could lead to testing against mock data instead of real production APIs.

## Affected Components
- **Localhost**: `aitbc-mock-coordinator.service`
- **AITBC Server**: `aitbc-coordinator.service` (mock version)
- **Production**: `aitbc-coordinator-api.service` (desired service)

## Root Cause Analysis
Historical development setup included mock coordinator services for testing purposes. These were never properly cleaned up when moving to production deployment, leading to:
- Multiple coordinator services running simultaneously
- Potential routing to mock endpoints instead of production
- Confusion about which service was handling requests

## Solution Implemented

### 1. Localhost Cleanup
```bash
# Stop and disable mock service
sudo systemctl stop aitbc-mock-coordinator.service
sudo systemctl disable aitbc-mock-coordinator.service

# Remove service file
sudo rm /etc/systemd/system/aitbc-mock-coordinator.service
sudo systemctl daemon-reload
```

### 2. AITBC Server Cleanup
```bash
# Stop and disable mock service
ssh aitbc-cascade "systemctl stop aitbc-coordinator.service"
ssh aitbc-cascade "systemctl disable aitbc-coordinator.service"

# Remove service file
ssh aitbc-cascade "rm /etc/systemd/system/aitbc-coordinator.service"
ssh aitbc-cascade "systemctl daemon-reload"
```

### 3. Production Service Verification
Confirmed production services running correctly:
- **Localhost**: `aitbc-coordinator-api.service` active on port 8000
- **AITBC Server**: `aitbc-coordinator-api.service` active in container

### 4. Database Configuration Fix
Fixed database configuration issue that was preventing localhost production service from starting:
- Added missing `effective_url` property to `DatabaseConfig` class
- Fixed module path in systemd service file
- Installed missing dependency (`python-json-logger`)

## Verification
Tested both production services:

```bash
# Localhost health check
curl -s http://localhost:8000/v1/health
# Response: {"status": "ok", "env": "dev"} ✅

# AITBC Server health check  
curl -s https://aitbc.bubuit.net/api/health
# Response: {"status": "ok", "env": "dev"} ✅
```

## Service Configuration Differences

### Before Cleanup
- **Localhost**: Mock service + broken production service
- **AITBC Server**: Mock service + working production service

### After Cleanup
- **Localhost**: Working production service only
- **AITBC Server**: Working production service only

## Impact
- **Clarity**: Clear separation between development and production environments
- **Reliability**: Production requests no longer risk hitting mock endpoints
- **Maintenance**: Reduced service footprint and complexity
- **Performance**: Eliminated redundant services

## Lessons Learned
1. **Service Hygiene**: Always clean up mock/test services before production deployment
2. **Documentation**: Keep accurate inventory of running services
3. **Configuration**: Ensure production services have correct paths and dependencies
4. **Verification**: Test both environments after configuration changes

## Current Service Status

### Localhost Services
- ✅ `aitbc-coordinator-api.service` - Production API (active)
- ❌ `aitbc-mock-coordinator.service` - Mock API (removed)

### AITBC Server Services  
- ✅ `aitbc-coordinator-api.service` - Production API (active)
- ❌ `aitbc-coordinator.service` - Mock API (removed)

## Related Documentation
- [Infrastructure Documentation](/docs/infrastructure.md)
- [Service Management Guidelines](/docs/operations/service-management.md)
- [Development vs Production Environments](/docs/development/environments.md)
