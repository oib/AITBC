# aitbc.database

Database utilities for AITBC applications.

## Submodules

- `aitbc.database.connection` - Database connections
- `aitbc.database.monitoring` - Query metrics and monitoring
- `aitbc.database.pooling` - Connection pooling
- `aitbc.database.replica` - Read replica support
- `aitbc.database.utils` - Database helper functions

## Exports

- `DatabaseConnection`, `get_database_connection`
- `QueryMetrics`, `QueryMonitor`, `DatabaseMetrics`
- `create_pooled_engine`, `create_async_pooled_engine`
- `ReadReplicaManager`
- `ensure_database`, `vacuum_database`

## Usage

```python
from aitbc.database import DatabaseConnection, get_database_connection
```
