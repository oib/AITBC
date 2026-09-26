"""Keep the production-probing verification scripts out of automated runs.

Several files in this directory are not unit tests. They point at the live deployment --
``BASE_URL = "https://hub.example.net/rpc"`` and
``COORDINATOR_URL = "https://hub.example.net/api"`` -- read the current head, and then
POST: newly constructed blocks to ``/rpc/importBlock``, jobs to ``/v1/jobs``, miner results to
``/v1/miners/{id}/result``. A passing run means blocks were accepted into production and real
jobs and payments were created there. They are named ``test_*.py``, so any ``pytest tests/``
picks them up and tries exactly that.

**The list used to be hand-maintained and was wrong.** It named three modules; seven name
the production host and all seven write to it. ``test_minimal.py``, ``test_simple_import.py``
and ``test_tx_import.py`` each POST to ``/importBlock``, and ``test_payment_integration.py``
creates jobs, polls as a miner, submits results and triggers a refund -- none of them
gated. A list that has to be updated by hand every time a file is added is a list that will
be wrong again, so the gate now reads the file instead: any module whose source names a
deployment host is skipped, and a new file naming one is covered the day it lands.

Matching on source text is deliberately blunt. It over-matches -- a module that only
mentions the host in a comment is skipped too -- and that is the right direction to err.
It also reads the file rather than importing it, so nothing in a gated module executes.

**The gate has to be confined to this directory** (V23-93). ``pytest_collection_modifyitems``
is handed the whole session's item list no matter which ``conftest.py`` defines it, so for one
release the blunt text match ran against every file in the repository: 159 ordinary unit
tests were skipped for naming the host in a URL constant or a docstring, among them the
``/coin-requests/execute`` authorization tests and the invocation-safety tests for the 3600x
balance migration. Over-matching is the right direction to err *here*, where every module
really does write to production; applied repo-wide it silently turned off the tests that
verify the protections. Hence ``_is_in_this_directory``.

Set ``AITBC_ALLOW_PRODUCTION_WRITE_TESTS=1`` to run them, which makes running them a
deliberate act. The read-only rest of this directory -- the import-surface checks, the model
validation, the coordinator health probes -- is ordinary and runs normally.

**Naming a host was never the real signal -- writing is.** The gated modules were later
converted to target the local node by default and to sign blocks with a deterministic test
key. That took the hostname out of their source, which silently took them out of the gate,
and left every ``POST`` exactly where it was. A plain ``pytest tests/`` then ran them against
whichever node the runner happened to be standing on. One follower was forked 32 blocks deep
by blocks this directory imported at ``head + 1``; every subsequent block from the real chain
was rejected for an unknown parent, and the node only recovered when its database was
replaced from a snapshot. "Points at production" had quietly become "points at you".

So the gate keys on the behaviour instead. A module in this directory that issues any HTTP
write -- ``.post``, ``.put``, ``.patch``, ``.delete`` -- is skipped whatever host it names,
and the host match is kept alongside it to cover read-only probes against a live deployment.
``localhost`` is not a safe default target here, just a different victim. Modules that only
read are untouched.

The rollback is opt-in as well: ``_reset_chain_db`` restores a pre-run copy of the chain
database only when ``AITBC_VERIFICATION_ENABLE_RESET=1``. With the reset off -- the default --
whatever these modules write stays written.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import requests

try:
    from aitbc.crypto.consensus_signing import sign_block_hash
except Exception:  # pragma: no cover
    sign_block_hash = None  # type: ignore[assignment]

try:
    from eth_keys import keys
except Exception:  # pragma: no cover
    keys = None  # type: ignore[assignment]

#: Hosts that are somebody's live deployment. Matched against module source, not resolved.
PRODUCTION_HOST_RE = re.compile(r"\bbubuit\.net\b")

#: An HTTP write of any shape: ``requests.post``, ``httpx.put``, ``self.client.delete``,
#: ``await client.patch``. Matched against module source for the same reasons the host match
#: is -- it reads the file instead of importing it, so nothing in a gated module executes, and
#: it over-matches rather than under-matches. Over-matching here costs a skip that
#: ``AITBC_ALLOW_PRODUCTION_WRITE_TESTS=1`` lifts; under-matching costs a forked node.
HTTP_WRITE_RE = re.compile(r"\.(?:post|put|patch|delete)\s*\(")

ALLOW_ENV = "AITBC_ALLOW_PRODUCTION_WRITE_TESTS"
RESET_ENV = "AITBC_VERIFICATION_ENABLE_RESET"

#: The only directory this gate speaks for. See the module docstring: the hook itself is
#: repo-wide, so the boundary has to be enforced here rather than assumed from placement.
GATED_DIR = Path(__file__).resolve().parent

#: Local RPC target for integration-style verification tests. Override with
#: ``AITBC_VERIFICATION_RPC_URL`` for a different node.
DEFAULT_RPC_URL = os.getenv("AITBC_VERIFICATION_RPC_URL", "http://127.0.0.1:8202/rpc")

#: Chain ID used by the local node. This value lives in conftest (not a test module) so the
#: production-host text gate does not match it when tests import it.
DEFAULT_CHAIN_ID = "ait-testchain.local"

#: Deterministic secp256k1 test key for signing verification blocks.
DEFAULT_PROPOSER_PRIVATE_KEY = "0x" + "1" * 64

#: DB file for the default local chain.
DEFAULT_CHAIN_DB = Path("/var/lib/aitbc/data") / DEFAULT_CHAIN_ID / "chain.db"


def _is_in_this_directory(path) -> bool:  # noqa: ANN001 - pytest hands us its own path type
    """Whether the item lives under ``tests/verification/``."""
    try:
        resolved = Path(str(path)).resolve()
    except OSError:
        return False
    return resolved == GATED_DIR or GATED_DIR in resolved.parents


def _names_production_host(path) -> bool:  # noqa: ANN001 - pytest hands us its own path type
    """Whether this file's source mentions a deployment host at all."""
    try:
        return PRODUCTION_HOST_RE.search(path.read_text(encoding="utf-8", errors="ignore")) is not None
    except OSError:
        # Unreadable means unknown, and unknown is treated as production-touching.
        return True


