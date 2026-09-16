# Exchange Integration

## Status

⚠️ **Not a standalone service.** There is no `apps/exchange-integration`
directory in this repository — this document previously described a
blockchain-connector / data-feed / webhook service that was never shipped.

The functionality this page covered is provided by existing components:

- **Exchange bridge endpoints** (ETH → AIT deposit/withdraw/estimate/status,
  cross-chain rates) — implemented inside the exchange service itself at
  `apps/exchange/simple_exchange/handlers/bridge.py`, exposed by
  `aitbc-exchange` on port 8106 (`/v1/bridge/*`, `/v1/cross-chain/rates`,
  `/exchange/price.json`). See [Exchange](./exchange.md).
- **Bridge monitoring** — `apps/bridge-monitor` (`aitbc-bridge-monitor`
  systemd unit, hub node) watches cross-chain bridge health, liquidity, and
  transaction status.
- **Exchange CLI** — `aitbc exchange` (`cli/aitbc_cli/commands/exchange/`)
  provides operator-facing exchange commands.

## What does not exist

The following were documented here but have no implementation — do not rely
on them:

- `POST /api/v1/integration/blockchain/sync`
- `POST /api/v1/integration/feeds/subscribe`,
  `GET /api/v1/integration/feeds/{feed_id}/data`
- `POST /api/v1/integration/webhooks`,
  `POST /api/v1/integration/webhooks/process`
- `GET /api/v1/integration/blockchain/status`
- `EXTERNAL_EXCHANGE_API_KEY`, `WEBHOOK_SECRET`, `SYNC_INTERVAL` env vars

If a webhook/data-feed integration layer is added in the future, this page
should be rewritten against its real implementation.

## Related

- [Exchange](./exchange.md) — the `aitbc-exchange` service (port 8106)
- [Trading engine](./trading-engine.md) — `apps/trading`
