"""#3034 AUDIT-SETTLEMENT-LOOKUP-PROOF-1: unusable chain evidence is not authoritative.

``_sealed_settlement_hashes`` feeds both hash audits' replacement search.
Two holes let unusable evidence drive money-path writes:

- a JSON-decodable non-list body (error object, ``{"transactions": [...]}``,
  ``null``) iterated as an *empty* result — read as authoritative absence,
  so the refund audit requeued and the release audit reported unbacked on
  garbage;
- the confirmed predicate lacked the #3016 seal standard — a
  ``status="confirmed"`` row with ``block_height=None`` counted as sealed
  and could be adopted as the replacement hash.

Pins cover: non-list bodies → unverifiable (never requeue/readopt),
heightless confirmed rows → not sealed, and preserved recovery on
authoritative empty results and valid confirmed replacements.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from coordinator_api.contexts.payments.services.settlement_reconciler import SettlementReconciler


def _payment(tx_hash="0xrecorded", job_id="job-1", status="released"):
    return SimpleNamespace(
        id="pay-1",
        job_id=job_id,
        status=status,
        transaction_hash=tx_hash,
        meta_data={},
        released_at=datetime.now(UTC) - timedelta(hours=1),
        updated_at=None,
    )


def _refund_payment(tx_hash="0xdeadbeef", job_id="job-1"):
    return SimpleNamespace(
        id="pay-1",
        job_id=job_id,
        status="refunded",
        refund_transaction_hash=tx_hash,
        refunded_at=datetime.now(UTC) - timedelta(hours=1),
        meta_data={},
        updated_at=None,
    )


def _audit_factory(payments):
    @contextmanager
    def _factory():
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = payments
        yield session

    return _factory


def _refund_audit_factory(payment, escrow=None, job=None):
    @contextmanager
    def _factory():
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [payment]
        session.execute.return_value.scalars.return_value.first.return_value = escrow
        session.get.return_value = job
        yield session

    return _factory


_MISSING = object()


class _FakeResp:
    def __init__(self, status_code, payload=_MISSING):
        self.status_code = status_code
        self._payload = [] if payload is _MISSING else payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.calls.append((url, params))
        for needle, outcome in self.routes.items():
            if needle in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        return _FakeResp(404)


def _patch_rpc_and_client(routes):
    client = _FakeClient(routes)
    settings = SimpleNamespace(blockchain_rpc_url="http://rpc.test")
    return (
        patch("coordinator_api.contexts.payments.services.payments.settings", settings),
        patch("coordinator_api.contexts.payments.services.settlement_reconciler.httpx.AsyncClient", return_value=client),
        client,
    )


# --- unit: the shared helper's evidence standard ----------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"error": "upstream exploded"},
        {"transactions": [{"transaction_hash": "0x1", "status": "confirmed", "block_height": 5}]},
        None,
        "ok",
        42,
    ],
)
async def test_sealed_hashes_non_list_body_is_unverifiable(body):
    """A decodable non-list body must read as None (unverifiable), never as
    an empty authoritative result — otherwise callers requeue/readopt on
    unusable evidence."""
    client = _FakeClient({"/rpc/transactions": _FakeResp(200, body)})
    result = await SettlementReconciler._sealed_settlement_hashes(client, "http://rpc", "job-1", "ESCROW_REFUND")
    assert result is None


@pytest.mark.asyncio
async def test_sealed_hashes_requires_confirmed_plus_block_height():
    """#3016 seal standard: status=confirmed without block_height never
    sealed; only confirmed+height rows establish settlement."""
    client = _FakeClient(
        {
            "/rpc/transactions": _FakeResp(
                200,
                [
                    {"transaction_hash": "0xnoheight", "status": "confirmed", "block_height": None},
                    {"transaction_hash": "0xheightless-key", "status": "confirmed"},
                    {"transaction_hash": "0xpending", "status": "pending", "block_height": 9},
                    {"transaction_hash": "0xsealed", "status": "confirmed", "block_height": 9},
                    {"transaction_hash": "0xrejected", "status": "rejected", "block_height": 9},
                ],
            )
        }
    )
    result = await SettlementReconciler._sealed_settlement_hashes(client, "http://rpc", "job-1", "ESCROW_REFUND")
    assert result == {"0xsealed"}


# --- end-to-end: refund audit -------------------------------------------------


@pytest.mark.asyncio
async def test_refund_audit_unusable_lookup_body_never_requeues():
    """Dead recorded hash + a JSON object where the row list belongs →
    unverifiable: the payment stays refunded, hash intact, no requeue."""
    payment = _refund_payment(tx_hash="0xdead")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xdead": _FakeResp(404),
            "/rpc/transactions": _FakeResp(200, {"error": "shape changed"}),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_unreachable"] == 1
    assert counts["refund_requeued"] == 0
    assert counts["refund_hash_readopted"] == 0
    assert payment.status == "refunded"
    assert payment.refund_transaction_hash == "0xdead"


@pytest.mark.asyncio
async def test_refund_audit_heightless_confirmed_cannot_readopt():
    """A 'confirmed' replacement row without block_height is not sealed
    evidence — it cannot be adopted; with no valid sealed refund the dead
    recorded hash still requeues (authoritative empty-of-sealed)."""
    payment = _refund_payment(tx_hash="0xdead")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xdead": _FakeResp(404),
            "/rpc/transactions": _FakeResp(
                200,
                [{"transaction_hash": "0xnoheight", "status": "confirmed", "block_height": None}],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_readopted"] == 0
    assert counts["refund_requeued"] == 1
    assert payment.status == "settlement_failed"
    assert payment.refund_transaction_hash is None


@pytest.mark.asyncio
async def test_refund_audit_authoritative_empty_still_requeues():
    """Preserve #3007 recovery: a real empty list is authoritative absence —
    the dead refund still requeues."""
    payment = _refund_payment(tx_hash="0xdead")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xdead": _FakeResp(404),
            "/rpc/transactions": _FakeResp(200, []),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_requeued"] == 1
    assert payment.status == "settlement_failed"


@pytest.mark.asyncio
async def test_refund_audit_valid_confirmed_replacement_still_readopts():
    """Preserve recovery: a confirmed+height ESCROW_REFUND is adopted."""
    payment = _refund_payment(tx_hash="0xdead")
    reconciler = SettlementReconciler(session_factory=_refund_audit_factory(payment))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xdead": _FakeResp(404),
            "/rpc/transactions": _FakeResp(
                200,
                [{"transaction_hash": "0xalive", "status": "confirmed", "block_height": 11}],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_readopted"] == 1
    assert payment.refund_transaction_hash == "0xalive"
    assert payment.status == "refunded"


# --- end-to-end: release audit -----------------------------------------------


@pytest.mark.asyncio
async def test_release_audit_unusable_lookup_body_never_readopts_or_unbacks():
    """Same guard on the release sibling: an object body is unverifiable —
    no adoption, no unbacked-critical, hash untouched."""
    payment = _payment(tx_hash="0xdead")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xdead": _FakeResp(404),
            "/rpc/transactions": _FakeResp(200, {"transactions": "not-a-list"}),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_unreachable"] == 1
    assert counts["hash_readopted"] == 0
    assert counts["hash_unbacked"] == 0
    assert payment.transaction_hash == "0xdead"


@pytest.mark.asyncio
async def test_release_audit_heightless_confirmed_cannot_be_adopted():
    """Heightless 'confirmed' replacement → not sealed → authoritative
    empty-of-sealed → unbacked-critical, never a guessed adoption."""
    payment = _payment(tx_hash="0xdead")
    reconciler = SettlementReconciler(session_factory=_audit_factory([payment]))
    p1, p2, _ = _patch_rpc_and_client(
        {
            "/rpc/transaction/0xdead": _FakeResp(404),
            "/rpc/transactions": _FakeResp(
                200,
                [{"transaction_hash": "0xnoheight", "status": "confirmed", "block_height": None}],
            ),
        }
    )
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_readopted"] == 0
    assert counts["hash_unbacked"] == 1
    assert payment.transaction_hash == "0xdead"
