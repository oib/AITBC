# Plugin Marketplace

## Status
✅ Operational

## Overview
Marketplace plugin for discovering, installing, and managing AITBC plugins and extensions.

## Architecture

### Core Components
- **Plugin Catalog**: Catalog of available plugins
- **Plugin Installer**: Handles plugin installation and updates
- **Dependency Manager**: Manages plugin dependencies
- **Version Manager**: Handles plugin versioning
- **License Manager**: Manages plugin licenses

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Internet access for plugin downloads
- Sufficient disk space for plugins

### Installation
```bash
cd /opt/aitbc/apps/plugin-marketplace
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
PLUGIN_REGISTRY_URL=https://plugins.aitbc.com
INSTALLATION_PATH=/opt/aitbc/plugins
AUTO_UPDATE_ENABLED=false
```

### Running the Service
```bash
.venv/bin/python main.py
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Configure plugin registry
5. Run tests: `pytest tests/`

### Project Structure
```
plugin-marketplace/
├── src/
│   ├── plugin_catalog/       # Plugin catalog
│   ├── plugin_installer/    # Plugin installation
│   ├── dependency_manager/  # Dependency management
│   ├── version_manager/      # Version management
│   └── license_manager/     # License management
├── tests/                   # Test suite
└── pyproject.toml           # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run installer tests
pytest tests/test_installer.py

# Run dependency manager tests
pytest tests/test_dependencies.py
```

## API Reference

### Plugin Catalog

#### List Plugins
```http
GET /api/v1/marketplace/plugins?category=analytics&limit=20
```

#### Get Plugin Details
```http
GET /api/v1/marketplace/plugins/{plugin_id}
```

#### Search Plugins
```http
POST /api/v1/marketplace/plugins/search
Content-Type: application/json

{
  "query": "analytics",
  "filters": {
    "category": "string",
    "version": "string"
  }
}
```

### Plugin Installation

#### Install Plugin
```http
POST /api/v1/marketplace/plugins/install
Content-Type: application/json

{
  "plugin_id": "string",
  "version": "string",
  "auto_dependencies": true
}
```

#### Uninstall Plugin
```http
DELETE /api/v1/marketplace/plugins/{plugin_id}
```

#### Update Plugin
```http
POST /api/v1/marketplace/plugins/{plugin_id}/update
Content-Type: application/json

{
  "version": "string"
}
```

#### Get Installation Status
```http
GET /api/v1/marketplace/plugins/{plugin_id}/status
```

### Dependencies

#### Get Plugin Dependencies
```http
GET /api/v1/marketplace/plugins/{plugin_id}/dependencies
```

#### Resolve Dependencies
```http
POST /api/v1/marketplace/dependencies/resolve
Content-Type: application/json

{
  "plugin_ids": ["plugin1", "plugin2"]
}
```

### Versions

#### List Plugin Versions
```http
GET /api/v1/marketplace/plugins/{plugin_id}/versions
```

#### Get Version Compatibility
```http
GET /api/v1/marketplace/plugins/{plugin_id}/compatibility?version=1.0.0
```

### Licenses

#### Validate License
```http
POST /api/v1/marketplace/licenses/validate
Content-Type: application/json

{
  "plugin_id": "string",
  "license_key": "string"
}
```

#### Get License Info
```http
GET /api/v1/marketplace/plugins/{plugin_id}/license
```

## Configuration

### Environment Variables
- `PLUGIN_REGISTRY_URL`: URL for plugin registry
- `INSTALLATION_PATH`: Path for plugin installation
- `AUTO_UPDATE_ENABLED`: Enable automatic plugin updates
- `MAX_CONCURRENT_INSTALLS`: Maximum concurrent installations

### Plugin Categories
- **Analytics**: Data analysis and reporting plugins
- **Security**: Security scanning and monitoring plugins
- **Infrastructure**: Infrastructure management plugins
- **Trading**: Trading and exchange plugins

### Installation Parameters
- **Installation Path**: Directory for plugin installation
- **Dependency Resolution**: Automatic dependency handling
- **Version Constraints**: Version compatibility checks

## Troubleshooting

**Plugin installation failed**: Check plugin compatibility and dependencies.

**License validation failed**: Verify license key and plugin ID.

**Dependency resolution failed**: Check dependency conflicts and versions.

**Auto-update not working**: Verify auto-update configuration and registry connectivity.

## Security Notes

- Validate plugin signatures before installation
- Scan plugins for security vulnerabilities
- Use HTTPS for plugin downloads
- Implement plugin sandboxing
- Regularly update plugins for security patches
- Monitor for malicious plugin behavior
