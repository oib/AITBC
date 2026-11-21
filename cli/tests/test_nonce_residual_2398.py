"""Nonce-lookahead residual coverage (#2398).

#2395 made ``wallet send`` and the staking nonce helper pending-aware, but
three surfaces still signed the sealed nonce — ``transactions send``/
``batch``, ``market get_next_nonce`` and ``utils/escrow.get_buyer_nonce`` —
and the staking ``sign_data`` nonce was made pending-aware even though the
node requires it to equal the *sealed* account nonce.

These pins cover: the staking split (API-message nonce sealed-only, tx
nonce pending-aware) and the remaining signing paths routing through
``pending_nonce_floor`` with the legacy offset/fallback semantics.
"""

from unittest.mock import MagicMock, patch

import pytest

SENDER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
OTHER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"


def _pending_tx(frm, nonce):
    return {"from": frm, "to": OTHER, "amount": 1, "fee": 1, "nonce": nonce, "type": "TRANSFER"}


def _endpoint_client(account_nonce, mempool_txs):
    """Fake AITBCHTTPClient: /rpc/account* → nonce, /rpc/mempool* → txs."""

    class _C:
        def __init__(self, base_url="", **kw):
            self.base_url = base_url

        def get(self, endpoint, **kw):
            if endpoint.startswith("/rpc/mempool"):
                return {"success": True, "transactions": list(mempool_txs), "count": len(mempool_txs)}
            if endpoint.startswith("/rpc/account"):
                return {"nonce": account_nonce}
            return {}

        def post(self, endpoint, json=None, **kw):
            return {"transaction_hash": "0xhash"}

    return _C


# ------------------------------------------------------- staking split (#2398 part 1)


def test_staking_account_nonce_stays_sealed_with_pending_txs():
    """Regression pin: /rpc/staking/* sign_data nonce must equal the sealed
    account nonce — pending-aware here would 400 'Stale nonce'."""
    from aitbc_cli.commands.wallet import staking as staking_mod

    client = MagicMock()
    client.base_url = "http://node:8202"

    def _get(endpoint, **kw):
        if endpoint.startswith("/rpc/mempool"):
            return {"transactions": [_pending_tx(SENDER, 4)]}
        return {"nonce": 4}

    client.get.side_effect = _get
    assert staking_mod._get_account_nonce(client, SENDER, "ait-test") == 4


def test_staking_tx_nonce_is_pending_aware():
    """The liquidity tx path still skips the sender's pending slots."""
    from aitbc_cli.commands.wallet import staking as staking_mod

    client = MagicMock()
    client.base_url = "http://node:8202"

    def _get(endpoint, **kw):
        if endpoint.startswith("/rpc/mempool"):
            return {"transactions": [_pending_tx(SENDER, 4), _pending_tx(SENDER, 5)]}
        return {"nonce": 4}

    client.get.side_effect = _get
    assert staking_mod._get_next_tx_nonce(client, SENDER, "ait-test") == 6


# ------------------------------------------------- transactions send path


def test_tx_resolve_next_nonce_skips_pending(monkeypatch):
    from aitbc_cli.commands import transactions as tx_mod

    monkeypatch.delenv("CHAIN_ID", raising=False)
    fake = _endpoint_client(5, [_pending_tx(SENDER, 5)])
    with patch("aitbc_cli.commands.transactions.AITBCHTTPClient", fake):
        assert tx_mod._resolve_next_nonce("http://node:8202", SENDER, "ait-test") == 6


def test_tx_resolve_next_nonce_offset_only_when_floor_cannot_advance(monkeypatch):
    """A readable mempool already counts queued txs — offset must not
    double them; it survives only as the probe-failure/empty fallback."""
    from aitbc_cli.commands import transactions as tx_mod

    monkeypatch.delenv("CHAIN_ID", raising=False)

    class _NoMempool:
        def __init__(self, base_url="", **kw):
            self.base_url = base_url

        def get(self, endpoint, **kw):
            if endpoint.startswith("/rpc/mempool"):
                return {}  # malformed → unknown
            return {"nonce": 5}

        def post(self, endpoint, json=None, **kw):
            return {"transaction_hash": "0xhash"}

    with patch("aitbc_cli.commands.transactions.AITBCHTTPClient", _NoMempool):
        assert tx_mod._resolve_next_nonce("http://node:8202", SENDER, "ait-test", nonce_offset=2) == 7

    fake = _endpoint_client(5, [])
    with patch("aitbc_cli.commands.transactions.AITBCHTTPClient", fake):
        # Probe ok, nothing pending: the legacy offset still applies.
        assert tx_mod._resolve_next_nonce("http://node:8202", SENDER, "ait-test", nonce_offset=2) == 7
        assert tx_mod._resolve_next_nonce("http://node:8202", SENDER, "ait-test") == 5


