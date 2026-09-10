"\nGPU marketplace endpoints backed by persistent SQLModel tables.\n"

import statistics
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, col, func, select

from aitbc.aitbc_logging import get_logger
from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient
from aitbc.marketplace.energy_oracle import EVMEnergyOracle
from aitbc.marketplace.energy_pricing import (
    DEFAULT_FEE_BASIS_POINTS,
    EnergyQuote,
    NATIVE_UNITS_PER_AIT,
    SettlementRoute,
    build_minimum_quote,
)
from aitbc.utils.units import ait_to_units, units_to_ait

from ....auth import AuthDep, MinerDep
from ....custom_types import Constraints
from ....validators import validate_ethereum_address
from ....utils.client_resolver import resolve_client

from ...trading.services.market_data_collector import MarketDataCollector
from ....config import settings
from ....storage.db import get_session
from ...trading.services.trading_marketplace.dynamic_pricing import (
    DynamicPricingEngine,
    PricingStrategy,
    ResourceType,
)
from ...infrastructure.services.jobs import JobService
from ....schemas import JobCreate
from ...infrastructure.domain.job import Job
from ..domain.energy import NativeEnergyProfile, NativeEnergyRate
from ..domain.gpu_marketplace import GPUBooking, GPURegistry, GPUReview
from ..services.native_energy import NativeEnergyOracle
from ..services.ollama_queue import get_queue

logger = get_logger(__name__)
router = APIRouter(tags=["marketplace-gpu"])
pricing_engine = None
market_collector = None


async def get_pricing_engine() -> DynamicPricingEngine:
    """Get pricing engine instance"""
    global pricing_engine
    if pricing_engine is None:
        pricing_engine = DynamicPricingEngine(
            {"min_price": 0.001, "max_price": 1000.0, "update_interval": 300, "forecast_horizon": 72}
        )
        await pricing_engine.initialize()
    return pricing_engine


async def get_market_collector() -> MarketDataCollector:
    """Get market data collector instance"""
    global market_collector
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
    duration_hours: float
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
    duration_hours: float
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
    # EVM settlement data. When the buyer funds the rental directly on-chain,
    # the CLI forwards the confirmed transaction hash and agreement/escrow id
    # so the coordinator can verify and record the protected rental.
    evm_tx_hash: str | None = None
    evm_agreement_id: int | None = None
    evm_escrow_id: int | None = None
    settlement_route: str | None = None


class GPUQuoteRequest(BaseModel):
    buyer_id: str
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


def _gpu_to_dict(gpu: GPURegistry) -> dict[str, Any]:
    return {
        "id": gpu.id,
        "miner_id": gpu.miner_id,
        "model": gpu.model,
        "memory_gb": gpu.memory_gb,
        "cuda_version": gpu.cuda_version,
        "region": gpu.region,
        "price_per_hour": gpu.price_per_hour,
        "status": gpu.status,
        "capabilities": gpu.capabilities,
        "created_at": gpu.created_at.isoformat() + "Z",
        "average_rating": gpu.average_rating,
        "total_reviews": gpu.total_reviews,
    }


def _get_gpu_or_404(session: Session, gpu_id: str) -> GPURegistry:
    gpu = session.get(GPURegistry, gpu_id)
    if not gpu:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"GPU {gpu_id} not found")
    return gpu


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
    except Exception as exc:
        logger.error("Failed to read energy inputs for %s: %s", gpu.resource_id, exc)
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not read energy inputs: {exc}",
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
        except Exception as exc:
            logger.warning("Could not pin EVM block for energy quote: %s", exc)

    quote = build_minimum_quote(
        profile=profile,
        rate=rate,
        buyer=buyer,
        job_id=job_id,
        quote_id=uuid4().hex,
        domain=settings.energy_quote_domain,
        chain_id=settings.native_chain_id,
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
        except Exception as exc:
            logger.error("Failed to sign energy quote: %s", exc)
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to sign energy quote",
            ) from exc
    return quote.to_dict(include_signature=True)


