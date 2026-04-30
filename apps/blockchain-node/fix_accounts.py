from aitbc_chain.database import session_scope, init_db
from aitbc_chain.models import Account
from datetime import datetime, UTC

def fix():
    init_db()
    with session_scope() as session:
        acc = Account(chain_id="ait-mainnet", address="aitbc1genesis", balance=10000000, nonce=0, updated_at=datetime.now(datetime.UTC), account_type="regular", metadata="{}")
        session.merge(acc)
        session.commit()
        print("Added aitbc1genesis to mainnet")

if __name__ == "__main__":
    fix()
