import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/client.py", "r") as f:
    content = f.read()

# Fix receipts endpoint
content = content.replace(
    """f"{config.coordinator_url}/v1/explorer/receipts",""",
    """f"{config.coordinator_url}/v1/receipts","""
)

# Fix jobs history endpoint (may not exist, change to jobs endpoint with parameters if needed)
content = content.replace(
    """f"{config.coordinator_url}/v1/jobs/history",""",
    """f"{config.coordinator_url}/v1/jobs",""" # the admin API has GET /jobs for history
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/client.py", "w") as f:
    f.write(content)
