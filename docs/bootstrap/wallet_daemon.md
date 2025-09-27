# wallet-daemon.md

> **Role:** Local wallet service (keys, signing, RPC) for the 🤖 AITBC 🤑 stack  
> **Audience:** Windsurf (programming assistant) + developers  
> **Stage:** Bootable without blockchain; later pluggable to chain node

---

## 1) What this daemon is (and isn’t)

**Goals**
1. Generate/import encrypted wallets (seed or raw keys).
2. Derive accounts/addresses (HD, multiple curves).
3. Hold keys **locally** and sign messages/transactions/receipts.
4. Expose a minimal **RPC** for client/coordinator/miner.
5. Provide a mock “ledger view” (balance cache + test transfers) until the chain is ready.

**Non-Goals (for now)**
- No P2P networking.
- No full node / block validation.
- No remote key export (never leaves box unencrypted).

---

## 2) Architecture (minimal, extensible)

- **Process:** Python FastAPI app (`uvicorn`)  
- **RPC:** HTTP+JSON (REST) and JSON-RPC (both; same server)  
- **KeyStore:** on-disk, encrypted with **Argon2id + XChaCha20-Poly1305**  
- **Curves:** `ed25519` (default), `secp256k1` (optional flag per-account)  
- **HD Derivation:** BIP-39 seed → SLIP-10 (ed25519), BIP-32 (secp256k1)  
- **Coin type (provisional):** `AITBC = 12345` (placeholder; replace once registered)  
- **Auth:** Local-only by default (bind `127.0.0.1`), optional token header for remote.  
- **Events:** Webhooks + local FIFO/Unix-socket stream for “signed” notifications.  
- **Mock Ledger (stage-1):** sqlite table for balances & transfers; sync adapter later.

**Directory layout**
```
wallet-daemon/
├─ app/                    # FastAPI service
│  ├─ main.py              # entrypoint
│  ├─ api_rest.py          # REST routes
│  ├─ api_jsonrpc.py       # JSON-RPC methods
│  ├─ crypto/              # key, derivation, sign, addr
│  ├─ keystore/            # encrypted store backend
│  ├─ models/              # pydantic schemas
│  ├─ ledger_mock/         # sqlite-backed balances
│  └─ settings.py          # config
├─ data/
│  ├─ keystore/            # *.kdb (per wallet)
│  └─ ledger.db
├─ tests/
└─ run.sh
```

---

## 3) Security model (Windsurf implementation notes)

- **Passwords:** Argon2id (tuned to machine; env overrides)  
  - `ARGON_TIME=4`, `ARGON_MEMORY=256MB`, `ARGON_PARALLELISM=2` (defaults)
- **Encryption:** libsodium `crypto_aead_xchacha20poly1305_ietf`  
- **At-Rest Format (per wallet file)**  
  ```
  magic=v1-kdb
  salt=32B
  argon_params={t,m,p}
  nonce=24B
  ciphertext=…  # includes seed or master private key; plus metadata JSON
  ```
- **In-memory:** zeroize sensitive bytes after use; use `memoryview`/`ctypes` scrubbing where possible.
- **API hardening:**
  - Bind to `127.0.0.1` by default.
  - Optional `X-Auth-Token: <TOKEN>` for REST/JSON-RPC.
  - Rate limits on sign endpoints.

---

## 4) Key & address strategy

- **Wallet types**
  1. **HD (preferred):** BIP-39 mnemonic (12/24 words) → master seed.
  2. **Single-key:** import raw private key (ed25519/secp256k1).

- **Derivation paths**
  - **ed25519 (SLIP-10):** `m / 44' / 12345' / account' / change / index`
  - **secp256k1 (BIP-44):** `m / 44' / 12345' / account' / change / index`

- **Address format (temporary)**
  - **ed25519:** `base32(bech32_hrp="ait")` of `blake2b-20(pubkey)`  
  - **secp256k1:** same hash → bech32; flag curve in metadata

> Replace HRP and hash rules if the canonical AITBC chain spec differs.

---

## 5) REST API (for Windsurf to scaffold)

**Headers**
- Optional: `X-Auth-Token: <token>`
- `Content-Type: application/json`

