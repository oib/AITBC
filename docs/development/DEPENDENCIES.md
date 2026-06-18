# AITBC Dependency Management

## Source of Truth

**Primary Source**: `pyproject.toml` (root) + `uv.lock`

All dependency management is centralized in the root `pyproject.toml` file using Poetry. The `uv.lock` file serves as the locked dependency tree for reproducible builds.

## Installation

### Development Installation
```bash
pip install -e ".[dev]"
```

This installs:
- Core production dependencies
- Development tools (pytest, black, ruff, mypy, etc.)
- All testing dependencies

### Production Installation
```bash
pip install -e .
```

This installs only core production dependencies.

### Optional Feature Groups

#### AI/ML Features
```bash
pip install -e ".[ai-ml]"
```
Includes: OpenAI, Google Translate, DeepL, spaCy, NLTK, transformers, etc.

#### Security Features
```bash
pip install -e ".[security]"
```
Includes: python-jose, passlib, sentry-sdk

#### Minimal Profile
```bash
pip install -e ".[minimal]"
```
Includes: psycopg2-binary, orjson, lz4 (for lightweight deployments)

## Migration from Legacy Files

The following files are **deprecated** and should not be used:
- `requirements.txt` → Use `pip install -e .`
- `requirements-dev.txt` → Use `pip install -e ".[dev]"`
- `requirements-minimal.txt` → Use `pip install -e ".[minimal]"`
- `requirements-optional/ai-ml.txt` → Use `pip install -e ".[ai-ml]"`
- `requirements-optional/security.txt` → Use `pip install -e ".[security]"`
- `requirements-optional/testing.txt` → Use `pip install -e ".[dev]"`
- `cli/requirements-cli.txt` → Use `pip install -e ".[dev]"`

These files are kept for backward compatibility during the transition period but will be removed in a future release.

## CI/CD

All CI jobs install the project using the standard command:
```bash
pip install -e ".[dev]"
```

This ensures that:
- Imports resolve correctly during linting and type checking
- Tests run against the installed package
- Development and production environments are aligned

## Dependency Updates

To update dependencies:
1. Edit `pyproject.toml` with new version constraints
2. Run `uv lock` to update `uv.lock`
3. Test the changes locally
4. Commit both files together

## App-Level Dependencies

Individual apps in `apps/` may have their own `pyproject.toml` files for app-specific dependencies. However, for shared dependencies, prefer adding them to the root `pyproject.toml` to maintain consistency across the project.

## Python Version

**Required**: Python >=3.13.5,<3.14.1 || >3.14.1,<3.15

This constraint is enforced in the root `pyproject.toml` and should be mirrored in all app-level `pyproject.toml` files.

## Troubleshooting

### Import Errors in CI
If you see import errors during CI linting or type checking:
- Ensure the CI job runs `pip install -e ".[dev]"` before lint/test/typecheck
- Check that the dependency is listed in `pyproject.toml`

### Dependency Conflicts
If you encounter dependency conflicts:
- Check `uv.lock` for the resolved tree
- Use `pip install -e ".[dev]"` locally to reproduce
- Report conflicts with the specific package versions

### Missing Optional Features
If an optional feature is not available:
- Install with the appropriate extra: `pip install -e ".[ai-ml]"`
- Check that the feature's dependencies are in the correct extras section in `pyproject.toml`

---

*Last updated: 2026-06-18*
