# Service operational notes

Service-level operational notes for agents. Deployment-specific values
(concrete hosts, addresses, keys) intentionally do not live here — this
file names env variables and code paths only.

## Exchange settlement — sell-escrow key slot

When an exchange order settles, the on-chain AIT spend is a `TRANSFER`
from the `AIT_SELL_ESCROW` account. The signing actor is the exchange
settlement monitor inside **`aitbc-wallet`**
(`apps/wallet/src/wallet_app/bridge/exchange_settlement_monitor.py`,
shared escrow machinery in `sell_escrow_monitor.py`):
`aitbc-exchange` itself only writes ledger rows and mirrors settlement
events — it holds no keys.

| step | actor/service | signing key env name | address env name |
|---|---|---|---|
| order/trade rows | `aitbc-exchange` | — none (DB writes only) | `AIT_SELL_ESCROW`, `BRIDGE_ETH_ADDRESS` |
| AIT sweep escrow→buyer + fee→treasury | `aitbc-wallet` settlement monitor | `SELL_ESCROW_WALLET_PATH` + `SELL_ESCROW_CREDENTIAL_FILE` / `SELL_ESCROW_CREDENTIAL_NAME` | `AIT_SELL_ESCROW` (from), `SELL_TREASURY_ADDRESS` (fee leg) |
| ETH leg → seller payout | `aitbc-wallet` withdraw machinery | `ETH_WALLET_PRIVATE_KEY` (fallback `BRIDGE_ADMIN_PRIVATE_KEY`) | `ETH_WALLET_ADDRESS` |
| bridge AIT payouts | `aitbc-bridge-monitor` | `BRIDGE_PAYOUT_PRIVATE_KEY` (deprecated fallback `GENESIS_WALLET_PRIVATE_KEY`) | `BRIDGE_PAYOUT_ADDRESS` (fallback `GENESIS_WALLET_ADDRESS`) |

Key-slot mechanics (`sell_escrow_monitor.py:_load_escrow_key`):

- The signing key exists only inside an encrypted wallet JSON at
  `SELL_ESCROW_WALLET_PATH`; the passphrase arrives via a
  systemd-creds sealed credential (`SELL_ESCROW_CREDENTIAL_FILE` /
  `SELL_ESCROW_CREDENTIAL_NAME`). **No `*_PRIVATE_KEY` env var exists on
  the AIT spend path — never invent one.**
- At load, the derived address is checked against `AIT_SELL_ESCROW`
  ("escrow key slot does not derive to AIT_SELL_ESCROW"). A slot whose
  key does not derive to the configured address fails the check — do
  not "fix" it by regenerating (see the wallet-key-mismatch rule in
  `AGENTS.md`); a new key is a different account.
- Nothing on the settlement path falls back to the bridge payout key or
  the genesis key.

## `GENESIS_*` vs `FAUCET_*`

`GENESIS_WALLET_ADDRESS` / `GENESIS_WALLET_PRIVATE_KEY` name the
treasury keypair where they are still read — the wallet app and
`aitbc-bridge-monitor` payout fallback
(`apps/wallet/src/wallet_app/bridge/bridge_monitor.py:49-50`,
`apps/bridge-monitor/src/bridge_monitor/main.py:51-58`).
Agent-coordinator and node env files instead use `GENESIS_ADDRESS` /
`GENESIS_PRIVATE_KEY` for the same treasury wallet.
`FAUCET_*` names the dedicated, budget-capped grant wallet for agent
coin requests — once #609 merges, `FAUCET_*` will be read first with
`GENESIS_*` as the fallback (#609, not merged yet). The exchange settlement
path reads neither.
