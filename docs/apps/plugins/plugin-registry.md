# Plugin Registry

## Status
✅ Operational

## Overview
Registry plugin for managing plugin metadata, versions, and availability in the AITBC ecosystem.

## Architecture

### Core Components
- **Registry Database**: Stores plugin metadata and versions
- **Metadata Manager**: Manages plugin metadata
- **Version Controller**: Controls plugin versioning
- **Availability Checker**: Checks plugin availability
- **Indexer**: Indexes plugins for search

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- PostgreSQL database
- Storage for plugin files

### Installation
```bash
cd /opt/aitbc/apps/plugin-registry
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
DATABASE_URL=postgresql://user:pass@localhost/plugin_registry
STORAGE_PATH=/opt/aitbc/plugins/storage
INDEXING_ENABLED=true
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
4. Set up database
5. Configure storage path
6. Run tests: `pytest tests/`

### Project Structure
```
plugin-registry/
├── src/
│   ├── registry_database/    # Registry database
│   ├── metadata_manager/    # Metadata management
│   ├── version_controller/   # Version control
│   ├── availability_checker/ # Availability checking
│   └── indexer/             # Plugin indexing
├── storage/                 # Plugin storage
├── tests/                   # Test suite
└── pyproject.toml           # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run registry database tests
pytest tests/test_registry.py

# Run indexer tests
pytest tests/test_indexer.py
```

## API Reference

### Plugin Registration

#### Register Plugin
```http
POST /api/v1/registry/plugins
Content-Type: application/json

{
  "plugin_id": "string",
  "name": "string",
  "version": "1.0.0",
  "description": "string",
  "author": "string",
  "category": "string",
  "metadata": {}
}
```

#### Update Plugin Metadata
```http
PUT /api/v1/registry/plugins/{plugin_id}
Content-Type: application/json

{
  "version": "1.0.1",
  "description": "updated description",
  "metadata": {}
}
```

#### Get Plugin Metadata
```http
GET /api/v1/registry/plugins/{plugin_id}
```

### Version Management

#### Add Version
```http
POST /api/v1/registry/plugins/{plugin_id}/versions
Content-Type: application/json

{
  "version": "1.1.0",
  "changes": ["fix1", "feature2"],
  "compatibility": {}
}
```

#### List Versions
```http
GET /api/v1/registry/plugins/{plugin_id}/versions
```

#### Get Latest Version
```http
GET /api/v1/registry/plugins/{plugin_id}/latest
```

### Availability

#### Check Availability
```http
GET /api/v1/registry/plugins/{plugin_id}/availability?version=1.0.0
```

#### Update Availability
```http
POST /api/v1/registry/plugins/{plugin_id}/availability
Content-Type: application/json

{
  "version": "1.0.0",
  "available": true,
  "download_url": "string"
}
```

### Search

#### Search Plugins
```http
POST /api/v1/registry/search
Content-Type: application/json

{
  "query": "analytics",
  "filters": {
    "category": "string",
    "author": "string",
    "version": "string"
  },
  "limit": 20
}
```

#### Reindex Plugins
```http
POST /api/v1/registry/reindex
```

## Configuration

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string
- `STORAGE_PATH`: Path for plugin storage
- `INDEXING_ENABLED`: Enable plugin indexing
- `MAX_METADATA_SIZE`: Maximum metadata size

### Registry Parameters
- **Plugin ID Format**: Format for plugin identifiers
- **Version Schema**: Version numbering scheme
- **Metadata Schema**: Metadata validation schema

### Indexing
- **Full Text Search**: Enable full text search
- **Faceted Search**: Enable faceted search
- **Index Refresh Interval**: Index refresh frequency

## Troubleshooting

**Plugin registration failed**: Validate plugin metadata and version format.

**Version conflict**: Check existing versions and compatibility rules.

**Index not updating**: Verify indexing configuration and database connectivity.

**Storage full**: Review storage usage and cleanup old versions.

## Security Notes

- Validate plugin metadata on registration
- Implement access controls for registry operations
- Scan plugins for security issues
- Regularly audit registry entries
- Implement rate limiting for API endpoints
