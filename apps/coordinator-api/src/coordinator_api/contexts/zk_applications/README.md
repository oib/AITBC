# zk_applications

Zero-knowledge applications — ZK proofs for ML and verifiable computation.

## Domain Models

- None (stub)

## Routes

From `ml_zk_proofs.py` (mounted at `/v1/ml-zk` when its deps import) and
`fhe.py` (`/v1/fhe`, gated on `settings.fhe_enabled`):

- POST /prove/training
- POST /verify/training
- POST /prove/modular
- POST /verify/inference
- POST /fhe/inference
- GET /circuits

From `zk_applications.py` — **unmounted, 404** (imported in
`routers/__init__.py` but never `include_router`'d in main.py):

- POST /zk/identity/commit
- POST /zk/membership/verify
- POST /zk/market/private-bid
- POST /zk/computation/verify
- POST /zk/receipt/attest
- GET /zk/anonymity/sets
- POST /zk/stealth/address
- GET /zk/status

## Services

- None (stub)
