# AITBC CLI Blockchain Explorer Tools

## Overview

The AITBC CLI provides a blockchain explorer command group, `aitbc explorer`,
that queries the blockchain explorer service (`aitbc-blockchain-explorer`,
listening on port 8100 by default) over its HTTP API. It covers blocks,
transactions, per-address lookups, and network analytics.

The target API is configured with the `explorer_api_url` config key
(default: `http://localhost:8100` — see `cli/aitbc_cli/config.py`).

All commands print their result as JSON to stdout. Most commands accept an
optional `--chain-id` flag to select a specific chain; when omitted, the
explorer service's default chain is used.

## Command Reference

### Chain and network

```bash
# List supported chains and their basic configuration
aitbc explorer chains

# Get the current chain head and latest block height
aitbc explorer chain-head
aitbc explorer chain-head --chain-id ait-mainnet

# Get network-wide statistics for a chain
aitbc explorer network-stats
aitbc explorer network-stats --chain-id ait-mainnet

# Daily transaction activity timeline (period: 1h, 24h, 7d, 30d; default 24h)
aitbc explorer activity-timeline
aitbc explorer activity-timeline --period 7d --chain-id ait-mainnet
```

### Blocks

```bash
# List the latest blocks (defaults: --limit 10 --offset 0)
aitbc explorer latest-blocks
aitbc explorer latest-blocks --limit 20 --offset 0 --chain-id ait-mainnet

# List only non-empty blocks
aitbc explorer non-empty-blocks --limit 20

# Get a block by height (required flag)
aitbc explorer block --height 100

# Get a block by hash (required flag)
aitbc explorer block-by-hash --block-hash 0x...

# List blocks containing transactions for an address (default --limit 50)
aitbc explorer blocks-by-address --address 0x... --limit 20
```

### Transactions

```bash
# Get a transaction summary by hash (required flag)
aitbc explorer transaction --tx-hash 0x...

# Get full transaction details by hash
aitbc explorer transaction-by-hash --tx-hash 0x...

# Search transactions involving an address (default --limit 100)
aitbc explorer search-transactions --address 0x... --limit 50
```

### Addresses and providers

```bash
# List top addresses by balance (default --limit 20)
aitbc explorer top-addresses --limit 50 --chain-id ait-mainnet

# Get reputation information for a provider (required flag)
aitbc explorer provider-reputation --provider-id provider-1
```

## Underlying REST API

The CLI commands above are thin wrappers around the explorer service's REST
API (`apps/blockchain-explorer`, systemd unit `aitbc-blockchain-explorer`,
port 8100). If you prefer raw HTTP access, the corresponding endpoints are:

| CLI command | Endpoint |
|---|---|
| `chain-head` | `GET /api/chain/head` |
| `chains` | `GET /api/chains` |
| `latest-blocks` | `GET /api/blocks/latest` |
| `non-empty-blocks` | `GET /api/blocks/non-empty` |
| `block --height` | `GET /api/blocks/{height}` |
| `block-by-hash` | `GET /api/blocks/by-hash/{hash}` |
| `blocks-by-address` | `GET /api/blocks/by-address/{address}` |
| `transaction` / `transaction-by-hash` | `GET /api/transactions/by-hash/{hash}` |
| `search-transactions` | `GET /api/transactions/search` |
| `activity-timeline` | `GET /api/analytics/activity` |
| `network-stats` | `GET /api/analytics/network-stats` |
| `top-addresses` | `GET /api/analytics/top-addresses` |
| `provider-reputation` | `GET /api/analytics/provider-reputation/{provider_id}` |

The service also exposes `GET /api/analytics/overview`,
`GET /api/transactions/{tx_hash}`, `GET /api/search/transactions`,
`GET /api/search/blocks`, `GET /api/export/search`, and
`GET /api/export/blocks`, which do not currently have dedicated CLI
subcommands — query them with plain `curl` if needed.

## Related: `aitbc blockchain` (chain management)

`aitbc explorer` is strictly for reading chain data. A separate command
group, `aitbc blockchain`, manages the chains themselves (multi-chain
lifecycle and consensus). Its real subcommands are:

```bash
aitbc blockchain list                 # list chains
aitbc blockchain status [--chain-id]  # chain status
aitbc blockchain info --chain-id ...  # chain details
aitbc blockchain create --config-file ...
aitbc blockchain delete --chain-id ...
aitbc blockchain add|remove --chain-id ... --node-id ...
aitbc blockchain migrate --chain-id ... --from-node ... --to-node ...
aitbc blockchain backup|restore --chain-id ...
aitbc blockchain monitor --chain-id ...
aitbc blockchain sync-status [--chain-id]
aitbc blockchain start|stop --chain-id ...
aitbc blockchain instances
aitbc blockchain consensus status|validators|slashing-history --chain-id ...
aitbc blockchain height
aitbc blockchain block <HEIGHT>
```

See `aitbc blockchain --help` for the full option list.

## Removed commands

Earlier versions of this document described CLI features that do not exist
in the current codebase — including real-time monitoring filters, `--since`/
`--until` time-range search, `--min-amount` filtering, `--output`/`--format`
formatting flags, CSV/database export, caching controls, API-proxy mode,
benchmarks, remote/tunnel access, batch lookups, and compliance/AML
reporting. None of these are implemented; use the commands listed above
(filter results with `jq` where needed).

## Help

```bash
aitbc explorer --help
aitbc explorer <COMMAND> --help
```
