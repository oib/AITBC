# AITBC __init__.py Refactoring Plan

**Date**: 2026-06-16
**Goal**: Split monolithic `aitbc/__init__.py` (254 lines, 150+ lazy exports) into logical submodules

## Current State

- **File**: `/opt/aitbc/aitbc/__init__.py`
- **Lines**: 254
- **Direct imports**: 28 items
- **Lazy exports**: 150+ items via `__getattr__`
- **Problem**: Monolithic file with lazy loading makes maintenance difficult

## Refactoring Strategy

### Phase 1: Create Submodule Structure
Create logical submodules to group related exports:

1. **aitbc.api** - API utilities (api_utils module)
2. **aitbc.async_helpers** - Async utilities (async_helpers module)
3. **aitbc.blockchain** - Blockchain services (blockchain_service, web3_utils)
4. **aitbc.crypto** - Cryptography utilities (crypto.crypto, crypto.security)
5. **aitbc.database** - Database utilities (database, database_service)
6. **aitbc.decorators** - Decorators (decorators module)
7. **aitbc.events** - Event system (events module)
8. **aitbc.monitoring** - Monitoring utilities (monitoring module)
9. **aitbc.network** - Network utilities (http_client, web3_utils)
10. **aitbc.queue** - Queue management (queue_manager module)
11. **aitbc.state** - State management (state module)
12. **aitbc.testing** - Testing utilities (testing module)
13. **aitbc.utils** - General utilities (json_utils, time_utils, validation, env, paths)

### Phase 2: Migrate Direct Imports
Move direct imports to appropriate submodules while maintaining backward compatibility:

- Keep core exports in `__init__.py`: logging, constants, exceptions, middleware
- Move utility imports to `aitbc.utils` submodule
- Move service imports to appropriate submodules

### Phase 3: Update Imports Across Codebase
Search and replace imports throughout the codebase:

- `from aitbc import X` → `from aitbc.utils import X` (for utils)
- `from aitbc import X` → `from aitbc.crypto import X` (for crypto)
- etc.

### Phase 4: Remove Lazy Loading
Remove `__getattr__` and `_LAZY_EXPORTS` after all imports are updated.

### Phase 5: Verification
- Run MyPy to ensure no type errors
- Run tests to ensure functionality
- Update documentation

## Implementation Order

1. **Low-risk submodules first**: testing, events, queue, state
2. **Medium-risk submodules**: utils, decorators, async_helpers
3. **High-risk submodules**: blockchain, crypto, database, network
4. **Direct imports cleanup**: Move to appropriate submodules
5. **Lazy loading removal**: Final cleanup

## Backward Compatibility

During migration, keep `__getattr__` to support old imports. Remove only after all code is updated.
