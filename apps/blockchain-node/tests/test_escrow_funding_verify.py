"""ESC-FUND-1: ``fund_contract`` must not mark a contract FUNDED on a hash it
never read. ``_verify_funding_lock`` re-loads the submitted ESCROW_LOCK —
sealed row first, hub mempool otherwise — and checks it carries the
contract's job_id, buyer, amount and escrow destination. Absence is
retryable (HTTP 425); a field mismatch or a different sealed hash for the
same job is permanent (HTTP 409). On refusal the create route drops the
just-created contract so no half state survives.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlmodel import Session

import aitbc_chain.rpc.escrow_routes as escrow_routes
from aitbc_chain.contracts.escrow import EscrowManager, EscrowState
from aitbc_chain.mempool import compute_tx_hash
from aitbc_chain.models import Escrow
from aitbc.utils import ait_to_units

BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"
NODE_WALLET = "0xADC923a0928B8415E666206D3703a870C1d578CE"
JOB_ID = "job-fund-verify"
CHAIN_ID = "test-chain"
AMOUNT = Decimal("1.0")
SETTLEMENT_KEY = "0x2222222222222222222222222222222222222222222222222222222222222222"


@pytest.fixture
def mgr() -> EscrowManager:
    return EscrowManager()


@pytest.fixture
def patched(monkeypatch, engine, mgr) -> EscrowManager:
    monkeypatch.setattr(escrow_routes, "_NODE_WALLET", NODE_WALLET)
    monkeypatch.setattr(escrow_routes, "_chain_id", lambda: CHAIN_ID)
    monkeypatch.setattr(escrow_routes, "_ESCROW_RELEASE_PRIVATE_KEY", SETTLEMENT_KEY)
    monkeypatch.setattr(escrow_routes, "_GENESIS_WALLET_PRIVATE_KEY", "")
    monkeypatch.setattr(escrow_routes, "_ESCROW_RELEASE_ADDRESS", "")
    monkeypatch.setattr(escrow_routes, "get_escrow_manager", lambda: mgr)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock", AsyncMock(return_value=None))

    @contextmanager
    def scope(chain_id: str = ""):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(escrow_routes, "session_scope", scope)
    return mgr


def _lock_tx() -> dict:
    """A canonical ESCROW_LOCK body as the create route would build it."""
    tx, _ = escrow_routes._build_lock_tx(JOB_ID, BUYER, PROVIDER, AMOUNT, nonce=0)
    tx["signature"] = "0xdeadbeef"
    return tx


def _sealed(tx: dict) -> dict:
    """A real sealed ``transactions`` row — `sender`/`recipient`/`value`, not
    the submitted body's `from`/`to`/`amount` (the shape the original fixture
    got wrong and live data corrected, queue 1066)."""
    return {
        "block_hash": "0x" + "11" * 32,
        "block_height": 123,
        "block_proposer": "0x" + "22" * 20,
        "created_at": 1761000000.0,
        "fee": tx["fee"],
        "nonce": tx["nonce"],
        "payload": dict(tx["payload"]),
        "recipient": tx["to"],
        "sender": tx["from"],
        "status": "confirmed",
        "timestamp": 1761000000,
        "transaction_id": 42,
        "tx_hash": compute_tx_hash(tx),
        "type": tx["type"],
        "value": tx["amount"],
    }


def _mempool_response(transactions: list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"success": True, "transactions": transactions, "count": len(transactions)}
    return resp


def _verify_kwargs() -> dict:
    return {"job_id": JOB_ID, "buyer": BUYER, "amount_units": ait_to_units(AMOUNT)}


@pytest.mark.asyncio
async def test_verify_sealed_lock_returns_it(patched, monkeypatch):
    tx = _lock_tx()
    sealed = _sealed(tx)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=sealed))
    get = AsyncMock()
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", get)

    found = await escrow_routes._verify_funding_lock(sealed["tx_hash"], **_verify_kwargs())

    assert found is sealed
    get.assert_not_awaited()  # sealed hit short-circuits the mempool probe


@pytest.mark.asyncio
async def test_verify_sealed_lock_with_different_hash_refuses(patched, monkeypatch):
    sealed = _sealed(_lock_tx())
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=sealed))

    with pytest.raises(HTTPException) as exc_info:
        await escrow_routes._verify_funding_lock("0x" + "ab" * 32, **_verify_kwargs())
    assert exc_info.value.status_code == 409


@pytest.mark.parametrize(
    "mutate, field",
    [
        (lambda row: row.update({"value": row["value"] + 1}), "amount"),
        (lambda row: row.update({"sender": PROVIDER}), "from"),
        (lambda row: row["payload"].update({"job_id": "other-job"}), "payload.job_id"),
        (lambda row: row.update({"recipient": BUYER}), "to"),
        (lambda row: row.update({"type": "TRANSFER"}), "type"),
    ],
)
@pytest.mark.asyncio
async def test_verify_sealed_lock_field_mismatch_refuses(patched, monkeypatch, mutate, field):
    """Mutations hit the sealed row's own keys (sender/recipient/value)."""
    sealed = _sealed(_lock_tx())
    mutate(sealed)
    sealed["tx_hash"] = "0x" + "ab" * 32  # pin the hash so the field check fires, not the hash check
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=sealed))

    with pytest.raises(HTTPException) as exc_info:
        await escrow_routes._verify_funding_lock("0x" + "ab" * 32, **_verify_kwargs())
    assert exc_info.value.status_code == 409
    assert field in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_mempool_lock_verifies_and_injects_hash(patched, monkeypatch):
    tx = _lock_tx()
    tx_hash = compute_tx_hash(tx)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=None))
    get = AsyncMock(return_value=_mempool_response([tx]))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", get)

    found = await escrow_routes._verify_funding_lock(tx_hash, **_verify_kwargs())

    assert found["tx_hash"] == tx_hash
    get.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_mempool_lock_state_tagged_still_verifies(patched, monkeypatch):
    """#2741: the live /mempool response tags entries ``state: "pending"``;
    the pending-match must hash the admitted body, not the decoration —
    otherwise a genuinely pending lock reads as absent and 425s."""
    tx = _lock_tx()
    tx_hash = compute_tx_hash(tx)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=None))
    tagged = {**tx, "state": "pending"}
    get = AsyncMock(return_value=_mempool_response([tagged]))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", get)

    found = await escrow_routes._verify_funding_lock(tx_hash, **_verify_kwargs())

    assert found["tx_hash"] == tx_hash


