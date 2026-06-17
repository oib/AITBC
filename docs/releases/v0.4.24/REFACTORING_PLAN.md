# AITBC __init__.py Refactoring Plan

**Date**: 2026-06-17
**Last Updated**: 2026-06-17
**Goal**: Split monolithic `aitbc/__init__.py` (248 lines, 150+ lazy exports) into logical submodules
**Status**: 📋 Planning Phase - Not Started
**Estimated Effort**: 8-12 hours
**Risk Level**: Medium (requires careful import migration)

---

## Current State Analysis

### File Structure
- **File**: `/opt/aitbc/aitbc/__init__.py`
- **Lines**: 248
- **Size**: 7,662 bytes
- **Direct imports**: 37 items (lines 12-72)
- **Lazy exports**: 150+ items via `_LAZY_EXPORTS` dict (lines 74-189)
- **Lazy loading mechanism**: `__getattr__` function (lines 192-197)

### Current Direct Imports (Lines 12-72)
**Logging (lines 12-17)**:
- `configure_logging`, `get_blockchain_logger`, `get_logger`, `setup_logger`
- Source: `aitbc.aitbc_logging`

**Constants (lines 18-33)**:
- `AGENT_COORDINATOR_PORT`, `BLOCKCHAIN_DATA_DIR`, `BLOCKCHAIN_P2P_PORT`, `BLOCKCHAIN_RPC_PORT`
- `CONFIG_DIR`, `DATA_DIR`, `ENV_FILE`, `KEYSTORE_DIR`, `LOG_DIR`, `MARKETPLACE_DATA_DIR`
- `NODE_ENV_FILE`, `PACKAGE_VERSION`, `REPO_DIR`
- Source: `aitbc.constants`

**Exceptions (lines 34-46)**:
- `AITBCError`, `AuthenticationError`, `BridgeError`, `CircuitBreakerOpenError`
- `ConfigurationError`, `DatabaseError`, `EncryptionError`, `NetworkError`
- `RateLimitError`, `RetryError`, `ValidationError`
- Source: `aitbc.exceptions`

**Middleware (lines 47-52)**:
- `ErrorHandlerMiddleware`, `PerformanceLoggingMiddleware`, `RequestIDMiddleware`, `RequestValidationMiddleware`
- Source: `aitbc.middleware`

**Environment Utils (lines 53-60)**:
- `get_bool_env_var`, `get_env_var`, `get_float_env_var`, `get_int_env_var`, `get_list_env_var`, `get_required_env_var`
- Source: `aitbc.utils.env`

**Path Utils (lines 61-72)**:
- `ensure_dir`, `ensure_file_dir`, `get_blockchain_data_path`, `get_config_path`, `get_data_path`
- `get_keystore_path`, `get_log_path`, `get_marketplace_data_path`, `get_repo_path`, `resolve_path`
- Source: `aitbc.utils.paths`

### Current Lazy Exports (Lines 74-189)
**JSON Utils (lines 78-81)**: 9 functions → `utils.json_utils`
**Blockchain Service (lines 84-85)**: 3 classes → `blockchain_service`
**Database Service (lines 88-89)**: 3 classes → `database_service`
**HTTP Client (lines 92-93)**: 4 classes/functions → `network`
**Config (lines 96-97)**: 2 classes → `config.hierarchical_config`
**Decorators (lines 100-101)**: 6 functions → `decorators`
**Validation (lines 104-108)**: 9 functions → `utils.validation`
**Async Helpers (lines 111-115)**: 8 functions → `async_helpers`
**Time Utils (lines 117-124)**: 24 functions → `utils.time_utils`
**Database Connection (lines 127-130)**: 5 functions → `database`
**Monitoring (lines 133-134)**: 3 classes → `monitoring`
**Data Layer (lines 137-138)**: 4 classes/functions → `data_layer`
**Crypto (lines 141-146)**: 9 functions → `crypto`
**Crypto Security (lines 149-154)**: 9 functions → `crypto.security`
**Events (lines 157-161)**: 11 classes/functions → `events`
**Queue Manager (lines 164-165)**: 9 classes/functions → `queue_manager`
**State (lines 168-172)**: 10 classes → `state`
**Testing (lines 175-179)**: 9 classes/functions → `testing`
**API Utils (lines 182-189)**: 25 functions → `api_utils`

**Total Lazy Exports**: ~150 items across 19 categories

### Existing Module Structure in `/opt/aitbc/aitbc/`
The following modules already exist and can be leveraged:
- `api_utils.py` (9,495 bytes)
- `async_helpers.py` (4,640 bytes)
- `blockchain_service.py` (8,811 bytes)
- `crypto/` directory (3 files)
- `database/` directory (6 files)
- `database_service.py` (5,474 bytes)
- `decorators.py` (5,091 bytes)
- `events.py` (8,419 bytes)
- `monitoring.py` (6,805 bytes)
- `network/` directory (3 files)
- `queue_manager.py` (13,221 bytes)
- `state.py` (11,356 bytes)
- `testing.py` (12,666 bytes)
- `utils/` directory (6 files)

---

## Impact Analysis

### Codebase Import Patterns

**Direct `from aitbc import` usage** (70+ files):
- **Most common**: `get_logger` (40+ occurrences)
- **Common**: `AITBCHTTPClient` (15+ occurrences)
- **Common**: `NetworkError` (10+ occurrences)
- **Common**: `DATA_DIR`, `LOG_DIR`, `KEYSTORE_DIR` (10+ occurrences)
- **Common**: `validate_address`, `validate_hash` (5+ occurrences)
- **Less common**: Various lazy-loaded items

**Direct `from aitbc.` usage** (40+ files):
- `aitbc.aitbc_logging`
- `aitbc.exceptions`
- `aitbc.network.http_client`
- `aitbc.testing`
- `aitbc.utils.paths`
- `aitbc.utils.validation`
- `aitbc.crypto.crypto`
- `aitbc.crypto.security`
- `aitbc.blockchain_service`
- `aitbc.api_utils`
- `aitbc.queue_manager`
- `aitbc.monitoring`
- `aitbc.events`
- `aitbc.async_helpers`
- `aitbc.database`
- `aitbc.middleware`
- `aitbc.config`

