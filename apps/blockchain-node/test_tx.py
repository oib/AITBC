from aitbc_chain.database import session_scope
from aitbc_chain.models import Account

with session_scope() as session:
    acc = session.get(Account, ("ait-mainnet", "aitbc1genesis"))
    print(acc.address, acc.balance)
