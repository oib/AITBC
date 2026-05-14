"""
Chain Isolation Metrics for Prometheus
Metrics for monitoring chain isolation violations and cross-chain transaction attempts
"""

from prometheus_client import Counter, Histogram
from prometheus_client.registry import CollectorRegistry

# Registry for chain isolation metrics
registry = CollectorRegistry()

# Counters for chain isolation violations
chain_isolation_violations_total = Counter(
    'chain_isolation_violations_total',
    'Total number of chain isolation violations detected',
    ['violation_type', 'node'],
    registry=registry
)

cross_chain_transaction_attempts = Counter(
    'cross_chain_transaction_attempts_total',
    'Total number of cross-chain transaction attempts',
    ['source_chain', 'target_chain', 'node'],
    registry=registry
)

chain_id_validation_failures = Counter(
    'chain_id_validation_failures_total',
    'Total number of chain_id validation failures',
    ['expected_chain', 'actual_chain', 'node'],
    registry=registry
)

bridge_request_chain_mismatches = Counter(
    'bridge_request_chain_mismatches_total',
    'Total number of bridge requests with chain mismatches',
    ['source_chain', 'target_chain', 'node'],
    registry=registry
)

# Histogram for transaction validation time
transaction_validation_duration = Histogram(
    'transaction_validation_duration_seconds',
    'Time spent validating transactions',
    ['chain_id'],
    registry=registry
)


def record_chain_isolation_violation(violation_type: str, node: str = 'unknown') -> None:
    """Record a chain isolation violation"""
    chain_isolation_violations_total.labels(
        violation_type=violation_type,
        node=node
    ).inc()


def record_cross_chain_transaction_attempt(
    source_chain: str,
    target_chain: str,
    node: str = 'unknown'
) -> None:
    """Record a cross-chain transaction attempt"""
    cross_chain_transaction_attempts.labels(
        source_chain=source_chain,
        target_chain=target_chain,
        node=node
    ).inc()


def record_chain_id_validation_failure(
    expected_chain: str,
    actual_chain: str,
    node: str = 'unknown'
) -> None:
    """Record a chain_id validation failure"""
    chain_id_validation_failures.labels(
        expected_chain=expected_chain,
        actual_chain=actual_chain,
        node=node
    ).inc()


def record_bridge_request_chain_mismatch(
    source_chain: str,
    target_chain: str,
    node: str = 'unknown'
) -> None:
    """Record a bridge request chain mismatch"""
    bridge_request_chain_mismatches.labels(
        source_chain=source_chain,
        target_chain=target_chain,
        node=node
    ).inc()
