"""Pure energy-pricing arithmetic, quote schema, and validation for AITBC GPU rentals.

This module contains no I/O, no HTTP calls, and no float arithmetic. It is the
single source of truth for the energy-cost floor used by the coordinator,
marketplace, blockchain-node, and CLI.

All monetary values are represented as integers in atomic units. EUR/kWh and
AIT/EUR are passed as 18-decimal fixed-point integers (``FIXED_POINT_SCALE``).
Settlement amounts use the token's own base unit scale (e.g. ``36_000_000``
compute units for native AIT, ``10**18`` for an 18-decimal ERC-20).

The authoritative formula is:

    energy_net_units = ceil(
        T * W * Q * D * R * U
        / (1000 * 3600 * S * S)
    )

where
  * T = ``eur_per_kwh_scaled`` (EUR/kWh * S)
  * W = ``tdp_watts`` (registered GPU TDP)
  * Q = ``gpu_count`` (positive integer)
  * D = ``duration_seconds`` (integer seconds)
  * R = ``ait_per_eur_scaled`` (AIT/EUR * S)
  * U = ``settlement_unit_scale`` (atomic units per settlement token)
  * S = ``FIXED_POINT_SCALE`` (10**18)

The result is the minimum provider net payout in settlement atomic units.
Platform fees are applied according to the fee model:

  * ``provider_deducted`` (native AIT): buyer locks ``gross``; provider is
    credited ``gross - fee``.
  * ``buyer_pays_on_top`` (EVM): buyer transfers ``principal + fee``; provider
    receives ``principal``.

See ``/home/oib/.devin/plans/plan-8c6402fc60d9b2a6.md`` for the full plan.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import StrEnum
from typing import Any

FIXED_POINT_SCALE = 10**18
SECONDS_PER_HOUR = 3600
WATTS_PER_KILOWATT = 1000
BASIS_POINTS = 10_000

NATIVE_UNITS_PER_AIT = 36_000_000
"""Native AIT compute-units per whole AIT."""

EVM_UNITS_PER_AIT = 10**18
"""Atomic units for an 18-decimal AIT ERC-20."""

DEFAULT_FEE_BASIS_POINTS = 250  # 2.5 %
MIN_FEE_BASIS_POINTS = 0
MAX_FEE_BASIS_POINTS = 1000  # 10 %, matching AIPowerRental.sol

DEFAULT_QUOTE_LIFETIME_SECONDS = 300
DEFAULT_MAX_RATE_AGE_SECONDS = 300
FUTURE_TIMESTAMP_TOLERANCE_SECONDS = 60

MAX_TDP_WATTS = 50_000
MAX_GPU_COUNT = 10_000
MAX_DURATION_SECONDS = 86400 * 365
MAX_SETTLEMENT_UNIT_SCALE = 10**36
MAX_EUR_PER_KWH_WHOLE = 1_000_000
MAX_AIT_PER_EUR_WHOLE = 1_000_000_000

MAX_UINT256 = 2**256 - 1
MAX_PRE_PRODUCT = 2**512 - 1


class FeeModel(StrEnum):
    """Who pays the platform fee and when."""

    PROVIDER_DEDUCTED = "provider_deducted"
    BUYER_PAYS_ON_TOP = "buyer_pays_on_top"


class SettlementRoute(StrEnum):
    """Settlement rail for the quote."""

    NATIVE = "native"
    EVM = "evm"


class RefusalCode(StrEnum):
    """Machine-readable reason for refusing a quote at funding time."""

    BELOW_FLOOR = "below_floor"
    BUYER_CAP_CONFLICT = "buyer_cap_conflict"
    HARD_CAP_CONFLICT = "hard_cap_conflict"
    EXPIRED = "expired"
    STALE_RATE = "stale_rate"
    FUTURE_TIMESTAMP = "future_timestamp"
    PROFILE_MISMATCH = "profile_mismatch"
    PROFILE_DISABLED = "profile_disabled"
    RATE_MISMATCH = "rate_mismatch"
    RATE_DISABLED = "rate_disabled"
    INVALID_INPUT = "invalid_input"


class EnergyPricingError(Exception):
    """Raised when energy pricing inputs are invalid or economically impossible."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, kw_only=True)