### 5.1 Wallet lifecycle
- `POST /v1/wallet/create`
  - body: `{ "name": "main", "password": "…", "mnemonic_len": 24 }`
  - returns: `{ "wallet_id": "…" }`
- `POST /v1/wallet/import-mnemonic`
  - `{ "name":"…","password":"…","mnemonic":"…","passphrase":"" }`
- `POST /v1/wallet/import-key`
  - `{ "name":"…","password":"…","curve":"ed25519|secp256k1","private_key_hex":"…" }`
- `POST /v1/wallet/unlock`
  - `{ "wallet_id":"…","password":"…" }` → unlocks into memory for N seconds (config TTL)
- `POST /v1/wallet/lock` → no body
- `GET /v1/wallets` → list minimal metadata (never secrets)

### 5.2 Accounts & addresses
- `POST /v1/account/derive`
  - `{ "wallet_id":"…","curve":"ed25519","path":"m/44'/12345'/0'/0/0" }`
- `GET /v1/accounts?wallet_id=…`
- `GET /v1/address/{account_id}` → `{ "address":"ait1…", "curve":"ed25519" }`

### 5.3 Signing
- `POST /v1/sign/message`
  - `{ "account_id":"…","message_base64":"…" }` → `{ "signature_base64":"…" }`
- `POST /v1/sign/tx`
  - `{ "account_id":"…","tx_bytes_base64":"…","type":"aitbc_v0" }` → signature + (optionally) signed blob
- `POST /v1/sign/receipt`
  - `{ "account_id":"…","payload":"…"}`
  - **Used by coordinator/miner** to sign job receipts & payouts.

### 5.4 Mock ledger (stage-1 only)
- `GET /v1/ledger/balance/{address}`
- `POST /v1/ledger/transfer`
  - `{ "from":"…","to":"…","amount":"123.456","memo":"test" }`
- `GET /v1/ledger/tx/{txid}`

### 5.5 Webhooks
- `POST /v1/webhooks`
  - `{ "url":"https://…/callback", "events":["signed","transfer"] }`

**Error model**
```json
{ "error": { "code": "WALLET_LOCKED|NOT_FOUND|BAD_PASSWORD|RATE_LIMIT", "detail": "…" } }
```

---

## 6) JSON-RPC mirror (method → params)

- `wallet_create(name, password, mnemonic_len)`  
- `wallet_import_mnemonic(name, password, mnemonic, passphrase)`  
- `wallet_import_key(name, password, curve, private_key_hex)`  
- `wallet_unlock(wallet_id, password)` / `wallet_lock()`  
- `account_derive(wallet_id, curve, path)`  
- `sign_message(account_id, message_base64)`  
- `sign_tx(account_id, tx_bytes_base64, type)`  
- `ledger_getBalance(address)` / `ledger_transfer(from, to, amount, memo)`  

Same auth header; endpoint `/rpc`.

---

## 7) Data schemas (Pydantic hints)

```py
class WalletMeta(BaseModel):
    wallet_id: str
    name: str
    curves: list[str]           # ["ed25519", "secp256k1"]
    created_at: datetime

class AccountMeta(BaseModel):
    account_id: str
    wallet_id: str
    curve: Literal["ed25519","secp256k1"]
    path: str                   # HD path or "imported"
    address: str                # bech32 ait1...

class SignedResult(BaseModel):
    signature_base64: str
    public_key_hex: str
    algo: str                   # e.g., ed25519
```

---

## 8) Configuration (ENV)

```
WALLET_BIND=127.0.0.1
WALLET_PORT=8555
WALLET_TOKEN= # optional
KEYSTORE_DIR=./data/keystore
LEDGER_DB=./data/ledger.db
UNLOCK_TTL_SEC=120
ARGON_TIME=4
ARGON_MEMORY_MB=256
ARGON_PARALLELISM=2
```

---

## 9) Minimal boot script (dev)

```bash
# run.sh
export WALLET_BIND=127.0.0.1
export WALLET_PORT=8555
export KEYSTORE_DIR=./data/keystore
mkdir -p "$KEYSTORE_DIR" data
exec uvicorn app.main:app --host ${WALLET_BIND} --port ${WALLET_PORT}
```

---

## 10) Systemd unit (prod, template)

