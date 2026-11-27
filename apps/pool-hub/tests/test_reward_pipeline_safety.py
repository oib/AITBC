"""Hermetic pins for the #3058 reward-pipeline enablement defects.

AUDIT-POOLHUB-REWARD-PIPELINE-1 fixed, one pin each:

1. Nonce collision — nonces increment across batch payouts and the mempool
   floor lifts the probe above pending txs.
2. Reconciliation — pending/failed rows resolve against the chain: sealed
   -> paid, mempool -> still pending, absent -> bounded resubmit ('retry').
3. Single distributor — DB advisory lock on postgres, in-process lock
   elsewhere; enablement gate refuses unsafe configuration.
4. Persistent shares — reward_shares table replaces the memory ledger.
5. Epoch finality — the in-progress epoch is never paid.
6. Verified shares only — self-reported/in-memory contributions feed nothing.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from poolhub.clients.blockchain import PoolHubBlockchainClient
from poolhub.models import RewardPayout, RewardShare
from poolhub.services.reward_gate import reward_enablement_blockers
from poolhub.services.reward_shares import record_verified_share
from poolhub.settings import Settings

SIGNER_ADDRESS = "0x1a642f0E3c3aF545E7AcBD38b07251B3990914F1"
SIGNER_KEY = "0101010101010101010101010101010101010101010101010101010101010101"
EVIDENCE = "0x" + "ef" * 32
PAYOUT_HEIGHT = 1500  # epoch 1 current, epoch 0 finalized


@pytest.fixture
def client():
    return PoolHubBlockchainClient(signer_address=SIGNER_ADDRESS, signer_private_key=SIGNER_KEY)


async def _share(session, miner_id: str, shares: int = 5000, epoch: int = 0, verified: bool = True) -> None:
    row = RewardShare(
        miner_id=miner_id,
        chain_id="ait-hub",
        epoch_number=epoch,
        shares=shares,
        jobs_completed=1,
        source="verified_chain",
        evidence_tx_hash=EVIDENCE,
        verified=verified,
    )
    session.shares.append(row)


def _mempool(txs: list[dict] | None = None):
    return {"success": True, "transactions": txs or [], "count": len(txs or [])}


def _sealed_reward_tx(
    miner_id: str,
    amount: int,
    wallet: str,
    tx_hash: str = "0x" + "5e" * 32,
    *,
    sender: str = SIGNER_ADDRESS,
    status: str = "confirmed",
    block_height: int | None = 1400,
    epoch: int = 0,
) -> dict:
    """REAL sealed-row shape from /rpc/transactions and
    /rpc/transaction/{hash} — aitbc_chain.rpc.transactions._tx_result_row:
    sender/recipient/payload/type/status/value/fee/nonce/block_height.
    There is NO ``amount``/``to``/``from`` on sealed rows; the respin
    blocker was matching on fields that do not exist there."""
    return {
        "transaction_id": "tx-1",
        "tx_hash": tx_hash,
        "block_height": block_height,
        "block_hash": "0x" + "aa" * 32,
        "sender": sender,
        "recipient": wallet,
        "payload": {"job_id": f"epoch-{epoch}-{miner_id}", "purpose": "mining_reward"},
        "type": "TRANSFER",
        "status": status,
        "nonce": 0,
        "value": amount,
        "fee": 36,
        "timestamp": "2026-01-01T00:00:00",
    }


def _mempool_reward_tx(miner_id: str, amount: int, wallet: str, *, nonce: int = 0, epoch: int = 0) -> dict:
    """REAL mempool-entry shape — the normalized admitted body
    (aitbc_chain.rpc.utils.normalize_transaction_data): from/to/amount AND
    value, no status/block_height."""
    return {
        "from": SIGNER_ADDRESS,
        "to": wallet,
        "amount": amount,
        "value": amount,
        "fee": 36,
        "nonce": nonce,
        "payload": {"job_id": f"epoch-{epoch}-{miner_id}", "purpose": "mining_reward"},
        "type": "TRANSFER",
        "chain_id": "ait-hub",
        "signature": "0xsig",
    }


def _payout_row(miner_id: str = "miner-1", epoch: int = 0, amount: int = 5000, **kw) -> RewardPayout:
    defaults = {
        "miner_id": miner_id,
        "chain_id": "ait-hub",
        "epoch_number": epoch,
        "amount": amount,
        "status": "failed",
        "created_at": datetime.now(UTC) - timedelta(hours=1),
        "reconcile_attempts": 0,
    }
    defaults.update(kw)
    return RewardPayout(**defaults)


# ---------------------------------------------------------------- nonce floor


class TestNonceAllocation:
    @pytest.mark.asyncio
    async def test_nonces_increment_across_batch_payouts(self, client, payout_session):
        """#3058-1: blocks don't seal between loop iterations — every payout
        after the first must NOT reuse the sealed nonce."""
        session = payout_session
        await _share(session, "miner-1")
        await _share(session, "miner-2")

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}) as submit,
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
        ):
            payouts = await client.distribute_rewards(block_height=PAYOUT_HEIGHT, session=session)

        assert sorted(p["status"] for p in payouts) == ["paid", "paid"]
        nonces = sorted(call.args[0]["nonce"] for call in submit.await_args_list)
        assert nonces == [0, 1], f"batch payouts must take sequential nonces, got {nonces}"

    @pytest.mark.asyncio
    async def test_nonce_gap_fill_skips_stranded_entry(self, client, payout_session):
        """#3058 respin: lowest-free-nonce semantics (cli nonce.py #2745).

        A stranded mempool entry at nonce 1 must NOT push later payouts
        into future-nonce territory: apply seals sequentially, so the hole
        at nonce 0 is the only slot guaranteed to land. Two payouts take
        nonces 0 and 2 — gap-filled around the occupant, not max+1=2,3.
        """
        session = payout_session
        await _share(session, "miner-1")
        await _share(session, "miner-2")
        pending = {"from": SIGNER_ADDRESS.lower(), "nonce": 1, "payload": {"job_id": "other"}}

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}) as submit,
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool([pending]),
            ),
        ):
            await client.distribute_rewards(block_height=PAYOUT_HEIGHT, session=session)

        nonces = sorted(call.args[0]["nonce"] for call in submit.await_args_list)
        assert nonces == [0, 2], f"gap-fill must skip the stranded nonce 1, got {nonces}"

    @pytest.mark.asyncio
    async def test_nonce_at_sealed_is_skipped(self, client, payout_session):
        """An occupant AT the sealed nonce lifts the first payout to 1."""
        session = payout_session
        await _share(session, "miner-1")
        pending = {"from": SIGNER_ADDRESS, "nonce": 0, "payload": {"job_id": "other"}}

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}) as submit,
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool([pending]),
            ),
        ):
            await client.distribute_rewards(block_height=PAYOUT_HEIGHT, session=session)

        assert submit.await_args.args[0]["nonce"] == 1

    @pytest.mark.asyncio
    async def test_mempool_probe_failure_degrades_to_sealed(self, client):
        """A probe miss must not fabricate a nonce — degrade to sealed."""
        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=7),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                side_effect=OSError("unreachable"),
            ),
        ):
            nonce = await client._probe_reward_nonce()
        assert nonce == 7


# ------------------------------------------------------------ finality gate


class TestEpochFinality:
    @pytest.mark.asyncio
    async def test_in_progress_epoch_is_never_paid(self, client, payout_session):
        """#3058-5: shares recorded for the CURRENT epoch must not pay — the
        epoch has not ended, contributions can still arrive."""
        session = payout_session
        await _share(session, "miner-1", epoch=1)  # epoch 1 is in progress at height 1500

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            payouts = await client.distribute_rewards(block_height=PAYOUT_HEIGHT, session=session)

        assert payouts == []
        assert submit.await_count == 0
        assert session.claimed == set()

    @pytest.mark.asyncio
    async def test_epoch_inside_finality_window_is_not_paid(self, client, payout_session):
        """Epoch 0 ends at block 999; finality=3 requires height >= 1003."""
        session = payout_session
        await _share(session, "miner-1", epoch=0)

        with (
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}) as submit,
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
        ):
            too_early = await client.distribute_rewards(block_height=1002, session=session)
            ok = await client.distribute_rewards(block_height=1003, session=session)

        assert too_early == []
        assert [p["status"] for p in ok] == ["paid"]
        assert submit.await_count == 1


# --------------------------------------------------------- verified shares


class TestVerifiedSharesOnly:
    @pytest.mark.asyncio
    async def test_unverified_share_rows_are_ignored(self, client, payout_session):
        """#3058-6: only verified=True rows reach the payout math."""
        session = payout_session
        await _share(session, "miner-1", verified=False)

        with patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit:
            payouts = await client.distribute_rewards(block_height=PAYOUT_HEIGHT, session=session)

        assert payouts == []
        assert submit.await_count == 0

    @pytest.mark.asyncio
    async def test_in_memory_record_contribution_feeds_nothing(self, client, payout_session):
        """The old caller-asserted path cannot move money anymore."""
        session = payout_session
        client.record_contribution("miner-1", score=99.0, shares=999_999)

        with patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit:
            payouts = await client.distribute_rewards(block_height=PAYOUT_HEIGHT, session=session)

        assert payouts == []
        assert submit.await_count == 0

    @pytest.mark.asyncio
    async def test_record_verified_share_requires_evidence(self, payout_session):
        with pytest.raises(ValueError, match="evidence_tx_hash"):
            await record_verified_share(
                payout_session,
                miner_id="m",
                chain_id="ait-hub",
                epoch_number=0,
                shares=10,
                evidence_tx_hash="  ",
            )

    @pytest.mark.asyncio
    async def test_record_verified_share_accumulates(self, payout_session):
        session = payout_session
        await record_verified_share(
            session,
            miner_id="m",
            chain_id="ait-hub",
            epoch_number=0,
            shares=10,
            evidence_tx_hash="0x" + "ab" * 32,
        )
        row = await record_verified_share(
            session, miner_id="m", chain_id="ait-hub", epoch_number=0, shares=5, evidence_tx_hash="0x" + "cd" * 32
        )
        assert row.shares == 15
        assert len(session.shares) == 1


