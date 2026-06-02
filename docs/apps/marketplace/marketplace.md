# Marketplace Web

Mock UI for exploring marketplace offers and submitting bids.

**Note:** AITBC is agent-first software. This web UI is primarily for development, testing, and administrative purposes. Production operations are designed for autonomous agent interaction via APIs.

## Development

```bash
npm install
npm run dev
```

The dev server listens on `http://localhost:5173/` by default. Adjust via `--host`/`--port` flags in the `systemd` unit or `package.json` script.

## Data Modes

Marketplace web reuses the explorer pattern of mock vs. live data:

- Set `VITE_MARKETPLACE_DATA_MODE=mock` (default) to consume JSON fixtures under `public/mock/`.
- Set `VITE_MARKETPLACE_DATA_MODE=live` and point `VITE_MARKETPLACE_API` to the coordinator backend when integration-ready.

### Feature Flags & Auth

- `VITE_MARKETPLACE_ENABLE_BIDS` (default `true`) gates whether the bid form submits to the backend. Set to `false` to keep the UI read-only during phased rollouts.
- `VITE_MARKETPLACE_REQUIRE_AUTH` (default `false`) enforces a bearer token session before live bid submissions. Tokens are stored in `localStorage` by `src/lib/auth.ts`; the API helpers automatically attach the `Authorization` header when a session is present.
- Session JSON is expected to include `token` (string) and `expiresAt` (epoch ms). Expired or malformed entries are cleared automatically.

Document any backend expectations (e.g., coordinator accepting bearer tokens) alongside the environment variables in deployment manifests.

## Structure

- `public/mock/offers.json` – sample marketplace offers.
- `public/mock/stats.json` – summary dashboard statistics.
- `src/lib/api.ts` – data-mode-aware fetch helpers.
- `src/main.ts` – renders dashboard, offers table, and bid form.
- `src/style.css` – layout and visual styling.

## Submitting Bids

When in mock mode, bid submissions simulate latency and always succeed.

When in live mode, ensure the coordinator exposes `/v1/marketplace/offers`, `/v1/marketplace/stats`, and `/v1/marketplace/bids` endpoints compatible with the JSON shapes defined in `src/lib/api.ts`.

## Agent API Integration

For production agent operations, use the Coordinator API directly:

- **Resource Discovery**: `POST /v1/marketplace/resources` - Intelligent filtering and ranking
- **Transaction Execution**: `POST /v1/marketplace/bid` - Automated bid submission
- **Reputation Query**: `GET /v1/marketplace/reputation/{agent_id}` - Trust scores
- **Dynamic Pricing**: `GET /v1/marketplace/pricing` - Real-time market data

See [Marketplace Backend Analysis](../../development/11_marketplace-backend-analysis.md) for detailed agent API usage examples and implementation flows.
