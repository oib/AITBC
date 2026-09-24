import hashlib
import json
import secrets
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from aitbc_chain.config import settings
from aitbc_chain.models import Account, Block, Transaction
from aitbc_chain.rpc import sync as rpc_sync
from aitbc_chain.rpc import utils as rpc_utils
from eth_account import Account as EthAccount
from eth_keys import keys
from eth_utils import keccak
from sqlmodel import Session, create_engine, select

from aitbc_chain.metadata import chain_metadata


def _hex(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture(autouse=True)
def _isolated_nonce_store(tmp_path, monkeypatch):
    """Point the shared nonce store at a per-test file, never the real DATA_DIR."""
    db_path = tmp_path / "admin_nonces.db"
    monkeypatch.setattr(rpc_utils, "_nonce_db_path", lambda: db_path)
    return db_path


@pytest.fixture
def admin_signer(monkeypatch):
    """Create an admin account, trust it, and return a payload-signing function.

    The signer injects the freshness fields the replay guard requires. Pass
    overrides to change them — ``None`` removes the field before signing.
    """
    admin = EthAccount.create()
    monkeypatch.setattr(settings, "bridge_admin_addresses", admin.address.lower())

    def _sign(payload: dict, **overrides) -> dict:
        payload.setdefault("issued_at", datetime.now(UTC).isoformat())
        payload.setdefault("nonce", secrets.token_hex(16))
        payload.setdefault("target_chain_id", settings.chain_id or "ait-mainnet")
        for key, value in overrides.items():
            if value is None:
                payload.pop(key, None)
            else:
                payload[key] = value
        payload["admin_address"] = admin.address.lower()
        message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        pk = keys.PrivateKey(admin.key)
        payload["admin_signature"] = pk.sign_msg_hash(keccak(message)).to_hex()
        return payload

    return _sign


@pytest.fixture
def isolated_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "test_force_sync_endpoints.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    chain_metadata.create_all(engine)

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    # session_scope is imported into rpc.sync from ..database — patch it there.
    monkeypatch.setattr(rpc_sync, "session_scope", _session_scope)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def mock_request():
    """FastAPI Request mock — export_chain/import_chain accept it but don't use it."""
    return Mock()


@pytest.mark.asyncio
async def test_export_chain_filters_records_by_chain_id(isolated_engine, mock_request):
    with Session(isolated_engine) as session:
        session.add(
            Block(
                chain_id="chain-a",
                height=0,
                hash=_hex("chain-a-block-0"),
                parent_hash="0x00",
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=1,
            )
        )
        session.add(
            Block(
                chain_id="chain-a",
                height=1,
                hash=_hex("chain-a-block-1"),
                parent_hash=_hex("chain-a-block-0"),
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 1),
                tx_count=0,
            )
        )
        session.add(
            Block(
                chain_id="chain-b",
                height=0,
                hash=_hex("chain-b-block-0"),
                parent_hash="0x00",
                proposer="node-b",
                timestamp=datetime(2026, 1, 1, 0, 0, 2),
                tx_count=1,
            )
        )
        session.add(Account(chain_id="chain-a", address="alice", balance=10, nonce=1))
        session.add(Account(chain_id="chain-b", address="mallory", balance=99, nonce=5))
        session.add(
            Transaction(
                chain_id="chain-a",
                tx_hash=_hex("chain-a-tx"),
                block_height=0,
                sender="alice",
                recipient="bob",
                payload={"kind": "payment"},
                value=7,
                fee=1,
                nonce=2,
                status="confirmed",
                timestamp="2026-01-01T00:00:00",
                tx_metadata="meta-a",
            )
        )
        session.add(
            Transaction(
                chain_id="chain-b",
                tx_hash=_hex("chain-b-tx"),
                block_height=0,
                sender="mallory",
                recipient="eve",
                payload={"kind": "payment"},
                value=3,
                fee=1,
                nonce=1,
                status="confirmed",
                timestamp="2026-01-01T00:00:02",
                tx_metadata="meta-b",
            )
        )
        session.commit()

    result = await rpc_sync.export_chain(mock_request, chain_id="chain-a")

    assert result["success"] is True
    assert result["export_data"]["chain_id"] == "chain-a"
    assert [block["height"] for block in result["export_data"]["blocks"]] == [0, 1]
    assert {block["chain_id"] for block in result["export_data"]["blocks"]} == {"chain-a"}
    assert len(result["export_data"]["accounts"]) == 1
    assert len(result["export_data"]["transactions"]) == 1
    assert result["export_data"]["transactions"][0]["tx_hash"] == _hex("chain-a-tx")
    assert result["export_data"]["transactions"][0]["payload"] == {"kind": "payment"}


