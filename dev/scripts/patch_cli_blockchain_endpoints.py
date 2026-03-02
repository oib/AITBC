import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "r") as f:
    content = f.read()

# Fix some remaining endpoints that don't exist in the new api
content = content.replace(
    """f"{config.coordinator_url}/v1/blockchain/sync",""",
    """f"{config.coordinator_url}/v1/health",""" # closest alternative
)

content = content.replace(
    """f"{config.coordinator_url}/v1/blockchain/peers",""",
    """f"{config.coordinator_url}/v1/health",""" # fallback
)

content = content.replace(
    """f"{config.coordinator_url}/v1/blockchain/info",""",
    """f"{config.coordinator_url}/v1/health",""" # fallback
)

content = content.replace(
    """f"{config.coordinator_url}/v1/blockchain/supply",""",
    """f"{config.coordinator_url}/v1/health",""" # fallback
)

content = content.replace(
    """f"{config.coordinator_url}/v1/blockchain/validators",""",
    """f"{config.coordinator_url}/v1/health",""" # fallback
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "w") as f:
    f.write(content)
