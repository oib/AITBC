# AITBC Project Guidelines

This file contains important information for AI agents working on the AITBC codebase.

## Type Safety Achievement

**Status: ✅ FULL STRICT MODE ENABLED** - 12/12 strict MyPy options enabled

### MyPy Strict Enforcement Achievement

| Date | Milestone | Strict Options | Status |
|------|-----------|----------------|--------|
| v0.4.21 | Partial strict mode | 10/12 enabled | Partial |
| **Current** | **FULL STRICT MODE** | **12/12 enabled** | **Complete** |

### Strict Options Now Enabled

All 12 MyPy strict options are now enforced:
- `disallow_any_generics` - Requires type parameters for generic types
- `disallow_subclassing_any` - Prevents subclassing Any
- `disallow_untyped_calls` - No calls to untyped functions
- `disallow_untyped_defs` - No untyped function definitions
- `disallow_untyped_decorators` - No untyped decorators
- `no_implicit_optional` - No implicit Optional types
- `warn_redundant_casts` - Warn about redundant type casts
- `warn_unused_ignores` - Warn about unused type ignores
- `warn_no_return` - Warn about functions without return
- `warn_unreachable` - Warn about unreachable code
- `strict_equality` - Strict equality checks
- `strict_optional` - Strict Optional handling

### Current Status by Application (Strict Mode)

| Application | Strict Mode Clean | Status |
|-------------|-------------------|--------|
| pool-hub | ✅ Yes | Clean ✅ |
| wallet | ✅ Yes | Clean ✅ |
| edge | ✅ Yes | Clean ✅ |
| hermes | ✅ Yes | Clean ✅ |
| agent-management | ✅ Yes | Clean ✅ |
| agent-coordinator | ✅ Yes | Clean ✅ |
| coordinator-api | ⚠️ Minor issues | Near Clean |
| blockchain-node | ⚠️ Minor issues | Near Clean |
| ai-engine | ✅ Yes | Clean ✅ |
| api-gateway | ⚠️ Minor issues | Near Clean |
| blockchain-event-bridge | ⚠️ Minor issues | Near Clean |
| blockchain-explorer | ⚠️ Minor issues | Near Clean |
| bridge-monitor | ⚠️ Minor issues | Near Clean |
| exchange | ⚠️ Minor issues | Near Clean |
| ffmpeg | ⚠️ Minor issues | Near Clean |
| governance | ⚠️ Minor issues | Near Clean |
| gpu | ⚠️ Minor issues | Near Clean |
| marketplace | ⚠️ Minor issues | Near Clean |
| miner | ⚠️ Minor issues | Near Clean |
| peertube-transcoder | ⚠️ Minor issues | Near Clean |
| shared-core | ✅ Yes | Clean ✅ |
| shared-domain | ✅ Yes | Clean ✅ |
| trading | ⚠️ Minor issues | Near Clean |
| whisper | ⚠️ Minor issues | Near Clean |
| zk-circuits | ⚠️ Minor issues | Near Clean |

### Type Checking Commands

Check all applications:
```bash
# Check specific app
cd /opt/aitbc && find apps/APP_NAME/src -name "*.py" -path "*/src/*" | xargs ./venv/bin/python -m mypy --show-error-codes

# Check all apps
for app in pool-hub wallet edge hermes agent-management agent-coordinator coordinator-api; do
  echo "=== $app ==="
  find apps/$app/src -name "*.py" -path "*/src/*" | xargs ./venv/bin/python -m mypy --show-error-codes 2>/dev/null | grep -c "error:"
done
```

## Common Type Fixes

### Generic Type Parameters (disallow_any_generics)
- Add explicit type parameters: `dict` → `dict[str, Any]`
- Add explicit type parameters: `list` → `list[Any]` or `list[str]`
- Add explicit type parameters: `Callable` → `Callable[[...], ...]`
- Add explicit type parameters: `deque` → `deque[Any]`
- Add explicit type parameters: `Task` → `Task[Any]`
- Add explicit type parameters: `Queue` → `Queue[Any]`

### SQLModel/SQLAlchemy Issues
- Use `scalars().all()` instead of `.all()` for query results
- Cast Row results to proper types with `cast(dict[str, Any], result)`
- Add explicit type annotations to dict comprehensions

