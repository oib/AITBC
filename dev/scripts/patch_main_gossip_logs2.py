import re

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "r") as f:
    content = f.read()

content = content.replace(
    """                    block_data = await block_sub.queue.get()
                    logger.info(f"Received block from gossip")
                    if isinstance(block_data, str):
                        import json
                        block_data = json.loads(block_data)
                    chain_id = block_data.get("chain_id", "ait-devnet")
                    sync = ChainSync(session_factory=session_scope, chain_id=chain_id)
                    sync.import_block(block_data)
                except Exception as exc:""",
    """                    block_data = await block_sub.queue.get()
                    logger.info(f"Received block from gossip")
                    if isinstance(block_data, str):
                        import json
                        block_data = json.loads(block_data)
                    chain_id = block_data.get("chain_id", "ait-devnet")
                    logger.info(f"Importing block for chain {chain_id}: {block_data.get('height')}")
                    sync = ChainSync(session_factory=session_scope, chain_id=chain_id)
                    res = sync.import_block(block_data)
                    logger.info(f"Import result: accepted={res.accepted}, reason={res.reason}")
                except Exception as exc:"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/main.py", "w") as f:
    f.write(content)