@pytest.mark.asyncio
async def test_pending_lock_hashes_ignore_state_tag(patched, monkeypatch):
    """#2741: pending-set membership must use sealable hashes — a decorated
    entry hashed verbatim produces a phantom that reads as 'not pending'."""
    tagged = {**_lock_tx(), "state": "pending"}
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(return_value=_mempool_response([tagged])))

    hashes = await escrow_routes._pending_lock_tx_hashes()

    assert hashes == {compute_tx_hash(_lock_tx())}


@pytest.mark.asyncio
async def test_pending_identical_lock_hash_state_tagged(patched, monkeypatch):
    """#2741: the adopted pending hash must be the sealable one, not the
    hash of the /mempool-decorated body."""
    pending = _pending_probe_tx(nonce=7, fee=999, signature="0xother")
    tagged = {**pending, "state": "pending"}
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(return_value=_mempool_response([tagged])))

    found = await escrow_routes._pending_identical_lock_hash(_lock_tx(), JOB_ID)

    assert found == compute_tx_hash(pending)
    assert found != compute_tx_hash(tagged)


@pytest.mark.asyncio
async def test_verify_mempool_lock_wrong_field_refuses(patched, monkeypatch):
    tx = _lock_tx()
    tx["payload"]["job_id"] = "other-job"  # wrong job in an otherwise well-formed lock
    tx_hash = compute_tx_hash(tx)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=None))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(return_value=_mempool_response([tx])))

    with pytest.raises(HTTPException) as exc_info:
        await escrow_routes._verify_funding_lock(tx_hash, **_verify_kwargs())
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_verify_lock_nowhere_is_retryable(patched, monkeypatch):
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=None))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(return_value=_mempool_response([])))

    with pytest.raises(HTTPException) as exc_info:
        await escrow_routes._verify_funding_lock("0x" + "ab" * 32, **_verify_kwargs())
    assert exc_info.value.status_code == 425
    assert exc_info.value.headers.get("Retry-After") == "5"


@pytest.mark.asyncio
async def test_verify_lock_probe_failure_is_retryable_not_half_state(patched, monkeypatch):
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=None))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(side_effect=ConnectionError("hub down")))

    with pytest.raises(HTTPException) as exc_info:
        await escrow_routes._verify_funding_lock("0x" + "ab" * 32, **_verify_kwargs())
    assert exc_info.value.status_code == 425


@pytest.mark.asyncio
async def test_fund_contract_stores_verified_hash(mgr):
    ok, _, cid = await mgr.create_contract(job_id=JOB_ID, client_address=BUYER, agent_address=PROVIDER, amount=AMOUNT)
    ok, msg = await mgr.fund_contract(cid, "0x" + "ab" * 32, {"tx_hash": "0x" + "ab" * 32})
    assert ok, msg
    contract = mgr.escrow_contracts[cid]
    assert contract.state is EscrowState.FUNDED
    assert contract.lock_tx_hash == "0x" + "ab" * 32