@pytest.mark.asyncio
async def test_import_chain_dedupes_duplicate_heights_and_preserves_transaction_fields(
    isolated_engine, mock_request, admin_signer
):
    with Session(isolated_engine) as session:
        session.add(
            Block(
                chain_id="chain-a",
                height=0,
                hash=_hex("old-chain-a-block"),
                parent_hash="0x00",
                proposer="node-a",
                timestamp=datetime(2025, 12, 31, 23, 59, 59),
                tx_count=0,
            )
        )
        session.add(Account(chain_id="chain-a", address="alice", balance=1, nonce=0))
        session.add(
            Transaction(
                chain_id="chain-a",
                tx_hash=_hex("old-chain-a-tx"),
                block_height=0,
                sender="alice",
                recipient="bob",
                payload={"kind": "payment"},
                value=1,
                fee=1,
                nonce=0,
                status="pending",
                timestamp="2025-12-31T23:59:59",
                tx_metadata="old",
            )
        )
        session.add(
            Block(
                chain_id="chain-b",
                height=0,
                hash=_hex("chain-b-existing-block"),
                parent_hash="0x00",
                proposer="node-b",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=0,
            )
        )
        session.commit()

    import_payload = {
        "chain_id": "chain-a",
        "blocks": [
            {
                "chain_id": "chain-a",
                "height": 0,
                "hash": _hex("incoming-block-0-old"),
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": "2026-01-02T00:00:00",
                "tx_count": 0,
            },
            {
                "chain_id": "chain-a",
                "height": 0,
                "hash": _hex("incoming-block-0-new"),
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": "2026-01-02T00:00:01",
                "tx_count": 1,
            },
            {
                "chain_id": "chain-a",
                "height": 1,
                "hash": _hex("incoming-block-1"),
                "parent_hash": _hex("incoming-block-0-new"),
                "proposer": "node-a",
                "timestamp": "2026-01-02T00:00:02",
                "tx_count": 1,
            },
        ],
        "accounts": [{"chain_id": "chain-a", "address": "alice", "balance": 25, "nonce": 2}],
        "transactions": [
            {
                "chain_id": "chain-a",
                "tx_hash": _hex("incoming-tx-1"),
                "block_height": 1,
                "sender": "alice",
                "recipient": "bob",
                "payload": {"kind": "payment"},
                "value": 10,
                "fee": 1,
                "nonce": 2,
                "timestamp": "2026-01-02T00:00:02",
                "status": "confirmed",
                "created_at": "2026-01-02T00:00:02",
                "tx_metadata": "new",
            }
        ],
    }

    result = await rpc_sync.import_chain(mock_request, admin_signer(import_payload))

    assert result["success"] is True
    assert result["imported_blocks"] == 2
    assert result["imported_transactions"] == 1

    with Session(isolated_engine) as session:
        chain_a_blocks = session.exec(select(Block).where(Block.chain_id == "chain-a").order_by(Block.height)).all()
        chain_b_blocks = session.exec(select(Block).where(Block.chain_id == "chain-b").order_by(Block.height)).all()
        chain_a_accounts = session.exec(select(Account).where(Account.chain_id == "chain-a")).all()
        chain_a_transactions = session.exec(select(Transaction).where(Transaction.chain_id == "chain-a")).all()

    assert [block.height for block in chain_a_blocks] == [0, 1]
    assert chain_a_blocks[0].hash == _hex("incoming-block-0-new")
    assert len(chain_b_blocks) == 1
    assert chain_b_blocks[0].hash == _hex("chain-b-existing-block")
    assert len(chain_a_accounts) == 1
    assert chain_a_accounts[0].balance == 25
    assert len(chain_a_transactions) == 1
    assert chain_a_transactions[0].tx_hash == _hex("incoming-tx-1")
    assert chain_a_transactions[0].timestamp == "2026-01-02T00:00:02"


