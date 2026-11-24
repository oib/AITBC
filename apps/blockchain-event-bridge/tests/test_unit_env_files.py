"""Regression tests for the event-bridge unit's env-file wiring (#2935).

The hub redis bus requires AUTH. Sibling units pick up the authenticated
``GOSSIP_BROADCAST_URL`` from ``/etc/aitbc/blockchain-secrets.env``; the
event-bridge unit must load it too — and *after* ``node.env``/``blockchain.env``,
whose passwordless ``redis://localhost:6379`` default would otherwise win
(systemd applies EnvironmentFile entries in order, later files override).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
UNIT = REPO / "apps" / "blockchain-event-bridge" / "aitbc-blockchain-event-bridge.service"


def _env_files() -> list[str]:
    return [line.split("=", 1)[1] for line in UNIT.read_text().splitlines() if line.startswith("EnvironmentFile")]


def test_unit_loads_blockchain_secrets_env() -> None:
    """The authenticated gossip URL lives in blockchain-secrets.env (#2935)."""
    assert "-/etc/aitbc/blockchain-secrets.env" in _env_files()


def test_secrets_env_is_loaded_last() -> None:
    """Later EnvironmentFile entries override earlier ones — secrets must come
    after node.env/blockchain.env so the password-bearing GOSSIP_BROADCAST_URL
    wins over the passwordless default."""
    files = _env_files()
    secrets_idx = files.index("-/etc/aitbc/blockchain-secrets.env")
    assert secrets_idx > files.index("/etc/aitbc/node.env")
    assert secrets_idx > files.index("/etc/aitbc/blockchain.env")