# ------------------------------------------------------------ reconciliation


class TestReconciliation:
    @pytest.mark.asyncio
    async def test_sealed_tx_marks_row_paid(self, client, payout_session):
        """A lost submit response resolves to paid when the chain proves it."""
        session = payout_session
        row = _payout_row(status="failed")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(
                client._rpc,
                "query_transactions",
                new_callable=AsyncMock,
                return_value=[_sealed_reward_tx("miner-1", 5000, session.default_wallet, "0xfound")],
            ),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["paid"] == 1
        assert row.status == "paid"
        assert row.tx_hash == "0xfound"
        assert submit.await_count == 0

    @pytest.mark.asyncio
    async def test_mempool_tx_leaves_row_pending(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="pending")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))
        mempool_tx = _mempool_reward_tx("miner-1", 5000, session.default_wallet)

        with (
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, return_value=[]),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool([mempool_tx]),
            ),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["still_pending"] == 1
        assert row.status == "pending"
        assert submit.await_count == 0

    @pytest.mark.asyncio
    async def test_absent_tx_is_resubmitted_with_attempt_counted(self, client, payout_session):
        """Proven-absent payout -> 'retry' path resubmits once, bounded."""
        session = payout_session
        row = _payout_row(status="failed", reconcile_attempts=0)
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, return_value=[]),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=3),
            patch.object(
                client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx-retry"}
            ) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["paid"] == 1
        assert row.status == "paid"
        assert row.reconcile_attempts == 1
        assert submit.await_count == 1
        assert submit.await_args.args[0]["nonce"] == 3

    @pytest.mark.asyncio
    async def test_resubmit_failure_keeps_retry_state(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="failed")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, return_value=[]),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, side_effect=OSError("down")),
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["retry"] == 1
        assert row.status == "failed"
        assert row.reconcile_attempts == 1

    @pytest.mark.asyncio
    async def test_attempt_cap_parks_row_for_operator(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="failed", reconcile_attempts=3)
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, return_value=[]),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["exhausted"] == 1
        assert row.status == "exhausted"
        assert submit.await_count == 0

    @pytest.mark.asyncio
    async def test_fresh_rows_are_not_raced(self, client, payout_session):
        """Rows younger than min_age may be mid-submit — leave them alone."""
        session = payout_session
        row = _payout_row(status="pending", created_at=datetime.now(UTC))
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with patch.object(client._rpc, "query_transactions", new_callable=AsyncMock) as qt:
            summary = await client.reconcile_payouts(session)

        assert summary["checked"] == 0
        qt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retry_row_is_reclaimable_by_claim(self, client, payout_session):
        """A proven-absent 'retry' row frees the (miner, chain, epoch) slot
        for a fresh claim instead of wedging it forever."""
        session = payout_session
        row = _payout_row(status="retry")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        claim = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=0, amount=5000)

        assert claim is row
        assert claim.status == "pending"


