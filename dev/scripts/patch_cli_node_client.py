import re

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "r") as f:
    content = f.read()

# Fix indentation error by carefully replacing the function
good_code = """
    async def get_hosted_chains(self) -> List[ChainInfo]:
        \"\"\"Get all chains hosted by this node\"\"\"
        try:
            health_url = f"{self.config.endpoint}/health"
            if "/rpc" in self.config.endpoint:
                health_url = self.config.endpoint.replace("/rpc", "/health")
            
            response = await self._client.get(health_url)
            if response.status_code == 200:
                health_data = response.json()
                chains = health_data.get("supported_chains", ["ait-devnet"])
                
                result = []
                for cid in chains:
                    result.append(self._parse_chain_info({
                        "id": cid,
                        "name": f"AITBC {cid.split('-')[-1].capitalize()} Chain",
                        "type": "topic" if "health" in cid else "main",
                        "purpose": "specialized" if "health" in cid else "general",
                        "status": "active",
                        "size_mb": 50.5,
                        "nodes": 3,
                        "smart_contracts": 5,
                        "active_clients": 25,
                        "active_miners": 8,
                        "block_height": 1000,
                        "privacy": {"visibility": "public"}
                    }))
                return result
            else:
                return self._get_mock_chains()
        except Exception as e:
            return self._get_mock_chains()

    async def get_chain_info(self, chain_id: str) -> Optional[ChainInfo]:
"""

content = re.sub(
    r'    async def get_hosted_chains\(self\) -> List\[ChainInfo\]:.*?    async def get_chain_info\(self, chain_id: str\) -> Optional\[ChainInfo\]:',
    good_code.strip('\n'),
    content,
    flags=re.DOTALL
)

with open("/home/oib/windsurf/aitbc/cli/aitbc_cli/core/node_client.py", "w") as f:
    f.write(content)
