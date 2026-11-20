"""
GPU market endpoints backed by persistent SQLModel tables.

Facade for the ``market_gpu_*`` split: this module keeps the shared helpers,
request models, singletons, the energy-quote builders, the quote endpoint and
the misc market endpoints, wires the sibling routers in, and re-exports every
name tests/imports resolve through
``coordinator_api.contexts.market.routers.market_gpu``. Sibling modules are
not meant to be imported directly (same contract as ``escrow_routes_*``).
"""

import asyncio
import statistics
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session, col, select, update
from web3.exceptions import Web3Exception

from aitbc.aitbc_logging import get_logger
from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient
from aitbc.exceptions import AITBCError
from aitbc.market.energy_oracle import EVMEnergyOracle
from aitbc.market.evm_rental_receipt import agreement_id_from_receipt_logs
from aitbc.market.energy_pricing import (
    DEFAULT_FEE_BASIS_POINTS,
    EnergyPricingError,
    EnergyQuote,
    NATIVE_UNITS_PER_AIT,
    SettlementRoute,
    build_minimum_quote,
)
from aitbc.utils.chain_id import resolve_chain_id
from aitbc.utils.units import ait_to_units, units_to_ait
from aitbc.rate_limiting import rate_limit
from aitbc_shared import JobPayment

from ....auth import AuthDep
from ....custom_types import Constraints
from ....validators import validate_ethereum_address
from ....schemas import JobCreate, brand_symbol

from ...payments.acceptance import REFUNDABLE_STATES
from ...trading.services.market_data_collector import MarketDataCollector
from ....config import settings
from ....storage.db import get_session
from ...trading.services.trading_market.dynamic_pricing import (
    DynamicPricingEngine,
    PricingStrategy,
    ResourceType,
)
from ...infrastructure.services.jobs import JobService
from ...infrastructure.domain.job import Job
from ...infrastructure.domain.user import Wallet
from ..domain.gpu_market import GPUBooking, GPURegistry
from ..services.native_energy import NativeEnergyOracle

logger = get_logger(__name__)

# Expected failure surface for the best-effort fallbacks and error-translate
# handlers below: session/DB errors (sqlmodel -> SQLAlchemyError), outbound
# HTTP/RPC I/O (httpx via the energy oracle and payment rails), energy-pricing
# domain errors, Decimal parsing, lazy imports, and data-shape/runtime errors.
# HTTPException is not in the tuple, so it propagates to the client untouched (#1863).
_OPS_ERRORS: tuple[type[BaseException], ...] = (
    AITBCError,
    ArithmeticError,
    AttributeError,
    EnergyPricingError,
    ImportError,
    InvalidOperation,
    KeyError,
    OSError,
    RuntimeError,
    SQLAlchemyError,
    TypeError,
    ValueError,
    Web3Exception,
    httpx.HTTPError,
)

router = APIRouter(tags=["market-gpu"])
pricing_engine = None
market_collector = None
# Serialize lazy singleton init: two racing first requests must not each
# construct + initialize (MarketDataCollector.initialize spawns ~10 loops and
# binds a WebSocket port — a loser instance would orphan its loops).
_singleton_init_lock = asyncio.Lock()


def _cas_book_gpu(session: Session, gpu_id: str) -> bool:
    """#1836: predicate-guarded available->booked CAS.

    ``with_for_update()`` is silently dropped on the default sqlite adapter,
    so the row lock cannot serialize concurrent bookings there — the status
    predicate in WHERE is the real arbiter on every adapter."""
    result = session.execute(
        update(GPURegistry)
        .where(col(GPURegistry.id) == gpu_id, col(GPURegistry.status) == "available")
        .values(status="booked")
        .execution_options(synchronize_session=False)
    )
    return getattr(result, "rowcount", 0) == 1


async def get_pricing_engine() -> DynamicPricingEngine:
    """Get pricing engine instance"""
    global pricing_engine
    if pricing_engine is None:
        async with _singleton_init_lock:
            if pricing_engine is None:
                pricing_engine = DynamicPricingEngine(
                    {
                        "min_price": Decimal("0.001"),
                        "max_price": Decimal("1000"),
                        "update_interval": 300,
                        "forecast_horizon": 72,
                    }
                )
                await pricing_engine.initialize()
    return pricing_engine


