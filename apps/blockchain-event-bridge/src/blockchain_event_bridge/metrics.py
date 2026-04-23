"""Prometheus metrics for blockchain event bridge."""

from prometheus_client import Counter, Histogram, Gauge

# Event metrics
events_received_total = Counter(
    "bridge_events_received_total",
    "Total number of events received from blockchain",
    ["event_type"]
)

events_processed_total = Counter(
    "bridge_events_processed_total",
    "Total number of events processed",
    ["event_type", "status"]
)

# Action metrics
actions_triggered_total = Counter(
    "bridge_actions_triggered_total",
    "Total number of actions triggered",
    ["action_type"]
)

actions_failed_total = Counter(
    "bridge_actions_failed_total",
    "Total number of actions that failed",
    ["action_type"]
)

# Performance metrics
event_processing_duration_seconds = Histogram(
    "bridge_event_processing_duration_seconds",
    "Time spent processing events",
    ["event_type"]
)

action_execution_duration_seconds = Histogram(
    "bridge_action_execution_duration_seconds",
    "Time spent executing actions",
    ["action_type"]
)

# Queue metrics
event_queue_size = Gauge(
    "bridge_event_queue_size",
    "Current size of event queue",
    ["topic"]
)

# Connection metrics
gossip_subscribers_total = Gauge(
    "bridge_gossip_subscribers_total",
    "Number of active gossip broker subscriptions"
)

coordinator_api_requests_total = Counter(
    "bridge_coordinator_api_requests_total",
    "Total number of coordinator API requests",
    ["endpoint", "method", "status"]
)