@router.post("/marketplace/gpu/register")
async def register_gpu(
    request: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, Any]:
    """Register a GPU in the marketplace."""
    gpu_specs = request.get("gpu", {})
    import uuid
    from datetime import datetime

    gpu_id = f"gpu_{uuid.uuid4().hex[:8]}"
    miner_id = gpu_specs.get("miner_id") or gpu_specs.get("miner") or "default_miner"
    compute_capability = gpu_specs.get("compute_capability", "")
    cuda_version = compute_capability if compute_capability else ""
    price_per_hour = Decimal(str(gpu_specs.get("price_per_hour", "0.05")))
    gpu_record = GPURegistry(
        id=gpu_id,
        miner_id=miner_id,
        model=gpu_specs.get("name", "Unknown GPU"),
        model_id=gpu_specs.get("model_id"),
        memory_gb=gpu_specs.get("memory_gb", 0),
        cuda_version=cuda_version,
        region="default",
        price_per_hour=price_per_hour,
        status="available",
        capabilities=[],
        average_rating=0.0,
        total_reviews=0,
        created_at=datetime.now(UTC),
        resource_id=gpu_specs.get("resource_id"),
        protected=bool(gpu_specs.get("protected")),
    )
    session.add(gpu_record)
    session.commit()
    session.refresh(gpu_record)
    return {
        "gpu_id": gpu_id,
        "status": "registered",
        "message": f"GPU {gpu_specs.get('name', 'Unknown GPU')} registered successfully",
        "price_per_hour": price_per_hour,
    }


@router.get("/marketplace/gpu/list")
async def list_gpus(
    session: Annotated[Session, Depends(get_session)],
    available: bool | None = Query(default=None),
    price_max: Decimal | None = None,
    region: str | None = Query(default=None),
    model: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """List GPUs with optional filters."""
    stmt = select(GPURegistry)
    if available is not None:
        target_status = "available" if available else "booked"
        stmt = stmt.where(GPURegistry.status == target_status)
    if price_max is not None:
        stmt = stmt.where(GPURegistry.price_per_hour <= price_max)
    if region:
        stmt = stmt.where(func.lower(GPURegistry.region) == region.lower())
    if model:
        stmt = stmt.where(col(GPURegistry.model).contains(model))
    stmt = stmt.limit(limit)
    gpus = session.execute(stmt).scalars().all()
    return [_gpu_to_dict(g) for g in gpus]


@router.get("/marketplace/gpu/{gpu_id}")
async def get_gpu_details(gpu_id: str, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Get GPU details."""
    gpu = _get_gpu_or_404(session, gpu_id)
    result = _gpu_to_dict(gpu)
    if gpu.status == "booked":
        booking = (
            session.execute(select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active").limit(1))
            .scalars()
            .first()
        )
        if booking:
            result["current_booking"] = {
                "booking_id": booking.id,
                "duration_hours": booking.duration_hours,
                "total_cost": booking.total_cost,
                "start_time": booking.start_time.isoformat() + "Z",
                "end_time": booking.end_time.isoformat() + "Z" if booking.end_time else None,
            }
    return result


@router.post("/marketplace/gpu/quote")
async def quote_gpu(
    request: GPUQuoteRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Prepare an unsigned energy quote and a bound job for a fixed-duration GPU rental.

    The returned quote is valid for a short window. The buyer funds it through
    POST /marketplace/gpu/purchase using the same job_id and energy_quote.
    """
    gpu = _get_gpu_or_404(session, request.gpu_id)
    if gpu.status != "available":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {request.gpu_id} is not available for quoting",
        )

    duration_seconds = int(request.duration_hours * 3600)
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
            min_vram_gb=gpu.memory_gb if gpu.memory_gb else None,
        ),
        ttl_seconds=duration_seconds + settings.energy_quote_lifetime_seconds + 60,
    )
    job = job_service.create_job(client_id=request.buyer_id, req=job_create)
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
        from aitbc.marketplace.energy_pricing import EVM_UNITS_PER_AIT

        settlement_unit_scale = EVM_UNITS_PER_AIT
    else:
        settlement_unit_scale = NATIVE_UNITS_PER_AIT

    quote_dict = _build_energy_quote(
        session=session,
        gpu=gpu,
        buyer=request.buyer_id,
        job_id=job.id,
        duration_hours=request.duration_hours,
        gpu_count=request.gpu_count,
        buyer_cap_units=buyer_cap_units,
        settlement_route=settlement_route,
        settlement_unit_scale=settlement_unit_scale,
    )
    quote = EnergyQuote.from_dict(quote_dict)
    # Validate that the minimum quote fits under the buyer cap and current freshness.
    from aitbc.marketplace.energy_pricing import evaluate_quote

    result = evaluate_quote(
        quote=quote,
        profile=quote.to_profile(),
        rate=quote.to_rate(),
        now=int(time.time()),
        hard_cap_units=buyer_cap_units,
    )
    if not result.approved:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Quote refused: {result.refusal_reason} ({result.refusal_code})",
        )

    job.energy_quote_snapshot = quote.to_dict(include_signature=False)
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


