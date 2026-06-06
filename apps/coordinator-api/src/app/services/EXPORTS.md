# Coordinator-API Service Exports Documentation

## Lazy Import Architecture

The coordinator-api services module uses a lazy import pattern to optimize startup performance and avoid importing all 101+ services at once. Only core services are exported in `__all__` and loaded on first access via `__getattr__`.

## Current Public API Exports

The following 4 core services are exported by default in `__all__`:

- `JobService` - Job management and scheduling
- `MinerService` - Miner coordination and management
- `MarketplaceService` - Marketplace operations
- `ExplorerService` - Blockchain exploration and analytics

## How to Import Services

### Importing Core Services (in __all__)
```python
from app.services import JobService, MinerService, MarketplaceService, ExplorerService
```

### Importing Other Services (not in __all__)
Import directly from their module:
```python
from app.services.blockchain import BlockchainService
from app.services.agent_service import AgentService
from app.services.analytics_service import AnalyticsService
```

## Adding a New Service to Public API

To make a service part of the public API:

1. Add the service name to `__all__` in `__init__.py`
2. Add an entry to `_MODULE_BY_EXPORT` mapping the service name to its module path
3. The service will be lazily loaded on first access

Example:
```python
__all__ = ["JobService", "MinerService", "MarketplaceService", "ExplorerService", "NewService"]

_MODULE_BY_EXPORT = {
    "ExplorerService": ".explorer",
    "JobService": ".jobs",
    "MarketplaceService": ".marketplace",
    "MinerService": ".miners",
    "NewService": ".new_service_module",  # Add this
}
```

## Available Service Modules

The following service modules are available (not all are exported):

- `access_control.py` - Access control and permissions
- `adaptive_learning.py` - Adaptive learning algorithms
- `agent_communication.py` - Agent-to-agent communication
- `agent_service.py` - Agent management
- `analytics_service.py` - Analytics and reporting
- `blockchain.py` - Blockchain integration
- `certification_service.py` - Certification management
- `compliance_engine.py` - Compliance checking
- `cross_chain_bridge.py` - Cross-chain operations
- `dao_governance_service.py` - DAO governance
- `enterprise_api_gateway.py` - Enterprise API gateway
- `explorer.py` - Blockchain explorer
- `federated_learning.py` - Federated learning
- `global_marketplace.py` - Global marketplace
- ... and 40+ more

## Why Lazy Loading?

1. **Performance**: Avoids importing 101+ services at startup
2. **Memory**: Only loads services that are actually used
3. **Flexibility**: Services can be added without affecting startup time
4. **Clear API**: Only core services are exported by default, others are imported explicitly

## Error Handling

If you try to import a service that is not in `__all__` and not in `_MODULE_BY_EXPORT`, you'll get:
```
AttributeError: module 'app.services' has no attribute 'ServiceName'
```

To fix this, either:
1. Import the service directly from its module
2. Add it to `__all__` and `_MODULE_BY_EXPORT` if it should be part of the public API
