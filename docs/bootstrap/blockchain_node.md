# blockchain-node/ — Minimal Chain (asset-backed by compute)

## 0) TL;DR boot path for Windsurf
1. Create the service: `apps/blockchain-node` (Python, FastAPI, asyncio, uvicorn).
2. Data layer: `sqlite` via `SQLModel` (later: PostgreSQL).
3. P2P: WebSocket gossip (lib: `websockets`) with a simple overlay (peer table + heartbeats).
4. Consensus (MVP): **PoA single-author** (devnet) → upgrade to **Compute-Backed Proof (CBP)** after coordinator & miner telemetry are wired.
5. Block content: **ComputeReceipts** = “proofs of delivered AI work” signed by miners, plus standard transfers.
6. Minting: AIToken minted per verified compute unit (e.g., `1 AIT = 1,000 token-ops` — calibrate later).
7. REST RPC: `/rpc/*` for clients & coordinator; `/p2p/*` for peers; `/admin/*` for node ops.
8. Ship a `devnet` script that starts: 1 bootstrap node, 1 coordinator-api mock, 1 miner mock, 1 client demo.

---

## 1) Goal & Scope
- Provide a **minimal, testable blockchain node** that issues AITokens **only** when real compute was delivered (asset-backed).
- Easy to run, easy to reset, deterministic devnet.
- Strong boundaries so **coordinator-api** (job orchestration) and **miner-node** (workers) can integrate quickly.

Out of scope (MVP):
- Smart contracts VM.
- Sharding/advanced networking.
- Custodial wallets. (Use local keypairs for dev.)

---

## 2) Core Concepts

### 2.1 Actors
- **Client**: pays AITokens to request compute jobs.
- **Coordinator**: matches jobs ↔ miners; returns signed receipts.
- **Miner**: executes jobs; produces **ComputeReceipt** signed with miner key.
- **Blockchain Node**: validates receipts, mints AIT for miners, tracks balances, finalizes blocks.

### 2.2 Asset-Backed Minting
- Unit of account: **AIToken (AIT)**.
- A miner earns AIT when a **ComputeReceipt** is included in a block.
- A receipt is valid iff:
  1) Its `job_id` exists in coordinator logs,
  2) `client_payment_tx` covers the quoted price,
  3) `miner_sig` over `(job_id, hash(output_meta), compute_units, price, nonce)` is valid,
  4) Not previously claimed (`receipt_id` unique).

---

## 3) Minimal Architecture

```
blockchain-node/
  ├─ src/
  │  ├─ main.py                 # FastAPI entry
  │  ├─ p2p.py                  # WS gossip, peer table, block relay
  │  ├─ consensus.py            # PoA/CBP state machine
  │  ├─ types.py                # dataclasses / pydantic models
  │  ├─ state.py                # DB access (SQLModel), UTXO/Account
  │  ├─ mempool.py              # tx pool (transfers + receipts)
  │  ├─ crypto.py               # ed25519 keys, signatures, hashing
  │  ├─ receipts.py             # receipt validation (with coordinator)
  │  ├─ blocks.py               # block build/verify, difficulty stub
  │  ├─ rpc.py                  # REST/RPC routes for clients & ops
  │  └─ settings.py             # env config
  ├─ tests/
  │  └─ ...                     # unit & integration tests
  ├─ scripts/
  │  ├─ devnet_up.sh            # run bootstrap node + mocks
  │  └─ keygen.py               # create node/miner/client keys
  ├─ README.md
  └─ requirements.txt
```

---

## 4) Data Model (SQLModel)

### 4.1 Tables
- `blocks(id, parent_id, height, timestamp, proposer, tx_count, hash, state_root, sig)`
- `tx(id, block_id, type, payload_json, sender, nonce, fee, sig, hash, status)`
- `accounts(address, balance, nonce, pubkey)`
- `receipts(receipt_id, job_id, client_addr, miner_addr, compute_units, price, output_hash, miner_sig, status)`
- `peers(node_id, addr, last_seen, score)`
- `params(key, value)` — chain config (mint ratios, fee rate, etc.)

### 4.2 TX Types
- `TRANSFER`: move AIT from A → B
- `RECEIPT_CLAIM`: include a **ComputeReceipt**; mints to miner and settles client escrow
- `STAKE/UNSTAKE` (later)
- `PARAM_UPDATE` (PoA only, gated by admin key for devnet)

---

## 5) Block Format (JSON)
```json
{
  "parent": "<block_hash>",
  "height": 123,
  "timestamp": 1699999999,
  "proposer": "<node_address>",
  "txs": ["<tx_hash>", "..."],
  "stateRoot": "<merkle_root_after_block>",
  "sig": "<proposer_signature_over_header>"
}
```