# ------------------------------------------------------------- enablement gate


class TestEnablementGate:
    def test_flag_off_is_a_blocker(self):
        blockers = reward_enablement_blockers(Settings())
        assert any("ENABLE_REWARD_DISTRIBUTION" in b for b in blockers)

    def test_missing_signer_env_blocks(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("POOL_REWARD_ADDRESS", raising=False)
        monkeypatch.delenv("POOL_REWARD_PRIVATE_KEY", raising=False)
        settings = Settings(enable_reward_distribution=True)
        blockers = reward_enablement_blockers(settings)
        assert any("POOL_REWARD_ADDRESS" in b for b in blockers)
        assert any("POOL_REWARD_PRIVATE_KEY" in b for b in blockers)

    def test_configured_single_node_passes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POOL_REWARD_ADDRESS", SIGNER_ADDRESS)
        monkeypatch.setenv("POOL_REWARD_PRIVATE_KEY", SIGNER_KEY)
        settings = Settings(enable_reward_distribution=True)
        assert reward_enablement_blockers(settings) == []

    def test_hostname_pin_refuses_other_nodes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POOL_REWARD_ADDRESS", SIGNER_ADDRESS)
        monkeypatch.setenv("POOL_REWARD_PRIVATE_KEY", SIGNER_KEY)
        settings = Settings(enable_reward_distribution=True, reward_distribution_node="definitely-not-this-host")
        blockers = reward_enablement_blockers(settings)
        assert any("not the pinned reward distributor" in b for b in blockers)

    def test_hostname_pin_accepts_pinned_node(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("POOL_REWARD_ADDRESS", SIGNER_ADDRESS)
        monkeypatch.setenv("POOL_REWARD_PRIVATE_KEY", SIGNER_KEY)
        settings = Settings(enable_reward_distribution=True, reward_distribution_node=socket.gethostname())
        assert reward_enablement_blockers(settings) == []

    @pytest.mark.parametrize(
        "field",
        [
            "reward_poll_interval_seconds",
            "reward_reconcile_min_age_seconds",
            "reward_max_reconcile_attempts",
            "reward_max_submissions_per_cycle",
            "reward_finality_blocks",
        ],
    )
    def test_nonpositive_numeric_knobs_block(self, monkeypatch: pytest.MonkeyPatch, field: str):
        """Respin: every numeric knob driving the money loop must be sane —
        a zero/negative value is never a valid operating point."""
        monkeypatch.setenv("POOL_REWARD_ADDRESS", SIGNER_ADDRESS)
        monkeypatch.setenv("POOL_REWARD_PRIVATE_KEY", SIGNER_KEY)
        bad_value = -1 if field == "reward_reconcile_min_age_seconds" else 0
        settings = Settings(enable_reward_distribution=True, **{field: bad_value})
        blockers = reward_enablement_blockers(settings)
        assert blockers, f"{field}={bad_value} must produce a blocker"

    def test_unpinned_enablement_warns_but_relies_on_advisory_lock(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        """No replica-count hint exists, so unpinned enablement cannot fail
        closed — it must at least warn that per-node databases double-pay."""
        monkeypatch.setenv("POOL_REWARD_ADDRESS", SIGNER_ADDRESS)
        monkeypatch.setenv("POOL_REWARD_PRIVATE_KEY", SIGNER_KEY)
        settings = Settings(enable_reward_distribution=True)
        import logging

        with caplog.at_level(logging.WARNING):
            blockers = reward_enablement_blockers(settings)
        assert blockers == []
        assert any("WITHOUT POOLHUB_REWARD_DISTRIBUTION_NODE" in r.message for r in caplog.records)


# --------------------------------------------------------- distributor lock


class TestDistributorLock:
    @pytest.mark.asyncio
    async def test_non_postgres_lock_excludes_second_holder(self):
        from poolhub.services.distributor_lock import RewardDistributorLock

        fake_engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
        lock = RewardDistributorLock(fake_engine)  # type: ignore[arg-type]
        assert await lock.acquire() is True
        other = RewardDistributorLock(fake_engine)  # type: ignore[arg-type]
        assert await other.acquire() is False
        await lock.release()
        assert await other.acquire() is True
        await other.release()


# ============================================================ respin pins
# Independent-review NO-SHIP fixes: real sealed-row shape, conservative
# unknown handling, retry-cap reclaim guard, nonce gap-fill, lookahead cap.


class TestSealedMatcherRealShape:
    """BLOCKER 1: sealed rows expose value/sender/recipient/status/
    block_height — never amount/to/from. Fixtures use the REAL
    _tx_result_row shape so the matcher cannot regress to fabricated
    fields again."""

    @pytest.mark.asyncio
    async def test_confirmed_sealed_row_marks_paid(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="failed")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        sealed_hash = "0x" + "5e" * 32
        with (
            patch.object(
                client._rpc,
                "query_transactions",
                new_callable=AsyncMock,
                return_value=[_sealed_reward_tx("miner-1", 5000, session.default_wallet, tx_hash=sealed_hash)],
            ),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["paid"] == 1
        assert row.status == "paid"
        assert row.tx_hash == sealed_hash
        # A matcher regression must NOT be masked by the resubmit path:
        # paid-via-match never submits.
        submit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unconfirmed_sealed_row_does_not_match(self, client, payout_session):
        """status != 'confirmed' is a dead letter, not a payment."""
        session = payout_session
        row = _payout_row(status="failed")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(
                client._rpc,
                "query_transactions",
                new_callable=AsyncMock,
                return_value=[_sealed_reward_tx("miner-1", 5000, session.default_wallet, status="rejected")],
            ),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}),
        ):
            summary = await client.reconcile_payouts(session)

        # rejected row -> not paid via match; proven absent -> resubmit path
        assert summary["paid"] == 1  # via resubmit, not via the rejected row
        assert row.tx_hash == "tx"

    @pytest.mark.asyncio
    async def test_missing_block_height_does_not_match(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="failed")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(
                client._rpc,
                "query_transactions",
                new_callable=AsyncMock,
                return_value=[_sealed_reward_tx("miner-1", 5000, session.default_wallet, block_height=None)],
            ),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}),
        ):
            await client.reconcile_payouts(session)

        assert row.status == "paid"  # via resubmit — the unsealed row never matched
        assert row.tx_hash == "tx"

    @pytest.mark.asyncio
    async def test_wrong_sender_does_not_match(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="failed")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        tx = _sealed_reward_tx("miner-1", 5000, session.default_wallet, sender="0x" + "99" * 20)
        with (
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, return_value=[tx]),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}),
        ):
            await client.reconcile_payouts(session)

        assert row.tx_hash == "tx"  # paid via resubmit; foreign tx ignored

    @pytest.mark.asyncio
    async def test_wrong_amount_does_not_match(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="failed", amount=5000)
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        tx = _sealed_reward_tx("miner-1", 4999, session.default_wallet)  # value=4999 != 5000
        with (
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, return_value=[tx]),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
            patch.object(client._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}),
        ):
            await client.reconcile_payouts(session)

        assert row.tx_hash == "tx"

    @pytest.mark.asyncio
    async def test_exact_hash_lookup_marks_paid_without_sweep(self, client, payout_session):
        """The deterministic hash persisted pre-submit is the exact key."""
        session = payout_session
        exact_hash = "0x" + "77" * 32
        row = _payout_row(status="failed", tx_hash=exact_hash, recipient=session.default_wallet)
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(
                client._rpc,
                "get_transaction",
                new_callable=AsyncMock,
                return_value=_sealed_reward_tx("miner-1", 5000, session.default_wallet, tx_hash=exact_hash),
            ),
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock) as qt,
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["paid"] == 1
        assert row.tx_hash == exact_hash
        qt.assert_not_awaited()  # exact hit short-circuits the sweep
        submit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wallet_rotation_still_matches_landed_tx(self, client, payout_session):
        """row.recipient (persisted at submit) beats the miner's CURRENT
        wallet — a rotation after submit must not cause a resubmit."""
        session = payout_session
        old_wallet = "0x" + "11" * 20
        row = _payout_row(status="failed", recipient=old_wallet)
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))
        # Miner now resolves to default_wallet; the landed tx paid old_wallet.
        tx = _sealed_reward_tx("miner-1", 5000, old_wallet)

        with (
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, return_value=[tx]),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["paid"] == 1
        assert row.status == "paid"
        submit.assert_not_awaited()