class EnergyProfile:
    """Operator-registered GPU power and provider tariff for a single resource."""

    resource_id: str
    provider: str
    model_id: str
    tdp_watts: int
    eur_per_kwh_scaled: int
    enabled: bool = True
    revision: int = 0

    def __post_init__(self) -> None:
        _require_positive_int(self.tdp_watts, "tdp_watts", max_value=MAX_TDP_WATTS)
        _require_scaled_positive(self.eur_per_kwh_scaled, "eur_per_kwh_scaled")
        if self.eur_per_kwh_scaled > FIXED_POINT_SCALE * MAX_EUR_PER_KWH_WHOLE:
            raise EnergyPricingError("eur_per_kwh_scaled out of range")


@dataclass(frozen=True, kw_only=True)
class EnergyRate:
    """Authorized AIT/EUR reference rate with provenance metadata."""

    ait_per_eur_scaled: int
    version: int
    observed_at: int  # Unix seconds
    submitted_at: int  # Unix seconds
    source_kind: str
    enabled: bool = True

    def __post_init__(self) -> None:
        _require_scaled_positive(self.ait_per_eur_scaled, "ait_per_eur_scaled")
        if self.ait_per_eur_scaled > FIXED_POINT_SCALE * MAX_AIT_PER_EUR_WHOLE:
            raise EnergyPricingError("ait_per_eur_scaled out of range")
        _require_positive_int(self.version, "version")
        _require_positive_int(self.observed_at, "observed_at")
        _require_positive_int(self.submitted_at, "submitted_at")
        if not self.source_kind or not self.source_kind.strip():
            raise EnergyPricingError("source_kind is required")


@dataclass(frozen=True, kw_only=True)
class FeePolicy:
    """Platform fee policy attached to a quote."""

    fee_basis_points: int = DEFAULT_FEE_BASIS_POINTS
    fee_model: FeeModel = FeeModel.PROVIDER_DEDUCTED

    def __post_init__(self) -> None:
        if not MIN_FEE_BASIS_POINTS <= self.fee_basis_points <= MAX_FEE_BASIS_POINTS:
            raise EnergyPricingError(
                f"fee_basis_points must be between {MIN_FEE_BASIS_POINTS} "
                f"and {MAX_FEE_BASIS_POINTS}"
            )
        if self.fee_model not in (FeeModel.PROVIDER_DEDUCTED, FeeModel.BUYER_PAYS_ON_TOP):
            raise EnergyPricingError(f"invalid fee_model: {self.fee_model}")


