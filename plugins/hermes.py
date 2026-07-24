"""Hermes white-label plugin."""

from aitbc_agent_core.branding import BrandSettings
from aitbc_agent_core.roles import Role

brand = BrandSettings(
    name="Hermes",
    token_symbol="HMS",
    token_name="Hermes Token",
    network_name="Hermes Network",
    dao_name="Hermes DAO",
    wallet_name="Hermes Wallet",
    explorer_name="Hermes Explorer",
)

roles = {
    Role.PROVIDER: "Provider",
    Role.CONSUMER: "Consumer",
    Role.VALIDATOR: "Validator",
    Role.ARBITER: "Arbiter",
}

identity_method = "did:hermes"
