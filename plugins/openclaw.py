"""OpenClaw white-label plugin."""

from aitbc_agent_core.branding import BrandSettings
from aitbc_agent_core.roles import Role

brand = BrandSettings(
    name="OpenClaw",
    token_symbol="CLAW",
    token_name="OpenClaw Token",
    network_name="OpenClaw Network",
    dao_name="OpenClaw DAO",
    wallet_name="OpenClaw Wallet",
    explorer_name="OpenClaw Explorer",
)

roles = {
    Role.PROVIDER: "Compute Provider",
    Role.CONSUMER: "Task Consumer",
    Role.VALIDATOR: "Validator",
    Role.ARBITER: "Arbiter",
}

identity_method = "did:openclaw"
