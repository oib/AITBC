with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "r") as f:
    lines = f.readlines()

# Indentation of async def get_chain_info
# Let's just fix it completely manually.
for i, line in enumerate(lines):
    if line.startswith("    async def get_chain_info"):
        lines[i] = "    async def get_chain_info(self, chain_id: str) -> Optional[ChainInfo]:\n"
        break

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "w") as f:
    f.writelines(lines)
