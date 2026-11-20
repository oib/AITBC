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
