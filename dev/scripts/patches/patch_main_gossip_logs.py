import re

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "r") as f:
    content = f.read()

content = content.replace(
    """                    block_data = await block_sub.queue.get()
                    if isinstance(block_data, str):""",
    """                    block_data = await block_sub.queue.get()
                    logger.info(f"Received block from gossip")
                    if isinstance(block_data, str):"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "w") as f:
    f.write(content)