@pytest.mark.asyncio
async def test_import_chain_requires_admin_signature(isolated_engine, mock_request):
    """import_chain rejects unauthenticated requests (v0.18.0 B2)."""
    from fastapi import HTTPException

    import_payload = {
        "chain_id": "chain-a",
        "blocks": [
            {
                "chain_id": "chain-a",
                "height": 0,
                "hash": _hex("block-0"),
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": "2026-01-01T00:00:00",
                "tx_count": 0,
            }
        ],
    }

    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, import_payload)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_import_chain_invalid_payload_leaves_chain_intact(isolated_engine, mock_request, admin_signer):
    """A malformed record must abort the import *before* any deletion (v0.18.0 B2)."""
    from fastapi import HTTPException

    with Session(isolated_engine) as session:
        session.add(
            Block(
                chain_id="chain-a",
                height=0,
                hash=_hex("existing-block-0"),
                parent_hash="0x00",
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=1,
            )
        )
        session.add(
            Transaction(
                chain_id="chain-a",
                tx_hash=_hex("existing-tx"),
                block_height=0,
                sender="alice",
                recipient="bob",
                payload={},
                value=1,
                fee=1,
                nonce=0,
                status="confirmed",
            )
        )
        session.commit()

    import_payload = {
        "chain_id": "chain-a",
        "blocks": [
            {
                "chain_id": "chain-a",
                "height": 0,
                "hash": _hex("incoming-block-0"),
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": "2026-01-02T00:00:00",
                "tx_count": 0,
            }
        ],
        "transactions": [
            {
                "chain_id": "chain-a",
                "tx_hash": _hex("bad-tx"),
                "block_height": 0,
                # missing required "sender"
                "recipient": "bob",
            }
        ],
    }

    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, admin_signer(import_payload))
    assert exc_info.value.status_code == 400

    with Session(isolated_engine) as session:
        blocks = session.exec(select(Block).where(Block.chain_id == "chain-a")).all()
        txs = session.exec(select(Transaction).where(Transaction.chain_id == "chain-a")).all()
    assert [b.hash for b in blocks] == [_hex("existing-block-0")]
    assert [t.tx_hash for t in txs] == [_hex("existing-tx")]


@pytest.mark.asyncio
async def test_import_chain_preserves_other_chains_on_hash_conflict(isolated_engine, mock_request, admin_signer):
    """Import must never delete blocks belonging to a different chain (v0.18.0 B2)."""
    with Session(isolated_engine) as session:
        session.add(
            Block(
                chain_id="chain-a",
                height=0,
                hash=_hex("chain-a-block-0"),
                parent_hash="0x00",
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=0,
            )
        )
        session.add(
            Block(
                chain_id="chain-a",
                height=1,
                hash=_hex("chain-a-block-1"),
                parent_hash=_hex("chain-a-block-0"),
                proposer="node-a",
                timestamp=datetime(2026, 1, 1, 0, 0, 1),
                tx_count=0,
            )
        )
        session.add(
            Block(
                chain_id="chain-b",
                height=0,
                hash=_hex("chain-b-block-0"),
                parent_hash="0x00",
                proposer="node-b",
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                tx_count=0,
            )
        )
        session.add(
            Block(
                chain_id="chain-b",
                height=1,
                hash=_hex("chain-b-block-1"),
                parent_hash=_hex("chain-b-block-0"),
                proposer="node-b",
                timestamp=datetime(2026, 1, 1, 0, 0, 1),
                tx_count=0,
            )
        )
        session.commit()

    with Session(isolated_engine) as session:
        chain_a_blocks = session.exec(select(Block).where(Block.chain_id == "chain-a").order_by(Block.height)).all()

    conflicting_hash = chain_a_blocks[0].hash

    import_payload = {
        "chain_id": "chain-c",
        "blocks": [
            {
                "chain_id": "chain-c",
                "height": 0,
                "hash": conflicting_hash,
                "parent_hash": _hex("parent-0"),
                "proposer": _hex("proposer-0"),
                "timestamp": "2026-01-01T00:00:00",
                "tx_count": 0,
            },
            {
                "chain_id": "chain-c",
                "height": 1,
                "hash": _hex("chain-c-block-1"),
                "parent_hash": conflicting_hash,
                "proposer": _hex("proposer-1"),
                "timestamp": "2026-01-01T00:00:01",
                "tx_count": 0,
            },
        ],
    }

    result = await rpc_sync.import_chain(mock_request, admin_signer(import_payload))

    assert result["success"] is True
    assert result["imported_blocks"] == 2

    with Session(isolated_engine) as session:
        chain_c_blocks = session.exec(select(Block).where(Block.chain_id == "chain-c").order_by(Block.height)).all()
        chain_a_blocks_after = session.exec(select(Block).where(Block.chain_id == "chain-a").order_by(Block.height)).all()

    assert [block.height for block in chain_c_blocks] == [0, 1]
    assert chain_c_blocks[0].hash == conflicting_hash
    # chain-a blocks must be untouched — a hash collision on another chain is
    # not a conflict under the (chain_id, hash) uniqueness model.
    assert [block.height for block in chain_a_blocks_after] == [0, 1]


