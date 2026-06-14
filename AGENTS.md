# AITBC Project Guidelines

This file contains important information for AI agents working on the AITBC codebase.

## Type Safety Achievement

**Status: IN PROGRESS** - 52.9% error reduction achieved, 1,349 errors remain

### MyPy Error Reduction Summary

| Date | Milestone | Errors | Reduction |
|------|-----------|--------|-----------|
| Original | Starting point | 2,861 | - |
| v0.4.21 | Partial completion | 1,463 | 48.9% |
| **Current** | **IN PROGRESS** | **1,938** | **32.3%** |

### Current Status by Application

| Application | Errors | Status |
|-------------|--------|--------|
| pool-hub | 0 | Clean ✅ (was 126) |
| wallet | 0 | Clean ✅ |
| edge | 0 | Clean ✅ |
| hermes | 0 | Clean ✅ |
| agent-management | 0 | Clean ✅ |
| agent-coordinator | 0 | Clean ✅ (was 235) |
| coordinator-api | 1,679 | 43.9% reduction (was 1,501) |
| blockchain-node | 259 | 10.7% reduction (was 234) |
| ai-engine | 0 | Clean ✅ |
| api-gateway | 0 | Clean ✅ |
| blockchain-event-bridge | 0 | Clean ✅ |
| blockchain-explorer | 0 | Clean ✅ |
| bridge-monitor | 0 | Clean ✅ |
| exchange | 0 | Clean ✅ |
| ffmpeg | 0 | Clean ✅ |
| governance | 0 | Clean ✅ |
| gpu | 0 | Clean ✅ |
| marketplace | 0 | Clean ✅ |
| miner | 0 | Clean ✅ |
| peertube-transcoder | 0 | Clean ✅ |
| shared-core | 0 | Clean ✅ |
| shared-domain | 0 | Clean ✅ |
| trading | 0 | Clean ✅ |
| whisper | 0 | Clean ✅ |
| zk-circuits | 0 | Clean ✅ |

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

The project uses strict MyPy settings. Key configurations:
- `--show-error-codes`: Show error codes for targeted fixes
- `--no-error-summary`: Cleaner output
- Various strict flags enabled in pyproject.toml

## Useful Tools

- `./venv/bin/python -m mypy --show-error-codes`: Run type checker
- `./venv/bin/python -m ruff check .`: Run linter
- `./venv/bin/python -m ruff format .`: Run formatter

---

*Last updated: v0.4.21 release - 32.3% error reduction achieved, 1,938 errors remain across all applications, agent-coordinator now fully clean (was 235), pool-hub now fully clean (was 126), py.typed marker added to aitbc module (now checking aitbc types strictly)*
