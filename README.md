# AITBC Monorepo

This repository houses all components of the Artificial Intelligence Token Blockchain (AITBC) stack, including coordinator services, blockchain node, miner daemon, client-facing web apps, SDKs, and documentation.

## Getting Started

1. Review the bootstrap documents under `docs/bootstrap/` to understand stage-specific goals.
2. Fill in service-specific READMEs located under `apps/` and `packages/` as the implementations progress.
3. Use the provided directory scaffold as the starting point for coding each subsystem.
4. Explore the new Python receipt SDK under `packages/py/aitbc-sdk/` for helpers to fetch and verify coordinator receipts (see `docs/run.md` for examples).
5. Run `scripts/ci/run_python_tests.sh` (via Poetry) to execute coordinator, SDK, miner-node, and wallet-daemon test suites before submitting changes.
6. GitHub Actions (`.github/workflows/python-tests.yml`) automatically runs the same script on pushes and pull requests targeting `main`.
