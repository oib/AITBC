# Unexercised CLI options — canonical list

Generated from the OPTION-DOCS-1 census on the current main (regenerate with
`scripts/dev/gen_option_coverage.py`; this file is the row-citation source).

Legend: 🔒 = secret-value flag, intentionally unexercised.
**46 non-secret unexercised, 258 secret-excluded.**


## `agent` — 0 unexercised (+9 🔒)

## `agent-comm` — 0 unexercised (+9 🔒)

## `agent-msg` — 0 unexercised (+12 🔒)

## `agent-task` — 0 unexercised (+9 🔒)

## `ai` — 0 unexercised (+10 🔒)

## `auth` — 0 unexercised (+5 🔒)

## `bridge` — 0 unexercised (+5 🔒)

## `crosschain` — 3 unexercised (+9 🔒)
- `aitbc crosschain bridge` `--wait`
- `aitbc crosschain bridge` `--timeout`
- `aitbc crosschain status` `--wait`

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

## `governance` — 0 unexercised (+9 🔒)

## `gpu-onchain` — 0 unexercised (+9 🔒)

## `ipfs` — 0 unexercised (+7 🔒)

## `liquidity-stake` — 6 unexercised (+0 🔒)
- `aitbc liquidity-stake` `--wallet-name`
- `aitbc liquidity-stake` `--wallet-path`
- `aitbc liquidity-stake` `--rpc-url`
- `aitbc liquidity-stake` `--pool`
- `aitbc liquidity-stake` `--lock-days`
- `aitbc liquidity-stake` `--fee`

## `market` — 0 unexercised (+10 🔒)

## `messaging` — 0 unexercised (+36 🔒)

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

## `reinvest` — 1 unexercised (+0 🔒)
- `aitbc reinvest simulate` `--reserve-address`

## `stake` — 2 unexercised (+0 🔒)
- `aitbc stake` `--wallet-path`
- `aitbc stake` `--rpc-url`

## `system` — 0 unexercised (+1 🔒)

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

## `wallet` — 0 unexercised (+62 🔒)