**Affected Areas**:
- **Apps**: agent-coordinator, edge, hermes, trading, marketplace, governance, gpu, wallet, exchange
- **Tests**: mutants/tests, tests
- **Scripts**: generate_openapi.py, migrate_encrypt_wallets.py, generate_wrappers.py
- **Documentation**: docs/api, docs/reference

### Risk Assessment
- **High Risk**: Core infrastructure modules (blockchain, crypto, database)
- **Medium Risk**: Utility modules (utils, decorators, async_helpers)
- **Low Risk**: Testing and specialized modules (testing, events, queue, state)

---

## Detailed Refactoring Strategy

### Phase 1: Create Submodule Structure (2-3 hours)

#### 1.1 Create `aitbc.api` Submodule
**Target file**: `/opt/aitbc/aitbc/api/__init__.py`
**Source**: `aitbc.api_utils.py`
**Exports**: 25 API utility functions
**Lazy mapping**: `api_utils` → `aitbc.api`

```python
# /opt/aitbc/aitbc/api/__init__.py
from aitbc.api_utils import (
    APIResponse, PaginatedResponse, success_response, error_response,
    not_found_response, unauthorized_response, forbidden_response,
    validation_error_response, conflict_response, internal_error_response,
    PaginationParams, paginate_items, build_paginated_response,
    RateLimitHeaders, build_cors_headers, build_standard_headers,
    validate_sort_field, validate_sort_order, build_sort_params,
    filter_fields, exclude_fields, sanitize_response, merge_responses,
    get_client_ip, get_user_agent, build_request_metadata
)

__all__ = [
    "APIResponse", "PaginatedResponse", "success_response", "error_response",
    "not_found_response", "unauthorized_response", "forbidden_response",
    "validation_error_response", "conflict_response", "internal_error_response",
    "PaginationParams", "paginate_items", "build_paginated_response",
    "RateLimitHeaders", "build_cors_headers", "build_standard_headers",
    "validate_sort_field", "validate_sort_order", "build_sort_params",
    "filter_fields", "exclude_fields", "sanitize_response", "merge_responses",
    "get_client_ip", "get_user_agent", "build_request_metadata"
]
```

#### 1.2 Create `aitbc.async_helpers` Submodule
**Target file**: `/opt/aitbc/aitbc/async_helpers/__init__.py`
**Source**: `aitbc.async_helpers.py`
**Exports**: 8 async utility functions
**Lazy mapping**: `async_helpers` → `aitbc.async_helpers`

```python
# /opt/aitbc/aitbc/async_helpers/__init__.py
from aitbc.async_helpers import (
    run_sync, gather_with_concurrency, run_with_timeout, batch_process,
    sync_to_async, async_to_sync, retry_async, wait_for_condition, Timer
)

__all__ = [
    "run_sync", "gather_with_concurrency", "run_with_timeout", "batch_process",
    "sync_to_async", "async_to_sync", "retry_async", "wait_for_condition", "Timer"
]
```

#### 1.3 Create `aitbc.blockchain` Submodule
**Target file**: `/opt/aitbc/aitbc/blockchain/__init__.py`
**Source**: `aitbc.blockchain_service.py`
**Exports**: 3 blockchain service classes
**Lazy mapping**: `blockchain_service` → `aitbc.blockchain`

```python
# /opt/aitbc/aitbc/blockchain/__init__.py
from aitbc.blockchain_service import (
    BlockchainService, RPCBlockchainService, BlockchainServiceFactory
)

__all__ = [
    "BlockchainService", "RPCBlockchainService", "BlockchainServiceFactory"
]
```

#### 1.4 Create `aitbc.crypto` Submodule
**Target file**: `/opt/aitbc/aitbc/crypto/__init__.py`
**Source**: `aitbc.crypto.crypto.py`, `aitbc.crypto.security.py`
**Exports**: 18 crypto functions
**Lazy mapping**: `crypto` → `aitbc.crypto`, `crypto.security` → `aitbc.crypto.security`

```python
# /opt/aitbc/aitbc/crypto/__init__.py
from aitbc.crypto.crypto import (
    derive_ethereum_address, sign_transaction_hash, verify_signature,
    encrypt_private_key, decrypt_private_key, generate_secure_random_bytes,
    keccak256_hash, sha256_hash, validate_ethereum_address,
    generate_ethereum_private_key
)
from aitbc.crypto.security import (
    generate_token, generate_api_key, validate_token_format, validate_api_key,
    generate_secure_random_string, generate_secure_random_int, SecretManager,
    hash_password, verify_password, generate_nonce, generate_hmac, verify_hmac
)

__all__ = [
    "derive_ethereum_address", "sign_transaction_hash", "verify_signature",
    "encrypt_private_key", "decrypt_private_key", "generate_secure_random_bytes",
    "keccak256_hash", "sha256_hash", "validate_ethereum_address",
    "generate_ethereum_private_key", "generate_token", "generate_api_key",
    "validate_token_format", "validate_api_key", "generate_secure_random_string",
    "generate_secure_random_int", "SecretManager", "hash_password",
    "verify_password", "generate_nonce", "generate_hmac", "verify_hmac"
]
```

#### 1.5 Create `aitbc.database` Submodule
**Target file**: `/opt/aitbc/aitbc/database/__init__.py`
**Source**: `aitbc.database.py`, `aitbc.database_service.py`
**Exports**: 8 database classes/functions
**Lazy mapping**: `database` → `aitbc.database`, `database_service` → `aitbc.database`

```python
# /opt/aitbc/aitbc/database/__init__.py
from aitbc.database import (
    DatabaseConnection, get_database_connection, ensure_database,
    vacuum_database, get_table_info, table_exists
)
from aitbc.database_service import (
    DatabaseService, SQLiteDatabaseService, DatabaseServiceFactory
)

__all__ = [
    "DatabaseConnection", "get_database_connection", "ensure_database",
    "vacuum_database", "get_table_info", "table_exists",
    "DatabaseService", "SQLiteDatabaseService", "DatabaseServiceFactory"
]
```

