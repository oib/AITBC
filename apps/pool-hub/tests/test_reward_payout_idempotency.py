"""Reward distribution pays each miner at most once per epoch (APP-29).

RewardPayout has existed since v0.6.7 with the docstring "prevent duplicate payouts", but
no migration created its table and nothing ever wrote to it. Duplicate protection lived in
RewardPolicy's in-process dicts, which are lost on restart and not shared between
replicas -- so the same miner could be paid twice for the same epoch.

Two levels of coverage here:

  - decision-logic tests, which run everywhere. They drive distribute_rewards with a
    session whose flush raises IntegrityError on a repeated (miner, chain, epoch), and
    assert no transaction is submitted for an already-claimed payout. This is the logic
    that decides whether money moves.
  - a constraint test gated on POOLHUB_TEST_POSTGRES_DSN, which proves the database
    actually rejects the duplicate. Without it the logic above is only as good as its mock.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from poolhub.clients.blockchain import PoolHubBlockchainClient
from poolhub.models import RewardPayout
from sqlalchemy.exc import IntegrityError


# Deterministic secp256k1 pair; the client verifies the address matches the key.
SIGNER_ADDRESS = "0x1a642f0E3c3aF545E7AcBD38b07251B3990914F1"
SIGNER_KEY = "0101010101010101010101010101010101010101010101010101010101010101"


@pytest.fixture
def client():
    return PoolHubBlockchainClient(signer_address=SIGNER_ADDRESS, signer_private_key=SIGNER_KEY)


class TestPayoutClaiming:
    @pytest.mark.asyncio
    async def test_first_claim_succeeds(self, client, payout_session):
        session = payout_session

        claim = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=7, amount=500)

        assert claim is not None
        assert claim.status == "pending"
        assert claim.epoch_number == 7

    @pytest.mark.asyncio
    async def test_second_claim_for_same_epoch_is_refused(self, client, payout_session):
        session = payout_session

        first = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=7, amount=500)
        second = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=7, amount=500)

        assert first is not None
        assert second is None, "a second claim for the same miner+epoch must be refused"
        assert session.rollbacks == 1

    @pytest.mark.asyncio
    async def test_same_miner_different_epoch_is_allowed(self, client, payout_session):
        session = payout_session

        first = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=7, amount=500)
        later = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=8, amount=500)

        assert first is not None
        assert later is not None

    @pytest.mark.asyncio
    async def test_different_miners_same_epoch_are_allowed(self, client, payout_session):
        session = payout_session

        one = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=7, amount=500)
        two = await client._claim_payout(session=session, miner_id="miner-2", epoch_number=7, amount=500)

        assert one is not None
        assert two is not None


class TestDistributionIsIdempotent:
    """The property that matters: a repeated run must not submit a second transaction."""

    @pytest.mark.asyncio
    async def test_rerun_does_not_submit_again(self, client, payout_session):
        client.record_contribution("miner-1", score=90.0, shares=5000)
        session = payout_session

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(
                client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx-1"}
            ) as submit,
        ):
            first = await client.distribute_rewards(block_height=100, session=session)

            # Simulate the state a restart produces: in-process bookkeeping wiped, the
            # database row still there. This is the exact scenario that paid twice.
            client._reward_policy._epochs.clear()
            client._reward_policy._last_reward_epoch.clear()
            client.record_contribution("miner-1", score=90.0, shares=5000)

            second = await client.distribute_rewards(block_height=100, session=session)

        assert [p["status"] for p in first] == ["paid"]
        assert [p["status"] for p in second] == ["already_paid"]
        assert submit.await_count == 1, "the reward transaction was submitted more than once"

    @pytest.mark.asyncio
    async def test_a_second_replica_does_not_pay_again(self, client, payout_session):
        """Two clients, separate in-process state, one shared database."""
        other = PoolHubBlockchainClient(signer_address=SIGNER_ADDRESS, signer_private_key=SIGNER_KEY)
        session = payout_session

        client.record_contribution("miner-1", score=90.0, shares=5000)
        other.record_contribution("miner-1", score=90.0, shares=5000)

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx-1"}),
            patch.object(other._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(other._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx-2"}) as second_submit,
        ):
            await client.distribute_rewards(block_height=100, session=session)
            replica = await other.distribute_rewards(block_height=100, session=session)

        assert [p["status"] for p in replica] == ["already_paid"]
        assert second_submit.await_count == 0, "the second replica paid the same miner again"

    @pytest.mark.asyncio
    async def test_claim_is_kept_when_submission_fails(self, client, payout_session):
        """A failed submission must not release the claim.

        The chain may or may not have accepted it; retrying blindly is how double payments
        happen. The row stays as 'failed' for reconciliation.
        """
        client.record_contribution("miner-1", score=90.0, shares=5000)
        session = payout_session

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, side_effect=Exception("Network error")),
        ):
            payouts = await client.distribute_rewards(block_height=100, session=session)

        assert payouts[0]["status"] == "failed"
        assert "Network error" in payouts[0]["error"]
        assert ("miner-1", client._chain_id, payouts[0]["epoch"]) in session.claimed

    @pytest.mark.asyncio
    async def test_successful_payout_records_tx_hash(self, client, payout_session):
        client.record_contribution("miner-1", score=90.0, shares=5000)
        session = payout_session

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx-abc"}),
        ):
            await client.distribute_rewards(block_height=100, session=session)

        row = session.added[-1]
        assert row.status == "paid"
        assert row.tx_hash == "tx-abc"
        assert row.paid_at is not None


@pytest.mark.skipif(
    not os.getenv("POOLHUB_TEST_POSTGRES_DSN"),
    reason="Set POOLHUB_TEST_POSTGRES_DSN to verify the real unique constraint",
)
class TestDatabaseConstraint:
    """Proves Postgres itself rejects the duplicate, not just our mock."""

    @pytest_asyncio.fixture
    async def seeded(self, db_session):
        db_session.add(
            RewardPayout(miner_id="miner-1", chain_id="ait-hub", epoch_number=7, amount=500, status="paid")
        )
        await db_session.commit()
        return db_session

    @pytest.mark.asyncio
    async def test_duplicate_insert_is_rejected(self, seeded):
        seeded.add(
            RewardPayout(miner_id="miner-1", chain_id="ait-hub", epoch_number=7, amount=500, status="pending")
        )
        with pytest.raises(IntegrityError):
            await seeded.flush()

    @pytest.mark.asyncio
    async def test_claim_returns_none_against_a_real_constraint(self, seeded, client):
        claim = await client._claim_payout(session=seeded, miner_id="miner-1", epoch_number=7, amount=500)

        assert claim is None

    @pytest.mark.asyncio
    async def test_has_been_paid_reflects_the_row(self, seeded, client):
        assert await client.has_been_paid(seeded, "miner-1", 7) is True
        assert await client.has_been_paid(seeded, "miner-1", 8) is False
