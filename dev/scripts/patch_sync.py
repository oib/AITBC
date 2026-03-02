with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/sync.py", "r") as f:
    content = f.read()

# Update _append_block
content = content.replace(
    """        block = Block(
            height=block_data["height"],
            hash=block_data["hash"],
            parent_hash=block_data["parent_hash"],
            proposer=block_data.get("proposer", "unknown"),
            timestamp=timestamp,
            tx_count=tx_count,
            state_root=block_data.get("state_root"),
        )""",
    """        block = Block(
            chain_id=self._chain_id,
            height=block_data["height"],
            hash=block_data["hash"],
            parent_hash=block_data["parent_hash"],
            proposer=block_data.get("proposer", "unknown"),
            timestamp=timestamp,
            tx_count=tx_count,
            state_root=block_data.get("state_root"),
        )"""
)

content = content.replace(
    """                tx = Transaction(
                    tx_hash=tx_data.get("tx_hash", ""),
                    block_height=block_data["height"],
                    sender=tx_data.get("sender", ""),
                    recipient=tx_data.get("recipient", ""),
                    payload=tx_data,
                )""",
    """                tx = Transaction(
                    chain_id=self._chain_id,
                    tx_hash=tx_data.get("tx_hash", ""),
                    block_height=block_data["height"],
                    sender=tx_data.get("sender", ""),
                    recipient=tx_data.get("recipient", ""),
                    payload=tx_data,
                )"""
)

# Update query in import_block
content = content.replace(
    """            # Check if block already exists
            existing = session.exec(
                select(Block).where(Block.hash == block_hash)
            ).first()""",
    """            # Check if block already exists
            existing = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == block_hash)
            ).first()"""
)

content = content.replace(
    """            # Get our chain head
            our_head = session.exec(
                select(Block).order_by(Block.height.desc()).limit(1)
            ).first()""",
    """            # Get our chain head
            our_head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(Block.height.desc()).limit(1)
            ).first()"""
)

content = content.replace(
    """                parent_exists = session.exec(
                    select(Block).where(Block.hash == parent_hash)
                ).first()""",
    """                parent_exists = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)
                ).first()"""
)

content = content.replace(
    """                existing_at_height = session.exec(
                    select(Block).where(Block.height == height)
                ).first()""",
    """                existing_at_height = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.height == height)
                ).first()"""
)

# Update get_sync_status
content = content.replace(
    """            head = session.exec(
                select(Block).order_by(Block.height.desc()).limit(1)
            ).first()

            total_blocks = session.exec(select(Block)).all()
            total_txs = session.exec(select(Transaction)).all()""",
    """            head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(Block.height.desc()).limit(1)
            ).first()

            total_blocks = session.exec(select(Block).where(Block.chain_id == self._chain_id)).all()
            total_txs = session.exec(select(Transaction).where(Transaction.chain_id == self._chain_id)).all()"""
)

# Update _resolve_fork queries
content = content.replace(
    """        blocks_to_remove = session.exec(
            select(Block).where(Block.height >= fork_height).order_by(Block.height.desc())
        ).all()""",
    """        blocks_to_remove = session.exec(
            select(Block).where(Block.chain_id == self._chain_id).where(Block.height >= fork_height).order_by(Block.height.desc())
        ).all()"""
)

content = content.replace(
    """            old_txs = session.exec(
                select(Transaction).where(Transaction.block_height == old_block.height)
            ).all()""",
    """            old_txs = session.exec(
                select(Transaction).where(Transaction.chain_id == self._chain_id).where(Transaction.block_height == old_block.height)
            ).all()"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/sync.py", "w") as f:
    f.write(content)
