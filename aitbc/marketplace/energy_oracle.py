"""Bounded EVM input reader for energy pricing.

Reads canonical energy profiles and rates from an on-chain ``IEnergyPricing``
contract at a pinned block. Returns native ``EnergyProfile``/``EnergyRate``
dataclasses so the coordinator, marketplace, CLI and operator tooling can build
and evaluate quotes with provenance.

The reader is intentionally thin: all arithmetic, validation and quote logic
lives in ``aitbc.marketplace.energy_pricing``. This module only fetches the
raw inputs and maps them into that format.
"""

from __future__ import annotations

from typing import Any

from aitbc.ethereum_rpc import EthereumRPCClient
from aitbc.marketplace.energy_pricing import EnergyPricingError, EnergyProfile, EnergyRate

# Canonical ABI for the IEnergyPricing view interface. This ABI is duplicated in
# ``contracts/contracts/IEnergyPricing.sol``; keep the two in sync.
DEFAULT_ENERGY_PRICING_ABI: list[dict] = [
    {
        "inputs": [{"name": "resourceId", "type": "string"}],
        "name": "getEnergyProfile",
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {"name": "enabled", "type": "bool"},
                    {"name": "revision", "type": "uint256"},
                    {"name": "modelId", "type": "string"},
                    {"name": "provider", "type": "address"},
                    {"name": "tdpWatts", "type": "uint256"},
                    {"name": "eurPerKwh", "type": "uint256"},
                ],
            },
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getEnergyRate",
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {"name": "enabled", "type": "bool"},
                    {"name": "version", "type": "uint256"},
                    {"name": "aitPerEur", "type": "uint256"},
                    {"name": "observedAt", "type": "uint256"},
                    {"name": "submittedAt", "type": "uint256"},
                    {"name": "sourceKind", "type": "string"},
                ],
            },
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "resourceId", "type": "string"},
            {"name": "gpuCount", "type": "uint256"},
            {"name": "durationSeconds", "type": "uint256"},
            {"name": "settlementUnitScale", "type": "uint256"},
        ],
        "name": "getEnergyFloor",
        "outputs": [
            {"name": "netFloor", "type": "uint256"},
            {"name": "valid", "type": "bool"},
            {"name": "reason", "type": "string"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


class EnergyOracleError(EnergyPricingError):
    """Raised when an EVM energy input read is missing, malformed, or stale."""


class EVMEnergyOracle:
    """Reads energy inputs from an IEnergyPricing contract at a pinned block."""

    def __init__(
        self,
        rpc_client: EthereumRPCClient,
        contract_address: str,
        chain_id: int | None = None,
    ) -> None:
        self.rpc = rpc_client
        self.contract_address = contract_address
        self.chain_id = chain_id

    def _call(
        self,
        function_name: str,
        *args: Any,
        block_identifier: int | str | None = None,
    ) -> Any:
        try:
            return self.rpc.call_contract(
                contract_address=self.contract_address,
                abi=DEFAULT_ENERGY_PRICING_ABI,
                function_name=function_name,
                args=list(args),
                block_identifier=block_identifier,
            )
        except Exception as exc:
            raise EnergyOracleError(f"EVM read failed for {function_name}: {exc}") from exc

    def _resolve_block(self, block_identifier: int | str | None) -> tuple[int, str]:
        """Return the concrete block number and hash for a block identifier."""
        if block_identifier is None:
            block = self.rpc.get_block("latest")
        else:
            block = self.rpc.get_block(block_identifier)
        return int(block["number"]), block["hash"]

    def get_profile(
        self,
        resource_id: str,
        block_identifier: int | str | None = None,
    ) -> EnergyProfile:
        """Fetch and validate the energy profile for ``resource_id``."""
        result = self._call("getEnergyProfile", resource_id, block_identifier=block_identifier)
        if not isinstance(result, tuple | list) or len(result) < 6:
            raise EnergyOracleError(f"unexpected getEnergyProfile return: {result}")
        enabled, revision, model_id, provider, tdp_watts, eur_per_kwh = result[:6]
        return EnergyProfile(
            resource_id=resource_id,
            provider=provider,
            model_id=model_id,
            tdp_watts=int(tdp_watts),
            eur_per_kwh_scaled=int(eur_per_kwh),
            enabled=bool(enabled),
            revision=int(revision),
        )

    def get_rate(
        self,
        block_identifier: int | str | None = None,
    ) -> EnergyRate:
        """Fetch and validate the current energy rate."""
        result = self._call("getEnergyRate", block_identifier=block_identifier)
        if not isinstance(result, tuple | list) or len(result) < 6:
            raise EnergyOracleError(f"unexpected getEnergyRate return: {result}")
        enabled, version, ait_per_eur, observed_at, submitted_at, source_kind = result[:6]
        return EnergyRate(
            ait_per_eur_scaled=int(ait_per_eur),
            version=int(version),
            observed_at=int(observed_at),
            submitted_at=int(submitted_at),
            source_kind=source_kind,
            enabled=bool(enabled),
        )

    def get_floor(
        self,
        resource_id: str,
        gpu_count: int,
        duration_seconds: int,
        settlement_unit_scale: int,
        block_identifier: int | str | None = None,
    ) -> int:
        """Fetch the on-chain energy floor for the given rental terms.

        The Python ``compute_energy_net_units`` should produce the same value;
        this view is a cross-check against the contract.
        """
        result = self._call(
            "getEnergyFloor",
            resource_id,
            gpu_count,
            duration_seconds,
            settlement_unit_scale,
            block_identifier=block_identifier,
        )
        if not isinstance(result, tuple | list) or len(result) < 3:
            raise EnergyOracleError(f"unexpected getEnergyFloor return: {result}")
        net_floor, valid, reason = result[:3]
        if not valid:
            raise EnergyOracleError(f"getEnergyFloor returned invalid: {reason}")
        return int(net_floor)

    def get_pinned_inputs(
        self,
        resource_id: str,
        block_identifier: int | str | None = None,
    ) -> tuple[EnergyProfile, EnergyRate, int, str]:
        """Return profile, rate, and pinned block number/hash at the same block."""
        block_number, block_hash = self._resolve_block(block_identifier)
        # Use the resolved block number for the calls so they are guaranteed to
        # read the same state even if the chain advances during the batch.
        profile = self.get_profile(resource_id, block_identifier=block_number)
        rate = self.get_rate(block_identifier=block_number)
        return profile, rate, block_number, block_hash
