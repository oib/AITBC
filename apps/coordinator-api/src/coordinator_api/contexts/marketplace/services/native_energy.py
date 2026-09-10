"""Native energy oracle backed by coordinator database tables.

This is the AIT-native equivalent of ``aitbc.marketplace.energy_oracle.EVMEnergyOracle``.
It returns the same ``EnergyProfile``/``EnergyRate`` dataclasses so the shared
energy-quote arithmetic can be reused without an EVM contract.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session

from aitbc.marketplace.energy_pricing import EnergyProfile, EnergyRate
from aitbc.marketplace.energy_oracle import EnergyOracleError

from ..domain.energy import NativeEnergyProfile, NativeEnergyRate


class NativeEnergyOracle:
    """Read energy inputs from the coordinator's native profile/rate tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _rate_record(self) -> NativeEnergyRate:
        record = self.session.get(NativeEnergyRate, 1)
        if record is None:
            raise EnergyOracleError("no native energy rate configured")
        if not record.enabled:
            raise EnergyOracleError("native energy rate is disabled")
        return record

    def get_profile(self, resource_id: str) -> EnergyProfile:
        """Fetch and validate the native energy profile for ``resource_id``."""
        profile = self.session.get(NativeEnergyProfile, resource_id)
        if profile is None:
            raise EnergyOracleError(f"native energy profile not found for {resource_id}")
        if not profile.enabled:
            raise EnergyOracleError(f"native energy profile disabled for {resource_id}")
        return EnergyProfile(
            resource_id=profile.resource_id,
            provider=profile.provider,
            model_id=profile.model_id,
            tdp_watts=profile.tdp_watts,
            eur_per_kwh_scaled=profile.eur_per_kwh_scaled,
            enabled=profile.enabled,
            revision=profile.revision,
        )

    def get_rate(self) -> EnergyRate:
        """Fetch the current native AIT/EUR rate."""
        rate = self._rate_record()
        return EnergyRate(
            ait_per_eur_scaled=rate.ait_per_eur_scaled,
            version=rate.version,
            observed_at=rate.observed_at,
            submitted_at=rate.submitted_at,
            source_kind=rate.source_kind,
            enabled=rate.enabled,
        )

    def get_pinned_inputs(self, resource_id: str) -> tuple[EnergyProfile, EnergyRate, int, str]:
        """Return profile and rate with synthetic pinned block metadata."""
        profile = self.get_profile(resource_id)
        rate = self.get_rate()
        now = int(datetime.now(UTC).timestamp())
        return profile, rate, now, "0x" + "0" * 64

    def get_energy_floor(
        self,
        resource_id: str,
        gpu_count: int,
        duration_seconds: int,
        settlement_unit_scale: int,
    ) -> int:
        """Compute the native energy floor in the contract-compatible way."""
        from aitbc.marketplace.energy_pricing import compute_energy_net_units

        profile = self.get_profile(resource_id)
        rate = self.get_rate()
        return compute_energy_net_units(
            tdp_watts=profile.tdp_watts,
            eur_per_kwh_scaled=profile.eur_per_kwh_scaled,
            ait_per_eur_scaled=rate.ait_per_eur_scaled,
            gpu_count=gpu_count,
            duration_seconds=duration_seconds,
            settlement_unit_scale=settlement_unit_scale,
        )