def test_tx_resolve_next_nonce_batch_entries_do_not_double_count(monkeypatch):
    """Simulates the batch loop: each entry sees the previous entry's
    pending tx, so per-entry offsets would skip nonces if applied twice."""
    from aitbc_cli.commands import transactions as tx_mod

    monkeypatch.delenv("CHAIN_ID", raising=False)
    pending: list[dict] = []

    class _C:
        def __init__(self, base_url="", **kw):
            self.base_url = base_url

        def get(self, endpoint, **kw):
            if endpoint.startswith("/rpc/mempool"):
                return {"transactions": list(pending)}
            return {"nonce": 5}

        def post(self, endpoint, json=None, **kw):
            pending.append(_pending_tx(SENDER, json["nonce"]))
            return {"transaction_hash": f"0x{json['nonce']}"}

    with patch("aitbc_cli.commands.transactions.AITBCHTTPClient", _C):
        n1 = tx_mod._resolve_next_nonce("http://node:8202", SENDER, "ait-test", nonce_offset=0)
        # entry 1 "submitted": its tx is now pending at n1
        pending.append(_pending_tx(SENDER, n1))
        n2 = tx_mod._resolve_next_nonce("http://node:8202", SENDER, "ait-test", nonce_offset=1)
        assert (n1, n2) == (5, 6)


# ------------------------------------------------------------- market nonce


def test_market_get_next_nonce_skips_pending(monkeypatch):
    from aitbc_cli.commands import market as market_mod

    monkeypatch.setattr(market_mod, "get_wallet_address", lambda: SENDER)
    monkeypatch.setattr(
        market_mod, "get_config", lambda: MagicMock(blockchain_rpc_url="http://node:8202", hub_discovery_url=None)
    )
    monkeypatch.setattr(market_mod, "get_chain_id", lambda: "ait-test")
    monkeypatch.setattr(market_mod, "get_account_nonce", lambda addr, cid: 8)

    class _C:
        def __init__(self, base_url="", **kw):
            self.base_url = base_url

        def get(self, endpoint, **kw):
            if endpoint.startswith("/rpc/mempool"):
                return {"transactions": [_pending_tx(SENDER, 8)]}
            return {}

    monkeypatch.setattr(market_mod, "AITBCHTTPClient", _C)
    monkeypatch.setattr(market_mod, "normalize_hub_base", lambda h: None)
    assert market_mod.get_next_nonce(SENDER) == 9


def test_market_get_next_nonce_probe_failure_returns_sealed(monkeypatch):
    from aitbc_cli.commands import market as market_mod

    monkeypatch.setattr(market_mod, "get_wallet_address", lambda: SENDER)
    monkeypatch.setattr(
        market_mod, "get_config", lambda: MagicMock(blockchain_rpc_url="http://node:8202", hub_discovery_url=None)
    )
    monkeypatch.setattr(market_mod, "get_chain_id", lambda: "ait-test")
    monkeypatch.setattr(market_mod, "get_account_nonce", lambda addr, cid: 8)

    class _Down:
        def __init__(self, base_url="", **kw):
            raise RuntimeError("unreachable")

    monkeypatch.setattr(market_mod, "AITBCHTTPClient", _Down)
    monkeypatch.setattr(market_mod, "normalize_hub_base", lambda h: None)
    assert market_mod.get_next_nonce(SENDER) == 8


# ------------------------------------------------------------- escrow nonce


def test_get_buyer_nonce_skips_pending():
    from aitbc_cli.utils import escrow as escrow_mod

    with patch.object(escrow_mod, "AITBCHTTPClient", _endpoint_client(11, [_pending_tx(SENDER, 11)])):
        assert escrow_mod.get_buyer_nonce(None, "http://node:8202", SENDER) == 12


def test_get_buyer_nonce_probe_failure_returns_sealed():
    from aitbc_cli.utils import escrow as escrow_mod

    class _C:
        def __init__(self, base_url="", **kw):
            self.base_url = base_url

        def get(self, endpoint, **kw):
            if endpoint.startswith("/rpc/mempool"):
                raise RuntimeError("down")
            return {"nonce": 11}

    # RuntimeError is outside pending_nonce_floor's expected probe errors and
    # propagates to get_buyer_nonce's broad abort — a mempool read failure
    # must never silently sign a colliding nonce.
    from aitbc_cli.utils.error_handling import CLIError

    with patch.object(escrow_mod, "AITBCHTTPClient", _C):
        with pytest.raises(CLIError):
            escrow_mod.get_buyer_nonce(None, "http://node:8202", SENDER)
