with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/chain.py", "r") as f:
    content = f.read()

import re

# Fix asyncio issues by wrapping in asyncio.run
content = content.replace(
    """        # Get chains
        chains = chain_manager.list_chains(
            chain_type=ChainType(chain_type) if chain_type != 'all' else None,
            include_private=show_private,
            sort_by=sort
        )""",
    """        # Get chains
        import asyncio
        chains = asyncio.run(chain_manager.list_chains(
            chain_type=ChainType(chain_type) if chain_type != 'all' else None,
            include_private=show_private,
            sort_by=sort
        ))"""
)

content = content.replace(
    """        # Get chain info
        chain_info = chain_manager.get_chain_info(chain_id)""",
    """        # Get chain info
        import asyncio
        chain_info = asyncio.run(chain_manager.get_chain_info(chain_id))"""
)

content = content.replace(
    """        # Get monitoring data
        stats = chain_manager.monitor_chain(chain_id, duration)""",
    """        # Get monitoring data
        import asyncio
        stats = asyncio.run(chain_manager.monitor_chain(chain_id, duration))"""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/chain.py", "w") as f:
    f.write(content)
