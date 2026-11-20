"""Module-level helpers for the payments service (split from payments.py; pure code motion)."""

from __future__ import annotations

import httpx

from aitbc_shared import JobPayment
from datetime import UTC, datetime
from decimal import InvalidOperation
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from web3.exceptions import Web3Exception

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError
from aitbc.network import AsyncAITBCHTTPClient

from aitbc.market.energy_pricing import (
    EnergyQuote,
    EnergyPricingError,
)
from aitbc.market.evm_rental_receipt import agreement_id_from_receipt_logs
from ....schemas import JobPaymentCreate
from ...infrastructure.domain.job import Job
from ...infrastructure.domain.job_receipt import JobReceipt
from ...zk_applications.services import model_registry


logger = get_logger(__name__)

# Expected failure surface for the payment service -- this module moves
# money, so the tuple is deliberately wider than the baseline:
# filesystem/JSON, data-shape (pydantic ValidationError is a ValueError),
# runtime, SQLAlchemy session errors, lazy in-function imports, httpx
# transport/decoding errors, the aitbc error hierarchy (chain RPC clients
# re-raise RateLimitError / CircuitBreakerOpenError unwrapped), web3
# contract-call errors, decimal parse failures (InvalidOperation is an
# ArithmeticError, not a ValueError), timestamp overflows, assertion
# guards, and HTTPException -- PaymentService raises it for
# ownership/validation failures and every handler below previously caught
# it, so it stays in the tuple to keep money-path semantics identical.
# Handlers that must re-raise HTTPException keep their explicit arms ahead
# of this tuple. BaseExceptions (incl. asyncio.CancelledError) propagate.
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    IndexError,
    TypeError,
    AttributeError,
    RuntimeError,
    AssertionError,
    OverflowError,
    ImportError,
    SQLAlchemyError,
    AITBCError,
    httpx.HTTPError,
    Web3Exception,
    InvalidOperation,
    HTTPException,
    EnergyPricingError,
)


def _resolve_authoritative_inputs(quote: EnergyQuote, session: Session | None = None) -> tuple[Any, Any]:
    """Return the authoritative (profile, rate) for a quote from the energy oracle.

    Reads the on-chain ``IEnergyPricing`` contract at the quote's pinned EVM
    block when available, so the funding gate compares the quote against the
    operator-registered inputs rather than the quote's self-attested embedded
    values. When the coordinator is configured for native energy pricing, reads
    from the local ``NativeEnergyOracle`` tables instead.
    """
    # Resolve via the facade module: tests patch ``payments.settings``.
    from . import payments as _pm

    if _pm.settings.native_energy_pricing:
        from ...market.services.native_energy import NativeEnergyOracle

        if session is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Native energy pricing requires a database session; refusing protected funding",
            )
        try:
            native_oracle = NativeEnergyOracle(session)
            profile = native_oracle.get_profile(quote.resource_id)
            rate = native_oracle.get_rate()
            return profile, rate
        except _OPS_ERRORS as exc:
            logger.warning(
                "Native energy oracle read failed for resource %s; refusing protected funding: %s",
                quote.resource_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not read native energy inputs; refusing protected funding",
            ) from exc

    from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient
    from aitbc.market.energy_oracle import EVMEnergyOracle

    contract = _pm.settings.energy_pricing_contract_address
    rpc_url = _pm.settings.eth_rpc_url
    if not contract or not rpc_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Energy pricing oracle is not configured (ENERGY_PRICING_CONTRACT_ADDRESS / ETH_RPC_URL); refusing protected funding",
        )
    try:
        rpc = EthereumRPCClient(EthereumConfig(rpc_url=rpc_url, network=str(_pm.settings.energy_pricing_chain_id)))
        evm_oracle = EVMEnergyOracle(rpc, contract, _pm.settings.energy_pricing_chain_id)
        block = quote.evm_block_number if quote.evm_block_number is not None else "latest"
        profile = evm_oracle.get_profile(quote.resource_id, block_identifier=block)
        rate = evm_oracle.get_rate(block_identifier=block)
        return profile, rate
    except _OPS_ERRORS as exc:
        logger.warning(
            "Authoritative energy oracle read failed for resource %s; refusing protected funding: %s",
            quote.resource_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not read authoritative energy inputs; refusing protected funding",
        ) from exc