async def get_market_collector() -> MarketDataCollector:
    """Get market data collector instance"""
    global market_collector
    if market_collector is None:
        async with _singleton_init_lock:
            if market_collector is None:
                market_collector = MarketDataCollector({"websocket_port": 8765})
                await market_collector.initialize()
    return market_collector


class GPURegisterRequest(BaseModel):
    miner_id: str
    model: str
    model_id: str | None = None
    memory_gb: int
    cuda_version: str
    region: str
    price_per_hour: Decimal
    capabilities: list[str] = []
    resource_id: str | None = None
    protected: bool = False


class GPUBookRequest(BaseModel):
    # #1931: same bounds/finite checks as GPUBuyRequest (#1923/F13) — a
    # plain float let NaN/inf reach timedelta/Decimal math downstream.
    duration_hours: float = Field(ge=0.0167, le=8760, allow_inf_nan=False)
    job_id: str | None = None


class GPUConfirmRequest(BaseModel):
    client_id: str | None = None


class OllamaTaskRequest(BaseModel):
    gpu_id: str
    model: str = "llama2"
    prompt: str
    parameters: dict[str, Any] = {}


class GPUBuyRequest(BaseModel):
    buyer_id: str
    gpu_id: str
    # #1923 (F13): same bounds/finite checks as GPUQuoteRequest — an
    # unbounded float let NaN/inf/negative durations reach timedelta and
    # Decimal math downstream.
    duration_hours: float = Field(ge=0.0167, le=8760, allow_inf_nan=False)
    payment_method: str = "blockchain"
    job_id: str | None = None
    energy_quote: dict[str, Any] | None = None
    protected: bool = False
    # Native ESCROW_LOCK buyer signature data. When the CLI signs the lock
    # locally, it forwards these fields so the coordinator can create the
    # on-chain escrow without signing on the buyer's behalf.
    buyer_address: str | None = None
    provider_address: str | None = None
    buyer_lock_signature: str | None = None
    buyer_lock_nonce: int | None = None
    buyer_lock_fee: int | None = None

    @model_validator(mode="after")
    def _lock_signature_needs_nonce(self):
        # ESCROW-LOCK-NONCE-1 (#807): a signature is over a concrete nonce; without it the
        # coordinator would guess the account nonce and the buyer's signature never verifies.
        if self.buyer_lock_signature and self.buyer_lock_nonce is None:
            raise ValueError("buyer_lock_nonce is required when buyer_lock_signature is given")
        return self

    # EVM settlement data. When the buyer funds the rental directly on-chain,
    # the CLI forwards the confirmed transaction hash and agreement/escrow id
    # so the coordinator can verify and record the protected rental.
    evm_tx_hash: str | None = None
    evm_agreement_id: int | None = None
    evm_escrow_id: int | None = None
    settlement_route: str | None = None
    buyer_agent_id: str | None = Field(default=None, max_length=128)
    provider_agent_id: str | None = Field(default=None, max_length=128)


class GPUQuoteRequest(BaseModel):
    buyer_id: str
    buyer_agent_id: str | None = Field(default=None, max_length=128)
    gpu_id: str
    duration_hours: float = Field(default=1.0, ge=0.0167, le=8760)
    gpu_count: int = Field(default=1, ge=1, le=10000)
    buyer_max_amount: Decimal | None = None
    payload: dict[str, Any] | None = None
    settlement_route: str = Field(default="native", description="Settlement rail: 'native' or 'evm'")


class GPUSellRequest(BaseModel):
    seller_id: str
    gpu_id: str
    listing_price: Decimal
    description: str | None = ""


class PaymentRequest(BaseModel):
    from_wallet: str
    to_wallet: str
    amount: Decimal = Field(gt=Decimal("0"))
    booking_id: str | None = None
    task_id: str | None = None

    @field_validator("from_wallet", "to_wallet")
    @classmethod
    def validate_wallet_address(cls, v: str) -> str:
        return validate_ethereum_address(v)


class GPUReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str


