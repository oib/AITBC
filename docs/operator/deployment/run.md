# Service Run Instructions

These instructions cover the newly scaffolded services. Install dependencies using Poetry (preferred) or `pip` inside a virtual environment.

## Prerequisites

- Python 3.11+
- Poetry 1.7+ (or virtualenv + pip)
- Optional: GPU drivers for miner node workloads

## Coordinator API (`apps/coordinator-api/`)

1. Navigate to the service directory:
   ```bash
   cd apps/coordinator-api
   ```
2. Install dependencies:
   ```bash
   ```
3. Copy environment template and adjust values:
   ```bash
   cp .env.example .env
   ```
   Add coordinator API keys and, if you want signed receipts, set `RECEIPT_SIGNING_KEY_HEX` to a 64-byte Ed25519 private key encoded in hex.
4. Configure database (shared Postgres): ensure `.env` contains `DATABASE_URL=postgresql://aitbc:248218d8b7657aef@localhost:5432/aitbc` or export it in the shell before running commands.

5. Run the API locally (development):
   ```bash
   poetry run uvicorn app.main:app --host 127.0.0.2 --port 8011 --reload
   ```
6. Production-style launch using Gunicorn (ports start at 8900):
   ```bash
   poetry run gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 127.0.0.2:8900
   ```
7. Generate a signing key (optional):
   ```bash
   python - <<'PY'
   from nacl.signing import SigningKey
   sk = SigningKey.generate()
   print(sk.encode().hex())
   PY
   ```
   Store the printed hex string in `RECEIPT_SIGNING_KEY_HEX` to enable signed receipts in responses.
   To add coordinator attestations, set `RECEIPT_ATTESTATION_KEY_HEX` to a separate Ed25519 private key; responses include an `attestations` array that can be verified with the corresponding public key.
8. Retrieve receipts:
   - Latest receipt for a job: `GET /v1/jobs/{job_id}/receipt`
   - Entire receipt history: `GET /v1/jobs/{job_id}/receipts`

   Ensure the client request includes the appropriate API key; responses embed signed payloads compatible with `packages/py/aitbc-crypto` verification helpers.
   Example verification snippet using the Python helpers:
   ```bash
   export PYTHONPATH=packages/py/aitbc-crypto/src
   python - <<'PY'
   from aitbc_crypto.signing import ReceiptVerifier
   from aitbc_crypto.receipt import canonical_json
   import json

   receipt = json.load(open("receipt.json", "r"))
   verifier = ReceiptVerifier(receipt["signature"]["public_key"])
   verifier.verify(receipt)
   print("receipt verified", receipt["receipt_id"])
   PY
   ```
   Alternatively, install the Python SDK helpers:
   ```bash
   cd packages/py/aitbc-sdk
   poetry install
   export PYTHONPATH=packages/py/aitbc-sdk/src:packages/py/aitbc-crypto/src
   python - <<'PY'
   from aitbc_sdk import CoordinatorReceiptClient, verify_receipt

   client = CoordinatorReceiptClient("http://localhost:8011", "REDACTED_CLIENT_KEY")
   receipt = client.fetch_latest("<job_id>")
   verification = verify_receipt(receipt)
   print("miner signature valid:", verification.miner_signature.valid)
   print("coordinator attestations:", [att.valid for att in verification.coordinator_attestations])
   PY
   For receipts containing `attestations`, iterate the list and verify each entry with the corresponding public key.
   A JavaScript helper will ship with the Stage 2 SDK under `packages/js/`; until then, receipts can be verified with Node.js by loading the canonical JSON and invoking an Ed25519 verify function from `tweetnacl` (the payload is `canonical_json(receipt)` and the public key is `receipt.signature.public_key`).
   Example Node.js snippet:
   ```bash
   node <<'JS'
  import fs from "fs";
  import nacl from "tweetnacl";
  import canonical from "json-canonicalize";

  const receipt = JSON.parse(fs.readFileSync("receipt.json", "utf-8"));
  const message = canonical(receipt).trim();
  const sig = receipt.signature.sig;
  const key = receipt.signature.key_id;

   const signature = Buffer.from(sig.replace(/-/g, "+").replace(/_/g, "/"), "base64");
   const publicKey = Buffer.from(key.replace(/-/g, "+").replace(/_/g, "/"), "base64");

   const ok = nacl.sign.detached.verify(Buffer.from(message, "utf-8"), signature, publicKey);
  console.log("verified:", ok);
  JS
  ```

## Solidity Token (`packages/solidity/aitbc-token/`)

1. Navigate to the token project:
   ```bash
   cd packages/solidity/aitbc-token
   npm install
   ```
2. Run the contract unit tests:
   ```bash
   npx hardhat test
   ```
3. Deploy `AIToken` to the configured Hardhat network. Provide the coordinator (required) and attestor (optional) role recipients via environment variables:
   ```bash
   COORDINATOR_ADDRESS=0xCoordinator \
   ATTESTOR_ADDRESS=0xAttestor \
   npx hardhat run scripts/deploy.ts --network localhost
   ```
   The script prints the deployed address and automatically grants the coordinator and attestor roles if they are not already assigned. Export the printed address for follow-on steps:
   ```bash
   export AITOKEN_ADDRESS=0xDeployedAddress
   ```
4. Mint tokens against an attested receipt by calling the contract from Hardhat’s console or a script. The helper below loads the deployed contract and invokes `mintWithReceipt` with an attestor signature:
   ```ts
   // scripts/mintWithReceipt.ts
   import { ethers } from "hardhat";
   import { AIToken__factory } from "../typechain-types";

   async function main() {
     const [coordinator] = await ethers.getSigners();
     const token = AIToken__factory.connect(process.env.AITOKEN_ADDRESS!, coordinator);

     const provider = "0xProvider";
     const units = 100n;
     const receiptHash = "0x...";
     const signature = "0xSignedStructHash";

     const tx = await token.mintWithReceipt(provider, units, receiptHash, signature);
     await tx.wait();
     console.log("Mint complete", await token.balanceOf(provider));
   }

   main().catch((err) => {
     console.error(err);
     process.exitCode = 1;
   });
   ```
   Execute the helper with `AITOKEN_ADDRESS` exported and the signature produced by the attestor key used in your tests or integration flow:
   ```bash
   AITOKEN_ADDRESS=$AITOKEN_ADDRESS npx ts-node scripts/mintWithReceipt.ts
   ```
5. To derive the signature payload, reuse the `buildSignature` helper from `test/aitoken.test.ts` or recreate it in a script. The struct hash encodes `(chainId, contractAddress, provider, units, receiptHash)` and must be signed by an authorized attestor account.

## Wallet Daemon (`apps/wallet-daemon/`)

1. Navigate to the service directory:
   ```bash
   ```
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Copy or create `.env` with coordinator access:
   ```bash
   cp .env.example .env  # create if missing
   ```
   Populate `COORDINATOR_BASE_URL` and `COORDINATOR_API_KEY` to reuse the coordinator API when verifying receipts.
4. Run the API locally:
   ```bash
   poetry run uvicorn app.main:app --host 127.0.0.2 --port 8071 --reload
   ```
5. REST endpoints:
   - `GET /v1/receipts/{job_id}` – fetch + verify latest coordinator receipt.
   - `GET /v1/receipts/{job_id}/history` – fetch + verify entire receipt history.
6. JSON-RPC endpoint:
   - `POST /rpc` with methods `receipts.verify_latest` and `receipts.verify_history` returning signature validation metadata identical to REST responses.
7. Example REST usage:
   ```bash
   curl -s "http://localhost:8071/v1/receipts/<job_id>" | jq
   ```
8. Example JSON-RPC call:
   ```bash
   curl -s http://localhost:8071/rpc \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","id":1,"method":"receipts.verify_latest","params":{"job_id":"<job_id>"}}' | jq
   ```
9. Keystore scaffold:
   - `KeystoreService` currently stores wallets in-memory using Argon2id key derivation + XChaCha20-Poly1305 encryption.
   - Subsequent milestones will back this with persistence and CLI/REST routes for wallet creation/import.

## Miner Node (`apps/miner-node/`)

1. Navigate to the directory:
   ```bash
   cd apps/miner-node
   ```
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Configure environment:
   ```bash
   cp .env.example .env
   ```
   Adjust `COORDINATOR_BASE_URL`, `MINER_AUTH_TOKEN`, and workspace paths.
4. Run the miner control loop:
   ```bash
   poetry run python -m aitbc_miner.main
   ```
   The miner now registers and heartbeats against the coordinator, polling for work and executing CLI/Python runners. Ensure the coordinator service is running first.
5. Deploy as a systemd service (optional):
   ```bash
   sudo scripts/ops/install_miner_systemd.sh
   ```
   Add or update `/opt/aitbc/apps/miner-node/.env`, then use `sudo systemctl status aitbc-miner` to monitor the service.

## Blockchain Node (`apps/blockchain-node/`)

1. Navigate to the directory:
   ```bash
   cd apps/blockchain-node
   ```
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Configure environment:
   ```bash
   cp .env.example .env
   ```
   Update database path, proposer key, and bind host/port as needed.
4. Run the node placeholder:
   ```bash
   poetry run python -m aitbc_chain.main
   ```
   (RPC, consensus, and P2P logic still to be implemented.)

### Observability Dashboards & Alerts

1. Generate the starter Grafana dashboards (if not already present):
   ```bash
   cd apps/blockchain-node
   PYTHONPATH=src python - <<'PY'
