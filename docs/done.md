# Completed Bootstrap Tasks

## Repository Initialization

- Scaffolded core monorepo directories reflected in `docs/bootstrap/dirs.md`.
- Added top-level config files: `.editorconfig`, `.gitignore`, `LICENSE`, and root `README.md`.
- Created Windsurf workspace metadata under `windsurf/`.

## Documentation

- Authored `docs/roadmap.md` capturing staged development targets.
- Added README placeholders for primary apps under `apps/` to outline purpose and setup notes.

## Coordinator API

- Implemented SQLModel-backed job persistence and service layer in `apps/coordinator-api/src/app/`.
- Wired client, miner, and admin routers to coordinator services (job lifecycle, scheduling, stats).
- Added initial pytest coverage under `apps/coordinator-api/tests/test_jobs.py`.
- Added signed receipt generation, persistence (`Job.receipt`, `JobReceipt` history table), retrieval endpoints, telemetry metrics, and optional coordinator attestations.
- Persisted historical receipts via `JobReceipt`; exposed `/v1/jobs/{job_id}/receipts` endpoint and integrated canonical serialization.
- Documented receipt attestation configuration (`RECEIPT_ATTESTATION_KEY_HEX`) in `docs/run.md` and coordinator README.

## Miner Node

- Created coordinator client, control loop, and capability/backoff utilities in `apps/miner-node/src/aitbc_miner/`.
- Implemented CLI/Python runners and execution pipeline with result reporting.
- Added starter tests for runners in `apps/miner-node/tests/test_runners.py`.

## Directory Preparation

- Established scaffolds for Python and JavaScript packages in `packages/py/` and `packages/js/`.
- Seeded example project directories under `examples/` for quickstart clients and receipt verification.
- Added `examples/receipts-sign-verify/fetch_and_verify.py` demonstrating coordinator receipt fetching + verification using Python SDK.

## Python SDK

- Created `packages/py/aitbc-sdk/` with coordinator receipt client and verification helpers consuming `aitbc_crypto` utilities.
- Added pytest coverage under `packages/py/aitbc-sdk/tests/test_receipts.py` validating miner/coordinator signature checks and client behavior.

## Wallet Daemon

- Added `apps/wallet-daemon/src/app/receipts/service.py` providing `ReceiptVerifierService` that fetches and validates receipts via `aitbc_sdk`.
- Created unit tests under `apps/wallet-daemon/tests/test_receipts.py` verifying service behavior.

## Explorer Web

- Initialized a Vite + TypeScript scaffold in `apps/explorer-web/` with `vite.config.ts`, `tsconfig.json`, and placeholder `src/main.ts` content.
- Installed frontend dependencies locally to unblock editor tooling and TypeScript type resolution.
