"""Historical replay fixture — one block per consensus era, replayed through
the real pull-sync import path.

Every consensus change so far was verified with unit tests plus a few live
blocks; nothing proved the v2-v8 version ladder still replays old blocks. This
fixture is that proof: a small deterministic chain replayed through
``ChainSync.import_block`` (``_append_block`` → parallel/sequential apply with
state-root verification), asserting each block's stored state_root equals the
FROZEN literal below. The literals were generated once under correct code —
regenerate them only when intentionally changing historical semantics.

Covered eras:

- h1 **v5 same-sender pair**: both txs signed at nonce 0 — the
  parallel-proposal-era pattern where the producer rewrote the second tx's
  nonce to the live account nonce. The pair is served with ``signature``
  fields intact: the signature covers the *signed* nonce (0), not the
  rewritten one (1), so a signature check inside ``compute_state_delta``
  rejects block h1 — the fixture fails under the ungated-v<7 check this
  guards against (see ``TestReplayParityPreV7``).
- h2 **v5 BRIDGE_RELEASE**: pseudo-sender credit carrying a
  ``bridge_signature`` from the on-chain ``bridge_release_authority``.
- h3 **v7 GPU_REGISTER**: the first version permitting GPU transaction types;
  sequential-only apply with strict signed nonce.
- h4 **v8 TRANSFER**: height/stamp-derived current-era rules — signed nonce is
  authoritative end to end.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aitbc_chain.base_models import Account, Block, ChainParameter
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.state_transition import get_block_version
from aitbc_chain.sync import ChainSync
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.bridge_credit import sign_bridge_credit
from sqlmodel import Session, create_engine, select

CHAIN = "replay-fixture"
T0 = datetime(2026, 1, 1, tzinfo=UTC)

# Fixed keys — deterministic signatures/addresses for a stable fixture.
KEY_A = "0x" + "11" * 32  # fixture sender
KEY_BRIDGE = "0x" + "22" * 32  # bridge release authority
KEY_RECIPIENT = "0x" + "33" * 32  # recipient account

ADDR_A = derive_ethereum_address(KEY_A)
ADDR_BRIDGE = derive_ethereum_address(KEY_BRIDGE)
ADDR_B = derive_ethereum_address(KEY_RECIPIENT)


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    return factory


def _seed_genesis(session_factory) -> None:
    """Block 0 + funded fixture accounts + the bridge authority parameter.

    Block 0's recorded state_root must be the real root of the seeded accounts:
    the import path refuses block 1 when the head row's root disagrees with the
    account table (the fork point check)."""
    from aitbc_chain.state.state_root_utils import compute_state_root_full

    with session_factory() as session:
        for addr, balance in ((ADDR_A, 10**9), (ADDR_B, 0)):
            session.add(Account(chain_id=CHAIN, address=addr, balance=balance, nonce=0))
        session.add(
            Block(
                chain_id=CHAIN,
                height=0,
                hash="0x" + "00" * 32,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
            )
        )
        session.add(ChainParameter(chain_id=CHAIN, parameter="bridge_release_authority", value=ADDR_BRIDGE, applied_height=0))
        session.commit()
        genesis = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 0)).one()
        genesis.state_root = compute_state_root_full(session, CHAIN)
        session.commit()


def _signed_tx(key: str, sender_addr: str, nonce: int, tx_type: str = "TRANSFER", **extra: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": sender_addr,
        "to": extra.pop("to", ADDR_B),
        "amount": extra.pop("amount", 10),
        "fee": extra.pop("fee", 1),
        "nonce": nonce,
        "payload": extra.pop("payload", {}),
        "type": tx_type,
        "chain_id": CHAIN,
        **extra,
    }
    tx["signature"] = sign_transaction_data(tx, key)
    return tx


def _block(height: int, parent_hash: str, version: int, txs: list[dict[str, Any]], state_root: str) -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": parent_hash,
        "proposer": ADDR_A,
        "timestamp": (T0 + timedelta(seconds=60 * height)).isoformat(),
        "tx_count": len(txs),
        "state_root": state_root,
        "block_metadata": f'{{"state_transition_version": {version}}}',
        "signature": "",
        "transactions": txs,
    }


def _bridge_release_tx(nonce: int = 0) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": "bridge_release",
        "to": ADDR_B,
        "amount": 500,
        "fee": 0,
        "nonce": nonce,
        "payload": {"remote_chain": "fixture-remote", "remote_tx": "0xremote1"},
        "type": "BRIDGE_RELEASE",
        "chain_id": CHAIN,
        "tx_hash": "0x" + "br"[:2].ljust(64, "0"),
    }
    tx["bridge_signature"] = sign_bridge_credit(tx, tx["tx_hash"], KEY_BRIDGE)
    return tx


def _gpu_register_tx(nonce: int) -> dict[str, Any]:
    return _signed_tx(
        KEY_A,
        ADDR_A,
        nonce,
        tx_type="GPU_REGISTER",
        amount=0,
        fee=0,
        payload={
            "gpu_id": "fixture-gpu-001",
            "model": "FIXTURE-9000",
            "memory_gb": 24,
            "cuda_version": "12.4",
            "region": "test",
            "capabilities": ["inference"],
            "price_per_hour": "1.0",
            "miner_id": "fixture-miner",
        },
    )


def _build_chain() -> list[dict[str, Any]]:
    """The fixture chain. Transaction *content* is deterministic; the recorded
    ``state_root`` per block is asserted against EXPECTED_ROOTS."""
    tx1 = _signed_tx(KEY_A, ADDR_A, nonce=0)
    tx2 = _signed_tx(KEY_A, ADDR_A, nonce=0)  # shared signed nonce — v5 parallel-era
    tx1["tx_hash"] = "0x" + "a1" * 32
    tx2["tx_hash"] = "0x" + "a2" * 32
    blocks = [
        _block(1, "0x" + "00" * 32, 5, [tx1, tx2], EXPECTED_ROOTS[1]),
        _block(2, "0x" + "01" * 16, 5, [_bridge_release_tx()], EXPECTED_ROOTS[2]),
        _block(3, "0x" + "02" * 16, 7, [_gpu_register_tx(nonce=2)], EXPECTED_ROOTS[3]),
        _block(4, "0x" + "03" * 16, 8, [_signed_tx(KEY_A, ADDR_A, nonce=3, amount=7)], EXPECTED_ROOTS[4]),
    ]
    for b in blocks[1:]:
        b["parent_hash"] = blocks[b["height"] - 2]["hash"]  # hash = f"0x{h:064x}"
    return blocks


# Frozen expected state roots per block height — generated once under correct
# code and frozen on purpose: a consensus change that alters v2-v8 apply
# semantics changes the computed root and fails here. Update the literals only
# alongside a deliberate semantics change (and say so in the commit).
EXPECTED_ROOTS: dict[int, str] = {
    1: "0x72079a920232018ceafaabd45e52a2387fbd0a78ed954d469bd0ea564dd6fe69",
    2: "0x40082b3630a44456a40ceff6758ea6d38bc788b52a1e9e71686d94dc2247ba82",
    3: "0x3faf51a01b0670b5743e29a966b5a5c726b3641b3662f18e9889026bdb74f273",
    4: "0x95b3d015e93ac365fd0f9d94545df7bb35e48205e86c93d3d98030df5f468f78",
}

EXPECTED_FINAL: dict[str, tuple[int, int]] = {
    ADDR_A: (999999970, 4),  # (balance, nonce) after h4
    ADDR_B: (527, 0),
}


class TestHistoricalReplay:
    def test_each_fixture_block_replays_its_era(self, session_factory, monkeypatch):
        # The eras the fixture asserts must resolve from the metadata stamps.
        for h, v in ((1, 5), (2, 5), (3, 7), (4, 8)):
            assert get_block_version({"block_metadata": f'{{"state_transition_version": {v}}}'}, h) == v

        # Exercise the parallel path like the fleet does — a 2-tx same-sender
        # block conflicts at rate 1.0, so the threshold is opened deliberately:
        # the bug this fixture guards lived inside compute_state_delta, which
        # only runs on that path.
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        monkeypatch.setattr(settings, "conflict_threshold", 1.0)

        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)
        blocks = _build_chain()
        for block_data in blocks:
            result = sync.import_block(block_data, transactions=block_data["transactions"])
            assert result.accepted, f"block {block_data['height']} rejected: {result.reason}"
            with session_factory() as session:
                stored = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == block_data["height"])).one()
                assert stored.state_root == EXPECTED_ROOTS[block_data["height"]]

        # Final state equality — the strongest replay contract.
        with session_factory() as session:
            got = {
                a.address: (a.balance, a.nonce) for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()
            }
        assert got == EXPECTED_FINAL

    def test_v5_pair_block_shape_is_the_regression_shape(self):
        """Guard the guard: the fixture must keep carrying the exact shape that
        exposed the bug — signature present, signed nonce != applied nonce."""
        blocks = _build_chain()
        v5 = blocks[0]
        tx1, tx2 = v5["transactions"]
        assert tx1["from"] == tx2["from"] == ADDR_A
        assert tx1["nonce"] == tx2["nonce"] == 0  # shared signed nonce
        assert tx1["signature"] and tx2["signature"]  # signatures on the wire