def _rpc_api_key() -> str | None:
    """X-API-Key for the gated /rpc routes (importBlock, subscription, …).

    Env first, then the node's secrets file — verification tests run on a node
    as root, so the file is readable there.
    """
    key = os.environ.get("BLOCKCHAIN_RPC_API_KEY")
    if key:
        return key
    secrets = Path("/etc/aitbc/blockchain-secrets.env")
    try:
        for line in secrets.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "BLOCKCHAIN_RPC_API_KEY":
                return v.strip().strip('"').strip("'") or None
    except OSError:
        pass
    return None


@pytest.fixture(autouse=True)
def _inject_rpc_api_key(monkeypatch):
    """Attach X-API-Key to every ``requests`` write aimed at the node RPC.

    /rpc mutation routes are API-key gated (GAP-56); without this the
    verification suite's importBlock/subscribe calls all 403.
    """
    key = _rpc_api_key()
    if not key:
        return
    for method in ("post", "put", "patch", "delete"):
        orig = getattr(requests, method)

        def _wrapped(url: str, *args, _orig=orig, **kwargs):
            headers = dict(kwargs.pop("headers", {}) or {})
            headers.setdefault("X-API-Key", key)
            return _orig(url, *args, headers=headers, **kwargs)

        monkeypatch.setattr(requests, method, _wrapped)


def _sends_http_writes(path) -> bool:  # noqa: ANN001 - pytest hands us its own path type
    """Whether this file's source issues an HTTP write of any kind.

    This is the predicate that actually matters: a module that POSTs blocks, jobs or miner
    results changes state on whatever node it is aimed at, and aiming it at ``127.0.0.1``
    makes the local node the thing it changes.
    """
    try:
        return HTTP_WRITE_RE.search(path.read_text(encoding="utf-8", errors="ignore")) is not None
    except OSError:
        # Unreadable means unknown, and unknown is treated as writing.
        return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(ALLOW_ENV) == "1":
        return

    skip_writes = pytest.mark.skip(
        reason=(
            f"Sends HTTP writes (blocks, jobs, miner results) to whatever node it is pointed "
            f"at, which by default is this one. Set {ALLOW_ENV}=1 to run deliberately."
        )
    )
    skip_host = pytest.mark.skip(
        reason=(f"Names a live deployment host and probes it. Set {ALLOW_ENV}=1 to run deliberately.")
    )

    gated: dict[str, Any] = {}
    for item in items:
        path = getattr(item, "path", None)
        if path is None:
            continue
        key = str(path)
        if key not in gated:
            marker = None
            if _is_in_this_directory(path):
                # Write behaviour first: it is the reason that survives a hostname change.
                if _sends_http_writes(path):
                    marker = skip_writes
                elif _names_production_host(path):
                    marker = skip_host
            gated[key] = marker
        if gated[key] is not None:
            item.add_marker(gated[key])


# ---------------------------------------------------------------------------
# Shared verification helpers
# ---------------------------------------------------------------------------


def _proposer_address(private_key_hex: str = DEFAULT_PROPOSER_PRIVATE_KEY) -> str:
    """Derive the proposer address for a given private key."""
    if keys is None:
        raise ImportError("eth_keys is required for block signing. Install with: pip install eth-keys")
    pk_hex = private_key_hex.removeprefix("0x")
    pk = keys.PrivateKey(bytes.fromhex(pk_hex))
    return pk.public_key.to_address()


def compute_block_hash(chain_id: str, height: int, parent_hash: str, timestamp: str) -> str:
    """Compute the same SHA-256 block hash the verification tests use."""
    payload = f"{chain_id}|{height}|{parent_hash}|{timestamp}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()