def _valid_import_payload(chain_id: str = "chain-a") -> dict:
    return {
        "chain_id": chain_id,
        "blocks": [
            {
                "chain_id": chain_id,
                "height": 0,
                "hash": _hex(f"{chain_id}-import-block-0"),
                "parent_hash": "0x00",
                "proposer": "node-a",
                "timestamp": "2026-01-02T00:00:00",
                "tx_count": 0,
            }
        ],
    }


@pytest.mark.asyncio
async def test_import_chain_rejects_replayed_signed_payload(isolated_engine, mock_request, admin_signer):
    """A captured signed request must not be usable twice (replay protection)."""
    from fastapi import HTTPException

    signed = admin_signer(_valid_import_payload())

    result = await rpc_sync.import_chain(mock_request, signed)
    assert result["success"] is True

    # Replaying the byte-identical payload (same nonce) is rejected even
    # though the admin signature itself is still valid.
    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, dict(signed))
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_import_chain_rejects_stale_issued_at(isolated_engine, mock_request, admin_signer):
    """Signatures older than the freshness window are rejected."""
    from fastapi import HTTPException

    stale = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    signed = admin_signer(_valid_import_payload(), issued_at=stale)

    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, signed)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_import_chain_rejects_missing_issued_at(isolated_engine, mock_request, admin_signer):
    from fastapi import HTTPException

    signed = admin_signer(_valid_import_payload(), issued_at=None)

    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, signed)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_import_chain_rejects_missing_nonce(isolated_engine, mock_request, admin_signer):
    from fastapi import HTTPException

    signed = admin_signer(_valid_import_payload(), nonce=None)

    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, signed)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_import_chain_rejects_nonce_reuse_on_different_payload(isolated_engine, mock_request, admin_signer):
    """The nonce binds the signature to one request, not just one payload."""
    from fastapi import HTTPException

    shared_nonce = secrets.token_hex(16)
    first = admin_signer(_valid_import_payload("chain-a"), nonce=shared_nonce)
    assert (await rpc_sync.import_chain(mock_request, first))["success"] is True

    second = admin_signer(_valid_import_payload("chain-b"), nonce=shared_nonce)
    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, second)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_signature_rejects_wrong_target_node(isolated_engine, mock_request, admin_signer, monkeypatch):
    """A payload signed for a different node is rejected (target binding)."""
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "p2p_node_id", "node-under-test")
    monkeypatch.setattr(settings, "proposer_id", "")
    signed = admin_signer(_valid_import_payload(), target_node_id="some-other-node")

    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, signed)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_signature_accepts_matching_target(isolated_engine, mock_request, admin_signer, monkeypatch):
    """Correctly targeted payloads still pass the binding check."""
    monkeypatch.setattr(settings, "p2p_node_id", "node-under-test")
    monkeypatch.setattr(settings, "chain_id", "chain-a")
    signed = admin_signer(_valid_import_payload(), target_node_id="node-under-test", target_chain_id="chain-a")
    result = await rpc_sync.import_chain(mock_request, signed)
    assert result["success"] is True


@pytest.mark.asyncio
async def test_admin_signature_rejects_wrong_target_chain(isolated_engine, mock_request, admin_signer, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "chain_id", "chain-a")
    signed = admin_signer(_valid_import_payload(), target_chain_id="chain-elsewhere")

    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, signed)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "peer_url",
    [
        "http://127.0.0.1:8006",
        "http://127.0.0.2:8006",
        "http://localhost:8006",
        "http://0.0.0.0:8006",
        "http://169.254.169.254:80",
        "http://[::1]:8006",
        "http://[::ffff:127.0.0.1]:8006",
        "http://[fe80::1]:8006",
        "http://[::ffff:169.254.169.254]:80",
    ],
)
async def test_force_sync_rejects_forbidden_peer_addresses(mock_request, admin_signer, peer_url):
    """Loopback, link-local/metadata, mapped and unspecified peers are SSRF."""
    from fastapi import HTTPException

    signed = admin_signer({"peer_url": peer_url})
    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.force_sync(mock_request, signed)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_force_sync_rejects_hostname_resolving_to_loopback(mock_request, admin_signer, monkeypatch):
    """A public-looking hostname that resolves to loopback is rejected."""
    import socket
    from fastapi import HTTPException

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 8006))]
    )
    signed = admin_signer({"peer_url": "http://peer.example.net:8006"})
    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.force_sync(mock_request, signed)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_force_sync_allows_private_peer_ips(mock_request, admin_signer, monkeypatch):
    """RFC1918 peers stay reachable — fleet nodes sync over internal LANs."""
    import requests
    from fastapi import HTTPException

    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(status_code=503)))
    # Deliberately a non-routable RFC1918 literal with no relation to any real
    # deployment: this file is public, and the SSRF check under test only rejects
    # loopback/link-local/multicast/reserved, so any private address exercises it.
    signed = admin_signer({"peer_url": "http://192.168.1.136:8006"})
    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.force_sync(mock_request, signed)
    # Passed signature + freshness + SSRF, failed only on the peer fetch.
    assert exc_info.value.status_code == 400
    assert "Failed to fetch peer chain" in exc_info.value.detail