# CE-004: book_gpu creates a GPU hold with no payment attached, which let any
# caller squat every listing indefinitely (gpu.status="booked" blocks the paid
# buy/quote paths). The hold is now client-bound at creation and expires
# lazily once it outlives BOOKING_HOLD_TTL without a funded payment recorded
# against the booking.
BOOKING_HOLD_TTL = timedelta(minutes=30)
# JobPayment states where money is committed or has moved — a booking bound to
# one must never be TTL-expired (#1924). REFUNDABLE_STATES covers the live
# escrow set (escrowed/pending_acceptance/disputed/settlement_failed); released
# and confirmed are kept from the original tuple as post-settlement states.
_PAID_PAYMENT_STATUSES = tuple(sorted(REFUNDABLE_STATES | {"released", "confirmed"}))
# #1930/#1974: "pending" payments are unverified — an EVM receipt that never
# mined (or no RPC to check it) leaves the row pending forever with no
# reaper, so shielding on the status alone let a made-up evm_tx_hash squat a
# GPU at zero cost. A pending payment shields the hold only while ALL of
# these hold: the recorded tx has a successful on-chain receipt AND that
# receipt binds to this payment's contract/chain/agreement (a bare successful
# hash is not enough — any cheap unrelated tx would otherwise pin the GPU),
# and the payment is younger than _PENDING_SHIELD_TTL so the shield stays
# bounded. Everything else expires by TTL like unpaid work.
_PENDING_SHIELD_TTL = timedelta(hours=24)
# "skipped" is terminal no-money (escrow unavailable) and does not protect.
# JobPayment states where no live *verified* money remains — pending is
# included because it is unverified, not committed: a pending EVM receipt
# that later confirms is an operator-visible payment anomaly, not a reason
# to hold the GPU hostage (#1974, owner/admin may release pending holds).
_RELEASE_SAFE_PAYMENT_STATUSES = frozenset({"released", "refunded", "failed", "pending"})


def _pending_payment_mined(payment: JobPayment) -> bool:
    """True only when a pending payment's recorded EVM tx has a successful
    receipt bound to THIS payment's contract/chain/agreement (#1974).

    Mirrors the creation-time binding in ``payments._verify_evm_receipt``:
    receipt ``to`` must equal the recorded ``evm_contract``, ``chainId`` the
    recorded ``evm_chain_id``, and the receipt's AgreementStarted log must
    carry the recorded ``evm_agreement_id``. Any missing piece fails closed —
    a bare successful tx hash proves nothing about this payment. Runs a
    synchronous Web3 call, so async callers must invoke it via
    ``run_in_threadpool``.
    """
    meta = payment.meta_data or {}
    tx_hash = meta.get("evm_tx_hash")
    contract = str(meta.get("evm_contract") or "").lower()
    chain_id = meta.get("evm_chain_id")
    agreement_id = meta.get("evm_agreement_id")
    rpc_url = settings.eth_rpc_url
    if not rpc_url or not tx_hash or not contract or chain_id is None or agreement_id is None:
        return False
    try:
        rpc = EthereumRPCClient(EthereumConfig(rpc_url=rpc_url, network=str(settings.energy_pricing_chain_id)))
        receipt = rpc.get_transaction_receipt(str(tx_hash))
        if receipt is None or int(receipt.get("status", 0)) != 1:
            return False
        if str(receipt.get("to") or "").lower() != contract:
            return False
        if int(receipt.get("chainId", 0)) != int(chain_id):
            return False
        observed = agreement_id_from_receipt_logs(receipt.get("log_entries") or [], contract)
        return observed is not None and int(observed) == int(agreement_id)
    except _OPS_ERRORS:
        return False


