# Plugin Service Migration - v0.4.7

**Release**: v0.4.7
**Date**: June 5, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.7 migrates the plugin service (port 8109) into the marketplace service (port 8102), consolidating marketplace functionality and providing database-backed persistence.

## Architecture Change

### Before
- aitbc-plugin.service (8109) - JSON file registry at `/var/lib/aitbc/plugins.json`
- Separate service to manage
- File-based storage

### After
- SoftwareService table in marketplace database
- Part of aitbc-marketplace.service (8102)
- Database-backed with better scalability

## New Endpoints

Software service registry is now available at:
- `GET /v1/marketplace/software-services` - List all software services
- `GET /v1/marketplace/software-services/{plugin_id}` - Get specific service
- `POST /v1/marketplace/software-services` - Register/update service
- `DELETE /v1/marketplace/software-services/{plugin_id}` - Unregister service

## API Gateway Routing

Legacy `/v1/plugin/*` requests are automatically rewritten to `/v1/marketplace/software-services/*`:
```
/v1/plugin/plugins → /v1/marketplace/software-services
/v1/plugin/{id} → /v1/marketplace/software-services/{id}
```

## Migration Script

Migration script at `/opt/aitbc/scripts/migration/migrate_plugin_to_marketplace.py`:
- Backs up original JSON file to `/var/lib/aitbc/plugins.json.backup`
- Converts JSON entries to SoftwareService database records
- Preserves all metadata (deployment_type, gpu_name, gpu_offer_id)
- 2 entries migrated successfully (ollama-llama3.2-3b, whisper-base)

## Service Decommission

- aitbc-plugin.service stopped and disabled
- Systemd symlink removed
- Port 8109 no longer in use
- Original JSON file preserved for reference

## Results

- ✅ Plugin service (port 8109) migrated into marketplace service (port 8102)
- ✅ SoftwareService model added to marketplace database
- ✅ Software service endpoints added to marketplace API (`/v1/marketplace/software-services/*`)
- ✅ CLI updated to register with marketplace service
- ✅ API Gateway updated to route plugin requests to marketplace service
- ✅ Migration script created and executed (2 entries migrated)
- ✅ aitbc-plugin.service decommissioned
- ✅ Database-backed registry replaces JSON file store

---

*Last Updated: 2026-06-05*
