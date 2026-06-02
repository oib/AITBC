# External Provider Integrations

## Overview

The ExternalProviderService enables integration with external GPU providers (AWS, GCP, Azure).

## Features

### Provider Registration
- Register AWS, GCP, or Azure providers
- API key/secret management
- Sync interval configuration

### Resource Synchronization
- Fetch external GPU resources
- Map to internal GPU registry
- Sync status tracking

### Resource Mapping
- Bidirectional resource mapping
- Automatic internal resource creation
- Mapping persistence

## Usage Example

```python
from app.contexts.marketplace.services.external_providers import ExternalProviderService

service = ExternalProviderService(session)

# Register provider
provider = service.register_provider(
    provider_name="aws-us-east",
    provider_type="aws",
    api_key="AKIA...",
    api_secret="...",
    region="us-east-1",
    sync_interval_minutes=60
)

# Sync resources
sync_status = service.sync_resources(provider_id=provider.id)

# Map external resource
internal_gpu = service.map_to_internal(
    provider_id=provider.id,
    external_resource_id="i-12345"
)

# Check sync status
status = service.get_sync_status(provider_id=provider.id)
```