def test_destructive_routes_require_api_key(admin_signer, monkeypatch, isolated_engine):
    """POST /rpc/import-chain and /rpc/force-sync reject without X-API-Key."""
    import requests
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aitbc_chain.rpc import escrow_routes
    from aitbc_chain.rpc.routers import core

    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", "test-api-key")
    # Keep force_sync's peer fetch off the network — it must fail fast with
    # a non-200 rather than dialing the (literal) test IP.
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(status_code=502)))
    app = FastAPI()
    app.include_router(core.router, prefix="/rpc")
    client = TestClient(app, raise_server_exceptions=False)

    import_payload = admin_signer(_valid_import_payload())
    assert client.post("/rpc/import-chain", json=import_payload).status_code == 403
    assert client.post("/rpc/import-chain", json=import_payload, headers={"X-API-Key": "wrong"}).status_code == 403

    # A second signed payload (fresh nonce) reaches the handler with the key.
    import_payload2 = admin_signer(_valid_import_payload())
    assert client.post("/rpc/import-chain", json=import_payload2, headers={"X-API-Key": "test-api-key"}).status_code == 200

    sync_payload = admin_signer({"peer_url": "http://192.168.1.9:8006"})
    assert client.post("/rpc/force-sync", json=sync_payload).status_code == 403

    sync_payload2 = admin_signer({"peer_url": "http://192.168.1.9:8006"})
    resp = client.post("/rpc/force-sync", json=sync_payload2, headers={"X-API-Key": "test-api-key"})
    # API key accepted; the handler then fails on the peer fetch, not auth.
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_chain_rejects_nonce_used_by_another_worker(
    isolated_engine, mock_request, admin_signer, _isolated_nonce_store
):
    """The nonce store is shared: a nonce consumed via a *separate* sqlite
    connection (a sibling gunicorn worker) still rejects the request."""
    import sqlite3

    from fastapi import HTTPException

    signed = admin_signer(_valid_import_payload())
    conn = sqlite3.connect(_isolated_nonce_store)
    conn.execute("CREATE TABLE IF NOT EXISTS admin_nonce (nonce TEXT PRIMARY KEY, expires_at REAL NOT NULL)")
    conn.execute("INSERT INTO admin_nonce (nonce, expires_at) VALUES (?, ?)", (signed["nonce"], time.time() + 600))
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, signed)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_issued_at", [float("nan"), float("inf"), float("-inf")])
async def test_import_chain_rejects_non_finite_issued_at(isolated_engine, mock_request, admin_signer, bad_issued_at):
    """json accepts NaN/Infinity literals; ``abs(now - nan) > skew`` is False,
    so a non-finite timestamp must be rejected explicitly, not trusted fresh."""
    from fastapi import HTTPException

    signed = admin_signer(_valid_import_payload(), issued_at=bad_issued_at)
    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, signed)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_signature_rejects_missing_target_chain(isolated_engine, mock_request, admin_signer):
    """target_chain_id is required — payloads without it cannot be replayed
    across chains."""
    from fastapi import HTTPException

    signed = admin_signer(_valid_import_payload(), target_chain_id=None)
    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, signed)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_signature_rejects_target_when_node_has_no_identity(
    isolated_engine, mock_request, admin_signer, monkeypatch
):
    """Fail closed: a payload naming a target node cannot be honoured by a
    node with no configured identity to match it against."""
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "p2p_node_id", "")
    monkeypatch.setattr(settings, "proposer_id", "")
    signed = admin_signer(_valid_import_payload(), target_node_id="any-node")
    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.import_chain(mock_request, signed)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_force_sync_rejects_scoped_ipv6_resolution(mock_request, admin_signer, monkeypatch):
    """getaddrinfo can return scoped literals like ``fe80::1%eth0`` that
    ``ip_address()`` cannot parse — must be a clean 400, not a 500."""
    import socket

    from fastapi import HTTPException

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1%eth0", 8006, 0, 2))],
    )
    signed = admin_signer({"peer_url": "http://peer.example.net:8006"})
    with pytest.raises(HTTPException) as exc_info:
        await rpc_sync.force_sync(mock_request, signed)
    assert exc_info.value.status_code == 400