#### 1.6 Create `aitbc.decorators` Submodule
**Target file**: `/opt/aitbc/aitbc/decorators/__init__.py`
**Source**: `aitbc.decorators.py`
**Exports**: 6 decorator functions
**Lazy mapping**: `decorators` → `aitbc.decorators`

```python
# /opt/aitbc/aitbc/decorators/__init__.py
from aitbc.decorators import (
    retry, timing, cache_result, validate_args, handle_exceptions,
    async_timing
)

__all__ = [
    "retry", "timing", "cache_result", "validate_args", "handle_exceptions",
    "async_timing"
]
```

#### 1.7 Create `aitbc.events` Submodule
**Target file**: `/opt/aitbc/aitbc/events/__init__.py`
**Source**: `aitbc.events.py`
**Exports**: 11 event classes/functions
**Lazy mapping**: `events` → `aitbc.events`

```python
# /opt/aitbc/aitbc/events/__init__.py
from aitbc.events import (
    Event, EventPriority, EventBus, AsyncEventBus, event_handler,
    publish_event, get_global_event_bus, set_global_event_bus,
    EventFilter, EventAggregator, EventRouter
)

__all__ = [
    "Event", "EventPriority", "EventBus", "AsyncEventBus", "event_handler",
    "publish_event", "get_global_event_bus", "set_global_event_bus",
    "EventFilter", "EventAggregator", "EventRouter"
]
```

#### 1.8 Create `aitbc.monitoring` Submodule
**Target file**: `/opt/aitbc/aitbc/monitoring/__init__.py`
**Source**: `aitbc.monitoring.py`
**Exports**: 3 monitoring classes
**Lazy mapping**: `monitoring` → `aitbc.monitoring`

```python
# /opt/aitbc/aitbc/monitoring/__init__.py
from aitbc.monitoring import (
    MetricsCollector, PerformanceTimer, HealthChecker
)

__all__ = [
    "MetricsCollector", "PerformanceTimer", "HealthChecker"
]
```

#### 1.9 Create `aitbc.network` Submodule
**Target file**: `/opt/aitbc/aitbc/network/__init__.py`
**Source**: `aitbc.network.http_client.py`
**Exports**: 4 network classes/functions
**Lazy mapping**: `network` → `aitbc.network`

```python
# /opt/aitbc/aitbc/network/__init__.py
from aitbc.network.http_client import (
    AsyncAITBCHTTPClient, AITBCHTTPClient, Web3Client, create_web3_client
)

__all__ = [
    "AsyncAITBCHTTPClient", "AITBCHTTPClient", "Web3Client", "create_web3_client"
]
```

#### 1.10 Create `aitbc.queue` Submodule
**Target file**: `/opt/aitbc/aitbc/queue/__init__.py`
**Source**: `aitbc.queue_manager.py`
**Exports**: 9 queue classes/functions
**Lazy mapping**: `queue_manager` → `aitbc.queue`

```python
# /opt/aitbc/aitbc/queue/__init__.py
from aitbc.queue_manager import (
    Job, JobStatus, JobPriority, TaskQueue, JobScheduler,
    BackgroundTaskManager, WorkerPool, debounce, throttle
)

__all__ = [
    "Job", "JobStatus", "JobPriority", "TaskQueue", "JobScheduler",
    "BackgroundTaskManager", "WorkerPool", "debounce", "throttle"
]
```

#### 1.11 Create `aitbc.state` Submodule
**Target file**: `/opt/aitbc/aitbc/state/__init__.py`
**Source**: `aitbc.state.py`
**Exports**: 10 state classes
**Lazy mapping**: `state` → `aitbc.state`

```python
# /opt/aitbc/aitbc/state/__init__.py
from aitbc.state import (
    StateTransition, StateTransitionError, StatePersistenceError,
    StateMachine, ConfigurableStateMachine, StatePersistence,
    AsyncStateMachine, StateMonitor, StateValidator, StateSnapshot
)

__all__ = [
    "StateTransition", "StateTransitionError", "StatePersistenceError",
    "StateMachine", "ConfigurableStateMachine", "StatePersistence",
    "AsyncStateMachine", "StateMonitor", "StateValidator", "StateSnapshot"
]
```

#### 1.12 Create `aitbc.testing` Submodule
**Target file**: `/opt/aitbc/aitbc/testing/__init__.py`
**Source**: `aitbc.testing.py`
**Exports**: 9 testing classes/functions
**Lazy mapping**: `testing` → `aitbc.testing`

```python
# /opt/aitbc/aitbc/testing/__init__.py
from aitbc.testing import (
    MockFactory, TestDataGenerator, TestHelpers, MockResponse,
    MockDatabase, MockCache, mock_async_call, create_mock_config,
    create_test_scenario
)

__all__ = [
    "MockFactory", "TestDataGenerator", "TestHelpers", "MockResponse",
    "MockDatabase", "MockCache", "mock_async_call", "create_mock_config",
    "create_test_scenario"
]
```

#### 1.13 Create `aitbc.utils` Submodule
**Target file**: `/opt/aitbc/aitbc/utils/__init__.py`
**Source**: `aitbc.utils.json_utils.py`, `aitbc.utils.time_utils.py`, `aitbc.utils.validation.py`, `aitbc.utils.env.py`, `aitbc.utils.paths.py`
**Exports**: 42 utility functions
**Lazy mapping**: `utils.json_utils` → `aitbc.utils`, `utils.time_utils` → `aitbc.utils`, `utils.validation` → `aitbc.utils`

