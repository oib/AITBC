import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/client.py", "r") as f:
    content = f.read()

# Fix blocks endpoint to /explorer/blocks
content = content.replace(
    """f"{config.coordinator_url}/blocks",""",
    """f"{config.coordinator_url}/explorer/blocks","""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/client.py", "w") as f:
    f.write(content)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "r") as f:
    content = f.read()

# Fix blockchain endpoints
content = content.replace(
    """f"{config.coordinator_url}/blocks",""",
    """f"{config.coordinator_url}/explorer/blocks","""
)
content = content.replace(
    """f"{config.coordinator_url}/blocks/{block_hash}",""",
    """f"{config.coordinator_url}/explorer/blocks/{block_hash}","""
)
content = content.replace(
    """f"{config.coordinator_url}/transactions/{tx_hash}",""",
    """f"{config.coordinator_url}/explorer/transactions/{tx_hash}","""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "w") as f:
    f.write(content)