@router.post("/marketplace/gpu/purchase")
async def buy_gpu(
    request: GPUBuyRequest,
    session: Annotated[Session, Depends(get_session)],
    engine: Annotated[DynamicPricingEngine, Depends(get_pricing_engine)],
    user: AuthDep,
) -> dict[str, Any]:
    """Buy GPU compute from marketplace with blockchain payment and AI job scheduling."""
    gpu = _get_gpu_or_404(session, request.gpu_id)
    if gpu.status != "available":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=f"GPU {request.gpu_id} is not available for purchase"
        )
    from datetime import datetime, timedelta

    start_time = datetime.now(UTC)
    duration_hours = request.duration_hours
    # E1: if the buyer supplied a signed energy quote, use its frozen terms.
    supplied_quote: EnergyQuote | None = None
    if request.energy_quote:
        try:
            supplied_quote = EnergyQuote.from_dict(request.energy_quote)
            duration_hours = supplied_quote.duration_seconds / 3600
        except Exception as exc:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid energy_quote: {exc}",
            ) from exc
    end_time = start_time + timedelta(hours=duration_hours)
    try:
        dynamic_result = await engine.calculate_dynamic_price(
            resource_id=gpu.id,
            resource_type=ResourceType.GPU,
            base_price=gpu.price_per_hour,
            strategy=PricingStrategy.MARKET_BALANCE,
            region=gpu.region,
        )
        current_price = dynamic_result.recommended_price
    except Exception:
        current_price = gpu.price_per_hour
    duration_dec = Decimal(str(duration_hours))
    total_cost = duration_dec * current_price
    if supplied_quote is not None:
        total_cost = units_to_ait(supplied_quote.principal_units)
    resolved_client_id, client_ref = resolve_client(session, request.buyer_id, auto_create=True)
    booking_id = str(uuid4())
    # E1: a supplied quote freezes the resource/model/count/duration.
    quote_resource_id = gpu.resource_id
    quote_model_id = gpu.model_id or gpu.model
    quote_gpu_count = 1
    quote_duration_seconds = int(duration_hours * 3600)
    if supplied_quote is not None:
        quote_resource_id = supplied_quote.resource_id
        quote_model_id = supplied_quote.model_id
        quote_gpu_count = supplied_quote.gpu_count
        quote_duration_seconds = supplied_quote.duration_seconds
    booking = GPUBooking(
        id=booking_id,
        gpu_id=request.gpu_id,
        client_id=resolved_client_id,
        client_ref=client_ref,
        job_id=f"purchase_{client_ref[:8]}",
        duration_hours=duration_hours,
        total_cost=total_cost,
        start_time=start_time,
        end_time=end_time,
        status="active",
        protected=(supplied_quote is not None) or request.protected or gpu.protected,
        resource_id=quote_resource_id,
        model_id=quote_model_id,
        gpu_count=quote_gpu_count,
        duration_seconds=quote_duration_seconds,
        energy_quote_snapshot=request.energy_quote,
    )
    gpu.status = "booked"
    session.add(booking)
    session.add(gpu)
    session.commit()
    session.refresh(gpu)
    session.refresh(booking)
    job_id = None
    payment_id = None
    payment_status = None
    try:
        from sqlmodel import Session as SQLModelSession

        from ....contexts.payments.services.payments import PaymentService
        from ....custom_types import Constraints
        from ....schemas import JobCreate, JobPaymentCreate
        from ...infrastructure.services.jobs import JobService

        job_session = SQLModelSession(bind=session.bind)
        job_service = JobService(job_session)
        if request.job_id:
            # E1: a prepared quote already created and bound the job.
            job = job_session.get(Job, request.job_id)
            if not job:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Prepared job {request.job_id} not found",
                )
            # E1: carry the frozen quote and binding fields from the prepared job.
            quote_snapshot = request.energy_quote or job.energy_quote_snapshot
            if quote_snapshot and job.energy_quote_snapshot:
                supplied = quote_snapshot.get("quote_id")
                stored = job.energy_quote_snapshot.get("quote_id")
                if supplied != stored:
                    raise HTTPException(
                        status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Energy quote does not match the prepared job",
                    )
            if quote_snapshot:
                try:
                    quote = EnergyQuote.from_dict(quote_snapshot)
                    booking.protected = True
                    booking.total_cost = units_to_ait(quote.principal_units)
                    booking.energy_quote_snapshot = quote.to_dict(include_signature=False)
                    booking.duration_seconds = quote.duration_seconds
                    booking.duration_hours = quote.duration_seconds / 3600
                    booking.gpu_count = quote.gpu_count
                    booking.resource_id = quote.resource_id
                    booking.model_id = quote.model_id
                except Exception as exc:
                    raise HTTPException(
                        status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Invalid energy quote for prepared job: {exc}",
                    ) from exc
            else:
                booking.protected = job.protected
            booking.job_id = job.id
            job_id = job.id
            total_cost = booking.total_cost
            duration_hours = booking.duration_hours
            duration_dec = Decimal(str(duration_hours))
            end_time = start_time + timedelta(seconds=booking.duration_seconds or 0)
        else:
            job_create = JobCreate(
                payload={
                    "type": "gpu_compute",
                    "gpu_id": request.gpu_id,
                    "task": "general_compute",
                    "duration_hours": duration_hours,
                    "gpu_count": quote_gpu_count,
                },
                constraints=Constraints(
                    gpu=quote_model_id,
                    region=gpu.region,
                    min_vram_gb=gpu.memory_gb if gpu.memory_gb else None,
                    max_price=total_cost * Decimal("1.1"),
                ),
                ttl_seconds=int(duration_dec * 3600),
                payment_amount=total_cost,
                payment_currency="AITBC",
            )
            job = job_service.create_job(client_id=request.buyer_id, req=job_create)
            job_id = job.id
        job_session.close()
        logger.info("Using job %s for GPU purchase %s", job_id, booking_id)
        try:
            payment_session = SQLModelSession(bind=session.bind)
            payment_service = PaymentService(payment_session)
            quote_payload = request.energy_quote or (job.energy_quote_snapshot if request.job_id else None)

            # Resolve the payment method. The CLI sends "blockchain" for the
            # legacy native path or "evm" for EVM-protected rentals. The
            # PaymentService expects "aitbc_token" for the native rail and
            # "evm" for the EVM rail.
            if request.payment_method == "blockchain":
                payment_method = "aitbc_token"
            else:
                payment_method = request.payment_method

            payment_create = JobPaymentCreate(
                job_id=job.id,
                amount=total_cost,
                currency="AITBC",
                payment_method=payment_method,
                escrow_timeout_seconds=int(duration_hours * 3600),
                protected=booking.protected,
                energy_quote=quote_payload,
                buyer_address=request.buyer_address,
                provider_address=request.provider_address,
                buyer_lock_signature=request.buyer_lock_signature,
                buyer_lock_nonce=request.buyer_lock_nonce,
                buyer_lock_fee=request.buyer_lock_fee,
                evm_tx_hash=request.evm_tx_hash,
                evm_agreement_id=request.evm_agreement_id,
                evm_escrow_id=request.evm_escrow_id,
            )
            # V23-46: client_id was missing entirely (TypeError). The job above was
            # created with client_id=request.buyer_id, which is what the ownership
            # check compares against.
            payment = await payment_service.create_payment(
                client_id=request.buyer_id, job_id=job.id, payment_data=payment_create
            )
            payment_id = payment.id
            payment_status = payment.status
            payment_session.close()
            logger.info("Created payment %s for job %s", payment.id, job.id)
        except Exception as e:
            logger.error("Failed to create payment for job %s: %s", job.id, e)
            payment_id = None
            payment_status = "failed"
        booking.job_id = job.id
        session.add(booking)
        session.commit()
        logger.info("Successfully created job %s and payment %s for GPU purchase %s", job.id, payment.id, booking_id)
    except Exception as e:
        logger.error("Failed to create job/payment for GPU purchase: %s", e)

    # Payment failure rolls back booking and GPU; the job is cancelled if payment
    # never succeeded, so we don't return a fake "purchased" status.
    if payment_status in ("failed", "skipped") or job_id is None:
        if job_id is not None:
            existing_job = session.get(Job, job_id)
            if existing_job and existing_job.state in ("QUEUED", "RUNNING"):
                existing_job.state = "CANCELED"
                existing_job.error = "Payment failed"
                session.add(existing_job)
        session.delete(booking)
        gpu.status = "available"
        session.commit()
        raise HTTPException(
            status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Payment failed: {payment_status}",
        )

    return {
        "purchase_id": booking_id,
        "gpu_id": request.gpu_id,
        "buyer_id": request.buyer_id,
        "job_id": job_id,
        "payment_id": payment_id,
        "duration_hours": duration_hours,
        "total_cost": total_cost,
        "price_per_hour": current_price,
        "status": "purchased",
        "payment_method": request.payment_method,
        "payment_status": payment_status,
        "start_time": start_time.isoformat() + "Z",
        "end_time": end_time.isoformat() + "Z",
    }