```python
# /opt/aitbc/aitbc/utils/__init__.py
from aitbc.utils.json_utils import (
    load_json, save_json, merge_json, json_to_string, string_to_json,
    get_nested_value, set_nested_value, flatten_json
)
from aitbc.utils.time_utils import (
    get_utc_now, get_timestamp_utc, format_iso8601, parse_iso8601,
    timestamp_to_iso, iso_to_timestamp, format_duration, format_duration_precise,
    parse_duration, add_duration, subtract_duration, get_time_until,
    get_time_since, calculate_deadline, is_deadline_passed, get_deadline_remaining,
    format_time_ago, format_time_in, to_timezone, get_timezone_offset,
    is_business_hours, get_start_of_day, get_end_of_day, get_start_of_week,
    get_end_of_week, get_start_of_month, get_end_of_month, sleep_until,
    retry_until_deadline
)
from aitbc.utils.validation import (
    validate_address, validate_hash, validate_url, validate_port, validate_email,
    validate_non_empty, validate_positive_number, validate_range,
    validate_chain_id, validate_uuid
)
from aitbc.utils.env import (
    get_bool_env_var, get_env_var, get_float_env_var, get_int_env_var,
    get_list_env_var, get_required_env_var
)
from aitbc.utils.paths import (
    ensure_dir, ensure_file_dir, get_blockchain_data_path, get_config_path,
    get_data_path, get_keystore_path, get_log_path, get_marketplace_data_path,
    get_repo_path, resolve_path
)

__all__ = [
    # JSON utils
    "load_json", "save_json", "merge_json", "json_to_string", "string_to_json",
    "get_nested_value", "set_nested_value", "flatten_json",
    # Time utils
    "get_utc_now", "get_timestamp_utc", "format_iso8601", "parse_iso8601",
    "timestamp_to_iso", "iso_to_timestamp", "format_duration", "format_duration_precise",
    "parse_duration", "add_duration", "subtract_duration", "get_time_until",
    "get_time_since", "calculate_deadline", "is_deadline_passed", "get_deadline_remaining",
    "format_time_ago", "format_time_in", "to_timezone", "get_timezone_offset",
    "is_business_hours", "get_start_of_day", "get_end_of_day", "get_start_of_week",
    "get_end_of_week", "get_start_of_month", "get_end_of_month", "sleep_until",
    "retry_until_deadline",
    # Validation
    "validate_address", "validate_hash", "validate_url", "validate_port", "validate_email",
    "validate_non_empty", "validate_positive_number", "validate_range",
    "validate_chain_id", "validate_uuid",
    # Environment
    "get_bool_env_var", "get_env_var", "get_float_env_var", "get_int_env_var",
    "get_list_env_var", "get_required_env_var",
    # Paths
    "ensure_dir", "ensure_file_dir", "get_blockchain_data_path", "get_config_path",
    "get_data_path", "get_keystore_path", "get_log_path", "get_marketplace_data_path",
    "get_repo_path", "resolve_path"
]
```

#### 1.14 Create `aitbc.data_layer` Submodule
**Target file**: `/opt/aitbc/aitbc/data_layer/__init__.py`
**Source**: `aitbc.data_layer.py`
**Exports**: 4 data layer classes/functions
**Lazy mapping**: `data_layer` → `aitbc.data_layer`

```python
# /opt/aitbc/aitbc/data_layer/__init__.py
from aitbc.data_layer import (
    DataLayer, MockDataGenerator, RealDataFetcher, get_data_layer
)

__all__ = [
    "DataLayer", "MockDataGenerator", "RealDataFetcher", "get_data_layer"
]
```

#### 1.15 Create `aitbc.config` Submodule
**Target file**: `/opt/aitbc/aitbc/config/__init__.py`
**Source**: `aitbc.config.hierarchical_config.py`
**Exports**: 2 config classes
**Lazy mapping**: `config.hierarchical_config` → `aitbc.config`

```python
# /opt/aitbc/aitbc/config/__init__.py
from aitbc.config.hierarchical_config import (
    HierarchicalConfig, ValidatedAITBCConfig
)

__all__ = [
    "HierarchicalConfig", "ValidatedAITBCConfig"
]
```

### Phase 2: Update `__init__.py` with New Submodule Structure (1 hour)

#### 2.1 Update Lazy Export Mappings
Replace existing lazy export mappings with new submodule paths:

