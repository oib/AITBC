import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/node.py", "r") as f:
    content = f.read()

# Add --node-id to node chains
new_chains_def = """@node.command()
@click.option('--show-private', is_flag=True, help='Show private chains')
@click.option('--node-id', help='Specific node ID to query')
@click.pass_context
def chains(ctx, show_private, node_id):
    \"\"\"List chains hosted on all nodes\"\"\"
    try:
        config = load_multichain_config()
        
        all_chains = []
        
        import asyncio
        
        async def get_all_chains():
            tasks = []
            for nid, node_config in config.nodes.items():
                if node_id and nid != node_id:
                    continue
                async def get_chains_for_node(nid, nconfig):"""

content = re.sub(
    r'@node.command\(\)\n@click.option\(\'--show-private\'.*?async def get_chains_for_node\(nid, nconfig\):',
    new_chains_def,
    content,
    flags=re.DOTALL
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/commands/node.py", "w") as f:
    f.write(content)