class TestLookupUncertaintySkips:
    """BLOCKER 2: RPC read failures are UNKNOWN — never 'proven absent'."""

    @pytest.mark.asyncio
    async def test_sealed_lookup_error_skips_row(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="failed")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, side_effect=OSError("rpc down")),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["unknown"] == 1
        assert summary["retry"] == 0
        assert row.status == "failed"  # untouched — NOT resubmitted
        assert row.reconcile_attempts == 0
        submit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mempool_lookup_error_skips_row(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="failed")
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, return_value=[]),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                side_effect=OSError("mempool down"),
            ),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["unknown"] == 1
        assert row.status == "failed"
        submit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exact_hash_lookup_error_makes_row_unknown(self, client, payout_session):
        """Exact-hash probe failure + empty sweep = unknown, not absent."""
        session = payout_session
        row = _payout_row(status="failed", tx_hash="0x" + "77" * 32, recipient=session.default_wallet)
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(client._rpc, "get_transaction", new_callable=AsyncMock, side_effect=OSError("down")),
            patch.object(client._rpc, "query_transactions", new_callable=AsyncMock, return_value=[]),
            patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit,
        ):
            summary = await client.reconcile_payouts(session)

        assert summary["unknown"] == 1
        submit.assert_not_awaited()


class TestRetryCapEnforced:
    """BLOCKER 3: reclaim must not resurrect rows at/over the attempt cap."""

    @pytest.mark.asyncio
    async def test_reclaim_refuses_row_at_cap(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="retry", reconcile_attempts=3)
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        claim = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=0, amount=5000)

        assert claim is None
        assert row.status == "retry"  # stays parked for the operator

    @pytest.mark.asyncio
    async def test_reclaim_below_cap_consumes_attempt(self, client, payout_session):
        session = payout_session
        row = _payout_row(status="retry", reconcile_attempts=1)
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        claim = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=0, amount=5000)

        assert claim is row
        assert claim.status == "pending"
        assert claim.reconcile_attempts == 2  # reclaim IS a resubmit attempt

    @pytest.mark.asyncio
    async def test_exhausted_status_is_terminal_for_sweep(self, client, payout_session):
        """'exhausted' rows drop out of the sweep entirely — no more RPC
        probes, no reclaim, operator-only."""
        session = payout_session
        row = _payout_row(status="exhausted", reconcile_attempts=3)
        session.payouts.append(row)
        session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with patch.object(client._rpc, "query_transactions", new_callable=AsyncMock) as qt:
            summary = await client.reconcile_payouts(session)

        assert summary["checked"] == 0
        qt.assert_not_awaited()

        claim = await client._claim_payout(session=session, miner_id="miner-1", epoch_number=0, amount=5000)
        assert claim is None