def _payment_shields_hold(session: Session, booking: GPUBooking) -> bool:
    """True when the booking's bound payment still protects the hold.

    Paid/committed states always shield. A pending payment shields only
    inside ``_PENDING_SHIELD_TTL`` and only when ``_pending_payment_mined``
    re-proves the receipt binds to this payment — real money in flight must
    not lose its GPU, but an unverified or foreign hash never pins one.
    """
    payment = (
        session.execute(
            select(JobPayment)
            .join(Job, col(Job.id) == JobPayment.job_id)
            .where(
                col(JobPayment.id) == booking.payment_id,
                col(Job.client_id) == booking.client_id,
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    if payment is None:
        return False
    if payment.status in _PAID_PAYMENT_STATUSES:
        return True
    if payment.status != "pending" or payment.created_at is None:
        return False
    paid_at = payment.created_at
    if paid_at.tzinfo is None:
        paid_at = paid_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - paid_at < _PENDING_SHIELD_TTL and _pending_payment_mined(payment)


def _expire_stale_booking(session: Session, gpu: GPURegistry) -> None:
    """Expire an unpaid booking hold past its TTL so the GPU becomes available.

    Lazy reaper: runs on the write paths that gate on ``gpu.status``, so a
    squatted listing frees itself the next time anyone tries to use it.
    """
    if gpu.status != "booked":
        return
    booking = (
        session.execute(select(GPUBooking).where(GPUBooking.gpu_id == gpu.id, GPUBooking.status == "active").limit(1))
        .scalars()
        .first()
    )
    if booking is None or booking.created_at is None:
        return
    created_at = booking.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - created_at < BOOKING_HOLD_TTL:
        return
    # The funded check keys ONLY on the payment bound to this booking
    # (#1199, tightened by #1231, corrected by #1923/F12): purchase-path
    # bookings carry booking.payment_id — the JobPayment created for THAT
    # booking — because job_id is shared across sibling bookings on one
    # prepared job, and a job-level join would let one paid payment
    # protect every unpaid sibling. Holds created by book_gpu carry no
    # payment_id and NO payment is ever bound to them, so they expire
    # strictly by TTL: the old job-linkage fallback let one paid purchase
    # pin unlimited squatting holds that all named the same job_id.
    # #1930 audit: booking.payment_id is bound in exactly one place — the
    # purchase path at booking creation — and no flow attaches a payment to
    # an existing hold afterwards, so no legitimate paid flow depends on
    # job linkage; book_gpu holds are paymentless by design.
    if booking.payment_id and _payment_shields_hold(session, booking):
        return
    booking.status = "expired"
    gpu.status = "available"
    session.add(booking)
    session.add(gpu)
    session.commit()


def _get_energy_oracle(session: Session) -> NativeEnergyOracle | EVMEnergyOracle | None:
    """Return a native or EVM energy oracle depending on configuration."""
    if settings.native_energy_pricing:
        return NativeEnergyOracle(session)
    contract = settings.energy_pricing_contract_address
    rpc_url = settings.eth_rpc_url
    if not contract or not rpc_url:
        return None
    rpc = EthereumRPCClient(EthereumConfig(rpc_url=rpc_url, network=str(settings.energy_pricing_chain_id)))
    return EVMEnergyOracle(rpc, contract, settings.energy_pricing_chain_id)


def _quote_buyer_payment_address(session: Session, request: GPUQuoteRequest) -> str:
    """Payment address embedded in the energy quote (may differ from client buyer_id)."""
    from ...payments.services.escrow_agent_binding import (
        default_resolve_chain_id,
        resolve_agent_payment_address_sync,
    )

    if not request.buyer_agent_id:
        return request.buyer_id
    resolved = resolve_agent_payment_address_sync(session, request.buyer_agent_id, default_resolve_chain_id())
    from aitbc.crypto.signature_recovery import canonical_address

    if request.buyer_id.startswith("0x"):
        if canonical_address(request.buyer_id) != resolved:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"buyer_id does not match resolved address for agent {request.buyer_agent_id}",
            )
    return resolved


def _build_energy_quote(
    session: Session,
    gpu: GPURegistry,
    buyer: str,
    job_id: str,
    duration_hours: float,
    gpu_count: int,
    buyer_cap_units: int | None = None,
    settlement_route: SettlementRoute = SettlementRoute.NATIVE,
    settlement_unit_scale: int = NATIVE_UNITS_PER_AIT,
) -> dict[str, Any]:
    """Build a signed minimum energy quote for a fixed-duration GPU rental.

    Falls back to an informative error dict if the energy oracle is unconfigured.
    The quote is signed by the coordinator operator when ``energy_operator_key``
    is configured; otherwise it is returned unsigned (legacy behaviour) so the
    CLI can detect the missing attestation and refuse to fund.
    """
    oracle = _get_energy_oracle(session)
    if oracle is None:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Energy pricing oracle is not configured",
        )
    if not gpu.resource_id:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"GPU {gpu.id} has no canonical resource_id",
        )
    try:
        profile = oracle.get_profile(gpu.resource_id)
        rate = oracle.get_rate()
    except _OPS_ERRORS as exc:
        logger.error("Failed to read energy inputs for %s: %s", gpu.resource_id, exc)
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not read energy inputs; refusing protected funding",
        ) from exc

    duration_seconds = int(duration_hours * 3600)
    if duration_seconds <= 0:
        duration_seconds = 3600

    # Pin the EVM block for provenance when reading from an EVM oracle so the
    # quote carries the exact inputs the operator attested to.
    evm_block_number = None
    evm_block_hash = None
    if settlement_route == SettlementRoute.EVM and isinstance(oracle, EVMEnergyOracle):
        try:
            block = oracle.rpc.get_block("latest")
            evm_block_number = int(block["number"])
            evm_block_hash = block["hash"]
        except _OPS_ERRORS as exc:
            logger.warning("Could not pin EVM block for energy quote: %s", exc)

    quote = build_minimum_quote(
        profile=profile,
        rate=rate,
        buyer=buyer,
        job_id=job_id,
        quote_id=uuid4().hex,
        domain=settings.energy_quote_domain,
        chain_id=settings.native_chain_id or resolve_chain_id(),
        settlement_asset="AITBC",
        settlement_unit_scale=settlement_unit_scale,
        settlement_route=settlement_route,
        gpu_count=gpu_count,
        duration_seconds=duration_seconds,
        buyer_cap_units=buyer_cap_units,
        fee_basis_points=DEFAULT_FEE_BASIS_POINTS,
        quote_lifetime_seconds=settings.energy_quote_lifetime_seconds,
        evm_chain_id=settings.energy_pricing_chain_id,
        evm_contract=settings.energy_pricing_contract_address,
        evm_block_number=evm_block_number,
        evm_block_hash=evm_block_hash,
        operator_address=settings.energy_operator_address,
    )

    # Sign the quote with the operator key when configured. The signature is
    # produced over the SHA-256 digest of the canonical quote JSON, matching
    # ``EnergyQuote.verify_operator_signature`` on the CLI side.
    operator_key = settings.energy_operator_key
    if operator_key is not None and settings.energy_operator_address:
        from aitbc.crypto.crypto import sign_transaction_hash

        try:
            signature_hex = sign_transaction_hash(
                "0x" + quote.digest_sha256().hex(),
                operator_key.get_secret_value(),
            )
            quote = quote.with_operator_signature(
                operator_address=settings.energy_operator_address,
                operator_signature=bytes.fromhex(signature_hex.removeprefix("0x")),
            )
        except _OPS_ERRORS as exc:
            logger.error("Failed to sign energy quote: %s", exc)
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to sign energy quote",
            ) from exc
    return quote.to_dict(include_signature=True)


