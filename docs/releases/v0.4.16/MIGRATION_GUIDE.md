# Migration Guide - v0.4.16

**Release**: v0.4.16
**Date**: June 12, 2026
**Status**: ✅ Released

## Overview

This guide provides migration instructions for the code refactoring changes in v0.4.16.

## Cache Migration

**Old Import:**
```python
from aitbc.cache import Cache
from aitbc.redis_cache import RedisCache
from aitbc.cache_decorators import cached
```

**New Import:**
```python
from aitbc.cache import Cache
from aitbc.cache.backends.redis import RedisCache
from aitbc.cache.decorators import cached
```

## HTTP Client Migration

**Old Import:**
```python
from aitbc.network.http_client import AITBCHTTPClient
```

**New Import:**
```python
from aitbc.http.client import AITBCHTTPClient
```

## Caching Module Migration

**Old Import:**
```python
from aitbc.caching import BlockchainCache
```

**New Import:**
```python
from aitbc.caching.blockchain import BlockchainCache
```

## Database Module Migration

**Old Import:**
```python
from aitbc.database import DatabaseConnection
```

**New Import:**
```python
from aitbc.database.connection import DatabaseConnection
```

## CLI Commands Migration

**Old Import:**
```python
from aitbc_cli.commands.node import node
from aitbc_cli.commands.exchange import exchange
```

**New Import:**
```python
from aitbc_cli.commands.node import node
from aitbc_cli.commands.exchange import exchange
```
*(No change - backward compatible)*

## API Modules Migration

**Old Import:**
```python
from apps.exchange.simple_exchange_api import run_server
```

**New Import:**
```python
from apps.exchange.api import run_server
```

**Old Import:**
```python
from apps.coordinator_api.src.app.main import app
```

**New Import:**
```python
from apps.coordinator-api.src.app.core import create_app
app = create_app()
```

## Deprecation Timeline

### Phase 1: Deprecation Warnings (v0.4.16)
- ✅ All old imports emit deprecation warnings
- ✅ Documentation updated with migration guide
- ✅ Team notified of upcoming changes

### Phase 2: Grace Period (v0.4.17 - v0.4.20)
- 📅 Deprecation warnings remain active
- 📅 New code should use new imports
- 📅 Old code gradually migrated

### Phase 3: Removal (v0.5.0)
- 📅 Remove thin wrapper files
- 📅 Remove deprecation warnings
- 📅 All code must use new imports

---

*Last Updated: 2026-06-12*