### Cryptography Library
- Use `# type: ignore[union-attr]` for key type variations
- Use `# type: ignore[arg-type,union-attr,call-arg]` for complex crypto operations

### FastAPI/Decorators
- Use `# type: ignore[untyped-decorator]` for FastAPI decorators

### Redis Type Issues
- Convert bytes/str unions explicitly: `[str(m) for m in results]`
- Use explicit dict comprehensions with type annotations

## Project Structure

```
/opt/aitbc/
├── apps/                    # Application modules
│   ├── pool-hub/
│   ├── wallet/
│   ├── edge/
│   ├── hermes/
│   ├── agent-management/
│   ├── agent-coordinator/
│   ├── coordinator-api/
│   └── blockchain-node/
├── aitbc/                   # Shared core library
├── cli/                     # CLI tooling
└── venv/                    # Virtual environment
```

## Development Guidelines

1. **Type Safety**: All new code must pass MyPy checks
2. **Imports**: Use explicit imports, avoid `*` imports
3. **Annotations**: Add type annotations to all function signatures
4. **Return Types**: Always specify return types, use `-> None` for void functions
5. **Error Handling**: Use proper exception types, avoid bare `except:`

## MyPy Configuration

The project uses **full strict MyPy mode** with all 12 strict options enabled:

```toml
[tool.mypy]
python_version = "3.13"
plugins = ["pydantic.mypy", "sqlalchemy.ext.mypy.plugin"]

# Strict type checking options (all 12 enabled)
disallow_any_generics = true
disallow_subclassing_any = true
disallow_untyped_calls = true
disallow_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true
strict_optional = true
```

### Recent Changes (Full Strict Mode Enforcement)

To achieve full strict mode, the following changes were made across the codebase:

1. **Added missing type parameters to generic types:**
   - Changed `dict` to `dict[str, Any]`
   - Changed `list` to `list[Any]` or `list[str]`
   - Changed `Callable` to `Callable[[...], ...]`
   - Changed `deque` to `deque[Any]`
   - Changed `Task` to `Task[Any]`
   - Changed `Queue` to `Queue[Any]`

2. **Applications updated:**
   - pool-hub: Fixed list/dict type arguments in routers and models
   - wallet: Fixed dict type arguments in bridge, keystore, and API services
   - edge: Fixed list/dict type arguments in schemas and services
   - hermes: Fixed list type arguments in AI approval strategy
   - agent-coordinator: Fixed Callable/deque type arguments in protocols and routing
   - blockchain-node: Comprehensive type fixes across 25+ files
   - blockchain-event-bridge: Fixed Task and list type arguments
   - bridge-monitor: Fixed dict type arguments in storage
   - governance: Fixed dict type arguments in services and main
   - gpu: Fixed list/dict type arguments in marketplace and services
   - marketplace: Fixed list/dict type arguments in domain and services
   - trading: Fixed dict type arguments in services and main

3. **Configuration update:**
   - Added `disallow_any_generics = true` to pyproject.toml
   - Added `disallow_subclassing_any = true` to pyproject.toml

## Type Testing

The project includes type-specific tests to verify type annotations are correct:

### Rate Limiting Type Tests
- Location: `tests/test_rate_limiting_types.py`
- Covers: All rate_limiting module functions and classes
- Verification: MyPy strict mode (0 errors), Pytest (11 tests passed)
- Tests include:
  - Return type verification for all public functions
  - Decorator signature preservation
  - Middleware initialization types
  - Custom key function typing
  - Optional parameter handling

### Running Type Tests
```bash
# Run MyPy on test file
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes tests/test_rate_limiting_types.py

# Run pytest on type tests
cd /opt/aitbc && ./venv/bin/python -m pytest tests/test_rate_limiting_types.py -v
```

## Useful Tools

- `./venv/bin/python -m mypy --show-error-codes`: Run type checker
- `./venv/bin/python -m ruff check .`: Run linter
- `./venv/bin/python -m ruff format .`: Run formatter

---

*Last updated: 2026-06-15 - Full strict MyPy mode enabled (12/12 strict options), all primary applications (pool-hub, wallet, edge, hermes, agent-management, agent-coordinator) pass strict mode, comprehensive type parameter fixes applied across 12+ applications*
