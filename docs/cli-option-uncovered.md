# Unexercised CLI options — canonical list

Generated from the OPTION-DOCS-1 census on the current main (regenerate with
`scripts/dev/gen_option_coverage.py`; this file is the row-citation source).

Legend: 🔒 = secret-value flag, intentionally unexercised.
**150 non-secret unexercised, 258 secret-excluded.**


## `account` — 2 unexercised (+0 🔒)
- `aitbc account list` `--rpc-url`
- `aitbc account list` `--chain-id`

## `agent` — 0 unexercised (+9 🔒)

## `agent-comm` — 0 unexercised (+9 🔒)

## `agent-msg` — 0 unexercised (+12 🔒)

## `agent-task` — 0 unexercised (+9 🔒)

## `agent-wallet` — 1 unexercised (+0 🔒)
- `aitbc agent-wallet stake` `--contract`

## `ai` — 0 unexercised (+10 🔒)

## `auth` — 0 unexercised (+5 🔒)

## `bond` — 18 unexercised (+0 🔒)
- `aitbc bond appeal` `--reason`
- `aitbc bond appeal` `--evidence`
- `aitbc bond appeal` `--coordinator-url`
- `aitbc bond appeal` `--format`
- `aitbc bond create` `--bond-id`
- `aitbc bond create` `--coordinator-url`
- `aitbc bond create` `--format`
- `aitbc bond lock` `--coordinator-url`
- `aitbc bond lock` `--format`
- `aitbc bond release` `--coordinator-url`
- `aitbc bond release` `--format`
- `aitbc bond slash` `--coordinator-url`
- `aitbc bond slash` `--format`
- `aitbc bond status` `--coordinator-url`
- `aitbc bond status` `--format`
- `aitbc bond top-up` `--bond-id`
- `aitbc bond top-up` `--coordinator-url`
- `aitbc bond top-up` `--format`

## `bridge` — 0 unexercised (+5 🔒)

## `crosschain` — 21 unexercised (+9 🔒)
- `aitbc crosschain bridge` `--rpc-url`
- `aitbc crosschain bridge` `--wait`
- `aitbc crosschain bridge` `--timeout`
- `aitbc crosschain bridge-status` `--rpc-url`
- `aitbc crosschain bridge-status` `--timeout`
- `aitbc crosschain confirm` `--source-chain`
- `aitbc crosschain confirm` `--rpc-url`
- `aitbc crosschain pools` `--rpc-url`
- `aitbc crosschain rates` `--from-token`
- `aitbc crosschain rates` `--to-token`
- `aitbc crosschain rates` `--rpc-url`
- `aitbc crosschain stats` `--rpc-url`
- `aitbc crosschain status` `--rpc-url`
- `aitbc crosschain status` `--wait`
- `aitbc crosschain status` `--timeout`
- `aitbc crosschain swap` `--min-amount`
- `aitbc crosschain swap` `--recipient`
- `aitbc crosschain swap` `--rpc-url`
- `aitbc crosschain swap` `--timeout`
- `aitbc crosschain swaps` `--user-address`
- `aitbc crosschain swaps` `--rpc-url`

## `dashboard` — 2 unexercised (+0 🔒)
- `aitbc dashboard shop` `--miner-id`
- `aitbc dashboard shop` `--limit`

## `developer` — 1 unexercised (+0 🔒)
- `aitbc developer register` `--format`

## `economics` — 2 unexercised (+0 🔒)
- `aitbc economics model` `--type`
- `aitbc economics vote` `--voting-power`

## `energy` — 0 unexercised (+9 🔒)

## `eth` — 7 unexercised (+0 🔒)
- `aitbc eth transfers` `--address`, `-a`
- `aitbc eth transfers` `--since`
- `aitbc eth transfers` `--json`
- `aitbc eth transfers` `--log`
- `aitbc eth transfers` `--no-log`
- `aitbc eth transfers` `--rpc-url`
- `aitbc eth transfers` `--explorer-url`

## `exchange` — 0 unexercised (+19 🔒)

## `exchange-island` — 0 unexercised (+9 🔒)

## `genesis` — 0 unexercised (+6 🔒)

## `governance` — 6 unexercised (+9 🔒)
- `aitbc governance execute` `--format`
- `aitbc governance propose` `--format`
- `aitbc governance status` `--format`
- `aitbc governance vote` `--voting-power`
- `aitbc governance vote` `--wallet`
- `aitbc governance vote` `--format`

## `gpu-onchain` — 0 unexercised (+9 🔒)

## `ipfs` — 6 unexercised (+7 🔒)
- `aitbc ipfs download` `--access-key`
- `aitbc ipfs download` `--rental-id`
- `aitbc ipfs island swarm-key` `--rpc-url`
- `aitbc ipfs island swarm-key` `--api-key`
- `aitbc ipfs island swarm-key` `--output`
- `aitbc ipfs island swarm-key` `--bootstrap`

