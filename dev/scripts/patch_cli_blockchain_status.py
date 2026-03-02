with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "r") as f:
    content = f.read()

# Fix the node status endpoints to reflect the new architecture
# Node 1 on container is at localhost:8082 but the endpoint is /rpc/head or /health, and it expects a chain_id.
# Let's hit the health endpoint instead for status.
content = content.replace(
    """    try:
        with httpx.Client() as client:
            response = client.get(
                f"{rpc_url}/head",
                timeout=5
            )""",
    """    try:
        with httpx.Client() as client:
            # First get health for general status
            health_url = rpc_url.replace("/rpc", "") + "/health" if "/rpc" in rpc_url else rpc_url + "/health"
            response = client.get(
                health_url,
                timeout=5
            )"""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/blockchain.py", "w") as f:
    f.write(content)
