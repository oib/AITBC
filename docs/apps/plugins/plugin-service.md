# Plugin Service

**Level**: Intermediate<br>
**Prerequisites**: Familiarity with AITBC plugin architecture<br>
**Estimated Time**: 10 minutes<br>
**Last Updated**: 2026-05-03<br>
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../../README.md)** → **📦 Apps** → **🔌 Plugins** → *You are here*

**breadcrumb**: Home → Apps → Plugins → Plugin Service

---

## 🎯 **See Also:**
- **📖 [About Documentation](../../about/README.md)** - Template standard and audit checklist
- **🧭 [Master Index](../../MASTER_INDEX.md)** - Full documentation catalog
- **🔌 [Plugins Overview](./README.md)** - Plugin system overview

---

## Overview

The Plugin Service provides the infrastructure for managing and executing plugins in the AITBC ecosystem. It handles plugin registration, lifecycle management, and provides a secure execution environment for third-party extensions.

## Features

- **Plugin Registry**: Central registry for all plugins
- **Lifecycle Management**: Install, enable, disable, and remove plugins
- **Sandboxed Execution**: Secure plugin execution environment
- **Dependency Management**: Automatic dependency resolution
- **Version Control**: Support for multiple plugin versions
- **API Gateway**: Plugin API endpoints for external integration

## Architecture

The Plugin Service consists of:

- **Registry**: Stores plugin metadata and configurations
- **Loader**: Dynamically loads plugin code
- **Executor**: Runs plugin code in sandboxed environment
- **API Server**: Exposes plugin endpoints
- **Dependency Manager**: Handles plugin dependencies
- **Version Manager**: Manages plugin versions

## Installation

```bash
cd /opt/aitbc
poetry install --with plugin-service
```

## Configuration

Configuration is managed through environment variables:

```bash
# Plugin Storage
PLUGIN_STORAGE_PATH=/var/lib/aitbc/plugins

# Registry
PLUGIN_REGISTRY_URL=http://localhost:9002

# Security
PLUGIN_SANDBOX_ENABLED=true
PLUGIN_SIGNATURE_VERIFICATION=true

# API
PLUGIN_API_PORT=9003
```

## Running

### Development
```bash
cd apps/plugin-service
python -m plugin_service.main
```

### Production (systemd)
```bash
sudo systemctl start plugin-service
sudo systemctl enable plugin-service
```

## Endpoints

- `GET /health` - Health check
- `GET /plugins` - List all plugins
- `POST /plugins/install` - Install plugin from repository
- `POST /plugins/{plugin_id}/enable` - Enable plugin
- `POST /plugins/{plugin_id}/disable` - Disable plugin
- `DELETE /plugins/{plugin_id}` - Remove plugin
- `GET /plugins/{plugin_id}/info` - Get plugin information
- `GET /plugins/{plugin_id}/versions` - List plugin versions

## Plugin Development

### Plugin Structure

```
my-plugin/
├── plugin.yaml          # Plugin metadata
├── src/
│   ├── __init__.py
│   └── main.py          # Plugin entry point
├── requirements.txt     # Plugin dependencies
└── tests/              # Plugin tests
```

### plugin.yaml Example

```yaml
name: my-plugin
version: 1.0.0
description: My custom plugin
author: Your Name
license: MIT
entry_point: src.main:main
dependencies:
  - aitbc-core>=1.0.0
permissions:
  - blockchain:read
  - marketplace:read
```

### Installing a Plugin

```bash
# From local directory
curl -X POST http://localhost:9003/plugins/install \
  -F "plugin=@/path/to/plugin.tar.gz"

# From repository
curl -X POST http://localhost:9003/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"repository": "https://repo.example.com/my-plugin", "version": "1.0.0"}'
```

### Managing Plugins

```bash
# Enable plugin
curl -X POST http://localhost:9003/plugins/my-plugin/enable

# Disable plugin
curl -X POST http://localhost:9003/plugins/my-plugin/disable

# Remove plugin
curl -X DELETE http://localhost:9003/plugins/my-plugin

# Get plugin info
curl http://localhost:9003/plugins/my-plugin/info
```

## Security

- **Sandboxed Execution**: Plugins run in isolated environment
- **Signature Verification**: Plugin signatures verified before installation
- **Permission System**: Granular permission controls
- **Dependency Isolation**: Plugin dependencies isolated from core system
- **Resource Limits**: CPU and memory limits for plugin execution

## Built-in Plugins

- **Plugin Analytics**: Analytics and metrics collection
- **Plugin Marketplace**: Plugin marketplace integration
- **Plugin Registry**: Plugin registry management
- **Plugin Security**: Security scanning and validation

## Troubleshooting

### Plugin Installation Fails
1. Verify plugin signature is valid
2. Check plugin dependencies are available
3. Review plugin logs for specific errors

### Plugin Won't Enable
1. Check plugin permissions are granted
2. Verify plugin dependencies are satisfied
3. Review plugin configuration

### Plugin Execution Errors
1. Check resource limits are not exceeded
2. Verify plugin code is compatible with current version
3. Review sandbox logs for errors

## Monitoring

### Health Check
```bash
curl http://localhost:9003/health
```

### Plugin Status
```bash
curl http://localhost:9003/plugins
```

### Plugin Logs
```bash
journalctl -u plugin-service -f
```

## Related Documentation

- [Plugin Analytics](./plugin-analytics.md)
- [Plugin Marketplace](./plugin-marketplace.md)
- [Plugin Registry](./plugin-registry.md)
- [Plugin Security](./plugin-security.md)

---

*Last updated: 2026-05-03*<br>
*Version: 1.0*<br>
*Status: Active service*<br>
*Tags: plugins, extensions, service, management*