Header sign bytes = `hash(parent|height|timestamp|proposer|stateRoot)`

---

## 6) Consensus

### 6.1 MVP: PoA (Single Author)
- One configured `PROPOSER_KEY` creates blocks at fixed interval (e.g., 2s).
- Honest mode only for devnet; finality by canonical longest/height rule.

### 6.2 Upgrade: **Compute-Backed Proof (CBP)**
- Each block’s **work score** = total `compute_units` in included receipts.
- Proposer election = weighted round-robin by recent work score and stake (later).
- Slashing: submitting invalid receipts reduces score; repeated offenses → temp ban.

---

## 7) Receipt Validation (Coordinator Check)

`receipts.py` performs:
1) **Coordinator attestation** (HTTP call to coordinator-api):
   - `/attest/receipt` with `job_id`, `client`, `miner`, `price`, `compute_units`, `output_hash`.
   - Returns `{exists: bool, paid: bool, not_double_spent: bool, quote: {...}}`.
2) **Signature check**: verify `miner_sig` with miner’s `pubkey`.
3) **Economic checks**: ensure `client_payment_tx` exists & covers `price + fee`.

> For devnet without live coordinator, ship a **mock** that returns deterministic attestation for known `job_id` ranges.

---

## 8) Fees & Minting

- **Fee model (MVP)**: `fee = base_fee + k * payload_size`.
- **Minting**:
  - Miner gets: `mint = compute_units * MINT_PER_UNIT`.
  - Coordinator gets: `coord_cut = mint * COORDINATOR_RATIO`.
  - Chain treasury (optional): small %, configurable in `params`.

---

## 9) RPC Surface (FastAPI)

### 9.1 Public
- `POST /rpc/sendTx` → `{txHash}`
- `GET  /rpc/getTx/{txHash}` → `{status, receipt}`
- `GET  /rpc/getBlock/{heightOrHash}`
- `GET  /rpc/getHead` → `{height, hash}`
- `GET  /rpc/getBalance/{address}` → `{balance, nonce}`
- `POST /rpc/estimateFee` → `{fee}`

### 9.2 Coordinator-facing
- `POST /rpc/submitReceipt` (alias of `sendTx` with type `RECEIPT_CLAIM`)
- `POST /rpc/attest` (devnet mock only)

### 9.3 Admin (devnet)
- `POST /admin/paramSet` (PoA only)
- `POST /admin/peers/add` `{addr}`
- `POST /admin/mintFaucet` `{address, amount}` (devnet)

### 9.4 P2P (WS)
- `GET  /p2p/peers` → list
- `WS   /p2p/ws` → subscribe to gossip: `{"type":"block"|"tx"|"peer","data":...}`

---

## 10) Keys & Crypto
- **ed25519** for account & node keys.
- Address = `bech32(hrp="ait", sha256(pubkey)[0:20])`.
- Sign bytes:
  - TX: `hash(type|sender|nonce|fee|payload_json_canonical)`
  - Block: header hash as above.

Ship `scripts/keygen.py` for dev use.

---

## 11) Mempool Rules
- Accept if:
  - `sig` valid,
  - `nonce == account.nonce + 1`,
  - `fee >= minFee`,
  - For `RECEIPT_CLAIM`: passes `receipts.validate()` *optimistically* (soft-accept), then **revalidate** at block time.

Replacement: higher-fee replaces same `(sender, nonce)`.

---

## 12) Node Lifecycle

**Start:**
1) Load config, open DB, ensure genesis.
2) Connect to bootstrap peers (if any).
3) Start RPC (FastAPI) + P2P WS server.
4) Start block proposer (if PoA key present).
5) Start peer heartbeats + gossip loops.

**Shutdown:**
- Graceful: flush mempool snapshot, close DB.

---

## 13) Genesis
- `genesis.json`:
  - `chain_id`, `timestamp`, `accounts` (faucet), `params` (mint ratios, base fee), `authorities` (PoA keys).

Provide `scripts/make_genesis.py`.

---

## 14) Devnet: End-to-End Demo

### 14.1 Components
- **blockchain-node** (this repo)
- **coordinator-api (mock)**: `/attest/receipt` returns valid for `job_id` in `[1..1_000_000]`
- **miner-node (mock)**: posts `RECEIPT_CLAIM` for synthetic jobs
- **client-web (demo)**: sends `TRANSFER` & displays balances

### 14.2 Flow
1) Client pays `price` to escrow address (coordinator).
2) Miner executes job; coordinator verifies output.
3) Miner submits **ComputeReceipt** → included in next block.
4) Mint AIT to miner; escrow settles; client charged.

---

## 15) Testing Strategy