# The pricing steps moved into _price_quote_job (#2000), two calls below the handler, which is
# deeper than the OpenAPI error scan descends; declare what _build_energy_quote can raise.
_QUOTE_ERROR_BODY = {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}
_QUOTE_PRICING_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {
        "description": "buyer_id does not match resolved address for agent {request.buyer_agent_id}",
        "content": _QUOTE_ERROR_BODY,
    },
    500: {"description": "Failed to sign energy quote", "content": _QUOTE_ERROR_BODY},
    503: {
        "description": ("Energy pricing oracle is not configured / Could not read energy inputs; refusing protected funding"),
        "content": _QUOTE_ERROR_BODY,
    },
}


def _authenticated_client_id(session: Session, sub: str, buyer_id: str) -> str:
    """Return the caller's client id if ``buyer_id`` is theirs, else raise 403.

    ``buyer_id`` is the caller's own id (``sub``) or a wallet address linked to
    that user (#2298). A wallet-login JWT carries a user UUID as ``sub`` while
    the native rail binds the quote's buyer to the paying wallet address, so
    the address must be accepted when this user owns it. The quote's job stays
    keyed by the client id; the address only becomes the quote's buyer field.
    """
    if buyer_id == sub:
        return sub
    if buyer_id.startswith("0x"):
        wallet = session.execute(select(Wallet).where(col(Wallet.address) == buyer_id.lower())).scalars().first()
        if wallet is not None and wallet.user_id == sub:
            return sub
    raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="buyer_id does not match authenticated buyer")