@dataclass(frozen=True, kw_only=True)
class EnergyQuote:
    """Immutable energy quote for a fixed-duration GPU rental.

    This dataclass is the canonical signed payload. The operator signs the
    canonical JSON of all fields except ``operator_signature``. The buyer's
    native transaction signature covers the same digest in the ``payload`` of
    ``ESCROW_LOCK``.
    """

    version: int = 1
    domain: str
    chain_id: str
    settlement_asset: str
    settlement_unit_scale: int
    buyer: str
    provider: str
    job_id: str
    quote_id: str
    settlement_route: SettlementRoute
    resource_id: str
    model_id: str
    gpu_count: int
    duration_seconds: int
    eur_per_kwh_scaled: int
    tdp_watts: int
    ait_per_eur_scaled: int
    rate_version: int
    rate_observed_at: int
    rate_submitted_at: int = 0
    rate_source_kind: str
    profile_revision: int
    evm_chain_id: int | None = None
    evm_contract: str | None = None
    evm_block_number: int | None = None
    evm_block_hash: str | None = None
    net_energy_floor_units: int = 0
    principal_units: int = 0
    fee_basis_points: int = DEFAULT_FEE_BASIS_POINTS
    fee_model: FeeModel = FeeModel.PROVIDER_DEDUCTED
    buyer_cap_units: int | None = None
    issued_at: int = 0
    expires_at: int = 0
    operator_signature: bytes | None = None
    buyer_signature: bytes | None = None

    def __post_init__(self) -> None:
        _require_positive_int(self.version, "version")
        _require_positive_int(
            self.settlement_unit_scale,
            "settlement_unit_scale",
            max_value=MAX_SETTLEMENT_UNIT_SCALE,
        )
        _require_positive_int(self.gpu_count, "gpu_count", max_value=MAX_GPU_COUNT)
        _require_positive_int(
            self.duration_seconds, "duration_seconds", max_value=MAX_DURATION_SECONDS
        )
        _require_positive_int(self.tdp_watts, "tdp_watts", max_value=MAX_TDP_WATTS)
        _require_scaled_positive(self.eur_per_kwh_scaled, "eur_per_kwh_scaled")
        if self.eur_per_kwh_scaled > FIXED_POINT_SCALE * MAX_EUR_PER_KWH_WHOLE:
            raise EnergyPricingError("eur_per_kwh_scaled out of range")
        _require_scaled_positive(self.ait_per_eur_scaled, "ait_per_eur_scaled")
        if self.ait_per_eur_scaled > FIXED_POINT_SCALE * MAX_AIT_PER_EUR_WHOLE:
            raise EnergyPricingError("ait_per_eur_scaled out of range")

        if isinstance(self.settlement_route, str):
            object.__setattr__(self, "settlement_route", SettlementRoute(self.settlement_route))
        if isinstance(self.fee_model, str):
            object.__setattr__(self, "fee_model", FeeModel(self.fee_model))

        if not 0 <= self.fee_basis_points <= MAX_FEE_BASIS_POINTS:
            raise EnergyPricingError("fee_basis_points out of range")
        if self.expires_at <= self.issued_at:
            raise EnergyPricingError("expires_at must be after issued_at")
        if self.net_energy_floor_units < 0 or self.principal_units < 0:
            raise EnergyPricingError("energy floor and principal must be non-negative")

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of the signed fields.

        Excludes operator- and buyer-signatures. Enums are reduced to strings.
        """
        data: dict[str, Any] = asdict(self)
        data.pop("operator_signature", None)
        data.pop("buyer_signature", None)
        data["settlement_route"] = self.settlement_route.value
        data["fee_model"] = self.fee_model.value
        return data

    def canonical_json(self) -> str:
        """Deterministic canonical JSON suitable for signing."""
        return json.dumps(
            self.to_canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def canonical_bytes(self) -> bytes:
        """Canonical JSON encoded as UTF-8."""
        return self.canonical_json().encode("utf-8")

    def to_profile(self) -> EnergyProfile:
        """Reconstruct the operator-attested profile from this quote."""
        return EnergyProfile(
            resource_id=self.resource_id,
            provider=self.provider,
            model_id=self.model_id,
            tdp_watts=self.tdp_watts,
            eur_per_kwh_scaled=self.eur_per_kwh_scaled,
            enabled=True,
            revision=self.profile_revision,
        )

    def to_rate(self) -> EnergyRate:
        """Reconstruct the operator-attested rate from this quote."""
        return EnergyRate(
            ait_per_eur_scaled=self.ait_per_eur_scaled,
            version=self.rate_version,
            observed_at=self.rate_observed_at,
            submitted_at=self.rate_submitted_at,
            source_kind=self.rate_source_kind,
            enabled=True,
        )

    def to_dict(self, include_signature: bool = True) -> dict[str, Any]:
        """Full JSON-serializable representation for database or wire storage.

        The canonical signing fields are still the ones returned by
        :meth:`to_canonical_dict`; this helper is for persistence and replay.
        """
        data = asdict(self)
        data["settlement_route"] = self.settlement_route.value
        data["fee_model"] = self.fee_model.value
        if self.operator_signature is not None:
            data["operator_signature"] = self.operator_signature.hex()
        if self.buyer_signature is not None:
            data["buyer_signature"] = self.buyer_signature.hex()
        if not include_signature:
            data.pop("operator_signature", None)
            data.pop("buyer_signature", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnergyQuote":
        """Reconstruct a quote from its JSON/database representation."""
        payload = dict(data)
        for key in ("operator_signature", "buyer_signature"):
            sig = payload.get(key)
            if isinstance(sig, str):
                payload[key] = bytes.fromhex(sig)
            elif sig is None:
                payload[key] = None
        return cls(**payload)

    def digest_sha256(self) -> bytes:
        """Stable 32-byte digest of the canonical quote.

        The operator signature should be produced over this digest or over a
        keccak256 variant; this module uses SHA-256 to remain free of external
        crypto dependencies.
        """
        return hashlib.sha256(self.canonical_bytes()).digest()


@dataclass(frozen=True, kw_only=True)
class FundingBreakdown:
    """Atomic-unit settlement breakdown for a funded quote."""

    net_units: int
    principal_units: int
    provider_credit_units: int
    platform_fee_units: int
    buyer_charge_units: int
    evm_principal_units: int | None = None


@dataclass(frozen=True, kw_only=True)
class QuoteResult:
    """Result of evaluating a quote against current profile/rate and caps."""

    quote: EnergyQuote
    breakdown: FundingBreakdown | None
    approved: bool
    refusal_code: RefusalCode | None = None
    refusal_reason: str | None = None


# --------------------------------------------------------------------------- #
# Boundary helpers
# --------------------------------------------------------------------------- #


def to_scaled(
    value: Decimal | str | int,
    *,
    scale: int = FIXED_POINT_SCALE,
    name: str = "value",
    allow_quantize: bool = False,
) -> int:
    """Convert a positive human-readable Decimal, string, or int to a scaled integer.

    Rejects binary floats, infinities, NaN, zero and negative values. By
    default it rejects values with more than 18 decimal places; set
    ``allow_quantize=True`` to round them to 18 places with ``ROUND_HALF_UP``.
    """
    if isinstance(value, float):
        raise EnergyPricingError(f"{name} must not be a binary float")
    try:
        dec = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise EnergyPricingError(f"{name} is not a valid decimal: {exc}") from exc
    if not isinstance(dec, Decimal):
        raise EnergyPricingError(
            f"{name} must be Decimal or str, got {type(value).__name__}"
        )
    if not dec.is_finite() or dec <= 0:
        raise EnergyPricingError(f"{name} must be finite and positive: {dec}")
    if dec.as_tuple().exponent < -18:
        if not allow_quantize:
            raise EnergyPricingError(
                f"{name} has more than 18 decimal places: {dec}; "
                "quantize explicitly before scaling"
            )
        dec = dec.quantize(Decimal(1) / scale, rounding=ROUND_HALF_UP)
    return int(dec * scale)


# --------------------------------------------------------------------------- #
# Core arithmetic
# --------------------------------------------------------------------------- #


def compute_energy_net_units(
    tdp_watts: int,
    eur_per_kwh_scaled: int,
    ait_per_eur_scaled: int,
    gpu_count: int,
    duration_seconds: int,
    settlement_unit_scale: int,
    fixed_point_scale: int = FIXED_POINT_SCALE,
) -> int:
    """Return the provider net floor in settlement atomic units.

    Uses exact integer arithmetic and ceiling. The result is checked to fit in
    a uint256 so it can be mirrored in the EVM contracts.
    """
    _require_positive_int(tdp_watts, "tdp_watts", max_value=MAX_TDP_WATTS)
    _require_scaled_positive(eur_per_kwh_scaled, "eur_per_kwh_scaled")
    _require_scaled_positive(ait_per_eur_scaled, "ait_per_eur_scaled")
    _require_positive_int(gpu_count, "gpu_count", max_value=MAX_GPU_COUNT)
    _require_positive_int(
        duration_seconds, "duration_seconds", max_value=MAX_DURATION_SECONDS
    )
    _require_positive_int(
        settlement_unit_scale,
        "settlement_unit_scale",
        max_value=MAX_SETTLEMENT_UNIT_SCALE,
    )

    if eur_per_kwh_scaled > fixed_point_scale * MAX_EUR_PER_KWH_WHOLE:
        raise EnergyPricingError("eur_per_kwh_scaled out of range")
    if ait_per_eur_scaled > fixed_point_scale * MAX_AIT_PER_EUR_WHOLE:
        raise EnergyPricingError("ait_per_eur_scaled out of range")

    numerator = (
        tdp_watts
        * eur_per_kwh_scaled
        * ait_per_eur_scaled
        * gpu_count
        * duration_seconds
        * settlement_unit_scale
    )
    denominator = WATTS_PER_KILOWATT * SECONDS_PER_HOUR * fixed_point_scale * fixed_point_scale

    # Detect numbers that would not fit in an OZ Math.mulDiv step. The product
    # T*W*Q*D*R*U may be up to ~2**512 for the bounded inputs above.
    if numerator > MAX_PRE_PRODUCT:
        raise EnergyPricingError("energy input product exceeds 512-bit bound")
    if numerator > MAX_UINT256 * denominator:
        raise EnergyPricingError("energy floor result would exceed uint256")

    return (numerator + denominator - 1) // denominator


def compute_native_gross_units(net_units: int, fee_basis_points: int) -> int:
    """Gross amount the native buyer must lock so the provider net is at least floor.

    ``fee_basis_points`` is deducted from the provider side, so we gross up:
    ``gross = ceil(net * 10000 / (10000 - fee))``.
    """
    _require_positive_int(net_units, "net_units")
    if not MIN_FEE_BASIS_POINTS <= fee_basis_points < BASIS_POINTS:
        raise EnergyPricingError("fee_basis_points must be in [0, 10000)")
    if fee_basis_points == 0:
        return net_units
    return (net_units * BASIS_POINTS + (BASIS_POINTS - fee_basis_points) - 1) // (
        BASIS_POINTS - fee_basis_points
    )


def compute_evm_buyer_charge(principal_units: int, fee_basis_points: int) -> int:
    """Total EVM buyer transfer for a given provider principal and fee.

    The contract charges the platform fee on top of principal:
    ``total = principal + floor(principal * fee / 10000)``.
    """
    _require_positive_int(principal_units, "principal_units")
    if not MIN_FEE_BASIS_POINTS <= fee_basis_points <= MAX_FEE_BASIS_POINTS:
        raise EnergyPricingError("fee_basis_points out of range")
    platform_fee = (principal_units * fee_basis_points) // BASIS_POINTS
    return principal_units + platform_fee


def compute_provider_credit_native(gross_units: int, fee_basis_points: int) -> int:
    """Provider net credit from a native gross lock after the fee is deducted."""
    _require_positive_int(gross_units, "gross_units")
    if not MIN_FEE_BASIS_POINTS <= fee_basis_points < BASIS_POINTS:
        raise EnergyPricingError("fee_basis_points must be in [0, 10000)")
    platform_fee = (gross_units * fee_basis_points) // BASIS_POINTS
    return gross_units - platform_fee


def compute_funding_breakdown(
    principal_units: int,
    fee_basis_points: int,
    fee_model: FeeModel,
    net_energy_floor_units: int | None = None,
) -> FundingBreakdown:
    """Return the full settlement breakdown from the agreed principal and fee model.

    ``principal_units`` is the agreed transfer amount excluding buyer-side fee:
    * native: the gross amount locked by the buyer
    * EVM: the provider principal
    """
    _require_positive_int(principal_units, "principal_units")
    if not 0 <= fee_basis_points <= MAX_FEE_BASIS_POINTS:
        raise EnergyPricingError("fee_basis_points out of range")
    if net_energy_floor_units is not None and principal_units < net_energy_floor_units:
        raise EnergyPricingError(
            f"principal_units {principal_units} below net floor {net_energy_floor_units}",
            code=RefusalCode.BELOW_FLOOR.value,
        )

    if fee_model == FeeModel.PROVIDER_DEDUCTED:
        if fee_basis_points >= BASIS_POINTS:
            raise EnergyPricingError("provider-deducted fee must be < 100%")
        buyer_charge = principal_units
        platform_fee = (principal_units * fee_basis_points) // BASIS_POINTS
        provider_credit = principal_units - platform_fee
        evm_principal = None
    elif fee_model == FeeModel.BUYER_PAYS_ON_TOP:
        platform_fee = (principal_units * fee_basis_points) // BASIS_POINTS
        buyer_charge = principal_units + platform_fee
        provider_credit = principal_units
        evm_principal = principal_units
    else:
        raise EnergyPricingError(f"invalid fee_model: {fee_model}")

    return FundingBreakdown(
        net_units=net_energy_floor_units if net_energy_floor_units is not None else 0,
        principal_units=principal_units,
        provider_credit_units=provider_credit,
        platform_fee_units=platform_fee,
        buyer_charge_units=buyer_charge,
        evm_principal_units=evm_principal,
    )


# --------------------------------------------------------------------------- #
# Quote evaluation
# --------------------------------------------------------------------------- #


def build_minimum_quote(
    profile: EnergyProfile,
    rate: EnergyRate,
    *,
    buyer: str,
    job_id: str,
    quote_id: str,
    domain: str,
    chain_id: str,
    settlement_asset: str,
    settlement_unit_scale: int,
    settlement_route: SettlementRoute,
    gpu_count: int,
    duration_seconds: int,
    buyer_cap_units: int | None = None,
    fee_basis_points: int = DEFAULT_FEE_BASIS_POINTS,
    fee_model: FeeModel | None = None,
    quote_lifetime_seconds: int = DEFAULT_QUOTE_LIFETIME_SECONDS,
    now: int | None = None,
    evm_chain_id: int | None = None,
    evm_contract: str | None = None,
    evm_block_number: int | None = None,
    evm_block_hash: str | None = None,
) -> EnergyQuote:
    """Create an EnergyQuote with the minimum principal covering the energy floor.

    The principal is set to the smallest value that satisfies the floor after
    the configured fee model. Buyer and hard caps are **not** checked here; use
    ``evaluate_quote`` before funding.
    """
    if not profile.enabled:
        raise EnergyPricingError("profile is disabled")
    if not rate.enabled:
        raise EnergyPricingError("rate is disabled")

    fee_model = fee_model or (
        FeeModel.PROVIDER_DEDUCTED
        if settlement_route == SettlementRoute.NATIVE
        else FeeModel.BUYER_PAYS_ON_TOP
    )

    net = compute_energy_net_units(
        tdp_watts=profile.tdp_watts,
        eur_per_kwh_scaled=profile.eur_per_kwh_scaled,
        ait_per_eur_scaled=rate.ait_per_eur_scaled,
        gpu_count=gpu_count,
        duration_seconds=duration_seconds,
        settlement_unit_scale=settlement_unit_scale,
    )

    if fee_model == FeeModel.PROVIDER_DEDUCTED:
        principal = compute_native_gross_units(net, fee_basis_points)
    elif fee_model == FeeModel.BUYER_PAYS_ON_TOP:
        principal = net
    else:
        raise EnergyPricingError(f"invalid fee_model: {fee_model}")

    now = now if now is not None else int(time.time())
    expires = now + quote_lifetime_seconds
    issued = now

    return EnergyQuote(
        version=1,
        domain=domain,
        chain_id=chain_id,
        settlement_asset=settlement_asset,
        settlement_unit_scale=settlement_unit_scale,
        buyer=buyer,
        provider=profile.provider,
        job_id=job_id,
        quote_id=quote_id,
        settlement_route=settlement_route,
        resource_id=profile.resource_id,
        model_id=profile.model_id,
        gpu_count=gpu_count,
        duration_seconds=duration_seconds,
        eur_per_kwh_scaled=profile.eur_per_kwh_scaled,
        tdp_watts=profile.tdp_watts,
        ait_per_eur_scaled=rate.ait_per_eur_scaled,
        rate_version=rate.version,
        rate_observed_at=rate.observed_at,
        rate_submitted_at=rate.submitted_at,
        rate_source_kind=rate.source_kind,
        profile_revision=profile.revision,
        evm_chain_id=evm_chain_id,
        evm_contract=evm_contract,
        evm_block_number=evm_block_number,
        evm_block_hash=evm_block_hash,
        net_energy_floor_units=net,
        principal_units=principal,
        fee_basis_points=fee_basis_points,
        fee_model=fee_model,
        buyer_cap_units=buyer_cap_units,
        issued_at=issued,
        expires_at=expires,
    )


def evaluate_quote(
    quote: EnergyQuote,
    profile: EnergyProfile,
    rate: EnergyRate,
    now: int,
    *,
    max_rate_age_seconds: int = DEFAULT_MAX_RATE_AGE_SECONDS,
    hard_cap_units: int | None = None,
) -> QuoteResult:
    """Validate a quote against current profile/rate and return funding result.

    This is the single entry point for the funding gate. It returns a typed
    refusal rather than raising for economic conflicts (cap, expiry, floor).
    Only programmer errors or corrupt quote objects raise ``EnergyPricingError``.
    """
    if not profile.enabled:
        return _refusal(quote, RefusalCode.PROFILE_DISABLED, "profile is disabled")
    if not rate.enabled:
        return _refusal(quote, RefusalCode.RATE_DISABLED, "rate is disabled")

    if quote.resource_id != profile.resource_id:
        return _refusal(quote, RefusalCode.PROFILE_MISMATCH, "resource_id mismatch")
    if quote.provider != profile.provider:
        return _refusal(quote, RefusalCode.PROFILE_MISMATCH, "provider mismatch")
    if quote.model_id != profile.model_id:
        return _refusal(quote, RefusalCode.PROFILE_MISMATCH, "model_id mismatch")
    if quote.tdp_watts != profile.tdp_watts:
        return _refusal(quote, RefusalCode.PROFILE_MISMATCH, "tdp_watts mismatch")
    if quote.eur_per_kwh_scaled != profile.eur_per_kwh_scaled:
        return _refusal(quote, RefusalCode.PROFILE_MISMATCH, "eur_per_kwh mismatch")
    if quote.profile_revision != profile.revision:
        return _refusal(
            quote, RefusalCode.PROFILE_MISMATCH, "profile revision mismatch"
        )
    if quote.ait_per_eur_scaled != rate.ait_per_eur_scaled:
        return _refusal(quote, RefusalCode.RATE_MISMATCH, "ait_per_eur mismatch")
    if quote.rate_version != rate.version:
        return _refusal(quote, RefusalCode.RATE_MISMATCH, "rate version mismatch")
    if quote.rate_source_kind != rate.source_kind:
        return _refusal(quote, RefusalCode.RATE_MISMATCH, "rate source kind mismatch")

    if now >= quote.expires_at:
        return _refusal(quote, RefusalCode.EXPIRED, "quote expired")
    if now < quote.issued_at - FUTURE_TIMESTAMP_TOLERANCE_SECONDS:
        return _refusal(quote, RefusalCode.FUTURE_TIMESTAMP, "quote issued in future")
    if now > rate.observed_at + max_rate_age_seconds:
        return _refusal(quote, RefusalCode.STALE_RATE, "rate observation too old")
    if rate.observed_at > now + FUTURE_TIMESTAMP_TOLERANCE_SECONDS:
        return _refusal(quote, RefusalCode.FUTURE_TIMESTAMP, "rate observed in future")
    if rate.submitted_at > now + FUTURE_TIMESTAMP_TOLERANCE_SECONDS:
        return _refusal(quote, RefusalCode.FUTURE_TIMESTAMP, "rate submitted in future")

    floor = compute_energy_net_units(
        tdp_watts=quote.tdp_watts,
        eur_per_kwh_scaled=quote.eur_per_kwh_scaled,
        ait_per_eur_scaled=quote.ait_per_eur_scaled,
        gpu_count=quote.gpu_count,
        duration_seconds=quote.duration_seconds,
        settlement_unit_scale=quote.settlement_unit_scale,
    )
    if floor != quote.net_energy_floor_units:
        return _refusal(
            quote,
            RefusalCode.INVALID_INPUT,
            "quote net_energy_floor_units does not match recomputed floor",
        )

    if quote.principal_units < floor:
        return _refusal(
            quote,
            RefusalCode.BELOW_FLOOR,
            f"principal_units {quote.principal_units} below floor {floor}",
        )

    breakdown = compute_funding_breakdown(
        principal_units=quote.principal_units,
        fee_basis_points=quote.fee_basis_points,
        fee_model=quote.fee_model,
        net_energy_floor_units=floor,
    )

    if quote.buyer_cap_units is not None and breakdown.buyer_charge_units > quote.buyer_cap_units:
        return _refusal(
            quote,
            RefusalCode.BUYER_CAP_CONFLICT,
            f"buyer charge {breakdown.buyer_charge_units} exceeds cap {quote.buyer_cap_units}",
        )
    if hard_cap_units is not None and breakdown.buyer_charge_units > hard_cap_units:
        return _refusal(
            quote,
            RefusalCode.HARD_CAP_CONFLICT,
            f"buyer charge {breakdown.buyer_charge_units} exceeds hard cap {hard_cap_units}",
        )

    return QuoteResult(
        quote=quote,
        breakdown=breakdown,
        approved=True,
    )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _require_positive_int(
    value: int,
    name: str,
    *,
    max_value: int | None = None,
) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EnergyPricingError(f"{name} must be an int, got {type(value).__name__}")
    if value <= 0:
        raise EnergyPricingError(f"{name} must be positive, got {value}")
    if max_value is not None and value > max_value:
        raise EnergyPricingError(f"{name} {value} exceeds maximum {max_value}")


def _require_scaled_positive(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EnergyPricingError(f"{name} must be an int, got {type(value).__name__}")
    if value <= 0:
        raise EnergyPricingError(f"{name} must be positive, got {value}")
    max_scaled = FIXED_POINT_SCALE * 10**12
    if value > max_scaled:
        raise EnergyPricingError(f"{name} {value} exceeds maximum scaled value")


def _refusal(
    quote: EnergyQuote,
    code: RefusalCode,
    reason: str,
) -> QuoteResult:
    return QuoteResult(
        quote=quote,
        breakdown=None,
        approved=False,
        refusal_code=code,
        refusal_reason=reason,
    )