class TestSubmissionCap:
    """Respin: batch submissions bounded below mempool_nonce_lookahead."""

    @pytest.mark.asyncio
    async def test_distribute_stops_at_submission_cap(self, payout_session):
        capped = PoolHubBlockchainClient(
            signer_address=SIGNER_ADDRESS, signer_private_key=SIGNER_KEY, max_submissions_per_cycle=1
        )
        session = payout_session
        await _share(session, "miner-1")
        await _share(session, "miner-2")

        with (
            patch.object(capped._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(capped._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}) as submit,
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
        ):
            payouts = await capped.distribute_rewards(block_height=PAYOUT_HEIGHT, session=session)

        assert len(payouts) == 1
        assert payouts[0]["status"] == "paid"
        assert submit.await_count == 1
        # The second miner was never even claimed — pays next cycle.
        assert ("miner-2", "ait-hub", 0) not in session.claimed

    @pytest.mark.asyncio
    async def test_reconcile_resubmits_share_the_budget(self, payout_session):
        capped = PoolHubBlockchainClient(
            signer_address=SIGNER_ADDRESS,
            signer_private_key=SIGNER_KEY,
            max_submissions_per_cycle=1,
        )
        session = payout_session
        for mid in ("miner-1", "miner-2"):
            row = _payout_row(miner_id=mid, status="failed")
            session.payouts.append(row)
            session.claimed.add((row.miner_id, row.chain_id, row.epoch_number))

        with (
            patch.object(capped._rpc, "query_transactions", new_callable=AsyncMock, return_value=[]),
            patch(
                "aitbc.market.blockchain_rpc.BlockchainRPCClient.get_mempool",
                new_callable=AsyncMock,
                return_value=_mempool(),
            ),
            patch.object(capped._rpc, "get_nonce", new_callable=AsyncMock, return_value=0),
            patch.object(capped._rpc, "submit_transaction", new_callable=AsyncMock, return_value={"tx_hash": "tx"}) as submit,
        ):
            summary = await capped.reconcile_payouts(session)

        assert submit.await_count == 1
        assert summary["paid"] == 1
        assert summary["deferred"] == 1