```python
# Updated lazy exports in /opt/aitbc/aitbc/__init__.py
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {}

# API utils → aitbc.api
for _name in (
    "APIResponse PaginatedResponse success_response error_response "
    "not_found_response unauthorized_response forbidden_response "
    "validation_error_response conflict_response internal_error_response "
    "PaginationParams paginate_items build_paginated_response "
    "RateLimitHeaders build_cors_headers build_standard_headers "
    "validate_sort_field validate_sort_order build_sort_params "
    "filter_fields exclude_fields sanitize_response merge_responses "
    "get_client_ip get_user_agent build_request_metadata"
).split():
    _LAZY_EXPORTS[_name] = ("api", _name)

# Blockchain → aitbc.blockchain
for _name in ("BlockchainService RPCBlockchainService BlockchainServiceFactory").split():
    _LAZY_EXPORTS[_name] = ("blockchain", _name)

# Database → aitbc.database
for _name in (
    "DatabaseConnection get_database_connection ensure_database vacuum_database "
    "get_table_info table_exists DatabaseService SQLiteDatabaseService DatabaseServiceFactory"
).split():
    _LAZY_EXPORTS[_name] = ("database", _name)

# Network → aitbc.network
for _name in ("AsyncAITBCHTTPClient AITBCHTTPClient Web3Client create_web3_client").split():
    _LAZY_EXPORTS[_name] = ("network", _name)

# Config → aitbc.config
for _name in ("HierarchicalConfig ValidatedAITBCConfig").split():
    _LAZY_EXPORTS[_name] = ("config", _name)

# Decorators → aitbc.decorators
for _name in ("retry timing cache_result validate_args handle_exceptions async_timing").split():
    _LAZY_EXPORTS[_name] = ("decorators", _name)

# Validation → aitbc.utils
for _name in (
    "validate_address validate_hash validate_url validate_port validate_email "
    "validate_non_empty validate_positive_number validate_range validate_chain_id validate_uuid"
).split():
    _LAZY_EXPORTS[_name] = ("utils", _name)

# Async helpers → aitbc.async_helpers
for _name in (
    "run_sync gather_with_concurrency run_with_timeout batch_process "
    "sync_to_async async_to_sync retry_async wait_for_condition Timer"
).split():
    _LAZY_EXPORTS[_name] = ("async_helpers", _name)

# Time utils → aitbc.utils
for _name in (
    "get_utc_now get_timestamp_utc format_iso8601 parse_iso8601 timestamp_to_iso iso_to_timestamp "
    "format_duration format_duration_precise parse_duration add_duration subtract_duration get_time_until "
    "get_time_since calculate_deadline is_deadline_passed get_deadline_remaining format_time_ago "
    "format_time_in to_timezone get_timezone_offset is_business_hours get_start_of_day get_end_of_day "
    "get_start_of_week get_end_of_week get_start_of_month get_end_of_month sleep_until retry_until_deadline"
).split():
    _LAZY_EXPORTS[_name] = ("utils", _name)

# JSON utils → aitbc.utils
for _name in ("load_json save_json merge_json json_to_string string_to_json get_nested_value set_nested_value flatten_json").split():
    _LAZY_EXPORTS[_name] = ("utils", _name)

# Monitoring → aitbc.monitoring
for _name in ("MetricsCollector PerformanceTimer HealthChecker").split():
    _LAZY_EXPORTS[_name] = ("monitoring", _name)

# Data layer → aitbc.data_layer
for _name in ("DataLayer MockDataGenerator RealDataFetcher get_data_layer").split():
    _LAZY_EXPORTS[_name] = ("data_layer", _name)

# Crypto → aitbc.crypto
for _name in (
    "derive_ethereum_address sign_transaction_hash verify_signature encrypt_private_key decrypt_private_key "
    "generate_secure_random_bytes keccak256_hash sha256_hash validate_ethereum_address "
    "generate_ethereum_private_key"
).split():
    _LAZY_EXPORTS[_name] = ("crypto", _name)

# Crypto security → aitbc.crypto
for _name in (
    "generate_token generate_api_key validate_token_format validate_api_key "
    "generate_secure_random_string generate_secure_random_int SecretManager "
    "hash_password verify_password generate_nonce generate_hmac verify_hmac"
).split():
    _LAZY_EXPORTS[_name] = ("crypto", _name)

# Events → aitbc.events
for _name in (
    "Event EventPriority EventBus AsyncEventBus event_handler publish_event "
    "get_global_event_bus set_global_event_bus EventFilter EventAggregator EventRouter"
).split():
    _LAZY_EXPORTS[_name] = ("events", _name)

# Queue → aitbc.queue
for _name in ("Job JobStatus JobPriority TaskQueue JobScheduler BackgroundTaskManager WorkerPool debounce throttle").split():
    _LAZY_EXPORTS[_name] = ("queue", _name)

# State → aitbc.state
for _name in (
    "StateTransition StateTransitionError StatePersistenceError StateMachine "
    "ConfigurableStateMachine StatePersistence AsyncStateMachine StateMonitor "
    "StateValidator StateSnapshot"
).split():
    _LAZY_EXPORTS[_name] = ("state", _name)

# Testing → aitbc.testing
for _name in (
    "MockFactory TestDataGenerator TestHelpers MockResponse MockDatabase MockCache "
    "mock_async_call create_mock_config create_test_scenario"
).split():
    _LAZY_EXPORTS[_name] = ("testing", _name)
```

#### 2.2 Update Direct Imports
Move utility imports to submodule while keeping core exports:

```python
# Updated direct imports in /opt/aitbc/aitbc/__init__.py
from __future__ import annotations

from importlib import import_module
from typing import Any

from ._version import __version__
from .aitbc_logging import (
    configure_logging,
    get_blockchain_logger,
    get_logger,
    setup_logger,
)
from .constants import (
    AGENT_COORDINATOR_PORT,
    BLOCKCHAIN_DATA_DIR,
    BLOCKCHAIN_P2P_PORT,
    BLOCKCHAIN_RPC_PORT,
    CONFIG_DIR,
    DATA_DIR,
    ENV_FILE,
    KEYSTORE_DIR,
    LOG_DIR,
    MARKETPLACE_DATA_DIR,
    NODE_ENV_FILE,
    PACKAGE_VERSION,
    REPO_DIR,
)
from .exceptions import (
    AITBCError,
    AuthenticationError,
    BridgeError,
    CircuitBreakerOpenError,
    ConfigurationError,
    DatabaseError,
    EncryptionError,
    NetworkError,
    RateLimitError,
    RetryError,
    ValidationError,
)
from .middleware import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
)

# Environment and path utilities moved to utils submodule
# These are now available via lazy loading from aitbc.utils
```

### Phase 3: Update Imports Across Codebase (3-4 hours)

#### 3.1 Priority 1: High-Frequency Imports (get_logger, AITBCHTTPClient, NetworkError)

**Pattern**: `from aitbc import get_logger`
**Replacement**: Keep as-is (core export, no change needed)

**Pattern**: `from aitbc import AITBCHTTPClient`
**Replacement**: `from aitbc.network import AITBCHTTPClient`

**Pattern**: `from aitbc import NetworkError`
**Replacement**: Keep as-is (core export, no change needed)

**Files to update** (15+ files):
- `/opt/aitbc/mutants/tests/verification/test_simple_import.py`
- `/opt/aitbc/mutants/tests/verification/test_minimal.py`
- `/opt/aitbc/mutants/tests/verification/test_tx_import.py`
- `/opt/aitbc/mutants/tests/verification/test_payment_integration.py`
- `/opt/aitbc/mutants/tests/verification/test_cross_node_blockchain.py`
- `/opt/aitbc/mutants/tests/verification/test_block_import_complete.py`
- `/opt/aitbc/mutants/tests/cli/test_simulate_integration.py`
- `/opt/aitbc/mutants/tests/cli/test_workflow.py`
- `/opt/aitbc/mutants/tests/cli/test_resource.py`
- `/opt/aitbc/mutants/tests/cli/test_edge_advanced.py`
- `/opt/aitbc/tests/verification/test_simple_import.py`
- `/opt/aitbc/tests/verification/test_payment_integration.py`
- `/opt/aitbc/tests/verification/test_tx_import.py`
- `/opt/aitbc/tests/verification/test_minimal.py`
- `/opt/aitbc/tests/verification/test_block_import_complete.py`

