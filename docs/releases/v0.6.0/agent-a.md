# v0.6.0 Database & Network Optimization — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Fix the `BlockchainCache` type mismatch, add an in-process block header cache, create a shared async HTTP connection pool, add a compression utility, and add benchmarking helpers. All consumed by Agent B.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/ && ./venv/bin/python -m ruff check aitbc/ && ./venv/bin/python -m pytest tests/unit -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Fix `BlockchainCache` — `chain_id: int` → `str`, add `get_block_by_hash`/`set_block_by_hash`, fix `block_number` → `height` naming | 🔴 P0 | `aitbc/caching/blockchain_cache.py` | ✅ |
| A2 | Add in-process `BlockHeaderCache` (LRU, no Redis dependency) for hot-path block header access | High | `aitbc/caching/block_header_cache.py` (new), `aitbc/caching/__init__.py` | ✅ |
| A3 | Add shared async HTTP connection pool — reusable `httpx.AsyncClient` singleton with configurable pool limits | High | `aitbc/network/http_pool.py` (new), `aitbc/network/__init__.py` | ✅ |
| A4 | Add compression utility — gzip + zstd helpers for network payloads | Medium | `aitbc/network/compression.py` (new), `aitbc/network/__init__.py` | ✅ |
| A5 | Add benchmarking helpers — context managers for timing DB queries, network transfers, cache hits/misses | Medium | `aitbc/benchmark.py` (new) | ✅ |
| A6 | Unit tests for A1–A4 | High | `tests/unit/test_blockchain_cache.py`, `tests/unit/test_block_header_cache.py`, `tests/unit/test_http_pool.py`, `tests/unit/test_compression.py` | ✅ |
| A7 | Verify mypy + ruff clean across all new/modified files | Medium | — | ✅ |

---

## A1: Fix BlockchainCache typing + add block-by-hash

- **Problem**: `BlockchainCache` types `chain_id` as `int` throughout (lines 40, 44, 48, 52, 57, 65, 72, 79, 86, 93, 100, 107, 117, 127, 137). The codebase uses `chain_id: str` (e.g., `"ait-hub"`, `"ait-island1"`). The cache is unusable as-is.
- **Fix**: Change all `chain_id: int` → `chain_id: str` in `blockchain_cache.py`. Update `generate_block_key` to accept `height: int` (rename from `block_number`). Add `get_block_by_hash(hash: str, chain_id: str)` / `set_block_by_hash(hash: str, chain_id: str, block_data: Any)` methods — the codebase frequently looks up blocks by hash, not just height.
- **Verify**: `mypy aitbc/caching/` clean. `pytest tests/unit/test_blockchain_cache.py` passes.

---

## A2: In-process BlockHeaderCache

- **Problem**: `BlockchainCache` requires Redis. The block import hot path needs a fast in-process cache for recently-seen block headers (no Redis round-trip per block).
- **Fix**: Create `aitbc/caching/block_header_cache.py` with a `BlockHeaderCache` class:
  - LRU eviction (configurable max size, default 1000)
  - Per-chain namespaces (key = `chain_id:height` and `chain_id:hash`)
  - `get(height, chain_id)`, `get_by_hash(hash, chain_id)`, `set(header, chain_id)`, `invalidate(chain_id, height)`
  - Thread-safe (asyncio lock or simple dict — blockchain-node is single-threaded for block processing)
- Export from `aitbc/caching/__init__.py` as `BlockHeaderCache`.
- **Verify**: Unit test: insert 100 headers, verify LRU evicts oldest, verify per-chain isolation.

---

## A3: Shared async HTTP connection pool

- **Problem**: 6 files in blockchain-node create `httpx.AsyncClient` per-request (no connection reuse). Agent B will replace them, but needs a shared pool utility to wire up.
- **Fix**: Create `aitbc/network/http_pool.py` with:
  ```python
  class SharedHttpClient:
      """Singleton async HTTP client with connection pooling."""
      def __init__(self, max_connections: int = 100, max_keepalive: int = 20, timeout: float = 30.0): ...
      async def get(self, url, **kwargs) -> httpx.Response: ...
      async def post(self, url, **kwargs) -> httpx.Response: ...
      async def close(self): ...
  ```
  - Uses a single `httpx.AsyncClient` with `httpx.Limits(max_connections=..., max_keepalive_connections=...)`
  - Lazy-init: client created on first use, reused thereafter
  - Export from `aitbc/network/__init__.py`
- **Verify**: Unit test: two `get()` calls reuse the same underlying client (mock the transport).

---

## A4: Compression utility

- **Problem**: Zero compression for block/tx propagation. JSON payloads are large.
- **Fix**: Create `aitbc/network/compression.py` with:
  ```python
  def compress(data: bytes | str, algorithm: str = "gzip") -> bytes: ...
  def decompress(data: bytes, algorithm: str = "gzip") -> bytes: ...
  def compress_json(obj: Any, algorithm: str = "gzip") -> bytes: ...
  def decompress_json(data: bytes, algorithm: str = "gzip") -> Any: ...
  ```
  - Support `gzip` (stdlib `gzip`) and `zstd` (if `zstandard` package available, else fall back to gzip)
  - `compress_json`: `json.dumps(separators=(",", ":"))` → encode → compress
  - `decompress_json`: decompress → decode → `json.loads`
  - Export from `aitbc/network/__init__.py`
- **Verify**: Unit test: compress/decompress round-trip, verify compressed size < raw size for typical block JSON.

---

## A5: Benchmarking helpers

- Create `aitbc/benchmark.py` with:
  ```python
  @contextmanager
  def timed(label: str): ...  # logs elapsed time

  class QueryTimer: ...  # accumulates DB query times

  class CacheMetrics: ...  # tracks hit/miss counts
  ```
- Keep it simple — no external dependencies. Used by Agent B's benchmarks (B8).

---

## A6: Unit tests

- `tests/unit/test_blockchain_cache.py` — A1: chain_id as str, block-by-hash, invalidation
- `tests/unit/test_block_header_cache.py` — A2: LRU eviction, per-chain isolation, get/set
- `tests/unit/test_http_pool.py` — A3: client reuse, lazy init, close
- `tests/unit/test_compression.py` — A4: round-trip, size reduction, JSON variants

---

## A7: Verify clean

- `mypy aitbc/` — 0 errors
- `ruff check aitbc/` — 0 errors
- `pytest tests/unit -q` — all pass

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.0 — Database & Network Optimization
**Agent**: Agent A (Shared Core)
