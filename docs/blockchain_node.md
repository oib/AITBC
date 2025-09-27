# Blockchain Node – Task Breakdown

## Status (2025-09-27)

- **Stage 1**: Design and scaffolding remain TODO; no implementation committed yet. Coordinator receipts now include historical persistence and attestations, so blockchain receipt ingestion should align with this schema when development begins.


## Stage 1 (MVP)

- **Project Scaffolding**
  - Create `apps/blockchain-node/src/` module layout (`types.py`, `state.py`, `blocks.py`, `mempool.py`, `consensus.py`, `rpc.py`, `p2p.py`, `receipts.py`, `settings.py`).
  - Add `requirements.txt` with FastAPI, SQLModel, websockets, orjson, python-dotenv.
  - Provide `.env.example` with `CHAIN_ID`, `DB_PATH`, bind addresses, proposer key.

- **State & Persistence**
  - Implement SQLModel tables for blocks, transactions, accounts, receipts, peers, params.
  - Set up database initialization and genesis loading.
  - Provide migration or reset script under `scripts/`.

- **RPC Layer**
  - Build FastAPI app exposing `/rpc/*` endpoints (sendTx, getTx, getBlock, getHead, getBalance, submitReceipt, metrics).
  - Implement admin endpoints for devnet (`mintFaucet`, `paramSet`, `peers/add`).

- **Consensus & Block Production**
  - Implement PoA proposer loop producing blocks at fixed interval.
  - Integrate mempool selection, receipt validation, and block broadcasting.
  - Add basic P2P gossip (websocket) for blocks/txs.

- **Receipts & Minting**
  - Wire `receipts.py` to coordinator attestation mock.
  - Mint tokens to miners based on compute_units with configurable ratios.

- **Devnet Tooling**
  - Provide `scripts/devnet_up.sh` launching bootstrap node and mocks.
  - Document curl commands for faucet, transfer, receipt submission.

## Stage 2+

- Upgrade consensus to compute-backed proof (CBP) with work score weighting.
- Introduce staking/slashing, replace SQLite with PostgreSQL, add snapshots/fast sync.
- Implement light client support and metrics dashboard.