@router.post("/marketplace/gpu/sell")
async def sell_gpu(
    request: GPUSellRequest, session: Annotated[Session, Depends(get_session)], user: AuthDep
) -> dict[str, Any]:
    """List GPU for sale on marketplace with specified price."""
    gpu = _get_gpu_or_404(session, request.gpu_id)
    gpu.price_per_hour = request.listing_price
    gpu.status = "available"
    session.commit()
    session.refresh(gpu)
    return {
        "gpu_id": request.gpu_id,
        "seller_id": request.seller_id,
        "listing_price": request.listing_price,
        "status": "listed",
        "description": request.description,
        "timestamp": datetime.now(UTC).isoformat() + "Z",
    }


@router.post("/marketplace/gpu/{gpu_id}/book", status_code=http_status.HTTP_201_CREATED)
async def book_gpu(
    gpu_id: str,
    request: GPUBookRequest,
    session: Annotated[Session, Depends(get_session)],
    engine: Annotated[DynamicPricingEngine, Depends(get_pricing_engine)],
    user: AuthDep,
) -> dict[str, Any]:
    """Book a GPU with dynamic pricing."""
    gpu = _get_gpu_or_404(session, gpu_id)
    if gpu.status != "available":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=f"GPU {gpu_id} is not available")
    if request.duration_hours <= 0:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Booking duration must be greater than 0 hours"
        )
    if request.duration_hours > 8760:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail="Booking duration cannot exceed 8760 hours (1 year)"
        )
    start_time = datetime.now(UTC)
    end_time = start_time + timedelta(hours=request.duration_hours)
    if end_time <= start_time:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Booking end time must be in the future")
    try:
        dynamic_result = await engine.calculate_dynamic_price(
            resource_id=gpu_id,
            resource_type=ResourceType.GPU,
            base_price=gpu.price_per_hour,
            strategy=PricingStrategy.MARKET_BALANCE,
            region=gpu.region,
        )
        current_price = dynamic_result.recommended_price
    except Exception:
        current_price = gpu.price_per_hour
    duration_dec = Decimal(str(request.duration_hours))
    total_cost = duration_dec * current_price
    booking = GPUBooking(
        gpu_id=gpu_id,
        job_id=request.job_id,
        duration_hours=request.duration_hours,
        total_cost=total_cost,
        start_time=start_time,
        end_time=end_time,
        status="active",
    )
    gpu.status = "booked"
    session.add(booking)
    session.commit()
    session.refresh(booking)
    return {
        "booking_id": booking.id,
        "gpu_id": gpu_id,
        "status": "booked",
        "total_cost": booking.total_cost,
        "base_price": gpu.price_per_hour,
        "dynamic_price": current_price,
        "price_per_hour": current_price,
        "start_time": booking.start_time.isoformat() + "Z" if booking.start_time else None,
        "end_time": booking.end_time.isoformat() + "Z" if booking.end_time else None,
        "pricing_factors": dynamic_result.factors_exposed if "dynamic_result" in locals() else {},
        "confidence_score": dynamic_result.confidence_score if "dynamic_result" in locals() else 0.8,
    }


