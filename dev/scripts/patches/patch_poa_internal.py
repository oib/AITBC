with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

import re

# Remove httpx import and the try/except block that checks localhost:8082/metrics
content = content.replace("import httpx\n", "")

bad_code = """        # Check RPC mempool for transactions
        try:
            response = httpx.get("http://localhost:8082/metrics")
            if response.status_code == 200:
                has_transactions = False
                for line in response.text.split("\\n"):
                    if line.startswith("mempool_size"):
                        size = float(line.split(" ")[1])
                        if size > 0:
                            has_transactions = True
                        break
                
                if not has_transactions:
                    return
        except Exception as exc:
            self._logger.error(f"Error checking RPC mempool: {exc}")
            return"""

good_code = """        # Check internal mempool
        from ..mempool import get_mempool
        if get_mempool().size(self._config.chain_id) == 0:
            return"""

content = content.replace(bad_code, good_code)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(content)