@router.post("/market/gpu/quote", responses=_QUOTE_PRICING_ERRORS)
@rate_limit(rate=30, per=60)
def quote_gpu(
    request: GPUQuoteRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    *,
    http_request: Request,
) -> dict[str, Any]:
    """Prepare an unsigned energy quote and a bound job for a fixed-duration GPU rental.

    The returned quote is valid for a short window. The buyer funds it through
    POST /market/gpu/purchase using the same job_id and energy_quote.
    """
    # #1848: quoting creates a Job row and can return an operator signature —
    # the buyer must be the caller, same binding as purchase (#1075).
    client_id = _authenticated_client_id(session, user["sub"], request.buyer_id)
    gpu = _get_gpu_or_404(session, request.gpu_id)
    _expire_stale_booking(session, gpu)
    if gpu.status != "available":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {request.gpu_id} is not available for quoting",
        )

    duration_seconds = max(1, int(request.duration_hours * 3600))
    job_service = JobService(session)
    job_create = JobCreate(
        payload={
            "type": "gpu_compute",
            "gpu_id": request.gpu_id,
            "task": "general_compute",
            "duration_hours": request.duration_hours,
            "gpu_count": request.gpu_count,
            "protected": True,
            **(request.payload or {}),
        },
        constraints=Constraints(
            gpu=gpu.model,
            region=gpu.region,
            min_vram_gb=None,
        ),
        ttl_seconds=duration_seconds + settings.energy_quote_lifetime_seconds + 60,
    )
    # #2000: the job is created NON-DISPATCHABLE (payment hold) and committed
    # before the quote is priced, because the quote needs its id. If anything
    # after that fails the job is cancelled, so no failure path (and no race
    # with a polling miner) can leave an unpriced dispatchable gpu_compute job.
    job = job_service.create_job(client_id=client_id, req=job_create, enforce_inflight_cap=True, payment_hold=True)
    try:
        return _price_quote_job(session, job, gpu, request, duration_seconds)
    except BaseException:
        _cancel_failed_quote_job(session, job_service, job)
        raise


def _cancel_failed_quote_job(session: Session, job_service: JobService, job: Job) -> None:
    """Cancel a quote's job after a post-create failure (#2000); never raises."""
    job_id = job.id
    try:
        session.rollback()
        job_service.cancel_job(job)
    except Exception:  # noqa: BLE001 - cleanup must not mask the original failure
        logger.exception("Could not cancel quote job %s after a failed quote", job_id)


def _price_quote_job(
    session: Session, job: Job, gpu: GPURegistry, request: GPUQuoteRequest, duration_seconds: int
) -> dict[str, Any]:
    """Build, evaluate and bind the energy quote on the (held) quote job."""
    job.protected = True
    job.resource_id = gpu.resource_id
    job.model_id = gpu.model_id or gpu.model
    job.gpu_count = request.gpu_count
    job.duration_seconds = duration_seconds

    buyer_cap_units = None
    if request.buyer_max_amount is not None:
        buyer_cap_units = ait_to_units(request.buyer_max_amount)

    # Resolve the settlement rail and unit scale for this quote.
    try:
        settlement_route = SettlementRoute(request.settlement_route)
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid settlement_route: {request.settlement_route}",
        ) from None
    if settlement_route == SettlementRoute.EVM:
        from aitbc.market.energy_pricing import EVM_UNITS_PER_AIT

        settlement_unit_scale = EVM_UNITS_PER_AIT
    else:
        settlement_unit_scale = NATIVE_UNITS_PER_AIT

    quote_dict = _build_energy_quote(
        session=session,
        gpu=gpu,
        buyer=_quote_buyer_payment_address(session, request),
        job_id=job.id,
        duration_hours=request.duration_hours,
        gpu_count=request.gpu_count,
        buyer_cap_units=buyer_cap_units,
        settlement_route=settlement_route,
        settlement_unit_scale=settlement_unit_scale,
    )
    quote = EnergyQuote.from_dict(quote_dict)
    # Validate that the minimum quote fits under the buyer cap and current freshness.
    from aitbc.market.energy_pricing import evaluate_quote

    result = evaluate_quote(
        quote=quote,
        profile=quote.to_profile(),
        rate=quote.to_rate(),
        now=int(time.time()),
        hard_cap_units=buyer_cap_units,
        max_rate_age_seconds=settings.energy_max_rate_age_seconds,
    )
    if not result.approved:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Quote refused: {result.refusal_reason} ({result.refusal_code})",
        )

    # #2300: the purchase check compares quote.model_id (the energy profile's
    # slug, e.g. rtx_4060_ti_16gb) with job.model_id. When the registry row has
    # no model_id the job fell back to the raw GPU name and a valid GPU could
    # never be bought. The quote is the authority for the energy profile, so
    # bind the job to it.
    if quote.model_id:
        job.model_id = quote.model_id
    job.energy_quote_snapshot = quote.to_dict(include_signature=False)
    # G4: a quoted but unfunded job must not be handed to a miner. Mark it as
    # priced but unpaid so the dispatch gate refuses it until buy_gpu creates the
    # real payment and binds the escrow.
    if result.breakdown:
        job.payment_amount = units_to_ait(result.breakdown.buyer_charge_units)
        job.payment_token = brand_symbol
    session.add(job)
    session.commit()
    return {
        "job_id": job.id,
        "gpu_id": gpu.id,
        "resource_id": gpu.resource_id,
        "duration_hours": request.duration_hours,
        "gpu_count": request.gpu_count,
        "settlement_route": settlement_route.value,
        "energy_quote": quote_dict,
        "buyer_charge_ait": units_to_ait(result.breakdown.buyer_charge_units) if result.breakdown else None,
    }


