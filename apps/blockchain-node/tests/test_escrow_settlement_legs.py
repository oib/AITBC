"""Settlement legs are read back from the chain, not guessed from the last txn.

Only the node that serves a release writes ``released_amount``/``refunded_amount``.
Every other node rebuilds the escrow row from the transactions it synced, and the
rebuild used to keep just the most recent ESCROW_RELEASE/ESCROW_REFUND. That is
enough for a full release, which settles one txn, and wrong for a metered one,
which settles two: the provider's payment and the buyer's unbilled change. The
later of the two decided the row's status, so the same escrow read back as
"released" or "refunded" depending on which order the two were mined in, and the
amounts fell back to reporting the whole lock as the settled leg.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Escrow, Transaction
from aitbc_chain.contracts.escrow import backfill_settlement_legs, settlement_legs_from_chain
from aitbc_chain.metadata import chain_metadata

CHAIN = "test-chain"
JOB = "sw_job_metered"
BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"

LOCKED = 3_600_000  # 0.1 AIT
PAID = 834_678  # what the provider billed, net of the 2.5% platform fee
CHANGE = 2_743_920  # what went back to the buyer unbilled

T0 = datetime(2026, 9, 2, 21, 16, 5, tzinfo=UTC)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    chain_metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


def _tx(session, tx_type: str, action: str, value: int, tx_hash: str, at: datetime) -> None:
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            sender=BUYER,
            recipient=PROVIDER,
            type=tx_type,
            value=value,
            created_at=at,
            payload={"action": action, "job_id": JOB},
        )
    )
    session.commit()


def _lock(session) -> None:
    _tx(session, "ESCROW_LOCK", "escrow_lock", LOCKED, "0xlock", T0)


def _release(session, at: datetime | None = None) -> None:
    _tx(session, "ESCROW_RELEASE", "escrow_release", PAID, "0xrelease", at or T0 + timedelta(seconds=2))


def _refund(session, at: datetime | None = None) -> None:
    _tx(session, "ESCROW_REFUND", "escrow_refund", CHANGE, "0xrefund", at or T0 + timedelta(seconds=1))


def _replica_row(session, **overrides) -> Escrow:
    """An escrow row as a non-settling node rebuilds it: settled, but no amounts."""
    fields = {
        "job_id": JOB,
        "chain_id": CHAIN,
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": LOCKED,
        "status": "released",
        "created_at": T0,
        "released_at": T0 + timedelta(seconds=2),
        "lock_tx_hash": "0xlock",
    }
    fields.update(overrides)
    record = Escrow(**fields)
    session.add(record)
    session.commit()
    return record


class TestSettlementLegsFromChain:
    def test_locked_escrow_has_no_legs(self, session):
        _lock(session)
        assert settlement_legs_from_chain(session, JOB) is None

    def test_metered_release_reports_both_legs(self, session):
        _lock(session)
        _refund(session)
        _release(session)

        legs = settlement_legs_from_chain(session, JOB)

        assert legs["status"] == "released"
        assert legs["released_amount"] == PAID
        assert legs["refunded_amount"] == CHANGE
        assert legs["release_tx_hash"] == "0xrelease"
        assert legs["refund_tx_hash"] == "0xrefund"

    def test_change_mined_last_is_still_a_release(self, session):
        """The regression: mining order must not decide the escrow's outcome."""
        _lock(session)
        _release(session, at=T0 + timedelta(seconds=1))
        _refund(session, at=T0 + timedelta(seconds=2))

        legs = settlement_legs_from_chain(session, JOB)

        assert legs["status"] == "released"
        assert legs["released_amount"] == PAID
        assert legs["refunded_amount"] == CHANGE
        # A release's change is not a refund: refunded_at marks an escrow refunded
        # *instead of* released, which is what the duplicate-release guard tests.
        assert legs["refunded_at"] is None

    def test_full_release_has_no_change_leg(self, session):
        _lock(session)
        _release(session)

        legs = settlement_legs_from_chain(session, JOB)

        assert legs["status"] == "released"
        assert legs["released_amount"] == PAID
        assert legs["refunded_amount"] == 0
        assert legs["refund_tx_hash"] is None

    def test_refund_only_escrow_is_refunded(self, session):
        _lock(session)
        _refund(session)

        legs = settlement_legs_from_chain(session, JOB)

        assert legs["status"] == "refunded"
        assert legs["refunded_amount"] == CHANGE
        assert legs["released_amount"] == 0
        assert legs["released_at"] is None
        assert legs["refunded_at"] is not None

    def test_other_jobs_settlements_are_not_counted(self, session):
        _lock(session)
        _release(session)
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash="0xother",
                sender=BUYER,
                recipient=PROVIDER,
                type="ESCROW_RELEASE",
                value=999,
                created_at=T0,
                payload={"action": "escrow_release", "job_id": "sw_job_someone_else"},
            )
        )
        session.commit()

        assert settlement_legs_from_chain(session, JOB)["released_amount"] == PAID


class TestBackfillSettlementLegs:
    def test_replica_row_learns_what_the_settlement_moved(self, session):
        _lock(session)
        _refund(session)
        _release(session)
        record = _replica_row(session)

        assert backfill_settlement_legs(session, record) is True
        assert record.released_amount == PAID
        assert record.refunded_amount == CHANGE
        assert record.release_tx_hash == "0xrelease"
        assert record.refund_tx_hash == "0xrefund"

    def test_backfill_is_idempotent(self, session):
        _lock(session)
        _release(session)
        record = _replica_row(session)

        assert backfill_settlement_legs(session, record) is True
        assert backfill_settlement_legs(session, record) is False

    def test_row_that_already_knows_its_amounts_is_left_alone(self, session):
        _lock(session)
        _release(session)
        record = _replica_row(session, released_amount=PAID, refunded_amount=CHANGE)

        assert backfill_settlement_legs(session, record) is False
        assert record.released_amount == PAID

    def test_locked_row_is_left_alone(self, session):
        _lock(session)
        record = _replica_row(session, status="locked", released_at=None)

        assert backfill_settlement_legs(session, record) is False
        assert record.released_amount is None

    def test_release_misrecorded_as_refund_is_repaired(self, session):
        """A row rebuilt from the change leg alone would 409 every later release."""
        _lock(session)
        _release(session)
        _refund(session, at=T0 + timedelta(seconds=3))
        record = _replica_row(
            session,
            status="refunded",
            released_at=None,
            refunded_at=T0 + timedelta(seconds=3),
        )

        assert backfill_settlement_legs(session, record) is True
        assert record.status == "released"
        assert record.released_at is not None
        assert record.refunded_at is None
        assert record.released_amount == PAID
        assert record.refunded_amount == CHANGE

    def test_settlement_missing_from_this_nodes_chain_is_not_invented(self, session):
        _lock(session)
        record = _replica_row(session)

        assert backfill_settlement_legs(session, record) is False
        assert record.released_amount is None
