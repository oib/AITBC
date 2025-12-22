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

## Blockchain Node

- Added websocket fan-out, disconnect cleanup, and load-test coverage in `apps/blockchain-node/tests/test_websocket.py`, ensuring gossip topics deliver reliably to multiple subscribers.

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
- Implemented wallet SDK receipt ingestion + attestation surfacing in `packages/py/aitbc-sdk/src/receipts.py`, including pagination client, signature verification, and failure diagnostics with full pytest coverage.
- Hardened REST API by wiring dependency overrides in `apps/wallet-daemon/tests/test_wallet_api.py`, expanding workflow coverage (create/list/unlock/sign) and enforcing structured password policy errors consumed in CI.

## Explorer Web

- Initialized a Vite + TypeScript scaffold in `apps/explorer-web/` with `vite.config.ts`, `tsconfig.json`, and placeholder `src/main.ts` content.
- Installed frontend dependencies locally to unblock editor tooling and TypeScript type resolution.
- Implemented `overview` page stats rendering backed by mock block/transaction/receipt fetchers, including robust empty-state handling and TypeScript type fixes.

## Pool Hub

- Implemented FastAPI service scaffolding with Redis/PostgreSQL-backed repositories, match/health/metrics endpoints, and Prometheus instrumentation (`apps/pool-hub/src/poolhub/`).
- Added Alembic migrations (`apps/pool-hub/migrations/`) and async integration tests covering repositories and endpoints (`apps/pool-hub/tests/`).

## Solidity Token

- Implemented attested minting logic in `packages/solidity/aitbc-token/contracts/AIToken.sol` using `AccessControl` role gates and ECDSA signature recovery.
- Added Hardhat unit tests in `packages/solidity/aitbc-token/test/aitoken.test.ts` covering successful minting, replay prevention, and invalid attestor signatures.
- Configured project TypeScript settings via `packages/solidity/aitbc-token/tsconfig.json` to align Hardhat, Node, and Mocha typings for the contract test suite.

## JavaScript SDK

- Delivered fetch-based client wrapper with TypeScript definitions and Vitest coverage under `packages/js/aitbc-sdk/`.