@pytest.mark.asyncio
async def test_fund_contract_rejects_mismatched_verified_lock(mgr):
    ok, _, cid = await mgr.create_contract(job_id=JOB_ID, client_address=BUYER, agent_address=PROVIDER, amount=AMOUNT)
    ok, msg = await mgr.fund_contract(cid, "0x" + "ab" * 32, {"tx_hash": "0x" + "cd" * 32})
    assert not ok
    assert mgr.escrow_contracts[cid].state is EscrowState.CREATED
    assert cid not in mgr.active_contracts


@pytest.mark.asyncio
async def test_create_marks_funded_only_on_verifiable_lock(patched, engine, monkeypatch):
    """End to end: submit returns a hash that is visible in the mempool."""
    mgr = patched
    tx = _lock_tx()
    tx_hash = compute_tx_hash(tx)
    monkeypatch.setattr(escrow_routes, "_submit_lock_tx", AsyncMock(return_value=tx_hash))
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=None))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(return_value=_mempool_response([tx])))

    body = {
        "job_id": JOB_ID,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": str(AMOUNT),
        "lock_tx": tx,
    }
    result = await escrow_routes.create_escrow(body)

    assert result["success"] is True
    assert result["lock_tx_hash"] == tx_hash
    contract = next(c for c in mgr.escrow_contracts.values() if c.job_id == JOB_ID)
    assert contract.state is EscrowState.FUNDED
    assert contract.lock_tx_hash == tx_hash


@pytest.mark.asyncio
async def test_create_drops_contract_when_lock_unverifiable(patched, engine, monkeypatch):
    """A submitted hash the node can no longer see must not leave a FUNDED
    contract or a half-created one — the retry starts clean."""
    mgr = patched
    tx = _lock_tx()
    monkeypatch.setattr(escrow_routes, "_submit_lock_tx", AsyncMock(return_value="0x" + "ef" * 32))
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=None))
    # Empty mempool: an identical-binding pending lock would now be adopted
    # by create (#2673) instead of submitted, so the unverifiable-hash path
    # needs a mempool that does not hold this lock at all.
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(return_value=_mempool_response([])))

    body = {
        "job_id": JOB_ID,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": str(AMOUNT),
        "lock_tx": tx,
    }
    with pytest.raises(HTTPException) as exc_info:
        await escrow_routes.create_escrow(body)
    assert exc_info.value.status_code == 425

    assert not any(c.job_id == JOB_ID for c in mgr.escrow_contracts.values())
    with Session(engine) as session:
        assert session.get(Escrow, JOB_ID) is None


def _resigned_lock_tx(nonce: int) -> dict:
    """The same escrow re-signed at a different nonce — identical payload, new hash."""
    tx, _ = escrow_routes._build_lock_tx(JOB_ID, BUYER, PROVIDER, AMOUNT, nonce=nonce)
    tx["signature"] = "0xdeadbeef"
    return tx


@pytest.mark.asyncio
async def test_verify_adopts_sealed_same_escrow_lock(patched, monkeypatch):
    """#2671: the submitted envelope died but an earlier identical-binding lock
    sealed — adopt the sealed hash instead of 409ing the purchase dead."""
    submitted = _lock_tx()
    sealed = _sealed(_resigned_lock_tx(nonce=1))
    assert sealed["tx_hash"] != compute_tx_hash(submitted)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=sealed))

    found = await escrow_routes._verify_funding_lock(compute_tx_hash(submitted), submitted_tx=submitted, **_verify_kwargs())

    assert found is sealed


@pytest.mark.asyncio
async def test_verify_different_payload_sealed_lock_still_refuses(patched, monkeypatch):
    """A sealed lock for the job with a *different* binding (other provider)
    is a genuinely different escrow — the 409 stands even with submitted_tx."""
    submitted = _lock_tx()
    other = _resigned_lock_tx(nonce=1)
    other["payload"]["provider"] = "0x" + "99" * 20
    sealed = _sealed(other)
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=sealed))

    with pytest.raises(HTTPException) as exc_info:
        await escrow_routes._verify_funding_lock(compute_tx_hash(submitted), submitted_tx=submitted, **_verify_kwargs())
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_verify_different_hash_without_submitted_tx_still_refuses(patched, monkeypatch):
    """No submitted tx to compare against → adoption cannot be proven → 409."""
    sealed = _sealed(_resigned_lock_tx(nonce=1))
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=sealed))

    with pytest.raises(HTTPException) as exc_info:
        await escrow_routes._verify_funding_lock("0x" + "ab" * 32, **_verify_kwargs())
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_create_adopts_sealed_lock_hash_end_to_end(patched, engine, monkeypatch):
    """#2671 end to end: submitted envelope lost, same-escrow lock sealed —
    the create funds against the sealed hash and records it everywhere."""
    mgr = patched
    submitted = _lock_tx()
    submitted_hash = compute_tx_hash(submitted)
    sealed = _sealed(_resigned_lock_tx(nonce=1))
    monkeypatch.setattr(escrow_routes, "_submit_lock_tx", AsyncMock(return_value=submitted_hash))
    monkeypatch.setattr(escrow_routes, "_find_existing_lock_tx", AsyncMock(return_value=sealed))

    body = {
        "job_id": JOB_ID,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": str(AMOUNT),
        "lock_tx": submitted,
    }
    result = await escrow_routes.create_escrow(body)

    assert result["success"] is True
    assert result["lock_tx_hash"] == sealed["tx_hash"]
    contract = next(c for c in mgr.escrow_contracts.values() if c.job_id == JOB_ID)
    assert contract.state is EscrowState.FUNDED
    assert contract.lock_tx_hash == sealed["tx_hash"]
    with Session(engine) as session:
        row = session.get(Escrow, JOB_ID)
        assert row is not None
        assert row.lock_tx_hash == sealed["tx_hash"]


