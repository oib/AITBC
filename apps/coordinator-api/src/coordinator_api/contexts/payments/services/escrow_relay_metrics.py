"""Escrow relay outcome counter (ESCROW-RELAY-OBS-1).

``aitbc_escrow_relay_requests_total{relay,result}`` counts each relayed
request once, at the boundary where the outcome is known. The generic
``http_requests_total`` middleware labels cannot split these classes:
replay vs ok are both 200, and a chain timeout vs a chain 5xx both
surface to the caller as 502 — so the result class is recorded here.

Result classes:

- ``ok``             — relayed to the chain and settled normally (200,
                       ``duplicate=false``)
- ``replay``         — dedup hit / idempotent-operation replay; the stored
                       result was returned without a second chain call
- ``business_4xx``   — a refusal the client can fix (binding mismatch,
                       over-cap amount, unknown job, conflicting lock, and
                       chain 4xx pass-throughs other than 425)
- ``too_early_425``  — chain answered 425 "lock not yet sealed"; normal
                       Retry-After traffic, alerted only on storms
- ``upstream_5xx``   — a 5xx surfaced to the caller: chain 5xx pass-through,
                       malformed upstream payload, or an internal error
- ``chain_timeout``  — transport failure reaching the settlement node with
                       no HTTP response (timeout, DNS, refused connection)

The ``refund`` relay is mid-review: its router calls
:func:`record_escrow_relay_result` the same way, and the counter simply
stays silent until that router is mounted (the include in ``main.py`` is
guarded so the hook no-ops when the module is absent).
"""

from __future__ import annotations

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)

ESCROW_RELAY_REQUESTS = Counter(
    "aitbc_escrow_relay_requests_total",
    "Escrow relay requests by relay (create/release/refund) and result class",
    ["relay", "result"],
)

RESULT_OK = "ok"
RESULT_REPLAY = "replay"
RESULT_BUSINESS_4XX = "business_4xx"
RESULT_TOO_EARLY_425 = "too_early_425"
RESULT_UPSTREAM_5XX = "upstream_5xx"
RESULT_CHAIN_TIMEOUT = "chain_timeout"

# Fixed label domains (ESCROW-RELAY-SERIES-1). The ``refund`` relay is
# pre-initialised alongside the mounted ones so its series export at 0
# before the router lands — same for the rarely-hit result classes.
RELAYS = ("create", "release", "refund")
RESULTS = (
    RESULT_OK,
    RESULT_REPLAY,
    RESULT_BUSINESS_4XX,
    RESULT_TOO_EARLY_425,
    RESULT_UPSTREAM_5XX,
    RESULT_CHAIN_TIMEOUT,
)


def preinitialise_escrow_relay_series() -> None:
    """Touch every relay×result child so the counter exports all series at 0.

    prometheus_client only creates a labelled child on first ``.labels()``
    call, so without this the ``create``/``refund`` series stay absent until
    first use and ``rate()``-based alerts see no series at all rather than a
    zero rate (director nit on #474, tracked as #484). Called once at import;
    idempotent and safe to call again (``labels`` returns the same child).
    """
    for relay in RELAYS:
        for result in RESULTS:
            ESCROW_RELAY_REQUESTS.labels(relay=relay, result=result)


preinitialise_escrow_relay_series()

# Stuck-escrow sweeper refund failures (#2329): the generic http_requests
# middleware cannot see these -- the sweep is a background loop, not a
# request -- so the sweeper counts its own failures here, labelled by the
# classified reason. ``settlement_wallet_underfunded`` is the chain's
# "insufficient balance for sender" refusal; ``refund_error`` is every other
# exception-path failure.
STUCK_ESCROW_REFUND_FAILURES = Counter(
    "aitbc_stuck_escrow_refund_failures_total",
    "Stuck-escrow sweeper refund failures by reason",
    ["reason"],
)

STUCK_ESCROW_REASON_UNDERFUNDED = "settlement_wallet_underfunded"
STUCK_ESCROW_REASON_REFUND_ERROR = "refund_error"
_STUCK_ESCROW_REASONS = (STUCK_ESCROW_REASON_UNDERFUNDED, STUCK_ESCROW_REASON_REFUND_ERROR)


def preinitialise_stuck_escrow_series() -> None:
    """Export both reason series at 0 before the first failure (see above)."""
    for reason in _STUCK_ESCROW_REASONS:
        STUCK_ESCROW_REFUND_FAILURES.labels(reason=reason)


preinitialise_stuck_escrow_series()


def record_stuck_escrow_refund_failure(reason: str) -> None:
    """Count one sweeper refund failure; never break a sweep for metrics."""
    try:
        STUCK_ESCROW_REFUND_FAILURES.labels(reason=reason).inc()
    except Exception:  # pragma: no cover - prometheus_client never raises here
        logger.exception("stuck escrow refund metric failed: reason=%s", reason)


# Attribute name used to carry the classified result on an HTTPException
# from the service (which can tell a timeout from a chain 5xx) to the
# router (which only sees the surfaced status).
ESCROW_RESULT_ATTR = "escrow_relay_result"


def record_escrow_relay_result(relay: str, result: str) -> None:
    """Count one relayed request outcome; never break a request for metrics."""
    try:
        ESCROW_RELAY_REQUESTS.labels(relay=relay, result=result).inc()
    except Exception:  # pragma: no cover - prometheus_client never raises here
        logger.exception("escrow relay metric failed: relay=%s result=%s", relay, result)


def classify_escrow_relay_status(status_code: int) -> str:
    """Map a surfaced HTTP status to a result class.

    Used by the routers for HTTPExceptions the service did not pre-classify
    via ``ESCROW_RESULT_ATTR`` — i.e. every status except the ambiguous 502
    that hides the timeout/5xx split.
    """
    if status_code == 425:
        return RESULT_TOO_EARLY_425
    if 400 <= status_code < 500:
        return RESULT_BUSINESS_4XX
    return RESULT_UPSTREAM_5XX


def tag_escrow_result(exc: BaseException, result: str) -> BaseException:
    """Attach a classified result to an HTTPException for the router."""
    setattr(exc, ESCROW_RESULT_ATTR, result)
    return exc


def classified_escrow_result(exc: BaseException, status_code: int) -> str:
    """Read a pre-classified result off an exception, else map the status."""
    tagged = getattr(exc, ESCROW_RESULT_ATTR, None)
    if isinstance(tagged, str) and tagged:
        return tagged
    return classify_escrow_relay_status(status_code)
