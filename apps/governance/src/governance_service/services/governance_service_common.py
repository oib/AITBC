"""Shared constants and helpers for the governance service (#1860 Phase 6 split).

Module-level names split out of ``governance_service.py`` so the service
class can be composed from mixin modules without circular imports:
``_OPS_ERRORS`` (the expected operational failure surface for the
best-effort handlers), the on-chain reconcile probe tuning,
``_VOTE_UNIQUE_INDEX`` (the DB backstop name for the duplicate-vote scan),
and ``_parse_datetime``.

``governance_service.py`` re-exports every name moved here, so the import
surface — including ``_RECONCILE_PROBE_CONCURRENCY`` used by tests — is
unchanged. This module is a leaf: it imports nothing from the service
modules.
"""

import httpx
from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from aitbc.exceptions import AITBCError

# Expected operational failure surface for the best-effort handlers below:
# chain RPC calls (httpx transport/status, aitbc network errors), DB session
# work, and the data-shape errors proposal/vote payload handling can raise.
_OPS_ERRORS = (
    httpx.HTTPError,
    AITBCError,
    SQLAlchemyError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ArithmeticError,
    TimeoutError,
)

# GOV-LIST-RECONCILE-COST-1: how many chain probes a list_proposals may run at
# once (they are one RPC call each) and how long a "not executed" answer is
# remembered. The cache is class-level: the service is constructed per request,
# so an instance dict would reset on every call and never save a probe.
_RECONCILE_PROBE_CONCURRENCY = 4
_RECONCILE_NEG_CACHE_SECONDS = 60.0

# Name of the unique index on votes(proposal_id, lower(voter_id)) — the DB
# backstop for the check-then-insert duplicate-vote scan (#1610). Must match
# ``uq_votes_proposal_voter_ci`` in domain/governance.py and migration 006.
_VOTE_UNIQUE_INDEX = "uq_votes_proposal_voter_ci"


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO string or datetime into a timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Pydantic-style ISO parsing
        try:
            from dateutil import parser

            return parser.isoparse(value)
        except ImportError:
            # Fallback using the standard library
            value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value)
    raise ValueError(f"Cannot parse datetime from {type(value)}")
