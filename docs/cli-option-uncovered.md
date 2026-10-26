# Unexercised CLI options — canonical list

Generated from the OPTION-DOCS-1 census on the current main (regenerate with
`scripts/dev/gen_option_coverage.py`; this file is the row-citation source).

Legend: 🔒 = secret-value flag, intentionally unexercised.
**347 non-secret unexercised, 271 secret-excluded.**


## `account` — 4 unexercised (+0 🔒)
- `aitbc account get` `--rpc-url`
- `aitbc account get` `--chain-id`
- `aitbc account list` `--rpc-url`
- `aitbc account list` `--chain-id`

## `agent` — 0 unexercised (+9 🔒)

## `agent-comm` — 12 unexercised (+9 🔒)
- `aitbc agent-comm collaborate` `--governance`
- `aitbc agent-comm receive` `--wallet`
- `aitbc agent-comm receive` `--format`
- `aitbc agent-comm register` `--agent-type`
- `aitbc agent-comm register` `--wallet`
- `aitbc agent-comm reputation` `--feedback`
- `aitbc agent-comm send` `--payload`
- `aitbc agent-comm send` `--target-chain`
- `aitbc agent-comm send` `--priority`
- `aitbc agent-comm send` `--ttl`
- `aitbc agent-comm send` `--wallet`
- `aitbc agent-comm status` `--format`

## `agent-msg` — 10 unexercised (+12 🔒)
- `aitbc agent-msg ping` `--wallet`
- `aitbc agent-msg receive` `--wallet`
- `aitbc agent-msg receive` `--sign`, `--no-sign`
- `aitbc agent-msg request-coins` `--sender`
- `aitbc agent-msg request-coins` `--coordinator-url`
- `aitbc agent-msg request-coins` `--timeout`
- `aitbc agent-msg send` `--message-type`
- `aitbc agent-msg send` `--ttl`
- `aitbc agent-msg send` `--wallet`
- `aitbc agent-msg send` `--sign`, `--no-sign`

## `agent-task` — 0 unexercised (+9 🔒)

## `agent-wallet` — 2 unexercised (+0 🔒)
- `aitbc agent-wallet rebalance` `--earnings`
- `aitbc agent-wallet stake` `--contract`

## `ai` — 5 unexercised (+10 🔒)
- `aitbc ai submit` `--auto-reinvest-pct`
- `aitbc ai submit` `--deterministic-decoding`, `--no-deterministic-decoding`
- `aitbc ai submit` `--chain-id`
- `aitbc ai submit` `--rpc-url`
- `aitbc ai submit` `--poll-interval`

## `auth` — 0 unexercised (+5 🔒)

## `blockchain` — 14 unexercised (+0 🔒)
- `aitbc blockchain monitor` `--interval`
- `aitbc blockchain remove` `--migrate`
- `aitbc blockchain restore` `--node`
- `aitbc blockchain restore` `--verify`
- `aitbc blockchain start` `--node-url`
- `aitbc blockchain start` `--type`
- `aitbc blockchain status` `--chain-id`
- `aitbc blockchain status` `--node-url`
- `aitbc blockchain status` `--detailed`
- `aitbc blockchain status` `--local`
- `aitbc blockchain stop` `--node-url`
- `aitbc blockchain sync-status` `--node-url`
- `aitbc blockchain sync-status` `--all-chains`
- `aitbc blockchain sync-status` `--chain-id`

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

## `bootstrap` — 1 unexercised (+0 🔒)
- `aitbc bootstrap bootstrap-env` `--overwrite`

## `bridge` — 1 unexercised (+9 🔒)
- `aitbc bridge unlock` `--signature`

## `contract` — 3 unexercised (+0 🔒)
- `aitbc contract call` `--method`
- `aitbc contract call` `--args`
- `aitbc contract call` `--rpc-url`

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

## `dashboard` — 4 unexercised (+0 🔒)
- `aitbc dashboard customer` `--limit`
- `aitbc dashboard customer` `--wallet-limit`
- `aitbc dashboard shop` `--miner-id`
- `aitbc dashboard shop` `--limit`

## `developer` — 4 unexercised (+0 🔒)
- `aitbc developer register` `--name`
- `aitbc developer register` `--email`
- `aitbc developer register` `--github-handle`
- `aitbc developer register` `--format`

## `dispute` — 2 unexercised (+0 🔒)
- `aitbc dispute file` `--node-url`
- `aitbc dispute file` `--format`

## `economics` — 4 unexercised (+0 🔒)
- `aitbc economics distributed` `--cost-optimize`
- `aitbc economics model` `--type`
- `aitbc economics vote` `--vote`
- `aitbc economics vote` `--voting-power`

