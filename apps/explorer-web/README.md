# Explorer Web

## Purpose & Scope

Static web explorer for the AITBC blockchain node, displaying blocks, transactions, and receipts as outlined in `docs/bootstrap/explorer_web.md`.

## Development Setup

  ```bash
  npm install
  ```
- Start the dev server (Vite):
  ```bash
  npm run dev
  ```
  The dev server listens on `http://localhost:5173/` by default. Adjust via `--host`/`--port` flags in the `systemd` unit or `package.json` script.

## Data Mode Toggle

- Configuration lives in `src/config.ts` and can be overridden with environment variables.
- Use `VITE_DATA_MODE` to choose between `mock` (default) and `live`.
- When switching to live data, set `VITE_COORDINATOR_API` to the coordinator base URL (e.g., `http://localhost:8000`).
- Example `.env` snippet:
  ```bash
  VITE_DATA_MODE=live
  VITE_COORDINATOR_API=https://coordinator.dev.internal
  ```

## Feature Flags & Auth

- Document any backend expectations (e.g., coordinator accepting bearer tokens) alongside the environment variables in deployment manifests.

## End-to-End Tests

- Install browsers after `npm install` by running `npx playwright install`.
- Launch the dev server (or point `EXPLORER_BASE_URL` at an already running instance) and run:
  ```bash
  npm run test:e2e
  ```
- Tests automatically persist live mode and stub coordinator responses to verify overview, blocks, and transactions views.

## Playwright

- Run `npm run test:e2e` to execute the end-to-end tests.
- The tests will automatically persist live mode and stub coordinator responses to verify overview, blocks, and transactions views.
