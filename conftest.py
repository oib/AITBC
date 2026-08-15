"""Repo-wide test setup, imported by pytest before any test module (V23-69).

Its one job is to stop the *deployed machine's* configuration from leaking into the test
process. `cli/aitbc_cli/commands/coin_requests.py` reads `/etc/aitbc/blockchain.env` and
friends into `os.environ` at import time — deliberately, because the CLI needs those values
before it imports storage — and importing that module during collection puts the hub's real
`BLOCKCHAIN_RPC_URL`, `GENESIS_*` and `AGENT_DB_PATH` in front of every test that runs
afterwards.

That made the suite depend on which machine it ran on. Tests asserting a config default read
the hub's value instead and failed here while passing in a clean container; the reverse is
worse, since a test can pass against deployed state that a CI box would never have. Both stayed
invisible while the app suites were not collected at all.
"""

from __future__ import annotations

import os

# Read by `_load_env_file`. Set before collection imports anything, so the env files are
# never read in-process. Deployments do not set it and are unaffected.
os.environ.setdefault("AITBC_SKIP_ENV_FILES", "1")