## `edge` — 11 unexercised (+0 🔒)
- `aitbc edge database init-db` `--capacity-gb`
- `aitbc edge gpu list-gpus` `--architecture`
- `aitbc edge gpu list-gpus` `--edge-optimized`
- `aitbc edge gpu list-gpus` `--min-memory-gb`
- `aitbc edge island join` `--island-name`
- `aitbc edge island join` `--chain-id`
- `aitbc edge island join` `--role`
- `aitbc edge island join` `--is-hub`
- `aitbc edge serve submit-request` `--escrow-id`
- `aitbc edge transfer` `--amount`
- `aitbc edge transfer` `--note`

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

## `gpu-onchain` — 9 unexercised (+9 🔒)
- `aitbc gpu-onchain allocate` `--wait`
- `aitbc gpu-onchain allocations` `--format`
- `aitbc gpu-onchain deregister` `--wait`
- `aitbc gpu-onchain deregister` `--format`
- `aitbc gpu-onchain register` `--cuda-version`
- `aitbc gpu-onchain register` `--region`
- `aitbc gpu-onchain register` `--capabilities`
- `aitbc gpu-onchain register` `--wait`
- `aitbc gpu-onchain register` `--format`

## `health` — 3 unexercised (+0 🔒)
- `aitbc health` `--services`
- `aitbc health` `--timeout`
- `aitbc health` `--output`

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

## `messaging` — 57 unexercised (+36 🔒)
- `aitbc messaging lock` `--confirm`
- `aitbc messaging mod-grant` `--wait`, `--no-wait`
- `aitbc messaging mod-grant` `--confirm`
- `aitbc messaging mod-grant` `--fee`
- `aitbc messaging mod-revoke` `--rpc-url`
- `aitbc messaging mod-revoke` `--wait-timeout`
- `aitbc messaging mod-revoke` `--wait`, `--no-wait`
- `aitbc messaging mod-revoke` `--confirm`
- `aitbc messaging mod-revoke` `--fee`
- `aitbc messaging moderators` `--rpc-url`
- `aitbc messaging pin` `--topic`
- `aitbc messaging pin` `--rpc-url`
- `aitbc messaging pin` `--wait-timeout`
- `aitbc messaging pin` `--wait`, `--no-wait`
- `aitbc messaging pin` `--confirm`
- `aitbc messaging pin` `--fee`
- `aitbc messaging reputation` `--rpc-url`
- `aitbc messaging send` `--reply-to`
- `aitbc messaging send` `--fee`
- `aitbc messaging send` `--confirm`
- `aitbc messaging send` `--wait`, `--no-wait`
- `aitbc messaging send` `--wait-timeout`
- `aitbc messaging send` `--rpc-url`
- `aitbc messaging show` `--rpc-url`
- `aitbc messaging state` `--rpc-url`
- `aitbc messaging stats` `--rpc-url`
- `aitbc messaging subscribe` `--from-cursor`
- `aitbc messaging subscribe` `--follow`
- `aitbc messaging subscribe` `--interval`
- `aitbc messaging subscribe` `--max-polls`
- `aitbc messaging subscribe` `--rpc-url`
- `aitbc messaging topics` `--offset`
- `aitbc messaging topics` `--rpc-url`
- `aitbc messaging unhide` `--topic`
- `aitbc messaging unhide` `--rpc-url`
- `aitbc messaging unhide` `--wait-timeout`
- `aitbc messaging unhide` `--wait`, `--no-wait`
- `aitbc messaging unhide` `--confirm`
- `aitbc messaging unhide` `--fee`
- `aitbc messaging unlock` `--target`
- `aitbc messaging unlock` `--rpc-url`
- `aitbc messaging unlock` `--wait-timeout`
- `aitbc messaging unlock` `--wait`, `--no-wait`
- `aitbc messaging unlock` `--confirm`
- `aitbc messaging unlock` `--fee`
- `aitbc messaging unpin` `--topic`
- `aitbc messaging unpin` `--rpc-url`
- `aitbc messaging unpin` `--wait-timeout`
- `aitbc messaging unpin` `--wait`, `--no-wait`
- `aitbc messaging unpin` `--confirm`
- `aitbc messaging unpin` `--fee`
- `aitbc messaging vote` `--topic`
- `aitbc messaging vote` `--rpc-url`
- `aitbc messaging vote` `--wait-timeout`
- `aitbc messaging vote` `--wait`, `--no-wait`
- `aitbc messaging vote` `--confirm`
- `aitbc messaging vote` `--fee`

## `monitor` — 5 unexercised (+0 🔒)
- `aitbc monitor campaigns` `--status`
- `aitbc monitor sweepers` `--config`
- `aitbc monitor webhooks` `--name`
- `aitbc monitor webhooks` `--url`
- `aitbc monitor webhooks` `--events`

## `network` — 4 unexercised (+1 🔒)
- `aitbc network subscribe` `--rpc-url`
- `aitbc network subscribers` `--chain-id`
- `aitbc network subscribers` `--rpc-url`
- `aitbc network test` `--rpc-url`

