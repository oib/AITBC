"""#2326 MARKET-ESCROW-SQUAT-1: ``sw_job_*`` ids double as on-chain escrow
keys, so they must be unguessable.

The old ``sha256(offer_id + buyer_wallet)[:8]`` suffix was deterministic —
offer ids and buyer wallets are public, so a squatter could enumerate the
second-granularity timestamp space and pre-register predicted future
escrow keys. The suffix is now CSPRNG output.
"""

from __future__ import annotations

import re

from aitbc_cli.commands.market.jobs import _new_sw_job_id


def test_sw_job_id_suffix_is_random() -> None:
    first = _new_sw_job_id()
    second = _new_sw_job_id()
    assert first != second
    assert first.startswith("sw_job_")
    suffix = first.rsplit("_", 1)[1]
    # secrets.token_hex(8) — 16 lowercase hex chars of CSPRNG output.
    assert re.fullmatch(r"[0-9a-f]{16}", suffix)


def test_sw_job_id_is_not_offer_wallet_derived() -> None:
    """The deterministic pre-#2326 shape hashed offer_id+buyer; two calls
    for the same logical job must still differ (no stable derivation)."""
    ids = {_new_sw_job_id() for _ in range(32)}
    assert len(ids) == 32


# --- #2326 residuals: alias-claim signature + lock-tx market_job_id binding ---


def test_build_escrow_lock_tx_carries_market_job_id() -> None:
    """The signed ESCROW_LOCK payload names the market job it backs so the
    market service can bind alias claims to this escrow (#2326)."""
    from decimal import Decimal

    from aitbc_cli.utils.escrow import build_escrow_lock_tx

    class _Ctx:
        pass

    tx = build_escrow_lock_tx(
        _Ctx(),
        "coord-job-1",
        "0x" + "11" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        Decimal("1.0"),
        7,
        chain_id="test-chain",
        market_job_id="ai_job_abc123",
    )
    assert tx["payload"]["market_job_id"] == "ai_job_abc123"
    assert tx["payload"]["job_id"] == "coord-job-1"

    tx_unbound = build_escrow_lock_tx(
        _Ctx(),
        "coord-job-1",
        "0x" + "11" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        Decimal("1.0"),
        7,
        chain_id="test-chain",
    )
    assert "market_job_id" not in tx_unbound["payload"]


def test_register_paid_market_job_signs_alias_claim(monkeypatch) -> None:
    """An escrow_job_id alias registration must carry the buyer signature
    fields bound to (escrow_job_id, buyer_address) — the user-tier API key
    alone no longer authorizes the claim (#2326)."""
    from decimal import Decimal

    import aitbc_cli.commands.market as market_pkg
    from aitbc_cli.commands.market.jobs import _register_paid_market_job

    posted: dict = {}

    class _Client:
        def post(self, path, json=None, **kwargs):
            posted["path"] = path
            posted["json"] = json
            return {"job_id": "j1"}

    monkeypatch.setattr("aitbc_cli.commands.ipfs._hub_market_client", lambda: _Client())
    monkeypatch.setattr(market_pkg, "get_chain_id", lambda: "test-chain")

    buyer_key = "0x" + "44" * 32
    from aitbc.crypto.crypto import derive_ethereum_address

    buyer = derive_ethereum_address(buyer_key)
    ctx = type("Ctx", (), {})()
    result = _register_paid_market_job(
        ctx,
        "ai_job_test1",
        {"model": "base"},
        buyer,
        "0x" + "22" * 20,
        "whisper",
        Decimal("1.0"),
        escrow_job_id="coord-job-9",
        signer_key=buyer_key,
    )
    assert result is not None
    body = posted["json"]
    assert body["payload"]["escrow_job_id"] == "coord-job-9"
    for field in ("signer_address", "chain_id", "issued_at", "signature"):
        assert body[field], field
    assert body["signer_address"] == buyer


def test_register_paid_market_job_self_bound_sends_no_signature(monkeypatch) -> None:
    """Jobs without an escrow_job_id alias keep the unsigned path — the
    signature requirement binds alias claims only."""
    from decimal import Decimal

    import aitbc_cli.commands.market as market_pkg
    from aitbc_cli.commands.market.jobs import _register_paid_market_job

    posted: dict = {}

    class _Client:
        def post(self, path, json=None, **kwargs):
            posted["json"] = json
            return {"job_id": "j2"}

    monkeypatch.setattr("aitbc_cli.commands.ipfs._hub_market_client", lambda: _Client())
    monkeypatch.setattr(market_pkg, "get_chain_id", lambda: "test-chain")

    ctx = type("Ctx", (), {})()
    result = _register_paid_market_job(
        ctx,
        "sw_job_x",
        {},
        "0x" + "11" * 20,
        "0x" + "22" * 20,
        "whisper",
        Decimal("1.0"),
    )
    assert result is not None
    for field in ("signer_address", "chain_id", "issued_at", "signature"):
        assert field not in posted["json"]