# --- #2673: pending identical-binding lock adoption -------------------------


def _pending_probe_tx(nonce: int, **overrides) -> dict:
    """A mempool-held lock envelope: same binding as ``_lock_tx`` but a fresh
    nonce — exactly the dead-envelope retry shape."""
    tx = _resigned_lock_tx(nonce=nonce)
    tx.update(overrides)
    return tx


@pytest.mark.asyncio
async def test_pending_identical_lock_hash_adopts_matching_envelope(patched, monkeypatch):
    """The probe returns the pending envelope's hash only when type, chain,
    canonical from/to/amount and the full payload all match — nonce, fee and
    signature are envelope mechanics and must not matter."""
    pending = _pending_probe_tx(nonce=7, fee=999, signature="0xother")
    other_job = _pending_probe_tx(nonce=8)
    other_job["payload"]["job_id"] = "job-unrelated"
    get = AsyncMock(return_value=_mempool_response([other_job, pending]))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", get)

    found = await escrow_routes._pending_identical_lock_hash(_lock_tx(), JOB_ID)

    assert found == compute_tx_hash(pending)


@pytest.mark.asyncio
async def test_pending_identical_lock_hash_ignores_different_binding(patched, monkeypatch):
    """Different provider or amount is a different escrow — never adopted."""
    pending = _pending_probe_tx(nonce=7)
    pending["payload"]["provider"] = "0x" + "99" * 20
    get = AsyncMock(return_value=_mempool_response([pending]))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", get)

    assert await escrow_routes._pending_identical_lock_hash(_lock_tx(), JOB_ID) is None

    pending2 = _pending_probe_tx(nonce=8, amount=ait_to_units(Decimal("2.0")))
    get2 = AsyncMock(return_value=_mempool_response([pending2]))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", get2)

    assert await escrow_routes._pending_identical_lock_hash(_lock_tx(), JOB_ID) is None


@pytest.mark.asyncio
async def test_pending_identical_lock_hash_empty_and_failed_probes(patched, monkeypatch):
    """Empty mempool, non-200, truncated and transport-failed probes all mean
    'submit normally' — never an error and never a guessed hash."""
    get = AsyncMock(return_value=_mempool_response([]))
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", get)
    assert await escrow_routes._pending_identical_lock_hash(_lock_tx(), JOB_ID) is None

    bad = MagicMock()
    bad.status_code = 500
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(return_value=bad))
    assert await escrow_routes._pending_identical_lock_hash(_lock_tx(), JOB_ID) is None

    truncated = _mempool_response([_lock_tx()] * escrow_routes._FUNDING_LOCK_MEMPOOL_LIMIT)
    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(return_value=truncated))
    assert await escrow_routes._pending_identical_lock_hash(_lock_tx(), JOB_ID) is None

    monkeypatch.setattr(escrow_routes.SharedHttpClient, "get", AsyncMock(side_effect=ConnectionError("hub down")))
    assert await escrow_routes._pending_identical_lock_hash(_lock_tx(), JOB_ID) is None


@pytest.mark.asyncio
async def test_same_lock_binding_compares_canonical_fields(patched):
    """Checksum/case differences in addresses must not break the match, and
    payload dicts compare by value."""
    a = _lock_tx()
    b = _resigned_lock_tx(nonce=3)
    b["from"] = b["from"].lower()
    b["to"] = b["to"].lower()
    b["payload"] = dict(b["payload"])
    assert escrow_routes._same_lock_binding(a, b) is True
    b["payload"]["job_id"] = "job-other"
    assert escrow_routes._same_lock_binding(a, b) is False
