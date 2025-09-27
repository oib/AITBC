# Receipts Sign & Verify Examples

This directory contains sample scripts demonstrating how to interact with the
coordinator receipt endpoints and validate miner/coordinator signatures.

## Prerequisites

- Python 3.11+
- Coordinator API running locally (defaults to `http://localhost:8011`)
- Client API key with access to the coordinator (defaults to
  `REDACTED_CLIENT_KEY` in development fixtures)

Install the helper packages:

```bash
poetry install --directory packages/py/aitbc-crypto
poetry install --directory packages/py/aitbc-sdk
```

## Fetch and Verify

`fetch_and_verify.py` fetches either the latest receipt or the entire receipt
history for a job, then verifies miner signatures and optional coordinator
attestations.

```bash
export PYTHONPATH=packages/py/aitbc-sdk/src:packages/py/aitbc-crypto/src
python examples/receipts-sign-verify/fetch_and_verify.py --job-id <job_id> \
  --coordinator http://localhost:8011 --api-key REDACTED_CLIENT_KEY
```

Use `--history` to iterate over all stored receipts:

```bash
python examples/receipts-sign-verify/fetch_and_verify.py --job-id <job_id> --history
```

The script prints whether the miner signature and each coordinator attestation
validated successfully.
