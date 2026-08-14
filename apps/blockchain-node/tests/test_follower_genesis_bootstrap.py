"""A follower must build block 0 itself, not sync it and not weaken validation to accept it.

This node reset to an empty database and could not reach height 1. `_ensure_genesis_for_chains`
ran only in hub mode, so the follower had no block 0 of its own and had to receive one over
sync — but block 0 carries `proposer="genesis"` and no signature, and `sync_validator` refuses
unsigned blocks unless `TRUSTED_PROPOSERS` is non-empty.

The workaround is worse than it looks. A non-empty trusted set is not an exception for the
unsigned genesis; it is an allowlist applied to *every* block, checked before the signature is
even examined. So the price of importing one unsigned block was permanently narrowing which
proposers the node would ever accept, on the node least able to notice.

Building block 0 locally trusts nothing new: `_ensure_genesis_block` takes the hash and
state_root out of genesis.json rather than recomputing them. The node either writes the hub's
exact block 0 or writes a different hash and fails the very next block's parent_hash check.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from aitbc_chain.config import ProposerConfig
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.sync import ProposerSignatureValidator
from sqlmodel import Session, SQLModel, create_engine

CHAIN_ID = "ait-test.example.net"

# The shape the hub actually publishes at /agent/genesis.json: no top-level `genesis_hash`,
# the values live under `block`. The loader falls back to `block.hash`, and a test that
# invented a flatter file would pass while the real file failed.
GENESIS_FILE = {
    "chain_id": CHAIN_ID,
    "block": {
        "height": 0,
        "hash": "0x7a444401f721fd10040fb0df1b482c0f3ee998ad6d6101e412a973d3e5ec8e02",
        "parent_hash": "0x00",
        "proposer": "genesis",
        "timestamp": "2026-08-12T10:55:15.216243+00:00",
        "tx_count": 0,
        "chain_id": CHAIN_ID,
        "state_root": "0xe135ccc691cadc7ac5e1353d26ae3fdd376566f10ad5b9f9151534d65b0cc7df",
    },
    "allocations": [{"address": "ait1" + "fe" * 20, "balance": 3600000000000, "nonce": 0}],
}


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}", echo=False)
    SQLModel.metadata.create_all(engine)

    @contextmanager
    def _factory():
        with Session(engine) as session:
            yield session

    try:
        yield _factory
    finally:
        engine.dispose()


@pytest.fixture
def proposer(session_factory, tmp_path):
    """A follower's proposer: it holds no key and will never propose. It only bootstraps."""
    config = ProposerConfig(
        chain_id=CHAIN_ID,
        proposer_id="",
        interval_seconds=5,
        max_block_size_bytes=1_000_000,
        max_txs_per_block=100,
    )
    node = PoAProposer(config=config, session_factory=session_factory)

    genesis_file = tmp_path / "genesis.json"
    genesis_file.write_text(json.dumps(GENESIS_FILE))

    # The loader hardcodes /var/lib/aitbc/data/<chain>/genesis.json; point it at the fixture.
    with patch.object(PoAProposer, "_load_genesis_data_from_file", lambda self: json.loads(genesis_file.read_text())):
        # RPC bootstrap is tried first and would reach the network; force the local path.
        with patch.object(PoAProposer, "_load_genesis_block_from_rpc", AsyncMock(return_value=None)):
            yield node


def test_the_unsigned_genesis_is_why_trusted_proposers_got_abused() -> None:
    """Documents the rejection this fix routes around, so the reason survives the fix."""
    validator = ProposerSignatureValidator(trusted_proposers=[])

    ok, reason = validator.validate_block_signature({**GENESIS_FILE["block"], "signature": ""})

    assert ok is False
    assert "Unsigned block" in reason


def test_a_non_empty_trusted_set_filters_every_block_not_just_genesis() -> None:
    """The cost of the workaround: admitting genesis silently rejects the real proposer.

    An operator setting TRUSTED_PROPOSERS=genesis to get past block 0 would sync exactly one
    block and stall again, with a different error — which is how this turns into an afternoon.
    """
    validator = ProposerSignatureValidator(trusted_proposers=["genesis"])

    ok, reason = validator.validate_block_signature(
        {
            "hash": "0x" + "ab" * 32,
            "proposer": "ait1" + "fe" * 20,
            "signature": "0x" + "cd" * 65,
            "height": 1,
            "parent_hash": GENESIS_FILE["block"]["hash"],
            "timestamp": "2026-08-12T10:55:20+00:00",
        }
    )

    assert ok is False
    assert "not in trusted set" in reason


def test_follower_startup_actually_calls_the_bootstrap() -> None:
    """The fix is one line in a 200-line branch; pin that it is still wired in."""
    source = Path(__file__).resolve().parents[1] / "src/aitbc_chain/main.py"
    text = source.read_text()

    follower_branch = text.split('elif settings.blockchain_mode == "follower":')[1].split("if settings.")[0]

    assert "_bootstrap_genesis_for_follower" in follower_branch, "follower mode no longer bootstraps genesis"


class TestPeerUrlScheme:
    """RPC genesis bootstrap was dead against any TLS-fronted hub (V23-60).

    The deployed follower logged `Trying to fetch genesis block from
    http://https://hub.aitbc.bubuit.net` and failed with "Name or service not known". The
    normalisation tested only for `http://` before prepending `http://`, so an `https://` URL
    fell through the strip and got a second scheme bolted on.

    It stayed hidden because the failure is indistinguishable from a hub being down: the peer
    loop logs a DNS error and falls through to the local genesis.json. This node had that file
    and recovered; a node relying on RPC bootstrap has nothing to fall back on.
    """

    def test_an_https_peer_is_left_alone(self) -> None:
        from aitbc_chain.consensus.poa import _with_scheme

        assert _with_scheme("https://hub.aitbc.bubuit.net") == "https://hub.aitbc.bubuit.net"

    def test_an_http_peer_is_left_alone(self) -> None:
        from aitbc_chain.consensus.poa import _with_scheme

        assert _with_scheme("http://10.0.0.4:8202") == "http://10.0.0.4:8202"

    def test_a_bare_host_still_gets_a_scheme(self) -> None:
        """The behaviour the old code was for; it must survive the fix."""
        from aitbc_chain.consensus.poa import _with_scheme

        assert _with_scheme("10.0.0.4:8202") == "http://10.0.0.4:8202"

    def test_no_url_ever_ends_up_with_two_schemes(self) -> None:
        from aitbc_chain.consensus.poa import _with_scheme

        for raw in ("https://hub.example.net", "http://hub.example.net", "hub.example.net", "hub.example.net:8202"):
            assert _with_scheme(raw).count("://") == 1, raw
