
# Tighten Mypy Configuration Plan

## Current State

**Root pyproject.toml [tool.mypy] settings:**
```toml
warn_return_any = true
warn_unused_configs = true
check_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_defs = false
disallow_untyped_decorators = false
no_implicit_optional = false
warn_redundant_casts = false
warn_unused_ignores = false
warn_no_return = true
warn_unreachable = false
strict_equality = false
```

**Overrides:**
- Heavy libraries (torch, cv2, pandas, numpy, web3, etc.) are `ignore_missing_imports = true`
- Coordiator-api modules are `ignore_errors = true` (catch-all)

This is **extremely permissive** - essentially just warns on return_any and missing configs. It does not enforce:
- Function argument/return type completeness
- Avoiding implicit `Any`
- Avoiding unnecessary type: ignore comments
- Detecting unreachable code
- Strict equality checks (None vs False)

## Proposed Tightening Phases

### Phase 1: Enable Foundational Checks (Low Effort, High Value)
Target: enable 4 key options that catch real bugs with minimal friction

```toml
disallow_untyped_defs = true
disallow_incomplete_defs = true
warn_redundant_casts = true
warn_unused_ignores = true
```

**Impact:**
- Functions must have complete type signatures (all args+returns typed)
- Redundant cast() calls will be flagged
- Unused `# type: ignore` comments will be flagged
- Minimal code changes required (most functions already typed)

**Estimated effort:**
- 1 hour to update config
- 2-4 hours to fix violations in production code
- Total: ~1 day

**Validation:**
- Run `mypy apps` and ensure 0 errors
- Keep existing overrides for external libraries and coordinator-api

### Phase 2: Stricter Optional Handling (Medium Effort)
Enable:
```toml
no_implicit_optional = true
warn_unreachable = true
strict_equality = true
```

**Impact:**
- Variables defaulting to `None` must be explicitly `Optional[...]`
- Unreachable code will be flagged (dead code detection)
- Equality comparisons with None must use `is` not `==`

**Estimated effort:** 2-3 days to fix violations across codebase

### Phase 3: Gradual Per-Module Strictness (Long-term)
- Move coordinator-api out of catch-all `ignore_errors`
- Add per-module overrides as we achieve correctness
- Eventually remove `ignore_errors` blanket

**Estimated effort:** Ongoing as part of decomposition

## Implementation Steps

### Step 1: Backup Current Config
```bash
cp pyproject.toml pyproject.toml.backup
```

### Step 2: Update Root Configuration

Modify `/opt/aitbc/pyproject.toml` [tool.mypy] section:

```diff
 [tool.mypy]
 python_version = "3.13"
 warn_return_any = true
 warn_unused_configs = true
 check_untyped_defs = false
-disallow_incomplete_defs = false
-disallow_untyped_defs = false
+disallow_incomplete_defs = true
+disallow_untyped_defs = true
 disallow_untyped_decorators = false
 no_implicit_optional = false
 warn_redundant_casts = false
 warn_unused_ignores = false
 warn_no_return = true
 warn_unreachable = false
 strict_equality = false
```

### Step 3: Run Mypy and Collect Errors

```bash
cd /opt/aitbc
venv/bin/mypy apps --show-error-codes --no-color-output > mypy_errors.txt 2>&1
```

### Step 4: Categorize Errors

Typical violations we'll see:
- `Function is missing a return type annotation` (from disallow_untyped_defs)
- `Function is missing a type annotation for one or more arguments` (from disallow_untyped_defs)
- `Class is missing type parameters for generic type` (rare)
- `dict, list, etc. used without type parameters` (from disallow_incomplete_defs)
- `Redundant cast to X` (from warn_redundant_casts)
- `Unused "type: ignore" comment` (from warn_unused_ignores)

### Step 5: Fix in Order of Impact

**A. Add missing type annotations to functions**
- Priority: functions in shared-core, services, routers
- Use explicit return types; if truly dynamic, use `-> Any` (but rarely needed)
- Example:
  ```python
  def get_engine(settings):  # BEFORE
  def get_engine(settings: ServiceSettings) -> Engine:  # AFTER
  ```

**B. Add generic type parameters**
- `list` -> `List[str]` or `list[int]`
- `dict` -> `Dict[str, Any]`
- Use `from typing import List, Dict`

**C. Remove redundant casts**
- Delete `cast(Type, value)` if type is already clear to mypy
- Use `reveal_type(value)` to check actual inferred type before removing

**D. Remove unused type: ignore**
- Some `# type: ignore` comments are legacy and no longer needed
- Delete them; if mypy still fails, leave or fix underlying issue

### Step 6: Iterate and Validate

After fixing categories, re-run mypy. Continue until `mypy apps` exits with code 0.

**Note:** We preserve `ignore_missing_imports` for heavy libraries, and `ignore_errors` for coordinator-api (since we're deferring decomposition).

### Step 7: Add CI Enforcement

Update pre-commit hooks or CI to run mypy on PRs:
```yaml
# .pre-commit-config.yaml or GitHub Actions
- repo: local
  hooks:
    - id: mypy
      name: mypy
      entry: mypy apps
      language: system
      pass_filenames: false
```

## Rollback Plan

If the effort becomes too large:
1. Revert pyproject.toml from backup
2. Keep per-module `# mypy: ignore-errors` as needed
3. Approach incrementally: enable one flag at a time

## Success Criteria

- `mypy apps` completes with 0 errors
- No new type: ignore comments added without explanation
- Production code has complete type signatures
- CI pipeline includes mypy check

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Overwhelming number of errors | Enable flags incrementally (2 at a time), fix in batches by module |
| Breaking existing functionality by incorrect type fixes | Run test suite after each batch; use `reveal_type` to debug |
| Third-party library types incompatible | Keep `ignore_missing_imports` for those packages |
| Coordinator-api too messy to fix now | Keep `ignore_errors` override; revisit after decomposition |

## Related Tasks

- **Decompose coordinator-api** - Once strict mypy is in place, easier to validate new services
- **Shared-core library** - Strict typing ensures compatibility across services
- **Connection pooling** - Use proper typed database sessions

## Open Questions

1. Should we also enable `strict` mode for new services? (Probably yes)
2. Should we add type-checking to pre-commit hook for changed files only? (Yes, use `mypy --files <changed>`)
3. How to handle legacy coordinator-api code? (Keep ignore_errors for now)

## Estimated Timeline

- **0-2 days:** Implement Phase 1, fix immediate violations
- **3-7 days:** Address accumulated type errors, reach clean mypy
- **Week 2:** Add CI enforcement, document guidelines
- **Ongoing:** Maintain strict typing in new code

## References

- Mypy configuration: https://mypy.readthedocs.io/en/stable/config_file.html
- Strict mode: https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict
