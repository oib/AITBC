# Contributing to AITBC

Thanks for your interest in contributing. AITBC is a Python 3.13 monorepo of FastAPI microservices, a CLI, and shared libraries for a decentralized AI-compute marketplace.

## Quick setup

```bash
# 1. Clone
git clone https://github.com/oib/aitbc.git /opt/aitbc
cd /opt/aitbc

# 2. Install dependencies (Poetry)
pip install poetry
poetry install

# 3. Activate the project venv
source .venv/bin/activate || true
```

## Branch and commit conventions

Create a feature branch from `main`:

```bash
git checkout -b AITBC-<number>-<short-description>
```

Use [Conventional Commits](https://www.conventionalcommits.org/) with an optional ticket reference:

```text
type(scope): short description [ABS-XXX]
```

Example: `docs(reference): link ports to SERVICE_PORTS.md [ABS-123]`

Keep the commit history linear. Rebase onto `main` before pushing:

```bash
git fetch origin
git rebase origin/main
git push --force-with-lease
```

## Validation before pushing

Run the relevant checks for the code or docs you touched:

```bash
# Python lint and type check
./venv/bin/python -m ruff check .
./venv/bin/python -m mypy --show-error-codes aitbc/

# Unit tests
./venv/bin/python -m pytest tests/unit -q

# Docs link check (required for any docs change)
bash scripts/validate_docs.sh

# Markdown lint for touched files
npx -y markdownlint-cli <file-or-dir>
```

## Code guidelines

- **Python**: target 3.13, line length 127, use `ruff` for linting.
- **Money**: use `Decimal` everywhere in wallet, marketplace, trading, and pool-hub code. Never `float`.
- **Dependencies**: do not add new dependencies without a clear justification and approval.
- **Security**: do not commit secrets, API keys, or `.env` files.
- **Tests**: non-trivial logic should include a test. Trivial one-liners do not.

## Pull requests

1. Use the PR template in `.github/pull_request_template.md`.
2. Ensure the branch is up to date with `main` and CI is green.
3. Merge via "Rebase and merge" only.

## Documentation

- For the current port and service reference, see [`docs/reference/SERVICE_PORTS.md`](docs/reference/SERVICE_PORTS.md).
- For CLI usage, see [`cli/README.md`](cli/README.md).
- For setup and node roles, see [`docs/getting-started/README.md`](docs/getting-started/README.md).