def _parse_settled_at(value: object) -> datetime | None:
    """Parse the settlement time the chain RPC reports, if it reported a usable one."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        logger.warning("Ignoring unparseable released_at from escrow release: %r", value)
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def _lookup_chain_refund(blockchain_rpc_url: str, client: AsyncAITBCHTTPClient, job_id: str) -> str | None:
    """Return the on-chain ESCROW_REFUND tx hash for job_id, if one exists.

    Raises on transport or non-2xx responses so callers do not mistake
    "could not tell" for "does not exist".
    """
    # /rpc/transactions returns a list, so use the union-returning accessor.
    txs = await client.get_json(
        f"{blockchain_rpc_url}/rpc/transactions?transaction_type=ESCROW_REFUND&job_id={job_id}&limit=10"
    )
    if isinstance(txs, list):
        for tx in txs:
            if (tx.get("payload") or {}).get("job_id") == job_id:
                tx_hash = tx.get("tx_hash")
                return str(tx_hash) if tx_hash is not None else None
    return None


async def _lookup_chain_lock(blockchain_rpc_url: str, client: AsyncAITBCHTTPClient, job_id: str) -> str | None:
    """Return the on-chain ESCROW_LOCK tx hash for job_id, if one exists.

    Raises on transport or non-2xx responses so callers do not mistake
    "could not tell" for "does not exist".
    """
    # /rpc/transactions returns a list, so use the union-returning accessor.
    txs = await client.get_json(f"{blockchain_rpc_url}/rpc/transactions?transaction_type=ESCROW_LOCK&job_id={job_id}&limit=10")
    if isinstance(txs, list):
        for tx in txs:
            if (tx.get("payload") or {}).get("job_id") == job_id:
                tx_hash = tx.get("tx_hash")
                return str(tx_hash) if tx_hash is not None else None
    return None


async def _lookup_escrow_record(blockchain_rpc_url: str, client: AsyncAITBCHTTPClient, job_id: str) -> dict[str, Any] | None:
    """Return the node's escrow record for job_id, or None on a definitive 404.

    Raises on transport or any other non-2xx so callers do not mistake
    "could not tell" for "does not exist". The /escrow/create route writes
    this row synchronously when it submits the lock, so a hit covers a lock
    that is still pending in the mempool, not only a sealed one.
    """
    try:
        return await client.get(f"{blockchain_rpc_url}/rpc/escrow/{job_id}")
    except _OPS_ERRORS as e:
        status_error = _find_http_status_error(e)
        if status_error is not None and status_error.response.status_code == 404:
            return None
        raise


_SETTLED_ESCROW_STATES = frozenset({"released", "refunded"})


def _escrow_record_is_settled(record: dict[str, Any]) -> bool:
    """True when the node's escrow record is already settled either way.

    Checks the settlement timestamps the GET exposes as well as the
    state/status strings, so a record settled by either path is caught.
    """
    if record.get("released_at") or record.get("refunded_at"):
        return True
    state = str(record.get("state") or "").lower()
    status = str(record.get("status") or "").lower()
    return state in _SETTLED_ESCROW_STATES or status in _SETTLED_ESCROW_STATES


def _find_http_status_error(exc: BaseException) -> httpx.HTTPStatusError | None:
    """Unwrap the chained exception to find the HTTP refusal, if any.

    AsyncAITBCHTTPClient maps every httpx failure to NetworkError with the
    original as ``__cause__``; a walk over cause/context recovers the status
    code without trusting the wrapped message text.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, httpx.HTTPStatusError):
            return cur
        cur = cur.__cause__ or cur.__context__
    return None


# The settlement node refuses ESCROW_REFUND/ESCROW_RELEASE with a 502 whose
# upstream detail names the payer: "insufficient balance for sender '0x…'"
# (#2327 ran ~2h unnoticed because it logged as a generic sweep error). Both
# fragments are required so a bare "insufficient balance" about the escrow
# itself is not misread as a settlement-wallet top-up signal.
_UNDERFUNDED_BALANCE_MARKERS = ("insufficient balance", "for sender")


def _exception_texts(exc: BaseException) -> list[str]:
    """Collect the human-readable texts along an exception's cause chain.

    Covers ``str(exc)``, an HTTPException's ``detail``, and the ``detail``
    field of a JSON body on any httpx.HTTPStatusError in the chain -- the
    three shapes the settlement refusal reaches callers in.
    """
    texts: list[str] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        rendered = str(cur)
        if rendered:
            texts.append(rendered)
        detail = getattr(cur, "detail", None)
        if isinstance(detail, str) and detail:
            texts.append(detail)
        if isinstance(cur, httpx.HTTPStatusError):
            try:
                body = cur.response.json()
            except ValueError:
                body = None
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                texts.append(body["detail"])
        cur = cur.__cause__ or cur.__context__
    return texts


def _is_settlement_underfunded(exc: BaseException) -> bool:
    """True when the refusal is the settlement wallet lacking funds to pay.

    Matches the node's ``insufficient balance for sender '0x…'`` signature in
    whichever layer carries it: the service's HTTPException detail, a raw
    httpx status error under a NetworkError, or the wrapped message text.
    """
    return any(all(marker in text.lower() for marker in _UNDERFUNDED_BALANCE_MARKERS) for text in _exception_texts(exc))


