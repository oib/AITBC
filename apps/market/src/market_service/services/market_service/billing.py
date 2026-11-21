"""Provider-attested metered billing → settlement-side partial release (#2365).

Metered ``market run``/``process``/``transcribe``/``hermes`` jobs lock an
escrow estimate, then the provider daemon reports the usage metric it
actually served (``eval_count``, ``duration_minutes``,
``processing_time_hours``) to ``POST /v1/market/jobs/{job_id}/billing``
authenticated by the job's ``X-Access-Key``/``X-Access-Secret`` pair. The
market service stores those attested actuals under the server-owned
``payload["attested_billing"]`` key and the settlement paths (sweeper +
manual release) price them against the offer's listed ``price``/
``price_unit`` — the same formulas the buyer CLI used to apply client-side,
which was buyer-tamperable and therefore unusable for partial release
(#2351 analysis, #1912 relay rule).

The attested amount is clamped to the locked payment amount: a provider
report can only ever reduce the charge below the estimate, never exceed it.
Anything that cannot be priced (unknown service type, missing metric,
missing SoftwareService row, non-positive result) returns ``None`` and the
caller falls back to the full-lock release — the estimate is the agreed
ceiling and the provider did serve the work.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger

from ...domain.market import MarketJob, MarketJobPayment, SoftwareService

logger = get_logger(__name__)

# Server-owned payload key holding provider-attested billing reports. Also
# listed in jobs._PAYLOAD_SERVER_KEYS so a caller cannot seed it at job
# creation.
PAYLOAD_BILLING_KEY = "attested_billing"

_METRIC_NAME_RE = re.compile(r"[A-Za-z0-9_.\-]{1,64}")
_MAX_BILLING_METRICS = 32
# Same 1e15 ceiling the payment validator uses — a metric is a usage count,
# not a money field, but bound it anyway so a hostile report cannot park an
# absurd Decimal in the job payload.
_MAX_BILLING_VALUE = Decimal("1000000000000000")

# States that may still accept billing reports: the job is live and its
# escrow has not been settled. Everything else is terminal for settlement
# purposes — a report arriving after the fact cannot change where the money
# went.
_BILLING_REPORT_STATES = frozenset({"QUEUED", "RUNNING"})


def validate_billing_metrics(raw: Any) -> dict[str, Decimal]:
    """Validate a caller-supplied metrics object; raise ValueError on garbage.

    Accepts ``{"eval_count": 123, ...}`` — names are restricted, values must
    be finite non-negative numbers (int/float/numeric string; bools and
    NaN/Infinity rejected). Returns ``{name: Decimal}``.
    """
    if not isinstance(raw, dict) or not raw:
        raise ValueError("metrics must be a non-empty object")
    if len(raw) > _MAX_BILLING_METRICS:
        raise ValueError(f"too many billing metrics (max {_MAX_BILLING_METRICS})")
    cleaned: dict[str, Decimal] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not _METRIC_NAME_RE.fullmatch(name):
            raise ValueError(f"invalid billing metric name: {name!r}")
        if isinstance(value, bool):
            raise ValueError(f"billing metric {name} must be a number")
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"billing metric {name} must be a number") from e
        if not number.is_finite() or number < 0 or number > _MAX_BILLING_VALUE:
            raise ValueError(f"billing metric {name} out of range")
        cleaned[name] = number
    return cleaned


def attested_billing_metrics(job: MarketJob) -> dict[str, Any] | None:
    """The provider-attested metrics stored on ``job``, or None."""
    billing = (job.payload or {}).get(PAYLOAD_BILLING_KEY)
    if not isinstance(billing, dict):
        return None
    metrics = billing.get("metrics")
    return metrics if isinstance(metrics, dict) and metrics else None


def _metric(metrics: dict[str, Any], name: str) -> Decimal | None:
    """Read one attested metric as Decimal; None when absent/unparseable."""
    raw = metrics.get(name)
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() and value >= 0 else None


# service_type -> (attested metric name, priced price_unit). The CLI bills
# ollama unconditionally per_1k_tokens and hermes by its own unit ladder;
# whisper/ffmpeg charge per listed unit and fall back to the flat price.
_METERED_METRIC = {
    "ollama": ("eval_count", "per_1k_tokens"),
    "cloud_ollama": ("eval_count", "per_1k_tokens"),
    "whisper": ("duration_minutes", "per_audio_min"),
    "ffmpeg": ("processing_time_hours", "per_processing_hour"),
    "hermes": ("duration_minutes", None),
}


def metered_actual_cost(
    service_type: str | None,
    price_unit: str | None,
    price: Decimal,
    metrics: dict[str, Any],
) -> Decimal | None:
    """Price attested usage into an AIT amount; None when it cannot be priced.

    Mirrors the buyer CLI's formulas (``cli/aitbc_cli/commands/market/jobs.py``)
    so the server-side charge equals what the client used to compute — the
    difference is the input now comes from the serving provider's report
    rather than the buyer's HTTP client.
    """
    spec = _METERED_METRIC.get(service_type or "")
    if spec is None:
        return None
    metric_name, unit_price_unit = spec
    usage = _metric(metrics, metric_name)
    if usage is None:
        return None
    if service_type in ("ollama", "cloud_ollama"):
        return (usage / Decimal("1000")) * price
    if service_type == "hermes":
        if price_unit == "per_minute":
            return price * usage
        if price_unit == "per_processing_hour":
            return price * (usage / Decimal("60"))
        return price
    return usage * price if price_unit == unit_price_unit else price


async def _find_software_service(session: AsyncSession, job: MarketJob) -> SoftwareService | None:
    """Resolve the offer's SoftwareService row for its listed price.

    Match order: ``offer_id``, then ``plugin_id``, then
    ``service_type``+``model`` — the same identifiers the job recorded at
    creation. The row lives in this service's own database because the
    offer the buyer resolved came from this service's listing.
    """
    clauses = []
    if job.offer_id:
        clauses.append(col(SoftwareService.offer_id) == job.offer_id)
    if job.plugin_id:
        clauses.append(col(SoftwareService.plugin_id) == job.plugin_id)
    if clauses:
        stmt = select(SoftwareService).where(or_(*clauses)).order_by(col(SoftwareService.registered_at).desc()).limit(5)
        rows = list((await session.execute(stmt)).scalars().all())
        if rows:
            # Prefer an exact offer_id hit, then plugin_id, then anything.
            for row in rows:
                if job.offer_id and row.offer_id == job.offer_id:
                    return row
            for row in rows:
                if job.plugin_id and row.plugin_id == job.plugin_id:
                    return row
            return rows[0]
    if job.service_type and job.model:
        stmt = (
            select(SoftwareService)
            .where(col(SoftwareService.service_type) == job.service_type)
            .where(col(SoftwareService.model) == job.model)
            .order_by(col(SoftwareService.registered_at).desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalars().first()
    return None


async def attested_release_amount(
    session: AsyncSession,
    job: MarketJob,
    payment: MarketJobPayment | None,
) -> Decimal | None:
    """AIT amount a provider-attested partial release should bill.

    Returns ``None`` when the job carries no usable attested billing — the
    caller then releases the full lock exactly as before. A resolved amount
    is clamped to ``payment.amount`` (the locked estimate): attestation can
    only reduce the charge, never exceed the escrow.
    """
    metrics = attested_billing_metrics(job)
    if metrics is None or payment is None:
        return None
    try:
        service = await _find_software_service(session, job)
    except Exception as e:  # noqa: BLE001 - pricing lookup failure must not break settlement
        logger.warning("Billing price lookup failed for job %s: %s", job.id, e)
        service = None
    if service is None:
        logger.warning(
            "Job %s has attested billing but no SoftwareService row for offer %s/plugin %s — releasing full lock",
            job.id,
            job.offer_id,
            job.plugin_id,
        )
        return None
    try:
        price = Decimal(str(service.price))
    except (InvalidOperation, ValueError):
        logger.warning(
            "Job %s service %s has an unreadable price %r — releasing full lock", job.id, service.plugin_id, service.price
        )
        return None
    cost = metered_actual_cost(job.service_type or service.service_type, service.price_unit, price, metrics)
    if cost is None or not cost.is_finite() or cost <= 0:
        logger.warning(
            "Job %s attested billing could not be priced (service_type=%s price_unit=%s metrics=%s) — releasing full lock",
            job.id,
            job.service_type,
            service.price_unit,
            metrics,
        )
        return None
    billed = min(cost, payment.amount)
    logger.info(
        "Job %s attested billing: metrics=%s price=%s/%s -> billed %s AIT (locked %s)",
        job.id,
        metrics,
        price,
        service.price_unit,
        billed,
        payment.amount,
    )
    return billed


def billing_report_state_error(state: str | None) -> str | None:
    """None when ``state`` may accept a billing report, else the refusal reason."""
    if state in _BILLING_REPORT_STATES:
        return None
    return f"job state {state} does not accept billing reports"