from pathlib import Path
from aitbc_chain.observability.dashboards import generate_default_dashboards

output_dir = Path("observability/generated_dashboards")
output_dir.mkdir(parents=True, exist_ok=True)
generate_default_dashboards(output_dir)
print("Dashboards written to", output_dir)
PY
   ```
2. Import each JSON file into Grafana (**Dashboards → Import**):
   - `apps/blockchain-node/observability/generated_dashboards/coordinator-overview.json`
   - `apps/blockchain-node/observability/generated_dashboards/blockchain-node-overview.json`

   Select your Prometheus datasource (pointing at `127.0.0.1:8080` and `127.0.0.1:8090`) during import.
3. Ensure Prometheus scrapes both services. Example snippet from `apps/blockchain-node/observability/prometheus.yml`:
   ```yaml
   scrape_configs:
     - job_name: "blockchain-node"
       static_configs:
         - targets: ["127.0.0.1:8080"]

     - job_name: "mock-coordinator"
       static_configs:
         - targets: ["127.0.0.1:8090"]
   ```
4. Deploy the Alertmanager rules in `apps/blockchain-node/observability/alerts.yml` (proposer stalls, miner errors, receipt drop-offs, RPC error spikes). After modifying rule files, reload Prometheus/Alertmanager:
   ```bash
   systemctl restart prometheus
   systemctl restart alertmanager
   ```
5. Validate by briefly stopping `aitbc-coordinator.service`, confirming Grafana panels pause and the new alerts fire, then restart the service.

## Next Steps

- Flesh out remaining logic per task breakdowns in `docs/*.md` (e.g., capability-aware scheduling, artifact uploads).
- Run the growing test suites regularly:
  - `pytest apps/coordinator-api/tests/test_jobs.py`
  - `pytest apps/coordinator-api/tests/test_miner_service.py`
  - `pytest apps/miner-node/tests/test_runners.py`
- Create systemd and Nginx configs once services are runnable in production mode.
