# Blockchain Node

## Purpose & Scope

Minimal asset-backed blockchain node that validates compute receipts and mints AIT tokens as described in `docs/bootstrap/blockchain_node.md`.

## Status

Scaffolded. Implementation pending per staged roadmap.

## Devnet Tooling

- `scripts/make_genesis.py` — Generate a deterministic devnet genesis file (`data/devnet/genesis.json`).
- `scripts/keygen.py` — Produce throwaway devnet keypairs (printed or written to disk).
- `scripts/devnet_up.sh` — Launch the blockchain node and RPC API with a freshly generated genesis file.

### Quickstart

```bash
cd apps/blockchain-node
python scripts/make_genesis.py --force
bash scripts/devnet_up.sh
```

The script sets `PYTHONPATH=src` and starts the proposer loop plus the FastAPI app (via `uvicorn`). Press `Ctrl+C` to stop the devnet.
