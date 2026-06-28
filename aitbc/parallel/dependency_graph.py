"""
Transaction dependency graph for parallel validation.

Analyzes read/write sets of transactions to partition them into conflict-free
groups that can be executed in parallel. Within each group, transactions are
ordered deterministically (by their original index) so that conflicting
transactions are serialized.
"""

from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class DependencyGraph:
    """Builds a transaction dependency graph from read/write sets.

    Transactions are partitioned into conflict-free groups that can be
    executed in parallel. Within each group, transactions conflict with
    each other and must be executed sequentially. Groups are independent
    and can be executed in parallel.

    The grouping is deterministic: transactions are processed in index
    order, and each is assigned to the first existing group where it has
    no conflicts with any member. If it conflicts with all existing groups,
    a new group is created.
    """

    def __init__(self) -> None:
        # tx_id → (read_set, write_set, index)
        self._transactions: dict[str, tuple[frozenset[str], frozenset[str], int]] = {}
        # List of groups; each group is a dict: tx_id → (read_set, write_set, index)
        self._groups: list[dict[str, tuple[frozenset[str], frozenset[str], int]]] = []
        self._dirty = False

    def add_transaction(
        self,
        tx_id: str,
        read_set: frozenset[str],
        write_set: frozenset[str],
        index: int = 0,
    ) -> None:
        """Add a transaction with its read/write sets.

        Args:
            tx_id: Unique transaction identifier (e.g., tx_hash).
            read_set: Set of account addresses read by this tx.
            write_set: Set of account addresses written by this tx.
            index: Original ordering index (for deterministic tie-breaking).
        """
        self._transactions[tx_id] = (read_set, write_set, index)
        self._dirty = True

    def _conflicts(
        self,
        read_a: frozenset[str],
        write_a: frozenset[str],
        read_b: frozenset[str],
        write_b: frozenset[str],
    ) -> bool:
        """Check if two transactions conflict via read/write set overlap."""
        return bool(write_a & write_b or read_a & write_b or write_a & read_b)

    def _build_groups(self) -> None:
        """Build conflict-free groups using greedy first-fit assignment."""
        self._groups = []
        # Process transactions in index order for determinism
        sorted_txs = sorted(self._transactions.items(), key=lambda item: item[1][2])

        for tx_id, (read_set, write_set, index) in sorted_txs:
            assigned = False
            for group in self._groups:
                # Check if this tx conflicts with any member of the group
                has_conflict = False
                for _, (g_read, g_write, _) in group.items():
                    if self._conflicts(read_set, write_set, g_read, g_write):
                        has_conflict = True
                        break
                if not has_conflict:
                    group[tx_id] = (read_set, write_set, index)
                    assigned = True
                    break
            if not assigned:
                # Create a new group
                self._groups.append({tx_id: (read_set, write_set, index)})

        self._dirty = False

    def get_conflict_groups(self) -> list[list[str]]:
        """Partition transactions into conflict-free groups.

        Returns a list of groups, where:
        - Each group contains transactions that conflict with each other
          (must be executed sequentially within the group).
        - Groups are independent and can be executed in parallel.
        - Within each group, transactions are ordered by their original index.
        - Groups are ordered by the minimum index of their members.
        """
        if self._dirty:
            self._build_groups()

        result: list[list[str]] = []
        for group in self._groups:
            # Sort within group by index
            sorted_members = sorted(group.items(), key=lambda item: item[1][2])
            result.append([tx_id for tx_id, _ in sorted_members])
        # Groups are already in creation order (first-fit), which corresponds
        # to min-index order since we process txs in index order.
        return result

    def get_execution_order(self) -> list[list[str]]:
        """Alias for get_conflict_groups — the execution order is the group order."""
        return self.get_conflict_groups()

    def conflict_rate(self) -> float:
        """Return the fraction of transactions that conflict with at least one other.

        A transaction "conflicts" if there exists another transaction whose
        read/write sets overlap with it. Returns 0.0 if there are no transactions.
        """
        total = len(self._transactions)
        if total == 0:
            return 0.0
        # Count txs that have at least one actual conflict
        tx_ids = list(self._transactions.keys())
        conflicting_txs: set[str] = set()
        for i, tx_id_a in enumerate(tx_ids):
            read_a, write_a, _ = self._transactions[tx_id_a]
            for j, tx_id_b in enumerate(tx_ids):
                if i == j:
                    continue
                read_b, write_b, _ = self._transactions[tx_id_b]
                if self._conflicts(read_a, write_a, read_b, write_b):
                    conflicting_txs.add(tx_id_a)
                    conflicting_txs.add(tx_id_b)
                    break
        return len(conflicting_txs) / total

    def stats(self) -> dict[str, Any]:
        """Return stats: total_txs, num_groups, max_group_size, conflict_rate."""
        groups = self.get_conflict_groups()
        return {
            "total_txs": len(self._transactions),
            "num_groups": len(groups),
            "max_group_size": max((len(g) for g in groups), default=0),
            "conflict_rate": self.conflict_rate(),
        }