@router.post("/payments/send")
@rate_limit(rate=20, per=60)
async def send_payment(
    request: PaymentRequest, session: Annotated[Session, Depends(get_session)], user: AuthDep, *, http_request: Request
) -> dict[str, Any]:
    """Record a real payment for a task or booking and return its actual status."""
    if request.amount <= 0:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero")
    if not request.task_id and not request.booking_id:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="task_id or booking_id is required")

    from ....contexts.payments.services.payments import PaymentService
    from ....schemas import JobPaymentCreate

    payment_service = PaymentService(session)
    payment_create = JobPaymentCreate(
        job_id=request.task_id or request.booking_id or f"manual_{uuid4().hex[:8]}",
        amount=request.amount,
        currency="AITBC",
        payment_method="aitbc_token",
        escrow_timeout_seconds=3600,
    )
    try:
        # V23-46: client_id was missing entirely (TypeError). The authenticated caller
        # is the payer, and _require_owned_job then verifies they own the job.
        payment = await payment_service.create_payment(
            client_id=user["sub"],
            job_id=payment_create.job_id,
            payment_data=payment_create,
        )
    except _OPS_ERRORS as e:
        logger.error("Payment failed for task %s: %s", request.task_id or request.booking_id, e)
        raise HTTPException(
            status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Payment failed: {e}",
        ) from e

    if payment.status in ("failed", "skipped"):
        raise HTTPException(
            status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Payment failed with status {payment.status}",
        )

    payment.meta_data = {
        "from_wallet": request.from_wallet,
        "to_wallet": request.to_wallet,
        "booking_id": request.booking_id,
        "task_id": request.task_id,
    }
    await run_in_threadpool(session.add, payment)
    await run_in_threadpool(session.commit)

    return {
        "tx_id": payment.id,
        "status": payment.status,
        "processed_at": payment.created_at.isoformat() + "Z",
        "from": request.from_wallet,
        "to": request.to_wallet,
        "amount": request.amount,
        "booking_id": request.booking_id,
        "task_id": request.task_id,
    }


