"""C-2 regression: proposer round advances within one heartbeat cycle.

The live fleet outage exercise (7 Sep) found that with 4 validators and 1
partitioned, the chain stalled for 120+ seconds because the proposer round
timeout was 2x the heartbeat interval. The fix aligns the round timeout with
the heartbeat so a silent proposer is skipped within one heartbeat cycle.
"""

from datetime import datetime, timedelta, UTC

from aitbc_chain.consensus.multi_validator_poa import proposer_round


class TestProposerRoundAdvancement:
    """Verify the round advances quickly enough to skip a silent proposer."""

    def test_round_advances_within_one_heartbeat(self):
        """After max_empty_block_interval seconds, the round must be >= 1."""
        parent = datetime(2026, 9, 7, 18, 0, 0, tzinfo=UTC)
        # 60 seconds later — one heartbeat interval
        block_ts = parent + timedelta(seconds=60)
        round_num = proposer_round(parent, block_ts, round_seconds=60)
        assert round_num >= 1, f"Round should advance after one heartbeat (60s), got round {round_num}"

    def test_round_zero_during_normal_block_time(self):
        """During normal block production (under 60s), round stays 0."""
        parent = datetime(2026, 9, 7, 18, 0, 0, tzinfo=UTC)
        # 15 seconds later — normal block interval
        block_ts = parent + timedelta(seconds=15)
        round_num = proposer_round(parent, block_ts, round_seconds=60)
        assert round_num == 0, f"Round should be 0 during normal block time (15s), got round {round_num}"

    def test_round_advances_every_heartbeat_cycle(self):
        """Each heartbeat cycle advances the round by 1."""
        parent = datetime(2026, 9, 7, 18, 0, 0, tzinfo=UTC)
        for cycle in range(1, 5):
            block_ts = parent + timedelta(seconds=60 * cycle)
            round_num = proposer_round(parent, block_ts, round_seconds=60)
            assert round_num == cycle, f"Round should be {cycle} after {cycle} heartbeats, got {round_num}"

    def test_old_120s_timeout_would_stall(self):
        """Document the old behaviour: 120s round vs 60s heartbeat = 2-cycle stall."""
        parent = datetime(2026, 9, 7, 18, 0, 0, tzinfo=UTC)
        # After 60 seconds (one heartbeat), old 120s round is still 0
        block_ts = parent + timedelta(seconds=60)
        old_round = proposer_round(parent, block_ts, round_seconds=120)
        assert old_round == 0, "Old 120s timeout should still be round 0 at 60s"
        # After 120 seconds (two heartbeats), old 120s round finally advances
        block_ts = parent + timedelta(seconds=120)
        old_round = proposer_round(parent, block_ts, round_seconds=120)
        assert old_round == 1, "Old 120s timeout should advance to round 1 at 120s"

    def test_partitioned_proposer_skipped_within_one_heartbeat(self):
        """With 4 validators, a partitioned proposer is skipped after 1 heartbeat."""
        from aitbc_chain.consensus.multi_validator_poa import (
            MultiValidatorPoA,
            ValidatorRole,
        )

        consensus = MultiValidatorPoA("test-chain")
        validators = ["0xAaaa", "0xBbbb", "0xCccc", "0xDddd"]
        for addr in validators:
            consensus.add_validator(addr)
            consensus.validators[addr].role = ValidatorRole.VALIDATOR

        height = 100
        # Round 0: proposer is validator at index (100 + 0) % 4 = 0
        round0_proposer = consensus.select_proposer(height, round_number=0)
        assert round0_proposer == "0xAaaa"

        # Round 1 (after 1 heartbeat): proposer is validator at index (100 + 1) % 4 = 1
        round1_proposer = consensus.select_proposer(height, round_number=1)
        assert round1_proposer == "0xBbbb"
        assert round1_proposer != round0_proposer, "Round 1 must select a different proposer than round 0"
