# Explorer Web

## Purpose & Scope

Static web explorer for the AITBC blockchain node, displaying blocks, transactions, and receipts as outlined in `docs/bootstrap/explorer_web.md`.

## Development Setup

- Install dependencies:
  ```bash
  npm install
  ```
- Start the dev server (Vite):
  ```bash
  npm run dev
  ```
- The explorer ships with mock data in `public/mock/` that powers the tables by default.

### Data Mode Toggle

- Configuration lives in `src/config.ts` and can be overridden with environment variables.
- Use `VITE_DATA_MODE` to choose between `mock` (default) and `live`.
- When switching to live data, set `VITE_COORDINATOR_API` to the coordinator base URL (e.g. `http://localhost:8000`).
- Example `.env` snippet:
  ```bash
  VITE_DATA_MODE=live
  VITE_COORDINATOR_API=https://coordinator.dev.internal
  ```
  With live mode enabled, the SPA will request `/v1/<resource>` routes from the coordinator instead of the bundled mock JSON.

## Next Steps

- Build out responsive styling and navigation interactions.
- Extend the data layer to support coordinator authentication and pagination when live endpoints are ready.
- Document coordinator API assumptions once the backend contracts stabilize.

## Coordinator API Contracts (Draft)

- **Blocks** (`GET /v1/blocks?limit=&offset=`)
  - Expected payload:
    ```json
    {
      "items": [
        {
          "height": 12045,
          "hash": "0x...",
          "timestamp": "2025-09-27T01:58:12Z",
          "tx_count": 8,
          "proposer": "miner-alpha"
        }
      ],
      "next_offset": 12040
    }
    ```
  - TODO: confirm pagination fields and proposer metadata.

- **Transactions** (`GET /v1/transactions?limit=&offset=`)
  - Expected payload:
    ```json
    {
      "items": [
        {
          "hash": "0x...",
          "block": 12045,
          "from": "0x...",
          "to": "0x...",
          "value": "12.5",
          "status": "Succeeded"
        }
      ],
      "next_offset": "0x..."
    }
    ```
  - TODO: finalize value units (AIT vs wei) and status enum.

- **Addresses** (`GET /v1/addresses/{address}`)
  - Expected payload:
    ```json
    {
      "address": "0x...",
      "balance": "1450.25",
      "tx_count": 42,
      "last_active": "2025-09-27T01:48:00Z",
      "recent_transactions": ["0x..."]
    }
    ```
  - TODO: detail pagination for recent transactions and add receipt summary references.

- **Receipts** (`GET /v1/jobs/{job_id}/receipts`)
  - Expected payload:
    ```json
    {
      "job_id": "job-0001",
      "items": [
        {
          "receipt_id": "rcpt-123",
          "miner": "miner-alpha",
          "coordinator": "coordinator-001",
          "issued_at": "2025-09-27T01:52:22Z",
          "status": "Attested",
          "payload": {
            "miner_signature": "0x...",
            "coordinator_signature": "0x..."
          }
        }
      ]
    }
    ```
  - TODO: confirm signature payload structure and include attestation metadata.

## Styling Guide

- **`public/css/base.css`**
  - Defines global typography, color scheme, and utility classes (tables, placeholders, code tags).
  - Use this file for cross-page primitives and reset/normalization rules.
  - When adding new utilities (e.g., badges, alerts), document them in this section and keep naming consistent with the existing BEM-lite approach.

- **`public/css/layout.css`**
  - Contains structural styles for the Explorer shell (header, footer, cards, forms, grids).
  - Encapsulate component-specific classes with a predictable prefix, such as `.blocks__table`, `.addresses__input-group`, or `.receipts__controls`.
  - Prefer utility classes from `base.css` when possible, and only introduce new layout classes when a component requires dedicated styling.

- **Adding New Components**
  - Create semantic markup first in `src/pages/` or `src/components/`, using descriptive class names that map to the page or component (`.transactions__filter`, `.overview__chart`).
  - Extend `layout.css` with matching selectors to style the new elements; keep related rules grouped together for readability.
  - For reusable widgets across multiple pages, consider extracting shared styles into a dedicated section or introducing a new partial CSS file when the component becomes complex.

## Deployment Notes

- **Environment Variables**
  - `VITE_DATA_MODE`: `mock` (default) or `live`.
  - `VITE_COORDINATOR_API`: Base URL for coordinator API when `live` mode is enabled.
  - Additional Vite variables can be added following the `VITE_*` naming convention.

- **Mock vs Live**
  - In non-production environments, keep `VITE_DATA_MODE=mock` to serve the static JSON under `public/mock/` for quick demos.
  - For staging/production deployments, set `VITE_DATA_MODE=live` and ensure the coordinator endpoint is reachable from the frontend origin; configure CORS accordingly on the backend.
  - Consider serving mock JSON from a CDN or static bucket if you want deterministic demos while backend dependencies are under development.

- **Build & Deploy**
  - Build command: `npm run build` (outputs to `dist/`).
  - Preview locally with `npm run preview` before publishing.
  - Deploy the `dist/` contents to your static host (e.g., Nginx, S3 + CloudFront, Vercel). Ensure environment variables are injected at build time or through runtime configuration mechanisms supported by your hosting provider.

## Error Handling (Live Mode)

- **Status Codes**
  - `2xx`: Treat as success; map response bodies into the typed models in `src/lib/models.ts`.
  - `4xx`: Surface actionable messages to the user (e.g., invalid job ID). For `404`, show “not found” states in the relevant page. For `429`, display a rate-limit notice and back off.
  - `5xx`: Show a generic coordinator outage message and trigger retry logic.

- **Retry Strategy**
  - Use an exponential backoff with jitter when retrying `5xx` or network failures (suggested base delay 500 ms, max 5 attempts).
  - Do not retry on `4xx` except `429`; instead, display feedback.

- **Telemetry & Logging**
  - Consider emitting console warnings or hooking into an analytics layer when retries occur, noting the endpoint and status code.
  - Bubble critical errors via a shared notification component so users understand whether data is stale or unavailable.
