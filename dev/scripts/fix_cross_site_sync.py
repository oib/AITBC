with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/sync.py", "r") as f:
    content = f.read()

# Update get_sync_status to also return supported_chains
content = content.replace(
    """        return {
            "chain_id": self._chain_id,
            "head_height": head.height if head else -1,""",
    """        return {
            "chain_id": self._chain_id,
            "head_height": head.height if head else -1,"""
)

# And in sync.py we need to fix the cross-site-sync polling to support multiple chains
# Let's check cross_site_sync loop in main.py