#### 3.2 Priority 2: Validation Functions

**Pattern**: `from aitbc import validate_address, validate_hash`
**Replacement**: `from aitbc.utils import validate_address, validate_hash`

**Files to update** (2 files):
- `/opt/aitbc/mutants/tests/verification/test_model_validation.py`
- `/opt/aitbc/tests/verification/test_model_validation.py`

#### 3.3 Priority 3: Constants (DATA_DIR, LOG_DIR, KEYSTORE_DIR)

**Pattern**: `from aitbc import DATA_DIR, LOG_DIR`
**Replacement**: Keep as-is (core export, no change needed)

**Files to update** (3 files):
- `/opt/aitbc/mutants/tests/fixtures/common.py`
- `/opt/aitbc/apps/wallet/aitbc-wallet-wrapper.py`
- `/opt/aitbc/scripts/generate_wrappers.py`

#### 3.4 Priority 4: Module Imports (ethereum_rpc, health_checks, api_versioning)

**Pattern**: `from aitbc import ethereum_rpc`
**Replacement**: `from aitbc import ethereum_rpc` (keep as-is, not in lazy exports)

**Pattern**: `from aitbc import health_checks`
**Replacement**: `from aitbc import health_checks` (keep as-is, not in lazy exports)

**Pattern**: `from aitbc import api_versioning`
**Replacement**: `from aitbc import api_versioning` (keep as-is, not in lazy exports)

**Files to update** (0 files - these are not in lazy exports)

#### 3.5 Priority 5: Wallet Crypto Functions

**Pattern**: `from aitbc import derive_ethereum_address`
**Replacement**: `from aitbc.crypto import derive_ethereum_address`

**Files to update** (1 file):
- `/opt/aitbc/apps/wallet/simple_daemon.py` (2 occurrences)

#### 3.6 Priority 6: Multi-Import Statements

**Pattern**: `from aitbc import ( ... )` with multiple items
**Strategy**: Split into multiple imports based on submodule

**Files to update** (5+ files):
- `/opt/aitbc/mutants/tests/test_constants.py`
- `/opt/aitbc/mutants/tests/verification/test_import_surface.py`
- `/opt/aitbc/tests/test_constants.py`
- `/opt/aitbc/tests/verification/test_import_surface.py`
- `/opt/aitbc/scripts/generate_openapi.py`

### Phase 4: Remove Lazy Loading (1 hour)

#### 4.1 Remove Lazy Export Mechanism
After all imports are updated, remove the lazy loading system:

```python
# Remove from /opt/aitbc/aitbc/__init__.py:
# Lines 74-189: _LAZY_EXPORTS dict and registration loops
# Lines 192-197: __getattr__ function
# Line 246: *_LAZY_EXPORTS.keys() from __all__
```

#### 4.2 Final __init__.py Structure
Clean, minimal __init__.py with only core exports:

```python
"""
AITBC Package
Centralized utilities for AITBC applications.
"""

from __future__ import annotations

from ._version import __version__
from .aitbc_logging import (
    configure_logging,
    get_blockchain_logger,
    get_logger,
    setup_logger,
)
from .constants import (
    AGENT_COORDINATOR_PORT,
    BLOCKCHAIN_DATA_DIR,
    BLOCKCHAIN_P2P_PORT,
    BLOCKCHAIN_RPC_PORT,
    CONFIG_DIR,
    DATA_DIR,
    ENV_FILE,
    KEYSTORE_DIR,
    LOG_DIR,
    MARKETPLACE_DATA_DIR,
    NODE_ENV_FILE,
    PACKAGE_VERSION,
    REPO_DIR,
)
from .exceptions import (
    AITBCError,
    AuthenticationError,
    BridgeError,
    CircuitBreakerOpenError,
    ConfigurationError,
    DatabaseError,
    EncryptionError,
    NetworkError,
    RateLimitError,
    RetryError,
    ValidationError,
)
from .middleware import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
)

__all__ = [
    "__version__",
    "configure_logging",
    "get_blockchain_logger",
    "get_logger",
    "setup_logger",
    "AGENT_COORDINATOR_PORT",
    "BLOCKCHAIN_DATA_DIR",
    "BLOCKCHAIN_P2P_PORT",
    "BLOCKCHAIN_RPC_PORT",
    "CONFIG_DIR",
    "DATA_DIR",
    "ENV_FILE",
    "KEYSTORE_DIR",
    "LOG_DIR",
    "MARKETPLACE_DATA_DIR",
    "NODE_ENV_FILE",
    "PACKAGE_VERSION",
    "REPO_DIR",
    "AITBCError",
    "AuthenticationError",
    "BridgeError",
    "CircuitBreakerOpenError",
    "ConfigurationError",
    "DatabaseError",
    "EncryptionError",
    "NetworkError",
    "RateLimitError",
    "RetryError",
    "ValidationError",
    "ErrorHandlerMiddleware",
    "PerformanceLoggingMiddleware",
    "RequestIDMiddleware",
    "RequestValidationMiddleware",
]
```

### Phase 5: Verification (1-2 hours)

#### 5.1 Type Checking
```bash
cd /opt/aitbc
./venv/bin/python -m mypy --show-error-codes aitbc/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/api/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/async_helpers/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/blockchain/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/crypto/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/database/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/decorators/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/events/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/monitoring/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/network/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/queue/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/state/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/testing/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/utils/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/data_layer/__init__.py
./venv/bin/python -m mypy --show-error-codes aitbc/config/__init__.py
```