class TestShareValidationRespin:
    @pytest.mark.asyncio
    async def test_malformed_evidence_hash_rejected(self, payout_session):
        for bad in ("0xa", "deadbeef", "0x" + "zz" * 32, "", "0x" + "ab" * 31):
            with pytest.raises(ValueError, match="evidence_tx_hash"):
                await record_verified_share(
                    payout_session,
                    miner_id="m",
                    chain_id="ait-hub",
                    epoch_number=0,
                    shares=1,
                    evidence_tx_hash=bad,
                )

    @pytest.mark.asyncio
    async def test_negative_epoch_rejected(self, payout_session):
        with pytest.raises(ValueError, match="epoch_number"):
            await record_verified_share(
                payout_session,
                miner_id="m",
                chain_id="ait-hub",
                epoch_number=-1,
                shares=1,
                evidence_tx_hash="0x" + "ab" * 32,
            )

    @pytest.mark.asyncio
    async def test_unvetted_source_is_not_payout_eligible(self, client, payout_session):
        """Payout-side source allowlist: verified rows under a non-allowlisted
        source must not reach the payout math."""
        session = payout_session
        row = RewardShare(
            miner_id="miner-1",
            chain_id="ait-hub",
            epoch_number=0,
            shares=5000,
            jobs_completed=1,
            source="self_reported",
            evidence_tx_hash="0x" + "ef" * 32,
            verified=True,
        )
        session.shares.append(row)

        with patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock) as submit:
            payouts = await client.distribute_rewards(block_height=PAYOUT_HEIGHT, session=session)

        assert payouts == []
        submit.assert_not_awaited()