@router.post("/marketplace/gpu/{gpu_id}/release")
async def release_gpu(gpu_id: str, session: Annotated[Session, Depends(get_session)], user: AuthDep) -> dict[str, Any]:
    """Release a booked GPU."""
    gpu = _get_gpu_or_404(session, gpu_id)
    if gpu.status != "booked":
        return {"status": "already_available", "gpu_id": gpu_id, "message": f"GPU {gpu_id} is already available"}
    booking = (
        session.execute(select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active").limit(1))
        .scalars()
        .first()
    )
    refund = Decimal("0")
    if booking:
        try:
            refund = booking.total_cost * Decimal("0.5")
            booking.status = "cancelled"
        except AttributeError as e:
            logger.warning("Booking missing attribute: %s", e)
            refund = Decimal("0")
    gpu.status = "available"
    session.commit()
    return {"status": "released", "gpu_id": gpu_id, "refund": refund, "message": f"GPU {gpu_id} released successfully"}


@router.post("/marketplace/gpu/{gpu_id}/confirm")
async def confirm_gpu_booking(
    gpu_id: str,
    request: GPUConfirmRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Confirm a booking (client ACK)."""
    gpu = _get_gpu_or_404(session, gpu_id)
    if gpu.status != "booked":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=f"GPU {gpu_id} is not booked")
    booking = session.execute(
        select(GPUBooking).where(GPUBooking.gpu_id == gpu_id, GPUBooking.status == "active").limit(1)
    ).scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Active booking for {gpu_id} not found")
    if request.client_id:
        booking.client_id = request.client_id
        session.add(booking)
        session.commit()
        session.refresh(booking)
    return {
        "status": "confirmed",
        "gpu_id": gpu_id,
        "booking_id": booking.id,
        "client_id": booking.client_id,
        "message": f"Booking confirmed for GPU {gpu_id}",
    }


@router.post("/tasks/ollama")
async def submit_ollama_task(
    request: OllamaTaskRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Submit an Ollama inference task to the persistent Redis queue."""
    _get_gpu_or_404(session, request.gpu_id)
    queue = await get_queue()
    task_id = await queue.enqueue(
        gpu_id=request.gpu_id,
        model=request.model,
        prompt=request.prompt,
        parameters=request.parameters,
    )
    return {
        "task_id": task_id,
        "gpu_id": request.gpu_id,
        "status": "queued",
        "model": request.model,
    }


@router.post("/payments/send")
async def send_payment(
    request: PaymentRequest, session: Annotated[Session, Depends(get_session)], user: AuthDep
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
    except Exception as e:
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
    session.add(payment)
    session.commit()

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


@router.delete("/marketplace/gpu/{gpu_id}")
async def delete_gpu(
    gpu_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
    force: bool = Query(default=False, description="Force delete even if GPU is booked"),
) -> dict[str, Any]:
    """Delete (unregister) a GPU from the marketplace."""
    gpu = _get_gpu_or_404(session, gpu_id)
    if gpu.status == "booked" and (not force):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"GPU {gpu_id} is currently booked. Use force=true to delete anyway.",
        )
    session.delete(gpu)
    session.commit()
    return {"status": "deleted", "gpu_id": gpu_id}


@router.get("/marketplace/gpu/{gpu_id}/reviews")
async def get_gpu_reviews(
    gpu_id: str, session: Annotated[Session, Depends(get_session)], limit: int = Query(default=10, ge=1, le=100)
) -> dict[str, Any]:
    """Get GPU reviews."""
    gpu = _get_gpu_or_404(session, gpu_id)
    reviews = (
        session.execute(select(GPUReview).where(GPUReview.gpu_id == gpu_id).order_by(GPUReview.created_at.desc()))  # type: ignore[attr-defined]
        .scalars()
        .all()
    )
    return {
        "gpu_id": gpu_id,
        "average_rating": gpu.average_rating,
        "total_reviews": gpu.total_reviews,
        "reviews": [
            {"rating": r.rating, "comment": r.comment, "user": r.user_id, "date": r.created_at.isoformat() + "Z"}
            for r in reviews
        ],
    }


@router.post("/marketplace/gpu/{gpu_id}/reviews", status_code=http_status.HTTP_201_CREATED)
async def add_gpu_review(
    gpu_id: str, request: GPUReviewRequest, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Add a review for a GPU."""
    try:
        gpu = _get_gpu_or_404(session, gpu_id)
        if not 1 <= request.rating <= 5:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Rating must be between 1 and 5")
        review = GPUReview(gpu_id=gpu_id, user_id="current_user", rating=request.rating, comment=request.comment)
        logger.info(
            "Starting review transaction for GPU %s",
            gpu_id,
            extra={"gpu_id": gpu_id, "rating": request.rating, "user_id": "current_user"},
        )
        session.add(review)
        session.flush()
        total_count_result = session.execute(select(func.count(GPUReview.id)).where(GPUReview.gpu_id == gpu_id)).one()  # type: ignore[arg-type]
        total_count = total_count_result[0] if hasattr(total_count_result, "__getitem__") else total_count_result
        avg_rating_result = session.execute(select(func.avg(GPUReview.rating)).where(GPUReview.gpu_id == gpu_id)).one()
        avg_rating = avg_rating_result[0] if hasattr(avg_rating_result, "__getitem__") else avg_rating_result
        avg_rating = avg_rating or 0.0
        gpu.average_rating = round(float(avg_rating), 2)
        gpu.total_reviews = total_count  # type: ignore[assignment]
        session.commit()
        session.refresh(review)
        logger.info(
            "Review transaction completed successfully for GPU %s",
            gpu_id,
            extra={
                "gpu_id": gpu_id,
                "review_id": review.id,
                "total_reviews": total_count,
                "average_rating": gpu.average_rating,
            },
        )
        return {"status": "review_added", "gpu_id": gpu_id, "review_id": review.id, "average_rating": gpu.average_rating}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to add review for GPU %s: %s",
            gpu_id,
            str(e),
            extra={"gpu_id": gpu_id, "exc": str(e), "error_type": type(e).__name__},
        )
        try:
            session.rollback()
        except Exception as rollback_error:
            logger.error("Failed to rollback transaction: %s", str(rollback_error))
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add review"
            ) from rollback_error
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add review") from e


@router.get("/marketplace/orders")
async def list_orders(
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


@router.get("/marketplace/pricing/{model}")
async def get_pricing(
    model: str,
    session: Annotated[Session, Depends(get_session)],
    engine: Annotated[DynamicPricingEngine, Depends(get_pricing_engine)],
    collector: Annotated[MarketDataCollector, Depends(get_market_collector)],
) -> dict[str, Any]:
    """Get enhanced pricing information for a model with dynamic pricing."""
    all_gpus = session.execute(select(GPURegistry)).scalars().all()
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
        except Exception:
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
    except Exception:
        market_analysis = None
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
            "avg_price_change": avg_dynamic_price - sum(static_prices) / len(static_prices),
            "avg_price_change_percent": (avg_dynamic_price - sum(static_prices) / len(static_prices))
            / (sum(static_prices) / len(static_prices))
            * 100,
            "gpus_with_price_increase": len([dp for dp in dynamic_prices if dp["price_change"] > 0]),
            "gpus_with_price_decrease": len([dp for dp in dynamic_prices if dp["price_change"] < 0]),
        },
        "individual_gpu_pricing": dynamic_prices,
        "market_analysis": market_analysis,
        "pricing_timestamp": datetime.now(UTC).isoformat() + "Z",
    }


@router.post("/marketplace/gpu/bid")
async def bid_gpu(request: dict[str, Any], session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Place a bid on a GPU"""
    bid_id = str(uuid4())
    return {
        "bid_id": bid_id,
        "status": "placed",
        "gpu_id": request.get("gpu_id"),
        "bid_amount": request.get("bid_amount"),
        "duration_hours": request.get("duration_hours"),
        "timestamp": datetime.now(UTC).isoformat() + "Z",
    }


@router.post("/marketplace/native-energy/profile", status_code=http_status.HTTP_201_CREATED)
async def register_native_energy_profile(
    request: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, Any]:
    """Register or update an AIT-native energy profile for a GPU resource."""
    data = request.get("profile") or request
    resource_id = data.get("resource_id")
    if not resource_id:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="resource_id is required")

    scale = 10**18
    eur = data.get("eur_per_kwh")
    try:
        eur_scaled = int(Decimal(str(eur)) * scale) if eur is not None else int(data.get("eur_per_kwh_scaled", 0))
    except Exception:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="eur_per_kwh is not a valid number") from None

    tdp = int(data.get("tdp_watts", 0))
    if tdp <= 0:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="tdp_watts must be positive")
    if eur_scaled <= 0:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="eur_per_kwh must be positive")

    existing = session.get(NativeEnergyProfile, resource_id)
    if existing:
        existing.provider = data.get("provider", existing.provider)
        existing.model_id = data.get("model_id", existing.model_id)
        existing.tdp_watts = tdp
        existing.eur_per_kwh_scaled = eur_scaled
        existing.enabled = data.get("enabled", True)
        existing.revision += 1
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
    else:
        profile = NativeEnergyProfile(
            resource_id=resource_id,
            provider=data.get("provider", user.get("sub", "")),
            model_id=data.get("model_id", resource_id),
            tdp_watts=tdp,
            eur_per_kwh_scaled=eur_scaled,
            enabled=data.get("enabled", True),
            revision=1,
        )
        session.add(profile)
    session.commit()

    return {
        "resource_id": resource_id,
        "status": "registered",
        "tdp_watts": tdp,
        "eur_per_kwh_scaled": eur_scaled,
    }


