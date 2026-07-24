"""White-label brand manifest for AITBC deployments (v0.16.2 §B2).

ponytail: This is a static manifest schema. A real white-label deployment would
persist manifests in the coordinator-api database and serve them via an admin API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrandAssets:
    """Brand visual assets."""

    logo_url: str = ""
    favicon_url: str = ""
    primary_color: str = "#000000"
    secondary_color: str = "#ffffff"


@dataclass
class SettlementRules:
    """White-label settlement configuration."""

    default_asset: str = ""
    min_bond_amount: str = "0"
    platform_fee_basis_points: int = 0
    disbursement_delay_blocks: int = 0


@dataclass
class BrandManifest:
    """A complete white-label brand manifest."""

    brand_id: str = ""
    name: str = ""
    domain: str = ""
    assets: BrandAssets = field(default_factory=BrandAssets)
    endpoints: dict[str, str] = field(default_factory=dict)
    settlement: SettlementRules = field(default_factory=SettlementRules)
    features: dict[str, bool] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the manifest to a JSON-compatible dictionary."""
        return {
            "brand_id": self.brand_id,
            "name": self.name,
            "domain": self.domain,
            "assets": {
                "logo_url": self.assets.logo_url,
                "favicon_url": self.assets.favicon_url,
                "primary_color": self.assets.primary_color,
                "secondary_color": self.assets.secondary_color,
            },
            "endpoints": self.endpoints,
            "settlement": {
                "default_asset": self.settlement.default_asset,
                "min_bond_amount": self.settlement.min_bond_amount,
                "platform_fee_basis_points": self.settlement.platform_fee_basis_points,
                "disbursement_delay_blocks": self.settlement.disbursement_delay_blocks,
            },
            "features": self.features,
            "meta": self.meta,
        }
