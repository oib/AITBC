with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/node.py", "r") as f:
    content = f.read()

import re

# Fix asyncio issues by wrapping in asyncio.run
content = content.replace(
    """        # Get node info
        node_info = chain_manager.get_node_info(node_id)""",
    """        # Get node info
        import asyncio
        node_info = asyncio.run(chain_manager.get_node_info(node_id))"""
)

content = content.replace(
    """        # Get chains from all nodes
        all_chains = chain_manager.list_hosted_chains()""",
    """        # Get chains from all nodes
        import asyncio
        all_chains = asyncio.run(chain_manager.list_hosted_chains())"""
)

content = content.replace(
    """        # Verify connection
        node_info = chain_manager.get_node_info(node_id)""",
    """        # Verify connection
        import asyncio
        node_info = asyncio.run(chain_manager.get_node_info(node_id))"""
)

content = content.replace(
    """        # Monitor node
        stats = chain_manager.monitor_node(node_id, duration)""",
    """        # Monitor node
        import asyncio
        stats = asyncio.run(chain_manager.monitor_node(node_id, duration))"""
)

content = content.replace(
    """        # Run diagnostics
        result = chain_manager.test_node_connectivity(node_id)""",
    """        # Run diagnostics
        import asyncio
        result = asyncio.run(chain_manager.test_node_connectivity(node_id))"""
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/node.py", "w") as f:
    f.write(content)