@router.post("/marketplace/native-energy/rate")
async def publish_native_energy_rate(
    request: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    user: MinerDep,
) -> dict[str, Any]:
    """Publish or update the global AIT/EUR rate for native energy quotes."""
    data = request.get("rate") or request
    scale = 10**18
    ait_per_eur = data.get("ait_per_eur")
    try:
        ait_scaled = (
            int(Decimal(str(ait_per_eur)) * scale) if ait_per_eur is not None else int(data.get("ait_per_eur_scaled", 0))
        )
    except Exception:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="ait_per_eur is not a valid number") from None
    if ait_scaled <= 0:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="ait_per_eur must be positive")

    now = int(datetime.now(UTC).timestamp())
    existing = session.get(NativeEnergyRate, 1)
    if existing:
        existing.ait_per_eur_scaled = ait_scaled
        existing.version = existing.version + 1
        existing.observed_at = data.get("observed_at", now)
        existing.submitted_at = now
        existing.source_kind = data.get("source_kind", "native_operator")
        existing.enabled = data.get("enabled", True)
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
    else:
        rate = NativeEnergyRate(
            id=1,
            ait_per_eur_scaled=ait_scaled,
            version=1,
            observed_at=data.get("observed_at", now),
            submitted_at=now,
            source_kind=data.get("source_kind", "native_operator"),
            enabled=data.get("enabled", True),
        )
        session.add(rate)
    session.commit()

    return {
        "ait_per_eur_scaled": ait_scaled,
        "version": existing.version if existing else 1,
        "status": "published",
    }
