# JSON Dependency Analysis

## Current State

### Dependency in pyproject.toml
```toml
# JSON & Serialization
orjson = ">=3.11.0"
msgpack = ">=3.11.0"
python-multipart = ">=0.0.27"
```

### Usage Analysis
- **orjson**: Listed in dependencies but **NOT USED** in codebase
  - No `import orjson` found in any Python files
  - No references to orjson API
  - Dead dependency

- **msgpack**: Listed in dependencies
  - Usage not analyzed in this scan
  - Potentially used for binary serialization

- **stdlib json**: Used throughout codebase
  - Standard library `json` module is the default
  - Used in 100+ files across codebase

## Performance Considerations

### orjson Benefits
- Faster serialization/deserialization than stdlib json
- Better performance for hot paths
- More efficient memory usage
- Better datetime handling

### orjson Drawbacks
- Additional dependency to maintain
- Not needed if not used
- Adds to dependency surface area
- Potential security vulnerabilities in third-party code

## Recommendation

### Decision: Remove orjson from dependencies

**Rationale:**
1. **Not Used**: No active usage found in codebase
2. **Unnecessary Overhead**: Adds dependency without benefit
3. **Security**: Reduces attack surface
4. **Maintenance**: One less dependency to update
5. **Cost**: Smaller dependency tree

### Future Consideration
If orjson is needed for performance-critical hot paths:
1. Add it only to the specific package/app that needs it
2. Use it conditionally in hot paths only
3. Benchmark to justify the addition
4. Document the performance benefit

## Migration Plan

### Phase 1: Remove orjson from root dependencies
- Remove `orjson = ">=3.11.0"` from `pyproject.toml`
- Run `poetry lock --no-update` to update lock file
- Verify no imports break

### Phase 2: Verify stdlib json usage
- Confirm stdlib json works correctly
- No performance issues in current usage
- All JSON operations functioning

### Phase 3: Document decision
- Add comment to pyproject.toml explaining removal
- Update documentation if needed
- Note future re-addition criteria

## Implementation

### Changes Required
```toml
# Before
# JSON & Serialization
orjson = ">=3.11.0"
msgpack = ">=3.11.0"
python-multipart = ">=0.0.27"

# After
# JSON & Serialization
# orjson removed - not used in codebase, can be re-added for hot paths if needed
msgpack = ">=3.11.0"
python-multipart = ">=0.0.27"
```

### Verification Steps
1. Remove orjson from pyproject.toml
2. Update poetry.lock
3. Run tests to ensure no breakage
4. Check for any hidden orjson usage
5. Commit changes

## Risk Assessment

### Low Risk
- orjson is not actively used
- stdlib json is the default
- No breaking changes expected
- Easy to re-add if needed

### Mitigation
- Keep stdlib json as default
- Document removal decision
- Monitor for performance issues
- Can re-add if hot paths identified

## Success Criteria

- [ ] orjson removed from pyproject.toml
- [ ] poetry.lock updated
- [ ] All tests passing
- [ ] No hidden orjson usage found
- [ ] Documentation updated
