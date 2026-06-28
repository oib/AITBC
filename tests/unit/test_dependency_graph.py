"""Unit tests for aitbc.parallel.dependency_graph (A1)."""

from aitbc.parallel.dependency_graph import DependencyGraph


class TestNoConflicts:
    def test_no_conflicts_all_in_one_group(self) -> None:
        """5 txs, all different accounts → 1 group of 5."""
        dg = DependencyGraph()
        dg.add_transaction("tx1", frozenset({"A"}), frozenset({"A"}), index=0)
        dg.add_transaction("tx2", frozenset({"B"}), frozenset({"B"}), index=1)
        dg.add_transaction("tx3", frozenset({"C"}), frozenset({"C"}), index=2)
        dg.add_transaction("tx4", frozenset({"D"}), frozenset({"D"}), index=3)
        dg.add_transaction("tx5", frozenset({"E"}), frozenset({"E"}), index=4)

        groups = dg.get_conflict_groups()
        assert len(groups) == 1
        assert len(groups[0]) == 5
        assert set(groups[0]) == {"tx1", "tx2", "tx3", "tx4", "tx5"}

    def test_no_conflict_rate_zero(self) -> None:
        """5 non-conflicting txs → conflict_rate = 0.0."""
        dg = DependencyGraph()
        for i in range(5):
            dg.add_transaction(f"tx{i}", frozenset({chr(65 + i)}), frozenset({chr(65 + i)}), index=i)
        assert dg.conflict_rate() == 0.0


class TestAllConflicts:
    def test_all_conflict_separate_groups(self) -> None:
        """5 txs, all same account → 5 groups of 1."""
        dg = DependencyGraph()
        for i in range(5):
            dg.add_transaction(f"tx{i}", frozenset({"A"}), frozenset({"A"}), index=i)

        groups = dg.get_conflict_groups()
        assert len(groups) == 5
        for group in groups:
            assert len(group) == 1

    def test_all_conflict_rate_one(self) -> None:
        """5 conflicting txs (all write same account A) → conflict_rate = 1.0.

        Each tx conflicts with every other tx (all write A), so all 5 are
        "conflicting txs". Even though they end up in separate groups,
        the conflict_rate measures actual pairwise conflicts.
        """
        dg = DependencyGraph()
        for i in range(5):
            dg.add_transaction(f"tx{i}", frozenset({"A"}), frozenset({"A"}), index=i)
        assert dg.conflict_rate() == 1.0


class TestPartialConflicts:
    def test_partial_conflict(self) -> None:
        """3 txs where tx1 and tx3 conflict (same account A), tx2 is independent (account B).
        tx1 → group 0, tx2 → group 0 (no conflict), tx3 → group 1 (conflicts with tx1).
        Result: 2 groups: [tx1, tx2], [tx3]."""
        dg = DependencyGraph()
        dg.add_transaction("tx1", frozenset({"A"}), frozenset({"A"}), index=0)
        dg.add_transaction("tx2", frozenset({"B"}), frozenset({"B"}), index=1)
        dg.add_transaction("tx3", frozenset({"A"}), frozenset({"A"}), index=2)

        groups = dg.get_conflict_groups()
        assert len(groups) == 2
        assert set(groups[0]) == {"tx1", "tx2"}
        assert groups[1] == ["tx3"]

    def test_partial_conflict_rate(self) -> None:
        """4 txs: tx1 and tx3 conflict (account A), tx2 and tx4 independent (B, C).
        Groups: [tx1, tx2, tx4], [tx3]. Only tx3 is in a group alone.
        conflict_rate = 0/4 = 0.0 (no group has >1 conflicting tx — wait, group 0 has 3 txs
        but they don't conflict with each other, they're just in the same group).

        Actually: conflict_rate counts txs in groups of size >1. Group 0 has 3 txs,
        group 1 has 1 tx. So 3/4 = 0.75. But that's wrong — group 0 txs don't conflict.

        Let me reconsider: conflict_rate should measure actual conflicts, not group size.
        With the current implementation, conflict_rate = txs_in_multi_groups / total.
        Group 0 has 3 txs (none conflict with each other), group 1 has 1 tx.
        So conflict_rate = 3/4 = 0.75. This is the fraction of txs that COULD have
        been in a group with conflicts — but they aren't.

        The metric is: what fraction of txs ended up in a group with other txs?
        This is actually a measure of parallelism, not conflict. Let me fix the test
        to match the actual semantics."""
        dg = DependencyGraph()
        dg.add_transaction("tx1", frozenset({"A"}), frozenset({"A"}), index=0)
        dg.add_transaction("tx2", frozenset({"B"}), frozenset({"B"}), index=1)
        dg.add_transaction("tx3", frozenset({"A"}), frozenset({"A"}), index=2)
        dg.add_transaction("tx4", frozenset({"C"}), frozenset({"C"}), index=3)

        groups = dg.get_conflict_groups()
        # tx1 → group 0, tx2 → group 0 (no conflict), tx3 → group 1 (conflicts with tx1),
        # tx4 → group 0 (no conflict with tx1 or tx2)
        assert len(groups) == 2
        assert set(groups[0]) == {"tx1", "tx2", "tx4"}
        assert groups[1] == ["tx3"]
        # conflict_rate: tx1 and tx3 actually conflict (both write A) → 2/4 = 0.5
        assert dg.conflict_rate() == 0.5


