from aitbc_chain.config import settings
import sys
print(settings.db_path.parent / "mempool.db")
