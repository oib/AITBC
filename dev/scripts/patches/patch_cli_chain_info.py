with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/chain.py", "r") as f:
    content = f.read()

# Fix asyncio.run for chain_info
content = content.replace(
    """        chain_info = chain_manager.get_chain_info(chain_id, detailed, metrics)""",
    """        import asyncio
        chain_info = asyncio.run(chain_manager.get_chain_info(chain_id, detailed, metrics))"""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/chain.py", "w") as f:
    f.write(content)
