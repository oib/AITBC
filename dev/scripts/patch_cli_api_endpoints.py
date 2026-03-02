import re

# Update blockchain.py endpoints
with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "r") as f:
    content = f.read()

# Fix blockchain blocks endpoint (Coordinator API uses /v1/explorer/blocks, but maybe it requires correct params)
# Wait, looking at explorer.py: `/blocks` is under the `explorer` router, which is mapped to `/v1/explorer` in main.py?
# Let's check main.py for explorer prefix. Yes: `app.include_router(explorer, prefix="/v1")` 
# Wait, `app.include_router(explorer, prefix="/v1")` means `/v1/blocks` not `/v1/explorer/blocks`.
content = content.replace(
    """f"{config.coordinator_url}/v1/explorer/blocks",""",
    """f"{config.coordinator_url}/v1/blocks","""
)

content = content.replace(
    """f"{config.coordinator_url}/v1/explorer/blocks/{block_hash}",""",
    """f"{config.coordinator_url}/v1/blocks/{block_hash}","""
)

content = content.replace(
    """f"{config.coordinator_url}/v1/explorer/transactions/{tx_hash}",""",
    """f"{config.coordinator_url}/v1/transactions/{tx_hash}","""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "w") as f:
    f.write(content)

# Update client.py endpoints
with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/client.py", "r") as f:
    content = f.read()

content = content.replace(
    """f"{config.coordinator_url}/v1/explorer/blocks",""",
    """f"{config.coordinator_url}/v1/blocks","""
)
content = content.replace(
    """f"{config.coordinator_url}/v1/jobs",""",
    """f"{config.coordinator_url}/v1/jobs",""" # Assuming this is correct, but let's check
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/client.py", "w") as f:
    f.write(content)