### 15.1 Unit
- `crypto`: keygen, sign/verify, address derivation
- `state`: balances, nonce, persistence
- `receipts`: signature + coordinator mock
- `blocks`: header hash, stateRoot

### 15.2 Integration
- Single node PoA: produce N blocks; submit transfers/receipts; assert balances.
- Two nodes P2P: block/tx relay; head convergence.

### 15.3 Property tests
- Nonce monotonicity; no double-spend; unique receipts.

---

## 16) Observability
- Structured logs (JSON) with `component`, `event`, `height`, `latency_ms`.
- `/rpc/metrics` (Prometheus format) — block time, mempool size, peers.

---

## 17) Configuration (ENV)
- `CHAIN_ID=ait-devnet`
- `DB_PATH=./data/chain.db`
- `P2P_BIND=0.0.0.0:7070`
- `RPC_BIND=0.0.0.0:8080`
- `BOOTSTRAP_PEERS=ws://host:7070,...`
- `PROPOSER_KEY=...` (optional for non-authors)
- `MINT_PER_UNIT=1000`
- `COORDINATOR_RATIO=0.05`

Provide `.env.example`.

---

## 18) Minimal API Payloads

### 18.1 TRANSFER
```json
{
  "type": "TRANSFER",
  "sender": "ait1...",
  "nonce": 1,
  "fee": 10,
  "payload": {"to":"ait1...","amount":12345},
  "sig": "<ed25519>"
}
```

### 18.2 RECEIPT_CLAIM
```json
{
  "type": "RECEIPT_CLAIM",
  "sender": "ait1miner...",
  "nonce": 7,
  "fee": 50,
  "payload": {
    "receipt_id": "rcpt_7f3a...",
    "job_id": "job_42",
    "client_addr": "ait1client...",
    "miner_addr": "ait1miner...",
    "compute_units": 2500,
    "price": 50000,
    "output_hash": "sha256:abcd...",
    "miner_sig": "<sig_over_core_fields>"
  },
  "sig": "<miner_account_sig>"
}
```

---

## 19) Security Notes (MVP)
- Devnet PoA means trust in proposer; do **not** expose to internet without firewall.
- Enforce coordinator host allowlist for attest calls.
- Rate-limit `/rpc/sendTx`.

---

## 20) Roadmap
1) ✅ PoA devnet with receipts.
2) 🔜 CBP proposer selection from rolling work score.
3) 🔜 Stake & slashing.
4) 🔜 Replace SQLite with PostgreSQL.
5) 🔜 Snapshots & fast-sync.
6) 🔜 Light client (SPV of receipts & balances).

---

## 21) Developer Tasks (Windsurf Order)

1) **Scaffold** project & `requirements.txt`:
   - `fastapi`, `uvicorn[standard]`, `sqlmodel`, `pydantic`, `websockets`, `pyyaml`, `python-dotenv`, `ed25519`, `orjson`.

2) **Implement**:
   - `crypto.py`, `types.py`, `state.py`.
   - `rpc.py` (public routes).
   - `mempool.py`.
   - `blocks.py` (build/validate).
   - `consensus.py` (PoA tick).
   - `p2p.py` (WS server + simple gossip).
   - `receipts.py` (mock coordinator).

3) **Wire** `main.py`:
   - Start RPC, P2P, PoA loops.

4) **Scripts**:
   - `scripts/keygen.py`, `scripts/make_genesis.py`, `scripts/devnet_up.sh`.

5) **Tests**:
   - Add unit + an integration test that mints on a receipt.

6) **Docs**:
   - Update `README.md` with curl examples.

---

## 22) Curl Snippets (Dev)

- Faucet (dev only):
```bash
curl -sX POST localhost:8080/admin/mintFaucet -H 'content-type: application/json' \
  -d '{"address":"ait1client...","amount":1000000}'
```

- Transfer:
```bash
curl -sX POST localhost:8080/rpc/sendTx -H 'content-type: application/json' \
  -d @transfer.json
```

- Submit Receipt:
```bash
curl -sX POST localhost:8080/rpc/submitReceipt -H 'content-type: application/json' \
  -d @receipt_claim.json
```

---

## 23) Definition of Done (MVP)
- Node produces blocks on PoA.
- Can transfer AIT between accounts.
- Can submit a valid **ComputeReceipt** → miner balance increases; escrow decreases.
- Two nodes converge on same head via P2P.
- Basic metrics exposed.

---

## 24) Next Files to Create
- `src/main.py`
- `src/crypto.py`
- `src/types.py`
- `src/state.py`
- `src/mempool.py`
- `src/blocks.py`
- `src/consensus.py`
- `src/p2p.py`
- `src/receipts.py`
- `src/rpc.py`
- `scripts/keygen.py`, `scripts/devnet_up.sh`
- `.env.example`, `README.md`, `requirements.txt`

