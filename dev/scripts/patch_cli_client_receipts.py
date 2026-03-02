import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/client.py", "r") as f:
    content = f.read()

# Fix explorer receipts endpoint
content = content.replace(
    """f"{config.coordinator_url}/receipts",""",
    """f"{config.coordinator_url}/explorer/receipts","""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/client.py", "w") as f:
    f.write(content)

