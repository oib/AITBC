# Debugging Playbook

Structured checklists for diagnosing common subsystem failures.

## CLI Command Fails with ImportError

1. Confirm service module exists: `ls apps/coordinator-api/src/app/services/`
2. Check `services/__init__.py` exists.
3. Verify command module adds `apps/coordinator-api/src` to `sys.path`.
4. Test import manually:
   ```bash
   python3 -c "import sys; sys.path.insert(0, 'apps/coordinator-api/src'); from app.services.trading_surveillance import start_surveillance"
   ```
5. If missing dependencies, install coordinator-api requirements.

## Blockchain Node Not Starting

1. Check virtualenv: `source apps/blockchain-node/.venv/bin/activate`
2. Verify database file exists: `apps/blockchain-node/data/chain.db`
   - If missing, run genesis generation: `python scripts/make_genesis.py`
3. Check `.env` configuration (ports, keys).
4. Test RPC health: `curl http://localhost:8026/health`
5. Review logs: `tail -f apps/blockchain-node/logs/*.log` (if configured)

## Package Installation Fails (pip)

1. Ensure `README.md` exists in package root.
2. Check `pyproject.toml` for required fields: `name`, `version`, `description`.
3. Install dependencies first: `pip install -r requirements.txt` if present.
4. Try editable install: `pip install -e .` with verbose: `pip install -v -e .`

## Git Push Permission Denied

1. Verify SSH key added to Gitea account.
2. Confirm remote URL is SSH, not HTTPS.
3. Test connection: `ssh -T git@gitea.bubuit.net`.
4. Ensure token has `push` permission if using HTTPS.

## CI Pipeline Not Running

1. Check `.github/workflows/` exists and YAML syntax is valid.
2. Confirm branch protection allows CI.
3. Check Gitea Actions enabled (repository settings).
4. Ensure Python version matrix includes active versions (3.11, 3.12, 3.13).

## Tests Fail with ImportError in aitbc-core

1. Confirm package installed: `pip list | grep aitbc-core`.
2. If not installed: `pip install -e ./packages/py/aitbc-core`.
3. Ensure tests can import `aitbc.logging`: `python3 -c "from aitbc.logging import get_logger"`.

## PR Cannot Be Merged (stuck)

1. Check if all required approvals present.
2. Verify CI status is `success` on the PR head commit.
3. Ensure no merge conflicts (Gitea shows `mergeable: true`).
4. If outdated, rebase onto latest main and push.
