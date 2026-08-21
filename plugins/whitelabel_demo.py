"""Sample white-label brand plugin for AITBC."""

from aitbc_agent_core.branding import BrandSettings

brand = BrandSettings(
    name="DemoHub",
    token_symbol="DEMO",
    token_name="Demo Token",
    network_name="Demo Network",
    dao_name="Demo DAO",
    wallet_name="Demo Wallet",
    explorer_name="Demo Explorer",
)

roles = {
    "Provider": "demo-provider",
    "Consumer": "demo-customer",
    "Validator": "demo-validator",
    "Arbiter": "demo-arbiter",
}

identity_method = "did:demo"