def _escrow_failure_reason(exc: BaseException) -> tuple[str, str]:
    """Classify an escrow-POST failure and return (kind, buyer-safe detail).

    A node 4xx is a permanent refusal -- its ``detail`` is a domain message
    (stale rate, binding mismatch) and safe to surface. Anything else
    (timeouts, connect errors, 5xx, ambiguous post-send failures) is
    retryable and reported generically so no internal URL or traceback leaks
    into what the buyer sees.
    """
    status_error = _find_http_status_error(exc)
    if status_error is not None and 400 <= status_error.response.status_code < 500:
        detail: object = None
        try:
            body = status_error.response.json()
            if isinstance(body, dict):
                detail = body.get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, str) and detail:
            return "refused", detail[:200]
        return "refused", f"the node refused the escrow (HTTP {status_error.response.status_code})"
    return "unavailable", "the escrow funding request could not reach the node; the purchase can be retried"


def _tee_attests_computation(receipt: dict[str, Any] | None, job: Job | None) -> bool:
    """Return True when a registered TEE quote attests a model with no Groth16 circuit.

    Groth16 remains mandatory for registered circuits such as ``linear-1``. A
    TEE quote is only a substitute when the model cannot be proven in-circuit.
    """
    if not receipt or job is None:
        return False
    if receipt.get("tee_status") != "verified":
        return False
    if receipt.get("zk_status") != "tee_attested":
        return False
    if receipt.get("computation_correct") is not True:
        return False
    model_id = model_registry.resolve_model_id(job, job.result if isinstance(job.result, dict) else None)
    return model_id is not None and model_registry.get_model(model_id) is None


def _computation_is_correct(receipt: dict[str, Any] | None, job: Job | None) -> bool:
    """Return True when escrow may release because computation was attested."""
    if not receipt:
        return False
    if receipt.get("computation_correct") is not True:
        return False
    zk_status = receipt.get("zk_status")
    if zk_status in ("verified", "not_required", "tee_attested"):
        return True
    return _tee_attests_computation(receipt, job)


def get_receipt_of_record(session: Session, job: Job | None) -> dict[str, Any] | None:
    """Return the canonical receipt for a job, or None when it has none.

    Prefer the ``JobReceipt`` row (indexed by ``job.receipt_id``) because it is the
    authoritative, signed record. The denormalised ``Job.receipt`` JSON is a
    fallback only when ``receipt_id`` is set (the coordinator signed a receipt and
    wrote the copy itself). A job without ``receipt_id`` has no receipt of record:
    its ``Job.receipt`` may be the miner's own ``complete`` body, and the release
    gates (:func:`_computation_is_correct`) must never trust verdict fields a
    miner wrote (SEC-20).
    """
    if job is None or not job.receipt_id:
        return None
    row = session.execute(select(JobReceipt).where(JobReceipt.receipt_id == job.receipt_id)).scalars().first()
    if row and row.payload:
        payload: dict[str, Any] = row.payload
        return payload
    return job.receipt if job.receipt else None


def _fail_evm_payment(payment: JobPayment, detail: str) -> None:
    payment.status = "failed"
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _validate_evm_receipt_target(
    payment: JobPayment,
    quote: EnergyQuote,
    receipt: dict[str, Any],
) -> str:
    """Check receipt.to and chainId; return lowercased expected contract address."""
    to_addr = (receipt.get("to") or "").lower()
    expected_contract = (quote.evm_contract or "").lower()
    if expected_contract and to_addr != expected_contract:
        _fail_evm_payment(payment, f"EVM tx sent to {to_addr}, expected {expected_contract}")
    chain_id = int(receipt.get("chainId", 0))
    if quote.evm_chain_id and chain_id != quote.evm_chain_id:
        _fail_evm_payment(
            payment,
            f"EVM tx chain {chain_id} does not match quote chain {quote.evm_chain_id}",
        )
    return expected_contract


def _bind_evm_agreement_or_fail(
    payment: JobPayment,
    payment_data: JobPaymentCreate,
    quote: EnergyQuote,
    receipt: dict[str, Any],
    expected_contract: str,
) -> None:
    claimed_agreement = payment_data.evm_agreement_id
    if claimed_agreement is None:
        _fail_evm_payment(payment, "EVM protected payment requires evm_agreement_id to bind the receipt")
    contract = expected_contract or (quote.evm_contract or "")
    log_entries = receipt.get("log_entries") or []
    observed_agreement = agreement_id_from_receipt_logs(log_entries, contract)
    if observed_agreement is None:
        _fail_evm_payment(payment, "EVM receipt has no AgreementStarted log for the rental contract")
    if observed_agreement != claimed_agreement:
        _fail_evm_payment(
            payment,
            (f"EVM receipt agreementId {observed_agreement} does not match claimed evm_agreement_id {claimed_agreement}"),
        )