## `liquidity-stake` — 6 unexercised (+0 🔒)
- `aitbc liquidity-stake` `--wallet-name`
- `aitbc liquidity-stake` `--wallet-path`
- `aitbc liquidity-stake` `--rpc-url`
- `aitbc liquidity-stake` `--pool`
- `aitbc liquidity-stake` `--lock-days`
- `aitbc liquidity-stake` `--fee`

## `market` — 0 unexercised (+10 🔒)

## `messaging` — 0 unexercised (+36 🔒)

## `monitor` — 4 unexercised (+0 🔒)
- `aitbc monitor sweepers` `--config`
- `aitbc monitor webhooks` `--name`
- `aitbc monitor webhooks` `--url`
- `aitbc monitor webhooks` `--events`

## `network` — 4 unexercised (+0 🔒)
- `aitbc network subscribe` `--rpc-url`
- `aitbc network subscribers` `--chain-id`
- `aitbc network subscribers` `--rpc-url`
- `aitbc network test` `--rpc-url`

## `operations` — 10 unexercised (+9 🔒)
- `aitbc operations agent message` `--rpc-url`
- `aitbc operations governance delegate` `--format`
- `aitbc operations governance execute` `--format`
- `aitbc operations governance get-proposal` `--format`
- `aitbc operations governance proposal` `--params`
- `aitbc operations governance proposal` `--format`
- `aitbc operations governance stake` `--format`
- `aitbc operations governance vote` `--reason`
- `aitbc operations governance vote` `--format`
- `aitbc operations governance voting-power` `--format`

## `plugin` — 2 unexercised (+0 🔒)
- `aitbc plugin create` `--type`
- `aitbc plugin load` `--plugins-dir`

## `reinvest` — 1 unexercised (+0 🔒)
- `aitbc reinvest simulate` `--reserve-address`

## `reputation` — 1 unexercised (+0 🔒)
- `aitbc reputation profile` `--format`

## `resource` — 7 unexercised (+0 🔒)
- `aitbc resource optimize` `--optimization-type`
- `aitbc resource optimize` `--current-accuracy`
- `aitbc resource optimize` `--current-latency`
- `aitbc resource optimize` `--current-throughput`
- `aitbc resource status` `--agent-id`
- `aitbc resource status` `--status`
- `aitbc resource status` `--limit`

## `simulate` — 1 unexercised (+0 🔒)
- `aitbc simulate run` `--async-run`

## `stake` — 2 unexercised (+0 🔒)
- `aitbc stake` `--wallet-path`
- `aitbc stake` `--rpc-url`

## `system` — 2 unexercised (+1 🔒)
- `aitbc system env-names` `--value`
- `aitbc system logs` `--severity-pattern`

## `trade` — 4 unexercised (+0 🔒)
- `aitbc trade create` `--offer-id`
- `aitbc trade create` `--price`
- `aitbc trade create` `--quantity`
- `aitbc trade lock-escrow` `--node-url`

## `transactions` — 8 unexercised (+4 🔒)
- `aitbc transactions search` `--recipient`
- `aitbc transactions search` `--rpc-url`
- `aitbc transactions send` `--fee`
- `aitbc transactions send` `--rpc-url`
- `aitbc transactions send` `--type`
- `aitbc transactions send` `--payload`
- `aitbc transactions send` `--use-explorer`
- `aitbc transactions status` `--rpc-url`

## `unstake` — 3 unexercised (+0 🔒)
- `aitbc unstake` `--wallet-name`
- `aitbc unstake` `--wallet-path`
- `aitbc unstake` `--rpc-url`

## `wallet` — 29 unexercised (+62 🔒)
- `aitbc wallet address` `--name`
- `aitbc wallet bridge float` `--hub-url`
- `aitbc wallet bridge sell lock` `--hub-url`
- `aitbc wallet bridge sell quote` `--wallet-name`
- `aitbc wallet bridge sell quote` `--hub-url`
- `aitbc wallet bridge settlements` `--state`
- `aitbc wallet bridge settlements` `--kind`
- `aitbc wallet bridge settlements` `--hub-url`
- `aitbc wallet bridge status` `--ait-tx-hash`
- `aitbc wallet bridge status` `--today`
- `aitbc wallet bridge status` `--24h`
- `aitbc wallet bridge status` `--hub-url`
- `aitbc wallet eth-balance` `--address`
- `aitbc wallet eth-balance` `--eth-rpc-url`
- `aitbc wallet eth-send` `--eth-rpc-url`
- `aitbc wallet eth-send` `--max-gas-gwei`
- `aitbc wallet eth-send` `--allow-contract`
- `aitbc wallet eth-send` `--confirm`
- `aitbc wallet eth-send` `--wait`
- `aitbc wallet inspect` `--field`
- `aitbc wallet liquidity-claim` `--fee`
- `aitbc wallet liquidity-stake` `--lock-days`
- `aitbc wallet liquidity-stake` `--fee`
- `aitbc wallet liquidity-unstake` `--fee`
- `aitbc wallet send` `--fee`
- `aitbc wallet send` `--wait`
- `aitbc wallet send` `--rpc-url`
- `aitbc wallet staking-info` `--address`
- `aitbc wallet transactions` `--limit`