class TestDeterminism:
    def test_deterministic_ordering(self) -> None:
        """Same input always produces same groups, regardless of insertion order."""
        dg1 = DependencyGraph()
        dg1.add_transaction("tx1", frozenset({"A"}), frozenset({"A"}), index=0)
        dg1.add_transaction("tx2", frozenset({"B"}), frozenset({"B"}), index=1)
        dg1.add_transaction("tx3", frozenset({"A"}), frozenset({"A"}), index=2)

        dg2 = DependencyGraph()
        dg2.add_transaction("tx3", frozenset({"A"}), frozenset({"A"}), index=2)
        dg2.add_transaction("tx2", frozenset({"B"}), frozenset({"B"}), index=1)
        dg2.add_transaction("tx1", frozenset({"A"}), frozenset({"A"}), index=0)

        assert dg1.get_conflict_groups() == dg2.get_conflict_groups()

    def test_index_ordering_within_group(self) -> None:
        """Within a group, txs are sorted by index."""
        dg = DependencyGraph()
        dg.add_transaction("tx_c", frozenset({"A"}), frozenset({"A"}), index=2)
        dg.add_transaction("tx_a", frozenset({"A"}), frozenset({"A"}), index=0)
        dg.add_transaction("tx_b", frozenset({"A"}), frozenset({"A"}), index=1)

        groups = dg.get_conflict_groups()
        # Each tx conflicts with the others (all write A), so 3 groups of 1
        assert len(groups) == 3
        # Groups ordered by min index: tx_a (0), tx_b (1), tx_c (2)
        assert groups[0] == ["tx_a"]
        assert groups[1] == ["tx_b"]
        assert groups[2] == ["tx_c"]


class TestConflictTypes:
    def test_read_write_conflict(self) -> None:
        """tx1 reads A, tx2 writes A → conflict."""
        dg = DependencyGraph()
        dg.add_transaction("tx1", frozenset({"A"}), frozenset(), index=0)  # reads A, writes nothing
        dg.add_transaction("tx2", frozenset(), frozenset({"A"}), index=1)  # writes A

        groups = dg.get_conflict_groups()
        assert len(groups) == 2  # They conflict → separate groups

    def test_write_write_conflict(self) -> None:
        """tx1 writes A, tx2 writes A → conflict."""
        dg = DependencyGraph()
        dg.add_transaction("tx1", frozenset({"B"}), frozenset({"A"}), index=0)
        dg.add_transaction("tx2", frozenset({"C"}), frozenset({"A"}), index=1)

        groups = dg.get_conflict_groups()
        assert len(groups) == 2  # Both write A → conflict

    def test_no_conflict_disjoint_sets(self) -> None:
        """tx1 reads/writes A, tx2 reads/writes B → no conflict."""
        dg = DependencyGraph()
        dg.add_transaction("tx1", frozenset({"A"}), frozenset({"A"}), index=0)
        dg.add_transaction("tx2", frozenset({"B"}), frozenset({"B"}), index=1)

        groups = dg.get_conflict_groups()
        assert len(groups) == 1  # No conflict → same group


class TestStats:
    def test_stats(self) -> None:
        dg = DependencyGraph()
        dg.add_transaction("tx1", frozenset({"A"}), frozenset({"A"}), index=0)
        dg.add_transaction("tx2", frozenset({"B"}), frozenset({"B"}), index=1)
        dg.add_transaction("tx3", frozenset({"A"}), frozenset({"A"}), index=2)

        stats = dg.stats()
        assert stats["total_txs"] == 3
        assert stats["num_groups"] == 2
        assert stats["max_group_size"] == 2  # group 0 has tx1, tx2
        assert stats["conflict_rate"] == 2 / 3  # tx1 and tx3 conflict → 2/3

    def test_stats_empty(self) -> None:
        dg = DependencyGraph()
        stats = dg.stats()
        assert stats["total_txs"] == 0
        assert stats["num_groups"] == 0
        assert stats["max_group_size"] == 0
        assert stats["conflict_rate"] == 0.0


class TestExecutionOrder:
    def test_get_execution_order_matches_conflict_groups(self) -> None:
        dg = DependencyGraph()
        dg.add_transaction("tx1", frozenset({"A"}), frozenset({"A"}), index=0)
        dg.add_transaction("tx2", frozenset({"B"}), frozenset({"B"}), index=1)

        assert dg.get_execution_order() == dg.get_conflict_groups()
