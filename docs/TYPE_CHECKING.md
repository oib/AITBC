# Type Checking Status

**Last Updated**: 2026-06-16
**Version**: v0.4.23
**MyPy Version**: 2.0.0

## Overview

This document tracks type checking debt across the AITBC codebase. The goal is 100% MyPy compliance with zero `# mypy: ignore-errors` comments.

## Progress History

| Version | Files with Ignores | Errors Fixed | Status |
|---------|-------------------|--------------|--------|
| v0.4.17 | 73 | - | High debt |
| v0.4.20 | 37 | 36 | Reduced |
| v0.4.22 | 2 | 35 | Near completion |
| v0.4.23 | 0 (target) | 2 | Target |

## Current Files with Type Ignores

### apps/blockchain-node/src/aitbc_chain/rpc/router.py

**Status**: 🔍 Under Investigation
**Lines**: 850
**Ignore Location**: Line 1
**Reason**: Complex conditional imports and dynamic module loading for optional features (disputes, contracts, island management)

**Investigation Notes**:
- Uses conditional imports for optional RPC modules
- Dynamic module loading pattern: `from .accounts import ...`
- Type errors expected due to optional feature architecture
- May require refactoring to dependency injection or explicit interfaces

**Target Fix Date**: v0.4.23
**Action Plan**:
1. Run MyPy to identify specific errors
2. Evaluate if errors are justified (external library limitations)
3. If justified: Document specific error codes and reasons
4. If fixable: Add type annotations or refactor
5. If architectural: Create issue for v0.4.24 refactoring

---

### apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py

**Status**: 🔍 Under Investigation
**Lines**: Unknown
**Ignore Location**: Line 1
**Reason**: Pending investigation

**Investigation Notes**:
- Not yet investigated
- Need to run MyPy to identify specific errors
- Determine if errors are fixable or require architectural changes

**Target Fix Date**: v0.4.23
**Action Plan**:
1. Run MyPy to identify specific errors
2. Investigate root cause
3. Apply appropriate fix (type annotations, refactoring, or documented ignore)

## MyPy Configuration

Current strict mode settings (pyproject.toml):
```toml
[tool.mypy]
python_version = "3.13"
strict = true
extra_checks = true
warn_return_any = true
warn_unused_configs = true
```

Exclusions:
- Tests and migrations excluded from strict checking
- External libraries (torch, web3, eth_account, sqlalchemy) ignore missing imports

## Type Checking Commands

### Check specific application
```bash
cd /opt/aitbc
find apps/APP_NAME/src -name "*.py" -path "*/src/*" | xargs ./venv/bin/python -m mypy --show-error-codes
```

### Check all applications
```bash
cd /opt/aitbc
for app in pool-hub wallet edge hermes agent-management agent-coordinator coordinator-api blockchain-node; do
  echo "=== $app ==="
  find apps/$app/src -name "*.py" -path "*/src/*" 2>/dev/null | xargs ./venv/bin/python -m mypy --show-error-codes 2>&1 | grep "error:" | wc -l
done
```

### Check specific file
```bash
./venv/bin/python -m mypy --show-error-codes apps/blockchain-node/src/aitbc_chain/rpc/router.py
```

### Find all files with type ignores
```bash
grep -r "# mypy: ignore-errors" --include="*.py" /opt/aitbc/apps /opt/aitbc/aitbc
```

## Common Type Fix Patterns

### SQLModel/SQLAlchemy Issues
- Use `scalars().all()` instead of `.all()` for query results
- Cast Row results to proper types with `cast(dict[str, Any], result)`
- Add explicit type annotations to dict comprehensions
- Use `col(Model.column)` for Python-typed columns in where clauses

### Cryptography Library
- Use `# type: ignore[union-attr]` for key type variations
- Use `isinstance(key, RSAPublicKey)` narrowing before calling methods
- Use `# type: ignore[arg-type,union-attr,call-arg]` for complex crypto operations

### FastAPI/Decorators
- Use `# type: ignore[untyped-decorator]` for FastAPI decorators
- Add type hints to dependency injection functions

### Redis Type Issues
- Convert bytes/str unions explicitly: `[str(m) for m in results]`
- Use explicit dict comprehensions with type annotations

### External Library Stubs
- Add `# type: ignore[import-not-found]` for missing stubs
- Install stub packages if available (types-*)
- Document justified ignores for unsupported libraries

## CI/CD Integration

### Pre-commit Hook
The `.pre-commit-config.yaml` includes MyPy checking for the 12 clean applications.

### CI Gate
- MyPy must pass for all applications before merge
- New `# mypy: ignore-errors` comments require documentation in this file
- Type checking debt tracked in release notes

## Guidelines for Developers

### When Adding Type Ignores

1. **Try to fix first**: Add type annotations, refactor, or use proper casts
2. **Document the reason**: Add comment explaining why ignore is necessary
3. **Update this file**: Add entry to "Current Files with Type Ignores" section
4. **Set target date**: When will this be fixed?
5. **Use specific error codes**: Prefer `# type: ignore[error-code]` over blanket ignore

### When Fixing Type Errors

1. **Run MyPy with error codes**: `mypy --show-error-codes file.py`
2. **Identify error category**: Use error code to determine fix strategy
3. **Apply appropriate fix**: Reference "Common Type Fix Patterns" above
4. **Verify fix**: Run MyPy again to confirm error resolved
5. **Update this file**: Remove entry from "Current Files with Type Ignores"

### Type Checking Best Practices

1. **Add type hints to all new functions**: Always specify return types
2. **Use `-> None` for void functions**: Explicit is better than implicit
3. **Avoid `Any` type**: Use specific types or `Unknown` when necessary
4. **Enable strict mode locally**: Use `# type: strict` for critical modules
5. **Run MyPy during development**: Use `mypy --follow-imports=skip <file>`

## References

- [MyPy Documentation](https://mypy.readthedocs.io/)
- [PEP 484 - Type Hints](https://www.python.org/dev/peps/pep-0484/)
- [PEP 561 - Distribution of Type Information](https://www.python.org/dev/peps/pep-0561/)
- [AITBC v0.4.22 Release Notes](./releases/RELEASE_v0.4.22.md)
- [AITBC v0.4.23 Release Plan](./releases/RELEASE_v0.4.23.md)

---

*Last updated: 2026-06-16*
*Version: 1.0*
*Status: Active tracking*
