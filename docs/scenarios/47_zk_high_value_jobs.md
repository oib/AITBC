# Scenario 47: ZK proofs for high-value jobs

## Goal

Submit a high-value AI job that requires a verifiable ZK receipt proof. Confirm the
job only releases escrow after the coordinator generates and verifies a Groth16
proof.

## Preconditions

- Coordinator API running with ZK enabled (`COORDINATOR_ENABLE_ZK_VERIFICATION=true`).
- Active `aitbc-miner` on a shop node with Ollama and the `llama3.2:3b` model.
- Customer wallet with enough AIT for the payment (e.g. `genesis`).
- `receipt_public` circuit files installed under the coordinator's `zk-circuits` tree.
- `node` and the `snarkjs` / `poseidon-lite` node modules available to the coordinator.

## Variables

```bash
CUSTOMER=ait1fe2d63fe87db282083b9159e5857cac788af9e03
PROVIDER=aitbc1a54b82312beb65d0e90c21717ea372396991fa36
```

## Step 1: Check ZK service health

```bash
export COORDINATOR_API_URL=http://127.0.0.1:8203
export CLIENT_JWT=$(JWT_SECRET=$(grep -h "JWT_SECRET=" /etc/aitbc/*.env | cut -d= -f2) \
  /opt/aitbc/venv/bin/python3.13 -c \
  "import sys; sys.path.insert(0, '/opt/aitbc'); from aitbc.auth import create_access_token; print(create_access_token('cli-client', 'client'))")

aitbc --api-key "$CLIENT_JWT" zk health
```

Expected output:

```json
{
  "status": "healthy",
  "available_circuits": [
    "receipt_public",
    "receipt_simple",
    ...
  ]
}
```

## Step 2: List available circuits

```bash
aitbc --api-key "$CLIENT_JWT" zk circuits
```

Expected output: `enabled: true` and the list of circuits the coordinator can use.

## Step 3: Submit a high-value job with ZK proof required

Either the default high-value threshold (10 AIT) triggers ZK automatically, or you
can force it with `--zk-proof-required`:

```bash
aitbc --api-key "$CLIENT_JWT" ai submit \
  --prompt "ZK high-value job validation" \
  --payment 5 \
  --zk-proof-required \
  --wallet genesis \
  --buyer-address "$CUSTOMER" \
  --provider-address "$PROVIDER" \
  --coordinator-url http://127.0.0.1:8203 \
  --wait \
  --timeout 240
```

Expected result:

```json
{
  "job_id": "<job_id>",
  "state": "COMPLETED",
  "payment_status": "released",
  "escrow_tx_hash": "0x...",
  "result": {
    ...,
    "zk_status": "verified",
    "tee_status": "not_required",
    "zk_proof": {
      "proof": { ... },
      "public_signals": [ ... ],
      "circuit": "receipt_public",
      "circuit_hash": "<hash>"
    }
  },
  "status": {
    "zk_status": "verified",
    "zk_proof_id": "<circuit_hash>"
  }
}
```

## Step 4: Re-verify the proof from the CLI

```bash
aitbc --api-key "$CLIENT_JWT" zk verify \
  --job-id <job_id> \
  --coordinator-url http://127.0.0.1:8203
```

Expected output:

```json
{
  "verified": true,
  "computation_correct": true,
  "privacy_preserved": true
}
```

## Step 5: Inspect the job status

```bash
aitbc --api-key "$CLIENT_JWT" ai status --job-id <job_id> --coordinator-url http://127.0.0.1:8203
```

Expected: `state: COMPLETED`, `payment_status: released`, `zk_status: verified`,
`zk_proof_id` set to the circuit hash.

## What the CLI actually does

- `aitbc zk health` calls `GET /v1/zk/health` and reports whether the service is
  healthy and which circuits are available.
- `aitbc zk circuits` calls `GET /v1/zk/info` and lists `enabled` and
  `available_circuits`.
- `aitbc ai submit --zk-proof-required` sets `job.constraints.zk_proof_required`
  to `true`.
- When the miner completes the job, the coordinator generates a `receipt_public`
  Groth16 proof over the receipt fields and verifies it.
- The `ai status` response includes `zk_status`, `zk_proof_id`, and the full
  `receipt.zk_proof` object.
- `aitbc zk verify --job-id` fetches the job receipt and posts its `zk_proof` to
  `/v1/zk/verify` for an independent re-verification.

## Validation

- `cli/tests/test_zk.py` — 5 tests covering `zk health`, `zk circuits`, and
  `zk verify` from both job receipts and explicit `--proof`/`--public-signals`.
- Live validation on `hub.aitbc` + `aitbc3` produced a released escrow with
  `zk_status: verified` and a full Groth16 `zk_proof` in the receipt.

## Notes

- The high-value threshold is controlled by `COORDINATOR_ZK_HIGH_VALUE_THRESHOLD`
  (default 10 AIT). Set it to `0` to always require ZK, or `-1` to disable the
  automatic high-value gate.
- Verification is disabled by default unless `COORDINATOR_ENABLE_ZK_VERIFICATION=true`
  is set in the coordinator's environment.
- The `receipt_public` circuit is the default. Other circuits can be selected on
  the `/v1/zk/generate` and `/v1/zk/verify` endpoints, but the job pipeline uses
  the receipt circuit.
- If ZK proof generation or verification fails, the job fails and escrow can be
  refunded with `aitbc ai refund <job_id>` or `aitbc market escrow refund <job_id>`.
