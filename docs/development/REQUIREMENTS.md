# AITBC Requirements Management

This document describes the three-tier requirements management system for AITBC dependencies.

## Structure

### Tier 1: Core Production Dependencies (`requirements.txt`)
Essential dependencies required by all AITBC services in production.

**Includes:**
- Web framework (FastAPI, uvicorn, gunicorn)
- Data validation (pydantic)
- Database (SQLAlchemy, SQLModel, Alembic, aiosqlite, asyncpg)
- Blockchain & cryptography (cryptography, web3, eth-account)
- Common utilities (python-dotenv, requests, pyyaml)
- Caching (redis)
- Monitoring & logging (structlog, prometheus-client)
- Performance utilities (orjson, lz4, psutil)

**When to use:**
- All production service deployments
- Base installation for any AITBC service
- Docker image base layer

### Tier 2: Development Dependencies (`requirements-dev.txt`)
Development tools, testing frameworks, and code quality utilities.

**Includes:**
- Testing (pytest, pytest-asyncio, pytest-mock, pytest-cov, httpx)
- Code quality (black, flake8, mypy, pre-commit, ruff)
- CLI tools (click, rich, typer, tabulate, keyring)
- Development utilities (tqdm, ipython)

**When to use:**
- Development environments
- CI/CD pipelines
- Local development setup

### Tier 3: Optional Modules (`requirements-optional/`)
Specialized dependency sets for specific use cases.

**Available modules:**
- `ai-ml.txt` - AI/ML and translation dependencies (torch, transformers, openai, google-cloud-translate, deepl, spacy, nltk)
- `security.txt` - Security and compliance (python-jose, passlib, sentry-sdk)
- `testing.txt` - Testing and quality (pytest, black, flake8, mypy, pre-commit)

**When to use:**
- Services requiring AI/ML capabilities
- Services requiring enhanced security features
- Development environments needing additional testing tools

## Installation

### Using Installation Script

The recommended method is using the installation profile script:

```bash
# Install core production dependencies
./scripts/deployment/install-profiles.sh core

# Install development dependencies
./scripts/deployment/install-profiles.sh dev

# Install all optional modules
./scripts/deployment/install-profiles.sh optional

# Install specific optional module
./scripts/deployment/install-profiles.sh ai-ml
./scripts/deployment/install-profiles.sh security
./scripts/deployment/install-profiles.sh testing

# Install everything (core + dev + optional)
./scripts/deployment/install-profiles.sh all
```

### Manual Installation

```bash
# Install core dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Install optional modules
pip install -r requirements-optional/ai-ml.txt
pip install -r requirements-optional/security.txt
pip install -r requirements-optional/testing.txt
```

### Legacy Profiles

The installation script maintains legacy profiles for backward compatibility:
- `web`, `database`, `blockchain`, `cli`, `monitoring`, `image`, `minimal`

These use exact version pinning (`==`) for reproducible builds but are considered legacy. New installations should use the tiered system.

## Versioning Strategy

- **Core requirements.txt**: Uses `>=` ranges for flexibility and security updates
- **Dev requirements-dev.txt**: Uses `>=` ranges for development tools
- **Optional modules**: Uses `>=` ranges for optional dependencies
- **Legacy profiles**: Use exact versions (`==`) for reproducible installations

## Dependency Updates

### Security Updates
1. Check advisories: `pip-audit` (Python), `pnpm audit` (npm), `cargo audit` (Rust)
2. Update affected packages in appropriate requirements file
3. Test in development environment
4. Deploy to production

### Feature Updates
1. Review changelog for breaking changes
2. Update version in appropriate requirements file
3. Test in development environment
4. Update documentation if needed

### Monthly Review
Run comprehensive vulnerability scans:
```bash
# Python
source /opt/aitbc/venv/bin/activate
pip-audit

# npm (pnpm)
cd /opt/aitbc/contracts && pnpm audit
cd /opt/aitbc/packages/solidity/aitbc-token && pnpm audit
cd /opt/aitbc/apps/zk-circuits && pnpm audit

# Rust
source ~/.cargo/env
cd /opt/aitbc/dev/gpu/gkpu_zk_research && cargo audit
```

## Service-Specific Dependencies

Services should not maintain their own `requirements.txt` files. Instead:

1. **Core dependencies**: Use `requirements.txt` (installed by default)
2. **Optional features**: Install from `requirements-optional/` as needed
3. **Development**: Use `requirements-dev.txt` for development tools

Example for a service requiring AI/ML:
```bash
# Install core dependencies
pip install -r /opt/aitbc/requirements.txt

# Install AI/ML optional module
pip install -r /opt/aitbc/requirements-optional/ai-ml.txt
```

## Package Dependencies

Python packages (e.g., `aitbc-agent-sdk`) should depend on the central system rather than maintaining standalone requirements files. Package installation should reference the central requirements files.

## Migration from Old Structure

### Removed Files
- `requirements-modules/` directory (replaced by `requirements-optional/`)
- Service-specific `requirements.txt` files (consolidated into central system)
- Package-specific `requirements.txt` files (use central system)

### Updated Files
- `cli/requirements.txt` removed (use `cli/requirements-cli.txt` + central system)
- `cli/requirements-cli.txt` updated to reference central system
- `scripts/deployment/install-profiles.sh` updated with new profiles

### New Files
- `requirements.txt` - Core production dependencies
- `requirements-dev.txt` - Development dependencies
- `requirements-optional/ai-ml.txt` - AI/ML optional module
- `requirements-optional/security.txt` - Security optional module
- `requirements-optional/testing.txt` - Testing optional module

## Troubleshooting

### Dependency Conflicts
If you encounter dependency conflicts:
1. Use fresh virtual environment
2. Install core dependencies first: `pip install -r requirements.txt`
3. Install optional modules separately
4. Check for version conflicts with `pip list`

### Missing Dependencies
If a service reports missing dependencies:
1. Verify core dependencies installed: `pip install -r requirements.txt`
2. Check if optional module needed: `pip install -r requirements-optional/<module>.txt`
3. Verify virtual environment is active

### Installation Script Issues
If `install-profiles.sh` fails:
1. Verify you're in `/opt/aitbc` directory
2. Check virtual environment exists at `./venv`
3. Run with bash explicitly: `bash scripts/deployment/install-profiles.sh <profile>`

## References

- [Dependency Monitoring Strategy](../security/DEPENDENCY_MONITORING.md)
- [Installation Script](../../scripts/deployment/install-profiles.sh)
- [Security Audit](../../scripts/security/security_audit.py)

## Last Updated
2026-05-29