## `operations` — 15 unexercised (+9 🔒)
- `aitbc operations agent message` `--message`
- `aitbc operations agent message` `--wallet`
- `aitbc operations agent message` `--rpc-url`
- `aitbc operations ai status` `--format`
- `aitbc operations governance delegate` `--format`
- `aitbc operations governance execute` `--format`
- `aitbc operations governance get-proposal` `--format`
- `aitbc operations governance proposal` `--params`
- `aitbc operations governance proposal` `--format`
- `aitbc operations governance stake` `--amount`
- `aitbc operations governance stake` `--lock-days`
- `aitbc operations governance stake` `--format`
- `aitbc operations governance vote` `--reason`
- `aitbc operations governance vote` `--format`
- `aitbc operations governance voting-power` `--format`

## `platform` — 1 unexercised (+0 🔒)
- `aitbc platform init-platform` `--template`

## `plugin` — 3 unexercised (+0 🔒)
- `aitbc plugin create` `--type`
- `aitbc plugin list` `--plugins-dir`
- `aitbc plugin load` `--plugins-dir`

## `prometheus` — 3 unexercised (+0 🔒)
- `aitbc prometheus rules` `--prometheus-url`
- `aitbc prometheus series` `--prometheus-url`
- `aitbc prometheus targets` `--prometheus-url`

## `reinvest` — 1 unexercised (+0 🔒)
- `aitbc reinvest simulate` `--reserve-address`

## `reputation` — 2 unexercised (+0 🔒)
- `aitbc reputation leaderboard` `--region`
- `aitbc reputation profile` `--format`

## `resource` — 7 unexercised (+0 🔒)
- `aitbc resource optimize` `--optimization-type`
- `aitbc resource optimize` `--current-accuracy`
- `aitbc resource optimize` `--current-latency`
- `aitbc resource optimize` `--current-throughput`
- `aitbc resource status` `--agent-id`
- `aitbc resource status` `--status`
- `aitbc resource status` `--limit`

## `service` — 3 unexercised (+0 🔒)
- `aitbc service harden` `--all`
- `aitbc service harden` `--read-write-paths`
- `aitbc service harden` `--no-restart`

## `simulate` — 2 unexercised (+5 🔒)
- `aitbc simulate price` `--delay`
- `aitbc simulate run` `--async-run`

## `stake` — 2 unexercised (+0 🔒)
- `aitbc stake` `--wallet-path`
- `aitbc stake` `--rpc-url`

## `system` — 2 unexercised (+1 🔒)
- `aitbc system env-names` `--value`
- `aitbc system logs` `--severity-pattern`

## `trade` — 47 unexercised (+1 🔒)
- `aitbc trade chains` `--format`
- `aitbc trade create` `--recipient`
- `aitbc trade create` `--amount`
- `aitbc trade create` `--offer-id`
- `aitbc trade create` `--price`
- `aitbc trade create` `--quantity`
- `aitbc trade create` `--format`
- `aitbc trade discover` `--region`
- `aitbc trade discover` `--gpu-model`
- `aitbc trade discover` `--format`
- `aitbc trade get` `--format`
- `aitbc trade health` `--format`
- `aitbc trade history` `--dest-chain`
- `aitbc trade history` `--format`
- `aitbc trade list` `--dest-chain`
- `aitbc trade list` `--limit`
- `aitbc trade list` `--format`
- `aitbc trade lock-escrow` `--node-url`
- `aitbc trade lock-escrow` `--api-key`
- `aitbc trade lock-escrow` `--timeout`
- `aitbc trade lock-escrow` `--format`
- `aitbc trade match` `--format`
- `aitbc trade match-all` `--format`
- `aitbc trade refund` `--node-url`
- `aitbc trade refund` `--api-key`
- `aitbc trade refund` `--format`
- `aitbc trade register-chain` `--endpoint`
- `aitbc trade register-chain` `--format`
- `aitbc trade search` `--service-type`
- `aitbc trade search` `--min-price`
- `aitbc trade search` `--max-price`
- `aitbc trade search` `--format`
- `aitbc trade settle` `--node-url`
- `aitbc trade settle` `--api-key`
- `aitbc trade settle` `--format`
- `aitbc trade settlement-status` `--node-url`
- `aitbc trade settlement-status` `--api-key`
- `aitbc trade settlement-status` `--format`
- `aitbc trade status` `--format`
- `aitbc trade subscription-status` `--format`
- `aitbc trade sync` `--format`
- `aitbc trade sync-status` `--format`
- `aitbc trade watch` `--min-price`
- `aitbc trade watch` `--max-price`
- `aitbc trade watch` `--region`
- `aitbc trade watch` `--gpu-model`
- `aitbc trade watch` `--format`

## `transactions` — 8 unexercised (+6 🔒)
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