@router.get("/market/orders")
def list_orders(
    session: Annotated[Session, Depends(get_session)],
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """List orders (bookings)."""
    stmt = select(GPUBooking)
    if status:
        stmt = stmt.where(GPUBooking.status == status)
    stmt = stmt.order_by(GPUBooking.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
    bookings = session.execute(stmt).scalars().all()

    # Batch-fetch all referenced GPUs in a single query to avoid N+1
    gpu_ids = {b.gpu_id for b in bookings if b.gpu_id}
    gpu_map: dict[str, GPURegistry] = {}
    if gpu_ids:
        gpus = session.execute(select(GPURegistry).where(col(GPURegistry.id).in_(gpu_ids))).scalars().all()
        gpu_map = {g.id: g for g in gpus}

    orders = []
    for b in bookings:
        gpu = gpu_map.get(b.gpu_id)
        orders.append(
            {
                "order_id": b.id,
                "gpu_id": b.gpu_id,
                "gpu_model": gpu.model if gpu else "unknown",
                "miner_id": gpu.miner_id if gpu else "",
                "duration_hours": b.duration_hours,
                "total_cost": b.total_cost,
                "status": b.status,
                "created_at": b.start_time.isoformat() + "Z",
                "job_id": b.job_id,
            }
        )
    return orders


@router.get("/market/pricing/{model}")
async def get_pricing(
    model: str,
    session: Annotated[Session, Depends(get_session)],
    engine: Annotated[DynamicPricingEngine, Depends(get_pricing_engine)],
    collector: Annotated[MarketDataCollector, Depends(get_market_collector)],
) -> dict[str, Any]:
    """Get enhanced pricing information for a model with dynamic pricing."""
    all_gpus = await run_in_threadpool(lambda: session.execute(select(GPURegistry)).scalars().all())
    compatible = [g for g in all_gpus if model.lower() in g.model.lower()]
    if not compatible:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"No GPUs found for model {model}")
    static_prices = [g.price_per_hour for g in compatible]
    cheapest = min(compatible, key=lambda g: g.price_per_hour)
    dynamic_prices: list[dict[str, Any]] = []
    for gpu in compatible:
        try:
            dynamic_result = await engine.calculate_dynamic_price(
                resource_id=gpu.id,
                resource_type=ResourceType.GPU,
                base_price=gpu.price_per_hour,
                strategy=PricingStrategy.MARKET_BALANCE,
                region=gpu.region,
            )
            recommended = dynamic_result.recommended_price
            dynamic_prices.append(
                {
                    "gpu_id": gpu.id,
                    "static_price": gpu.price_per_hour,
                    "dynamic_price": recommended,
                    "price_change": recommended - gpu.price_per_hour,
                    "price_change_percent": (recommended - gpu.price_per_hour) / gpu.price_per_hour * 100,
                    "confidence": dynamic_result.confidence_score,
                    "trend": dynamic_result.price_trend.value,
                    "reasoning": dynamic_result.reasoning,
                }
            )
        except _OPS_ERRORS:
            dynamic_prices.append(
                {
                    "gpu_id": gpu.id,
                    "static_price": gpu.price_per_hour,
                    "dynamic_price": gpu.price_per_hour,
                    "price_change": Decimal("0"),
                    "price_change_percent": Decimal("0"),
                    "confidence": 0.5,
                    "trend": "unknown",
                    "reasoning": ["Dynamic pricing unavailable"],
                }
            )
    dynamic_price_values = [dp["dynamic_price"] for dp in dynamic_prices]
    avg_dynamic_price = sum(dynamic_price_values) / len(dynamic_price_values)
    best_value_gpu = min(
        dynamic_prices, key=lambda x: x["dynamic_price"] / Decimal(str(x["confidence"])) if x["confidence"] else Decimal("1")
    )
    market_analysis = None
    try:
        regions = [gpu.region for gpu in compatible]
        most_common_region = max(set(regions), key=regions.count) if regions else "global"
        market_data = await collector.get_aggregated_data("gpu", most_common_region)
        if market_data:
            market_analysis = {
                "demand_level": market_data.demand_level,
                "supply_level": market_data.supply_level,
                "market_volatility": market_data.price_volatility,
                "utilization_rate": market_data.utilization_rate,
                "market_sentiment": market_data.market_sentiment,
                "confidence_score": market_data.confidence_score,
            }
    except _OPS_ERRORS:
        market_analysis = None
    # #1373: zero-priced listings make the static average 0 — the percent
    # change denominator must be guarded.
    avg_static_price = sum(static_prices) / len(static_prices)
    return {
        "model": model,
        "static_pricing": {
            "min_price": min(static_prices),
            "max_price": max(static_prices),
            "average_price": sum(static_prices) / len(static_prices),
            "available_gpus": len([g for g in compatible if g.status == "available"]),
            "total_gpus": len(compatible),
            "recommended_gpu": cheapest.id,
        },
        "dynamic_pricing": {
            "min_price": min(dynamic_price_values),
            "max_price": max(dynamic_price_values),
            "average_price": avg_dynamic_price,
            "price_volatility": statistics.stdev([float(p) for p in dynamic_price_values])
            if len(dynamic_price_values) > 1
            else 0,
            "avg_confidence": sum(dp["confidence"] for dp in dynamic_prices) / len(dynamic_prices),
            "recommended_gpu": best_value_gpu["gpu_id"],
            "recommended_price": best_value_gpu["dynamic_price"],
        },
        "price_comparison": {
            "avg_price_change": avg_dynamic_price - avg_static_price,
            "avg_price_change_percent": (
                (avg_dynamic_price - avg_static_price) / avg_static_price * 100 if avg_static_price != 0 else 0
            ),
            "gpus_with_price_increase": len([dp for dp in dynamic_prices if dp["price_change"] > 0]),
            "gpus_with_price_decrease": len([dp for dp in dynamic_prices if dp["price_change"] < 0]),
        },
        "individual_gpu_pricing": dynamic_prices,
        "market_analysis": market_analysis,
        "pricing_timestamp": datetime.now(UTC).isoformat() + "Z",
    }


# --- split siblings (imported last: they import facade names) -------------
from .market_gpu_energy import router as _energy_router
from .market_gpu_purchase import router as _purchase_router
from .market_gpu_registry import _get_gpu_or_404, router as _registry_router

router.include_router(_registry_router)
router.include_router(_purchase_router)
router.include_router(_energy_router)