def sign_block(block_data: dict[str, Any], private_key_hex: str = DEFAULT_PROPOSER_PRIVATE_KEY) -> dict[str, Any]:
    """Add a deterministic proposer and signature to a block payload."""
    if sign_block_hash is None:
        raise ImportError("aitbc.crypto.consensus_signing is required for block signing")
    block_data["proposer"] = _proposer_address(private_key_hex)
    block_data["signature"] = sign_block_hash(block_data["hash"], private_key_hex)
    return block_data


def make_signed_block(
    chain_id: str = DEFAULT_CHAIN_ID,
    height: int = 1,
    parent_hash: str = "0x00",
    timestamp: str | None = None,
    private_key_hex: str = DEFAULT_PROPOSER_PRIVATE_KEY,
    transactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a signed block payload ready for ``/importBlock``.

    The block is signed by the deterministic test proposer, so the local node's
    ``ProposerSignatureValidator`` accepts it even when the trusted-proposer set is empty.
    """
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()
    transactions = transactions or []
    block_hash = compute_block_hash(chain_id, height, parent_hash, timestamp)
    block: dict[str, Any] = {
        "height": height,
        "hash": block_hash,
        "parent_hash": parent_hash,
        "timestamp": timestamp,
        "tx_count": len(transactions),
        "chain_id": chain_id,
        "transactions": transactions,
    }
    return sign_block(block, private_key_hex)


def get_head(base_url: str = DEFAULT_RPC_URL) -> dict[str, Any]:
    """Fetch the current head block from the local node."""
    response = requests.get(f"{base_url}/head", timeout=10)
    response.raise_for_status()
    return response.json()


def _hash(label: str) -> str:
    """Return a deterministic 64-hex hash for a test label."""
    return "0x" + hashlib.sha256(label.encode()).hexdigest()


def unique_address(label: str) -> str:
    """Return a deterministic 0x-prefixed 40-hex address for ``label``."""
    return _hash(label)[:42]


def unique_tx_hash(label: str) -> str:
    """Return a deterministic 64-hex transaction hash for ``label``."""
    return _hash(label)


def _wait_for_node(base_url: str, timeout: float = 30.0) -> None:
    """Poll ``/head`` until the local RPC is responsive."""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/head", timeout=2)
            if response.status_code == 200 and response.json().get("height") is not None:
                return
        except (requests.RequestException, ValueError) as exc:
            last_err = exc
        time.sleep(0.5)
    raise TimeoutError(f"Local RPC not ready after {timeout}s: {last_err}")


def _service_action(action: str) -> None:
    """Run ``systemctl <action> aitbc-blockchain-rpc`` if systemctl is available."""
    if shutil.which("systemctl") is None:
        return
    subprocess.run(
        ["systemctl", action, "aitbc-blockchain-rpc.service"],
        check=False,
        capture_output=True,
        text=True,
    )


def _reset_chain_db(chain_id: str, baseline_height: int, db_path: Path) -> None:
    """Delete blocks, transactions, and ephemeral accounts created above ``baseline_height``.

    This is an optional, destructive teardown step. It is only executed when the
    ``AITBC_VERIFICATION_ENABLE_RESET`` environment variable is set, and only on the
    designated local verification node.
    """
    if not db_path.exists():
        return

    try:
        import sqlite3
    except ImportError:
        return

    _service_action("stop")
    try:
        with sqlite3.connect(db_path, isolation_level=None) as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute('DELETE FROM "transaction" WHERE chain_id = ? AND block_height > ?', (chain_id, baseline_height))
            conn.execute("DELETE FROM block WHERE chain_id = ? AND height > ?", (chain_id, baseline_height))
    finally:
        _service_action("start")
        _wait_for_node(DEFAULT_RPC_URL)


@pytest.fixture(scope="module")
def local_node() -> dict[str, Any]:
    """Provide the local blockchain RPC URL and chain ID and capture a reset baseline.

    A fresh, deterministic ``baseline_height`` is captured per module.  Tests should use
    :func:`unique_address` and :func:`unique_tx_hash` to avoid collisions with the live
    chain and with other tests.  If ``AITBC_VERIFICATION_ENABLE_RESET=1`` is set, the chain
    is rolled back to ``baseline_height`` after the module finishes, restoring the node to
    its pre-test state.
    """
    base_url = DEFAULT_RPC_URL
    _wait_for_node(base_url)
    baseline = get_head(base_url)
    node_info = {
        "url": base_url,
        "chain_id": DEFAULT_CHAIN_ID,
        "db_path": DEFAULT_CHAIN_DB,
        "baseline_height": baseline["height"],
        "baseline_hash": baseline["hash"],
    }

    yield node_info

    if os.environ.get(RESET_ENV) == "1":
        _reset_chain_db(DEFAULT_CHAIN_ID, baseline["height"], DEFAULT_CHAIN_DB)


@pytest.fixture
def test_id(request: pytest.FixtureRequest) -> str:
    """Return a stable, test-scoped identifier based on the test name."""
    return f"{request.module.__name__}.{request.node.name}"
