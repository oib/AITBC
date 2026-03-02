import re

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "r") as f:
    content = f.read()

# Fix getBalance and address routes
content = content.replace("session.get(Account, address)", "session.get(Account, (chain_id, address))")
content = content.replace("session.get(Account, request.address)", "session.get(Account, (chain_id, request.address))")

# Also fix Account creation
content = content.replace("Account(address=request.address, balance=request.amount)", "Account(chain_id=chain_id, address=request.address, balance=request.amount)")

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "w") as f:
    f.write(content)
