# Scenario 46: Confidential AI job with TEE attestation

## Goal

Run a CLI-first confidential inference job. The job is marked confidential,
requires a TEE attestation for the target enclave measurement, and only
releases escrow after a verified attestation is attached to the job receipt.

## Preconditions

- Coordinator API running on the hub (`aitbc-coordinator-api.service`).
- Active `aitbc-miner` on a shop node that can execute Ollama jobs.
- Customer wallet with enough AIT for payment (e.g. `genesis`).
- A funded customer wallet (e.g. `customer-wallet`) and `aitbc auth login`.

## Variables

```bash
# Customer / provider addresses from the live network
CUSTOMER=0xFe2d63FE87Db282083b9159e5857Cac788af9E03
PROVIDER=0xA54B82312beb65D0E90c21717ea372396991Fa36

# A stable enclave measurement used to pin the job to a specific enclave image
MEASUREMENT="sha256:0000000000000000000000000000000000000000000000000000000000000001"
```

## Step 1: Register a TEE enclave identity

```bash
export COORDINATOR_API_URL=http://127.0.0.1:8203
export WALLET=customer-wallet

# Log in once with a funded customer wallet; subsequent commands use the stored token.
aitbc auth login --wallet "$WALLET" --coordinator-url "$COORDINATOR_API_URL"

aitbc tee register enc-live-01 --agent-id hub-coordinator
```

Expected output:

```text
{
  "enclave_id": "enc-live-01",
  "public_key": "xwLsql6cJ27SlqnfvDIQvYMnH5fAvuBGzwRPHgjJXmc=",
  "status": "active",
  "id": "ei_54cca06a04",
  ...
}
```

## Step 2: Query the enclave registration

```bash
aitbc tee status enc-live-01
```

Expected output: the same registration record with `status: active`.

## Step 3: Submit a confidential TEE job

```bash
aitbc ai submit \
  --prompt "Confidential TEE live validation" \
  --payment 1.0 \
  --wallet genesis \
  --buyer-address "$CUSTOMER" \
  --provider-address "$PROVIDER" \
  --coordinator-url http://127.0.0.1:8203 \
  --confidential \
  --enclave-measurement "$MEASUREMENT" \
  --wait \
  --timeout 180
```

Expected job result:

```json
{
  "job_id": "<job_id>",
  "state": "COMPLETED",
  "payment_status": "released",
  "tee_status": "verified",
  "tee_attestation_id": "<attestation_id>",
  "escrow_tx_hash": "<0x...>",
  "result": { ... }
}
```

## Step 4: Verify the attestation record

The coordinator stored the TEE attestation referenced in the receipt:

```bash
# The attestation id comes from the job receipt above, e.g. ta_a9bef0c722
curl -s -H "Authorization: Bearer $(python3 -c "from aitbc_cli.auth import AuthManager; print(AuthManager().get_credential('client'))")" \
  http://127.0.0.1:8203/v1/tee/attestations/<tee_attestation_id>
```

Expected response:

```json
{
  "id": "ta_a9bef0c722",
  "enclave_id": "sha256:0000000000000000000000000000000000000000000000000000000000000001",
  "measurement": "sha256:0000000000000000000000000000000000000000000000000000000000000001",
  "status": "verified",
  ...
}
```

## What the CLI actually does

- `--confidential` sets `job.constraints.confidential = true` and
  `job.constraints.tee_attestation_required = true`.
- `--enclave-measurement` sets both `required_enclave_measurement` and
  `tee_enclave_id` to the supplied measurement hash.
- When the miner completes the job, the coordinator auto-generates a simulated
  TEE quote for the required measurement, verifies it, and attaches it to the
  receipt (`tee_status: verified`).
- Only after `tee_status: verified` does the coordinator release the escrow.

## Validation

- `cli/tests/test_tee.py` — 6 tests covering `tee register`, `status`, `attest`,
  and local `verify`.
- `cli/tests/test_ai_tee_submit.py` — 2 tests covering `--confidential` and
  `--enclave-measurement` payload construction.
- Live validation on `hub.aitbc` + `aitbc3` produced a released escrow with
  `tee_status: verified` and `confidential: true` in the job constraints.

## Notes

- This scenario uses the simulated TEE path (`SIMULATED_TEE=1`). Real SGX/TDX
  attestation is deferred to **release 2.0** and will stay deferred until
  TEE-capable hardware is available to the fleet; no validator host currently has
  an enclave runtime. See "Deferred to v2.0 — hardware-backed TEE" in
  `docs/releases/STATUS.md`. Everything below therefore proves the gate logic, not
  a hardware root of trust.
- The `--enclave-measurement` value is treated as the target measurement by
  both the job constraint and the auto-generated quote.
- If the miner cannot produce a valid attestation, the job fails and escrow
  can be refunded with `aitbc ai refund <job_id>` or
  `aitbc market escrow refund <job_id>` (see Scenario 44).
