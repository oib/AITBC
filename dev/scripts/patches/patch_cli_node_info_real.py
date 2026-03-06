import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "r") as f:
    content = f.read()

# We need to change get_chain_info to also fetch the real block height
new_get_chain_info = """    async def get_chain_info(self, chain_id: str) -> Optional[ChainInfo]:
        \"\"\"Get specific chain information\"\"\"
        try:
            # Re-use the health endpoint logic
            health_url = f"{self.config.endpoint}/health"
            if "/rpc" in self.config.endpoint:
                health_url = self.config.endpoint.replace("/rpc", "/health")
                
            response = await self._client.get(health_url)
            if response.status_code == 200:
                health_data = response.json()
                chains = health_data.get("supported_chains", ["ait-devnet"])
                if chain_id in chains:
                    block_height = 0
                    try:
                        head_url = f"{self.config.endpoint}/rpc/head?chain_id={chain_id}"
                        if "/rpc" in self.config.endpoint:
                            head_url = f"{self.config.endpoint}/head?chain_id={chain_id}"
                        head_resp = await self._client.get(head_url, timeout=2.0)
                        if head_resp.status_code == 200:
                            head_data = head_resp.json()
                            block_height = head_data.get("height", 0)
                    except Exception:
                        pass
                        
                    return self._parse_chain_info({
                        "id": chain_id,
                        "name": f"AITBC {chain_id.split('-')[-1].capitalize()} Chain",
                        "type": "topic" if "health" in chain_id else "main",
                        "purpose": "specialized" if "health" in chain_id else "general",
                        "status": "active",
                        "size_mb": 50.5,
                        "nodes": 3,
                        "smart_contracts": 5,
                        "active_clients": 25,
                        "active_miners": 8,
                        "block_height": block_height,
                        "privacy": {"visibility": "public"}
                    })
            return None
        except Exception as e:
            # Fallback to pure mock
            chains = self._get_mock_chains()
            for chain in chains:
                if chain.id == chain_id:
                    return chain
            return None"""

content = re.sub(
    r'    async def get_chain_info\(self, chain_id: str\) -> Optional\[ChainInfo\]:.*?    async def create_chain',
    new_get_chain_info + '\n\n    async def create_chain',
    content,
    flags=re.DOTALL
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "w") as f:
    f.write(content)