#### 5.2 Import Testing
```bash
cd /opt/aitbc
./venv/bin/python -c "import aitbc; print('Core imports OK')"
./venv/bin/python -c "from aitbc.api import APIResponse; print('API imports OK')"
./venv/bin/python -c "from aitbc.async_helpers import run_sync; print('Async imports OK')"
./venv/bin/python -c "from aitbc.blockchain import BlockchainService; print('Blockchain imports OK')"
./venv/bin/python -c "from aitbc.crypto import derive_ethereum_address; print('Crypto imports OK')"
./venv/bin/python -c "from aitbc.database import DatabaseService; print('Database imports OK')"
./venv/bin/python -c "from aitbc.decorators import retry; print('Decorator imports OK')"
./venv/bin/python -c "from aitbc.events import EventBus; print('Events imports OK')"
./venv/bin/python -c "from aitbc.monitoring import MetricsCollector; print('Monitoring imports OK')"
./venv/bin/python -c "from aitbc.network import AITBCHTTPClient; print('Network imports OK')"
./venv/bin/python -c "from aitbc.queue import TaskQueue; print('Queue imports OK')"
./venv/bin/python -c "from aitbc.state import StateMachine; print('State imports OK')"
./venv/bin/python -c "from aitbc.testing import MockFactory; print('Testing imports OK')"
./venv/bin/python -c "from aitbc.utils import validate_address; print('Utils imports OK')"
./venv/bin/python -c "from aitbc.data_layer import DataLayer; print('Data layer imports OK')"
./venv/bin/python -c "from aitbc.config import HierarchicalConfig; print('Config imports OK')"
```

#### 5.3 Application Testing
```bash
cd /opt/aitbc
# Test key applications
./venv/bin/python -c "from apps.edge.src.aitbc_edge.main import main; print('Edge app imports OK')"
./venv/bin/python -c "from apps.hermes.src.hermes_service.main import main; print('Hermes app imports OK')"
./venv/bin/python -c "from apps.trading.src.trading_service.main import main; print('Trading app imports OK')"
./venv/bin/python -c "from apps.marketplace.src.marketplace_service.main import main; print('Marketplace app imports OK')"
./venv/bin/python -c "from apps.governance.src.governance_service.main import main; print('Governance app imports OK')"
./venv/bin/python -c "from apps.gpu.src.gpu_service.main import main; print('GPU app imports OK')"
```

#### 5.4 Test Suite
```bash
cd /opt/aitbc
./venv/bin/python -m pytest tests/test_aitbc_init.py -v
./venv/bin/python -m pytest tests/verification/test_import_surface.py -v
./venv/bin/python -m pytest tests/verification/test_model_validation.py -v
./venv/bin/python -m pytest tests/verification/test_simple_import.py -v
./venv/bin/python -m pytest tests/core/test_api_versioning_module.py -v
./venv/bin/python -m pytest tests/core/test_ethereum_rpc_module.py -v
./venv/bin/python -m pytest tests/core/test_health_checks_module.py -v
```

#### 5.5 Linting
```bash
cd /opt/aitbc
./venv/bin/python -m ruff check aitbc/__init__.py
./venv/bin/python -m ruff check aitbc/api/__init__.py
./venv/bin/python -m ruff check aitbc/async_helpers/__init__.py
./venv/bin/python -m ruff check aitbc/blockchain/__init__.py
./venv/bin/python -m ruff check aitbc/crypto/__init__.py
./venv/bin/python -m ruff check aitbc/database/__init__.py
./venv/bin/python -m ruff check aitbc/decorators/__init__.py
./venv/bin/python -m ruff check aitbc/events/__init__.py
./venv/bin/python -m ruff check aitbc/monitoring/__init__.py
./venv/bin/python -m ruff check aitbc/network/__init__.py
./venv/bin/python -m ruff check aitbc/queue/__init__.py
./venv/bin/python -m ruff check aitbc/state/__init__.py
./venv/bin/python -m ruff check aitbc/testing/__init__.py
./venv/bin/python -m ruff check aitbc/utils/__init__.py
./venv/bin/python -m ruff check aitbc/data_layer/__init__.py
./venv/bin/python -m ruff check aitbc/config/__init__.py
```

---

## Implementation Order

### Iteration 1: Low-Risk Submodules (2 hours)
1. **aitbc.testing** - Only used in tests
2. **aitbc.events** - Self-contained event system
3. **aitbc.queue** - Queue management, limited usage
4. **aitbc.state** - State machine, limited usage
5. **aitbc.data_layer** - Data abstraction, limited usage
6. **aitbc.config** - Configuration, limited usage

### Iteration 2: Medium-Risk Submodules (2 hours)
7. **aitbc.utils** - High usage but well-defined boundaries
8. **aitbc.decorators** - Decorator functions, medium usage
9. **aitbc.async_helpers** - Async utilities, medium usage
10. **aitbc.api** - API utilities, medium usage
11. **aitbc.monitoring** - Monitoring utilities, medium usage

### Iteration 3: High-Risk Submodules (3 hours)
12. **aitbc.network** - HTTP client, high usage (AITBCHTTPClient)
13. **aitbc.crypto** - Cryptography, critical security functions
14. **aitbc.database** - Database services, critical infrastructure
15. **aitbc.blockchain** - Blockchain services, critical infrastructure

### Iteration 4: Direct Imports Cleanup (1 hour)
16. Move environment and path utilities to utils submodule
17. Update __all__ exports list
18. Remove redundant imports

### Iteration 5: Lazy Loading Removal (1 hour)
19. Remove _LAZY_EXPORTS dict
20. Remove __getattr__ function
21. Final verification

---

## Backward Compatibility Strategy

### During Migration (Phases 1-3)
- **Keep `__getattr__` active**: Maintain lazy loading for backward compatibility
- **Update lazy mappings**: Point to new submodule paths
- **Gradual migration**: Update imports incrementally
- **Test after each iteration**: Verify no regressions

### After Migration (Phase 4)
- **Remove lazy loading**: Delete _LAZY_EXPORTS and __getattr__
- **Clean __all__**: Remove lazy export keys
- **Final verification**: Comprehensive testing

### Rollback Plan
If issues arise during migration:
1. **Git revert**: Revert to previous commit
2. **Restore __init__.py**: Use git checkout
3. **Delete new submodules**: Remove created __init__.py files
4. **Re-run tests**: Verify system stability

---

## Success Criteria

