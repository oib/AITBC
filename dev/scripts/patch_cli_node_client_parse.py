import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "r") as f:
    content = f.read()

# Fix _parse_chain_info to look for 'id' instead of 'chain_id' to match our mock data above
content = content.replace(
    """        return ChainInfo(
            id=chain_data["chain_id"],""",
    """        return ChainInfo(
            id=chain_data.get("chain_id", chain_data.get("id", "unknown")),"""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "w") as f:
    f.write(content)
