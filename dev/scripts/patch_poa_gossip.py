import re

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

content = content.replace(
    """            await gossip_broker.publish(
                "blocks",
                {
                    "height": block.height,
                    "hash": block.hash,
                    "parent_hash": block.parent_hash,
                    "proposer": block.proposer,
                    "timestamp": block.timestamp.isoformat(),
                    "tx_count": block.tx_count,
                    "state_root": block.state_root,
                }
            )""",
    """            await gossip_broker.publish(
                "blocks",
                {
                    "chain_id": self._config.chain_id,
                    "height": block.height,
                    "hash": block.hash,
                    "parent_hash": block.parent_hash,
                    "proposer": block.proposer,
                    "timestamp": block.timestamp.isoformat(),
                    "tx_count": block.tx_count,
                    "state_root": block.state_root,
                }
            )"""
)

content = content.replace(
    """            await gossip_broker.publish(
                "blocks",
                {
                    "height": genesis.height,
                    "hash": genesis.hash,
                    "parent_hash": genesis.parent_hash,
                    "proposer": genesis.proposer,
                    "timestamp": genesis.timestamp.isoformat(),
                    "tx_count": genesis.tx_count,
                    "state_root": genesis.state_root,
                }
            )""",
    """            await gossip_broker.publish(
                "blocks",
                {
                    "chain_id": self._config.chain_id,
                    "height": genesis.height,
                    "hash": genesis.hash,
                    "parent_hash": genesis.parent_hash,
                    "proposer": genesis.proposer,
                    "timestamp": genesis.timestamp.isoformat(),
                    "tx_count": genesis.tx_count,
                    "state_root": genesis.state_root,
                }
            )"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(content)