### Functional Requirements
- ✅ All imports work correctly with new submodule structure
- ✅ All applications start without errors
- ✅ All tests pass (test suite)
- ✅ No import errors in production code

### Quality Requirements
- ✅ MyPy passes with zero errors
- ✅ Ruff linting passes with zero errors
- ✅ Code follows existing style guidelines
- ✅ Type annotations are correct

### Maintainability Requirements
- ✅ __init__.py reduced to <100 lines
- ✅ Clear separation of concerns
- ✅ Each submodule has single responsibility
- ✅ Documentation updated

### Performance Requirements
- ✅ No performance degradation
- ✅ Import time remains acceptable
- ✅ Memory usage unchanged

---

## Documentation Updates

### Files to Update
1. **`/opt/aitbc/docs/REFACTORING_PLAN.md`** - This file (mark as complete)
2. **`/opt/aitbc/docs/TYPE_CHECKING.md`** - Update type checking status
3. **`/opt/aitbc/docs/reference/faq.md`** - Update import examples
4. **`/opt/aitbc/docs/api/README.md`** - Update SDK import examples
5. **`/opt/aitbc/docs/api/examples/python-sdk-examples.md`** - Update code examples
6. **`/opt/aitbc/docs/api/coordinator/README.md`** - Update coordinator examples
7. **`/opt/aitbc/docs/api/blockchain/README.md`** - Update blockchain examples

### New Documentation
1. **`/opt/aitbc/docs/development/aitbc-module-refactoring.md`** - Detailed migration guide
2. **`/opt/aitbc/aitbc/README.md`** - Module structure overview
3. **`/opt/aitbc/aitbc/api/README.md`** - API utilities documentation
4. **`/opt/aitbc/aitbc/utils/README.md`** - Utilities documentation

---

## Risk Mitigation

### High-Risk Areas
1. **Network module (AITBCHTTPClient)**: High usage across codebase
   - **Mitigation**: Update all imports in single iteration, test thoroughly
   - **Fallback**: Keep lazy loading active if issues arise

2. **Crypto module**: Critical security functions
   - **Mitigation**: Verify all crypto operations still work correctly
   - **Fallback**: Keep lazy loading active if issues arise

3. **Database module**: Critical infrastructure
   - **Mitigation**: Test database connections and operations
   - **Fallback**: Keep lazy loading active if issues arise

### Testing Strategy
1. **Unit tests**: Test each submodule independently
2. **Integration tests**: Test cross-module interactions
3. **Application tests**: Test all applications using new imports
4. **Performance tests**: Verify no performance degradation
5. **Security tests**: Verify crypto operations remain secure

---

## Timeline

### Day 1: Setup and Low-Risk Submodules (4 hours)
- Phase 1: Create submodule structure (2-3 hours)
- Iteration 1: Low-risk submodules (2 hours)

### Day 2: Medium-Risk Submodules (2 hours)
- Iteration 2: Medium-risk submodules (2 hours)

### Day 3: High-Risk Submodules (3 hours)
- Iteration 3: High-risk submodules (3 hours)

### Day 4: Cleanup and Verification (2 hours)
- Iteration 4: Direct imports cleanup (1 hour)
- Iteration 5: Lazy loading removal (1 hour)
- Phase 5: Verification (1-2 hours)

**Total Estimated Time**: 8-12 hours over 4 days

---

## Post-Refactoring Benefits

### Maintainability
- **Reduced complexity**: __init__.py from 248 lines to ~80 lines
- **Clear separation**: Each module has single responsibility
- **Easier navigation**: Logical module structure
- **Better testing**: Each module can be tested independently

### Performance
- **Faster imports**: Direct imports instead of lazy loading
- **Better caching**: Module-level imports cached by Python
- **Predictable behavior**: No dynamic import overhead

### Developer Experience
- **Better IDE support**: Auto-completion works correctly
- **Clearer imports**: Explicit import paths
- **Easier debugging**: Direct module references
- **Better documentation**: Each module can be documented separately

---

## Checklist

### Pre-Refactoring
- [ ] Create backup branch
- [ ] Document current state
- [ ] Identify all import patterns
- [ ] Create test baseline

### Phase 1: Create Submodules
- [ ] Create aitbc/api/__init__.py
- [ ] Create aitbc/async_helpers/__init__.py
- [ ] Create aitbc/blockchain/__init__.py
- [ ] Create aitbc/crypto/__init__.py
- [ ] Create aitbc/database/__init__.py
- [ ] Create aitbc/decorators/__init__.py
- [ ] Create aitbc/events/__init__.py
- [ ] Create aitbc/monitoring/__init__.py
- [ ] Create aitbc/network/__init__.py
- [ ] Create aitbc/queue/__init__.py
- [ ] Create aitbc/state/__init__.py
- [ ] Create aitbc/testing/__init__.py
- [ ] Create aitbc/utils/__init__.py
- [ ] Create aitbc/data_layer/__init__.py
- [ ] Create aitbc/config/__init__.py

### Phase 2: Update __init__.py
- [ ] Update lazy export mappings
- [ ] Update direct imports
- [ ] Update __all__ exports
- [ ] Test backward compatibility

### Phase 3: Update Codebase
- [ ] Update AITBCHTTPClient imports (15+ files)
- [ ] Update validation imports (2 files)
- [ ] Update crypto imports (1 file)
- [ ] Update multi-import statements (5+ files)
- [ ] Test all updated files

### Phase 4: Remove Lazy Loading
- [ ] Remove _LAZY_EXPORTS dict
- [ ] Remove __getattr__ function
- [ ] Clean __all__ exports
- [ ] Final __init__.py structure

### Phase 5: Verification
- [ ] MyPy type checking
- [ ] Import testing
- [ ] Application testing
- [ ] Test suite
- [ ] Linting

### Post-Refactoring
- [ ] Update documentation
- [ ] Create migration guide
- [ ] Update release notes
- [ ] Merge to main branch
- [ ] Deploy to production

---

**Last Updated**: 2026-06-17
**Status**: 📋 Planning Phase - Not Started
**Next Steps**: Begin Phase 1 - Create Submodule Structure
