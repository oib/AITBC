from aitbc_chain.config import settings
from aitbc_chain.mempool import init_mempool, get_mempool
init_mempool(backend=settings.mempool_backend, db_path=str(settings.db_path.parent / "mempool.db"), max_size=settings.mempool_max_size, min_fee=settings.min_fee)
pool = get_mempool()
print(pool.__class__.__name__)