```
[Unit]
Description=AITBC Wallet Daemon
After=network.target

[Service]
User=root
WorkingDirectory=/opt/aitbc/wallet-daemon
Environment=WALLET_BIND=127.0.0.1
Environment=WALLET_PORT=8555
Environment=KEYSTORE_DIR=/opt/aitbc/wallet-daemon/data/keystore
ExecStart=/usr/bin/uvicorn app.main:app --host 127.0.0.1 --port 8555
Restart=always
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
```

---

## 11) Curl smoke tests

```bash
# 1) Create + unlock
curl -s localhost:8555/v1/wallet/create -X POST \
  -H 'Content-Type: application/json' \
  -d '{"name":"main","password":"pw","mnemonic_len":24}'

curl -s localhost:8555/v1/wallets

# 2) Derive first account
curl -s localhost:8555/v1/account/derive -X POST \
  -H 'Content-Type: application/json' \
  -d '{"wallet_id":"W1","curve":"ed25519","path":"m/44'/12345'/0'/0/0"}'

# 3) Sign message
curl -s localhost:8555/v1/sign/message -X POST \
  -H 'Content-Type: application/json' \
  -d '{"account_id":"A1","message_base64":"aGVsbG8="}'
```

---

## 12) Coordinator/miner integration (stage-1)

**Coordinator needs:**
- `GET /v1/address/{account_id}` for payout address lookup.
- `POST /v1/sign/receipt` to sign `{job_id, miner_id, result_hash, ts}`.
- Optional webhook on `signed` to chain/queue the payout request.

**Miner needs:**
- Local message signing for **proof-of-work-done** receipts.
- Optional “ephemeral sub-accounts” derived at `change=1` for per-job audit.

---

## 13) Migration path to real chain

1. Introduce **ChainAdapter** interface:
   - `get_balance(address)`, `broadcast_tx(signed_tx)`, `fetch_utxos|nonce`, `estimate_fee`.
2. Implement `MockAdapter` (current), then `AitbcNodeAdapter` (RPC to real node).
3. Swap via `WALLET_CHAIN=mock|aitbc`.

---

## 14) Windsurf tasks checklist

1. Create repo structure (see **Directory layout**).  
2. Add dependencies: `fastapi`, `uvicorn`, `pydantic`, `argon2-cffi`, `pynacl` (or `libsodium` bindings), `bech32`, `sqlalchemy` (for mock ledger), `aiosqlite`.  
3. Implement **keystore** (encrypt/decrypt, file IO, metadata).  
4. Implement **HD derivation** (SLIP-10 for ed25519, BIP-32 for secp256k1).  
5. Implement **address** helper (hash → bech32 with `ait`).  
6. Implement **REST** routes, then JSON-RPC shim.  
7. Implement **mock ledger** with sqlite + simple transfers.  
8. Add **webhook** delivery (async task + retry).  
9. Add **rate limits** on signing; add unlock TTL.  
10. Write unit tests for keystore, derivation, signing.  
11. Provide `run.sh` + systemd unit.  
12. Add curl examples to `README`.

---

## 15) Open questions (defaults proposed)

1. Keep both curves or start **ed25519-only**? → **Start ed25519-only**, gate secp256k1 by flag.  
2. HRP `ait` and hash `blake2b-20` acceptable as interim? → **Yes (interim)**.  
3. Store **per-account tags** (e.g., “payout”, “ops”)? → **Yes**, simple string map.

---

## 16) Threat model notes (MVP)

- Local compromise = keys at risk ⇒ encourage **passphrase on mnemonic** + **short unlock TTL**.  
- Add **IPC allowlist** if binding to non-localhost.  
- Consider **YubiKey/PKCS#11** module later (signing via hardware).

---

## 17) Logging

- Default: INFO without sensitive fields.  
- Redact: passwords, mnemonics, private keys, nonces.  
- Correlate by `req_id` header (generate if missing).

---

## 18) License / Compliance

- Keep crypto libs permissive (MIT/ISC/BSD).  
- Record algorithm choices & versions in `/about` endpoint for audits.

---

**Proceed to generate the scaffold (FastAPI app + keystore + ed25519 HD + REST) now?** `y` / `n`

