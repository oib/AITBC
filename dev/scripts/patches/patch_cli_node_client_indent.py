with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.startswith("async def get_hosted_chains"):
        lines[i] = "    " + line

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "w") as f:
    f.writelines(lines)
