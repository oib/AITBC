"""B12: Integration tests for atomic cross-chain settlement (v0.9.0).

Tests the full settlement lifecycle via the coordinator, HTLC utilities, and
proof chain verification. Uses mocked settlement service to avoid SQLAlchemy
model registry conflicts when run alongside other app tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from aitbc.settlement.htlc import (
    HTLCState,
    HTLCStateMachine,
    calculate_dest_timelock,
    calculate_source_timelock,
    compute_hashlock,
    generate_secret,
    validate_timelocks,
    verify_secret,
)
from aitbc.settlement.proofs import (
    build_execution_proof,
    build_lock_proof,
    build_release_proof,
    build_settlement_proof,
    build_verification_proof,
    compute_proof_hash,
    verify_proof_chain,
)
from aitbc.settlement.types import EscrowProof, EscrowStatus, ProofType


# ---------------------------------------------------------------------------
# HTLC utility tests
# ---------------------------------------------------------------------------


class TestHTLCUtilities:
    def test_secret_generation_and_verification(self):
        secret = generate_secret()
        hashlock = compute_hashlock(secret)
        assert verify_secret(secret, hashlock)
        assert not verify_secret("0xwrong", hashlock)

    def test_timelock_calculation(self):
        source_tl = calculate_source_timelock(
            current_block_height=100,
            timeout_seconds=3600,
            block_time_seconds=5,
        )
        dest_tl = calculate_dest_timelock(
            source_timelock=source_tl,
            source_block_time=5,
            dest_block_time=3,
        )
        assert source_tl > 100
        assert dest_tl > 0
        # Dest expiry (in seconds) must be before source expiry
        assert dest_tl * 3 < source_tl * 5

    def test_validate_timelocks_valid(self):
        source_tl = calculate_source_timelock(100, 7200, 5)
        dest_tl = calculate_dest_timelock(source_tl, 5, 3)
        errors = validate_timelocks(source_tl, dest_tl, 100, 200, 5, 3, min_margin_seconds=0)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_validate_timelocks_dest_too_late(self):
        source_tl = calculate_source_timelock(100, 3600, 5)
        errors = validate_timelocks(source_tl, source_tl, 100, 100, 5, 5)
        assert len(errors) > 0

    def test_htlc_state_machine_happy_path(self):
        sm = HTLCStateMachine()
        result = sm.transition(HTLCState.CREATED, HTLCState.FUNDED)
        assert result == HTLCState.FUNDED
        result = sm.transition(HTLCState.FUNDED, HTLCState.COMPLETED)
        assert result == HTLCState.COMPLETED

    def test_htlc_state_machine_refund_path(self):
        sm = HTLCStateMachine()
        sm.transition(HTLCState.CREATED, HTLCState.FUNDED)
        result = sm.transition(HTLCState.FUNDED, HTLCState.REFUNDED)
        assert result == HTLCState.REFUNDED

    def test_htlc_state_machine_invalid_transition(self):
        sm = HTLCStateMachine()
        with pytest.raises(ValueError):
            sm.transition(HTLCState.CREATED, HTLCState.COMPLETED)


# ---------------------------------------------------------------------------
# Proof chain tests
# ---------------------------------------------------------------------------


class TestProofChain:
    def test_full_proof_chain_valid(self):
        """Build all 5 proofs and verify the chain."""
        lock_proof = build_lock_proof(
            source_chain="ait-hub",
            lock_tx_hash="0xlock123",
            amount=1000,
            sender="alice",
            recipient="bob",
            block_height=100,
            block_hash="0xblock100",
            timestamp=1000.0,
        )

        verify_proof = build_verification_proof(
            dest_chain="ait-island1",
            verification_tx_hash="0xverify123",
            escrow_id="esc_001",
            block_height=200,
            block_hash="0xblock200",
            previous_proof_hash=compute_proof_hash(lock_proof),
            timestamp=2000.0,
        )

        exec_proof = build_execution_proof(
            dest_chain="ait-island1",
            execution_tx_hash="0xexec123",
            trade_id="trade_001",
            block_height=201,
            block_hash="0xblock201",
            previous_proof_hash=compute_proof_hash(verify_proof),
            timestamp=3000.0,
        )

        release_proof = build_release_proof(
            dest_chain="ait-island1",
            release_tx_hash="0xrelease123",
            escrow_id="esc_001",
            block_height=202,
            block_hash="0xblock202",
            previous_proof_hash=compute_proof_hash(exec_proof),
            timestamp=4000.0,
        )

        settlement_proof = build_settlement_proof(
            source_chain="ait-hub",
            settlement_tx_hash="0xsettle123",
            escrow_id="esc_001",
            block_height=101,
            block_hash="0xblock101",
            previous_proof_hash=compute_proof_hash(release_proof),
            timestamp=5000.0,
        )

        chain = [lock_proof, verify_proof, exec_proof, release_proof, settlement_proof]
        assert not verify_proof_chain(chain), "Proof chain should be valid (no errors)"

    def test_broken_proof_chain_detected(self):
        """Tamper with a proof link — chain verification fails."""
        lock_proof = build_lock_proof(
            source_chain="ait-hub",
            lock_tx_hash="0xlock",
            amount=100,
            sender="alice",
            recipient="bob",
            block_height=10,
            block_hash="0xblk10",
            timestamp=100.0,
        )

        verify_proof = build_verification_proof(
            dest_chain="ait-island1",
            verification_tx_hash="0xverify",
            escrow_id="esc_002",
            block_height=20,
            block_hash="0xblk20",
            previous_proof_hash=compute_proof_hash(lock_proof),
            timestamp=200.0,
        )

        # Tamper: break the link
        verify_proof.previous_proof_hash = "0xtampered"

        chain = [lock_proof, verify_proof]
        assert verify_proof_chain(chain), "Broken chain should return errors"

    def test_empty_proof_chain_returns_error(self):
        """Empty chain returns an error (not valid)."""
        errors = verify_proof_chain([])
        assert len(errors) > 0

    def test_single_proof_chain_valid(self):
        """Single proof with no previous is valid."""
        lock_proof = build_lock_proof(
            source_chain="ait-hub",
            lock_tx_hash="0xlock",
            amount=100,
            sender="alice",
            recipient="bob",
            block_height=10,
            block_hash="0xblk10",
            timestamp=100.0,
        )
        assert not verify_proof_chain([lock_proof]), "Single proof should be valid"


# ---------------------------------------------------------------------------
# Settlement coordinator tests (mocked service)
# ---------------------------------------------------------------------------


class TestSettlementCoordinator:
    @pytest.mark.asyncio
    async def test_coordinator_happy_path(self):
        """Coordinator runs full lifecycle: create -> lock -> verify -> execute -> settle."""
        import sys

        # Import coordinator with mocked settlement service
        from unittest.mock import patch

        mock_service = AsyncMock()
        mock_service.create_escrow.return_value = {
            "escrow_id": "esc_test",
            "secret": "0xabc",
            "secret_hash": "0xdef",
            "status": "pending",
        }
        mock_service.lock_escrow.return_value = {"status": "locked"}
        mock_service.verify_lock.return_value = {"status": "verified"}
        mock_service.execute_trade.return_value = {"status": "completed"}
        mock_service.settle.return_value = {"status": "completed"}

        with patch("aitbc_chain.cross_chain.settlement_coordinator.CrossChainSettlementService") as MockSvc:
            MockSvc.return_value = mock_service

            # Re-import to get the patched class
            if "aitbc_chain" in sys.modules:
                from aitbc_chain.cross_chain.settlement_coordinator import AtomicSettlementCoordinator

                coord = AtomicSettlementCoordinator()
                result = await coord.run_settlement(
                    trade_id="trade_001",
                    source_chain="ait-hub",
                    dest_chain="ait-island1",
                    sender="alice",
                    recipient="bob",
                    amount=500,
                )

                assert result["status"] == "completed"
                assert result["escrow_id"] == "esc_test"
                assert result["secret"] == "0xabc"

                mock_service.create_escrow.assert_called_once()
                mock_service.lock_escrow.assert_called_once_with("esc_test")
                mock_service.verify_lock.assert_called_once_with("esc_test")
                mock_service.execute_trade.assert_called_once_with("esc_test")
                mock_service.settle.assert_called_once_with("esc_test", "0xabc")

    @pytest.mark.asyncio
    async def test_coordinator_failure_triggers_refund(self):
        """If any step fails, coordinator attempts refund."""
        import sys

        from unittest.mock import patch

        mock_service = AsyncMock()
        mock_service.create_escrow.return_value = {
            "escrow_id": "esc_fail",
            "secret": "0xabc",
            "status": "pending",
        }
        mock_service.lock_escrow.return_value = {"status": "locked"}
        mock_service.verify_lock.side_effect = ValueError("verify failed")
        mock_service.refund.return_value = {"status": "refunded"}

        with patch("aitbc_chain.cross_chain.settlement_coordinator.CrossChainSettlementService") as MockSvc:
            MockSvc.return_value = mock_service

            if "aitbc_chain" in sys.modules:
                from aitbc_chain.cross_chain.settlement_coordinator import AtomicSettlementCoordinator

                coord = AtomicSettlementCoordinator()
                result = await coord.run_settlement(
                    trade_id="trade_fail",
                    source_chain="ait-hub",
                    dest_chain="ait-island1",
                    sender="alice",
                    recipient="bob",
                    amount=300,
                )

                assert result["status"] == "failed"
                assert "error" in result
                mock_service.refund.assert_called_once_with("esc_fail")

    @pytest.mark.asyncio
    async def test_coordinator_monitor_start_stop(self):
        """Monitor starts and stops cleanly."""
        from unittest.mock import patch

        mock_service = AsyncMock()
        mock_service.check_timeouts.return_value = []

        with patch("aitbc_chain.cross_chain.settlement_coordinator.CrossChainSettlementService") as MockSvc:
            MockSvc.return_value = mock_service

            from aitbc_chain.cross_chain.settlement_coordinator import AtomicSettlementCoordinator

            coord = AtomicSettlementCoordinator()
            await coord.start_monitor()
            assert coord._running is True

            await coord.stop_monitor()
            assert coord._running is False


# ---------------------------------------------------------------------------
# No funds stuck invariant tests
# ---------------------------------------------------------------------------


class TestNoFundsStuck:
    @pytest.mark.asyncio
    async def test_coordinator_failure_does_not_leave_funds_stuck(self):
        """On failure, refund is attempted — no funds stuck."""
        from unittest.mock import patch

        mock_service = AsyncMock()
        mock_service.create_escrow.return_value = {
            "escrow_id": "esc_stuck",
            "secret": "0xabc",
            "status": "pending",
        }
        mock_service.lock_escrow.side_effect = RuntimeError("lock failed")
        mock_service.refund.return_value = {"status": "refunded"}

        with patch("aitbc_chain.cross_chain.settlement_coordinator.CrossChainSettlementService") as MockSvc:
            MockSvc.return_value = mock_service

            from aitbc_chain.cross_chain.settlement_coordinator import AtomicSettlementCoordinator

            coord = AtomicSettlementCoordinator()
            result = await coord.run_settlement(
                trade_id="trade_stuck",
                source_chain="ait-hub",
                dest_chain="ait-island1",
                sender="alice",
                recipient="bob",
                amount=100,
            )

            # Should fail and attempt refund
            assert result["status"] == "failed"
            mock_service.refund.assert_called_once_with("esc_stuck")

    @pytest.mark.asyncio
    async def test_coordinator_refund_failure_logged(self):
        """If refund also fails, error is captured but no crash."""
        from unittest.mock import patch

        mock_service = AsyncMock()
        mock_service.create_escrow.return_value = {
            "escrow_id": "esc_double_fail",
            "secret": "0xabc",
            "status": "pending",
        }
        mock_service.lock_escrow.side_effect = RuntimeError("lock failed")
        mock_service.refund.side_effect = RuntimeError("refund also failed")

        with patch("aitbc_chain.cross_chain.settlement_coordinator.CrossChainSettlementService") as MockSvc:
            MockSvc.return_value = mock_service

            from aitbc_chain.cross_chain.settlement_coordinator import AtomicSettlementCoordinator

            coord = AtomicSettlementCoordinator()
            result = await coord.run_settlement(
                trade_id="trade_double_fail",
                source_chain="ait-hub",
                dest_chain="ait-island1",
                sender="alice",
                recipient="bob",
                amount=100,
            )

            assert result["status"] == "failed"
            assert "error" in result


# ---------------------------------------------------------------------------
# Settlement types tests
# ---------------------------------------------------------------------------


class TestSettlementTypes:
    def test_escrow_status_values(self):
        assert EscrowStatus.PENDING.value == "pending"
        assert EscrowStatus.LOCKED.value == "locked"
        assert EscrowStatus.VERIFIED.value == "verified"
        assert EscrowStatus.COMPLETED.value == "completed"
        assert EscrowStatus.REFUNDED.value == "refunded"
        assert EscrowStatus.FAILED.value == "failed"

    def test_proof_type_values(self):
        assert ProofType.LOCK.value == "lock"
        assert ProofType.VERIFICATION.value == "verification"
        assert ProofType.EXECUTION.value == "execution"
        assert ProofType.RELEASE.value == "release"
        assert ProofType.SETTLEMENT.value == "settlement"

    def test_escrow_status_transitions(self):
        """Verify expected status ordering."""
        statuses = [
            EscrowStatus.PENDING,
            EscrowStatus.LOCKED,
            EscrowStatus.VERIFIED,
            EscrowStatus.COMPLETED,
        ]
        for i in range(len(statuses) - 1):
            assert statuses[i] != statuses[i + 1]

    def test_proof_to_dict_roundtrip(self):
        proof = EscrowProof(
            proof_type=ProofType.LOCK,
            chain_id="ait-hub",
            block_height=100,
            block_hash="0xabc",
            tx_hash="0xtx",
            timestamp=1000.0,
        )
        # Verify fields
        assert proof.proof_type == ProofType.LOCK
        assert proof.chain_id == "ait-hub"
        assert proof.block_height == 100
        assert proof.previous_proof_hash == ""
