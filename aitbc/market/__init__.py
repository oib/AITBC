"""AITBC market shared utilities (v0.6.6).

Provides:
- OfferFSM: formal offer state machine with validated transitions
- OfferStatus: offer lifecycle status enum
- BlockchainRPCClient: chain-aware blockchain RPC client for market operations
- EnergyPricing: pure energy-cost floor arithmetic and quote schema
- EVMEnergyOracle: pinned-block EVM input reader for energy quotes
"""

from __future__ import annotations

from .blockchain_rpc import BlockchainRPCClient
from .energy_oracle import DEFAULT_ENERGY_PRICING_ABI, EnergyOracleError, EVMEnergyOracle
from .energy_pricing import (
    EnergyPricingError,
    EnergyProfile,
    EnergyQuote,
    EnergyRate,
    FeeModel,
    FeePolicy,
    FundingBreakdown,
    QuoteResult,
    RefusalCode,
    SettlementRoute,
    build_minimum_quote,
    compute_energy_net_units,
    compute_evm_buyer_charge,
    compute_funding_breakdown,
    compute_native_gross_units,
    compute_provider_credit_native,
    evaluate_quote,
    to_scaled,
)
from .job_routing import is_market_ipfs_escrow_rail
from .offer_fsm import OfferFSM, OfferStatus

__all__ = [
    "BlockchainRPCClient",
    "DEFAULT_ENERGY_PRICING_ABI",
    "EnergyOracleError",
    "EnergyPricingError",
    "EnergyProfile",
    "EnergyQuote",
    "EnergyRate",
    "EVMEnergyOracle",
    "FeeModel",
    "FeePolicy",
    "FundingBreakdown",
    "is_market_ipfs_escrow_rail",
    "OfferFSM",
    "OfferStatus",
    "QuoteResult",
    "RefusalCode",
    "SettlementRoute",
    "build_minimum_quote",
    "compute_energy_net_units",
    "compute_evm_buyer_charge",
    "compute_funding_breakdown",
    "compute_native_gross_units",
    "compute_provider_credit_native",
    "evaluate_quote",
    "to_scaled",
]
