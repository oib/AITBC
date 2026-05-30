# Requirements Management

AITBC uses a centralized three-tier requirements management system.

## Tier 1: Core Production Dependencies (`requirements.txt`)

Essential dependencies for all AITBC services in production:
- Web framework (FastAPI, uvicorn, gunicorn)
- Data validation (pydantic)
- Database (SQLAlchemy, SQLModel, Alembic, aiosqlite, asyncpg)
- Blockchain & cryptography (cryptography, web3, eth-account)
- Common utilities (python-dotenv, requests, pyyaml)
- Caching (redis)
- Monitoring & logging (structlog, prometheus-client)

## Tier 2: Development Dependencies (`requirements-dev.txt`)

Development tools, testing frameworks, and code quality utilities:
- Testing (pytest, pytest-asyncio, pytest-mock, pytest-cov, httpx)
- Code quality (black, flake8, mypy, pre-commit, ruff)
- CLI tools (click, rich, typer, tabulate, keyring)
- Development utilities (tqdm, ipython)

## Tier 3: Optional Modules (`requirements-optional/`)

Specialized dependency sets for specific use cases:
- `ai-ml.txt` - AI/ML and translation (torch, transformers, openai, spacy, nltk)
- `security.txt` - Security and compliance (python-jose, passlib, sentry-sdk)
- `testing.txt` - Testing and quality (references requirements-dev.txt)

## Installation Profiles

Use the installation profile script for dependency management:

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

## Missing Dependencies

If services report missing dependencies, use the installation profile script:

```bash
# Install core dependencies
./scripts/deployment/install-profiles.sh core

# Install development dependencies
./scripts/deployment/install-profiles.sh dev

# Install optional modules if needed
./scripts/deployment/install-profiles.sh ai-ml
./scripts/deployment/install-profiles.sh security
./scripts/deployment/install-profiles.sh testing

# Install everything
./scripts/deployment/install-profiles.sh all
```

## See Also

- [Quick Start](quick-start.md)
- [Prerequisites](prerequisites.md)
