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
- Code quality (ruff, mypy, pre-commit)
- CLI tools (click, rich, typer, tabulate, keyring)
- Development utilities (tqdm, ipython)

## Tier 3: Optional Dependency Groups (Poetry extras)

Specialized dependency sets live in `[tool.poetry.extras]` in the root `pyproject.toml`.
There are no standalone optional requirements files — the extras and the lock file are the
single source of truth, so optional packages stay pinned to the same versions as everything else.

| Extra | Packages |
|---|---|
| `gpu` | pycuda |
| `ml` | torch, torchvision, pillow, opencv-python |
| `fhe` | tenseal |
| `language` | openai, deepl, google-cloud-translate, langdetect, fasttext, polyglot |
| `search` | meilisearch |
| `sqlcipher` | sqlcipher3-binary |
| `security` | detect-secrets |
| `observability` | opentelemetry-sdk, opentelemetry-exporter-otlp |

No installation profile currently maps to `language`, `search`, `sqlcipher`, `security`, or
`observability`. Install those directly when a service needs them:

```bash
poetry install --extras language
```

## Installation Profiles

`scripts/deployment/install-profiles.sh <profile>` resolves a profile to a set of extras, runs
`poetry export --only main --extras "<extras>"` into `.requirements/requirements-<profile>.txt`,
strips pip/setuptools/wheel from the export, and pip-installs the remainder.

Valid profile names — anything else logs a warning and falls back to base dependencies:

| Profile | Extras installed |
|---|---|
| `provider-gpu` (alias `gpu`) | `gpu ml` |
| `ai` (alias `ml`) | `ml` |
| `fhe` | `fhe` |
| `hub`, `customer-no-gpu`, `server-no-gpu`, `default` | none — base dependencies only |

```bash
# Non-GPU shop node
./scripts/deployment/install-profiles.sh server-no-gpu

# GPU provider node
./scripts/deployment/install-profiles.sh provider-gpu
```

`deploy.sh` and `setup.sh` derive the profile automatically from `BLOCKCHAIN_MODE`,
`MARKET_ROLE`, and `HARDWARE_PROFILE`, so it rarely needs to be passed by hand.

## Missing Dependencies

If services report missing dependencies, re-run the profile installer for the node's own
profile. It is idempotent:

```bash
./scripts/deployment/install-profiles.sh server-no-gpu
```

Development and test tooling is not part of any profile — install it separately:

```bash
pip install -r requirements-dev.txt
```

## See Also

- [Quick Start](quick-start.md)
- [Prerequisites](prerequisites.md)
