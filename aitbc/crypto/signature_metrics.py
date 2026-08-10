"""Counters that separate "this signature is wrong" from "this signature is unreadable".

V23-04: every verification site swallowed both outcomes into ``return False``, so *a node
rejecting every honestly-signed block* and *a node under attack* produced the same log line
and the same metric. The log halves were separated when the recovery paths were centralised;
this is the metric half.

The distinction is not cosmetic. It is the difference between two operational stories:

    signature_verification_failures_total{outcome="mismatch"} rising
        Someone is presenting signatures that parse but recover to the wrong address.
        Either an attack or a client signing over the wrong payload.

    signature_verification_failures_total{outcome="unparseable"} rising
        The bytes are not a signature this code can read. Almost always an encoding
        mismatch on our side -- which is exactly what V23-01 was, and it was invisible for
        as long as it was because nothing counted it separately.

A sustained ``unparseable`` rate is a deployment fault, not an attack, and it is the one
worth paging on: V23-01 meant the node rejected transactions from *every standard wallet*,
and no counter anywhere would have shown it.

These live in the default registry alongside the HTTP metrics, so any service already
exposing ``/metrics`` publishes them without further wiring.
"""

from __future__ import annotations

from prometheus_client import Counter

SIGNATURE_VERIFICATION_FAILURES = Counter(
    "signature_verification_failures_total",
    "Signature verifications that did not succeed, by why",
    ["context", "outcome"],
)

# Verified signatures are counted too: "unparseable is 3% of attempts" is a different
# statement from "there were 40 unparseable signatures", and only the first is actionable
# without knowing the traffic.
SIGNATURE_VERIFICATIONS = Counter(
    "signature_verifications_total",
    "Signature verification attempts",
    ["context"],
)

MISMATCH = "mismatch"
UNPARSEABLE = "unparseable"
ERROR = "error"


def record_attempt(context: str) -> None:
    """Count a verification attempt. ``context`` names the call site, e.g. ``"block"``."""
    SIGNATURE_VERIFICATIONS.labels(context=context).inc()


def record_failure(context: str, outcome: str) -> None:
    """Count a verification failure.

    ``outcome`` is one of ``MISMATCH`` (recovered a valid but different address),
    ``UNPARSEABLE`` (the bytes are not a signature) or ``ERROR`` (anything unexpected,
    which is a bug rather than either of the above).
    """
    SIGNATURE_VERIFICATION_FAILURES.labels(context=context, outcome=outcome).inc()
