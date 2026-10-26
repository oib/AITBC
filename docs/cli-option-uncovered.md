# Unexercised CLI options — canonical list

Generated from the OPTION-DOCS-1 census on the current main (regenerate with
`scripts/dev/gen_option_coverage.py`; this file is the row-citation source).

Legend: 🔒 = secret-value flag, intentionally unexercised.
**921 non-secret unexercised, 255 secret-excluded.**


## `account` — 4 unexercised (+0 🔒)
- `aitbc account get` --rpc-url
- `aitbc account get` --chain-id
- `aitbc account list` --rpc-url
- `aitbc account list` --chain-id

## `agent` — 24 unexercised (+9 🔒)
- `aitbc agent capabilities` --format
- `aitbc agent create` --auto-detect
- `aitbc agent inbox` --agent-id
- `aitbc agent inbox` --unread-only
- `aitbc agent inbox` --wallet
- `aitbc agent inbox` --coordinator-url
- `aitbc agent inbox` --format
- `aitbc agent list` --agent-dir
- `aitbc agent register` --wallet
- `aitbc agent status` --coordinator-url
- `aitbc agent subscribe` --filter
- `aitbc agent subscribe` --wallet
- `aitbc agent subscribe` --coordinator-url
- `aitbc agent subscribe` --format
- `aitbc agent workflow create-workflow` --description
- `aitbc agent workflow create-workflow` --coordinator-url
- `aitbc agent workflow create-workflow` --format
- `aitbc agent workflow execute` --input-file
- `aitbc agent workflow execute` --coordinator-url
- `aitbc agent workflow execute` --format
- `aitbc agent workflow list-workflows` --coordinator-url
- `aitbc agent workflow list-workflows` --format
- `aitbc agent workflow workflow-status` --coordinator-url
- `aitbc agent workflow workflow-status` --format

## `agent-comm` — 17 unexercised (+9 🔒)
- `aitbc agent-comm collaborate` --governance
- `aitbc agent-comm discover` --format
- `aitbc agent-comm list` --status
- `aitbc agent-comm monitor` --realtime
- `aitbc agent-comm monitor` --interval
- `aitbc agent-comm network` --format
- `aitbc agent-comm receive` --wallet
- `aitbc agent-comm receive` --format
- `aitbc agent-comm register` --agent-type
- `aitbc agent-comm register` --wallet
- `aitbc agent-comm reputation` --feedback
- `aitbc agent-comm send` --payload
- `aitbc agent-comm send` --target-chain
- `aitbc agent-comm send` --priority
- `aitbc agent-comm send` --ttl
- `aitbc agent-comm send` --wallet
- `aitbc agent-comm status` --format

## `agent-msg` — 10 unexercised (+12 🔒)
- `aitbc agent-msg ping` --wallet
- `aitbc agent-msg receive` --wallet
- `aitbc agent-msg receive` --sign`, `--no-sign
- `aitbc agent-msg request-coins` --sender
- `aitbc agent-msg request-coins` --coordinator-url
- `aitbc agent-msg request-coins` --timeout
- `aitbc agent-msg send` --message-type
- `aitbc agent-msg send` --ttl
- `aitbc agent-msg send` --wallet
- `aitbc agent-msg send` --sign`, `--no-sign

## `agent-task` — 14 unexercised (+9 🔒)
- `aitbc agent-task hire` --model
- `aitbc agent-task hire` --from-agent
- `aitbc agent-task hire` --timeout
- `aitbc agent-task hire` --wait-seconds
- `aitbc agent-task hire` --sign`, `--no-sign
- `aitbc agent-task hire` --coordinator-url
- `aitbc agent-task result` --from-agent
- `aitbc agent-task result` --wallet
- `aitbc agent-task result` --sign`, `--no-sign
- `aitbc agent-task result` --coordinator-url
- `aitbc agent-task status` --from-agent
- `aitbc agent-task status` --wallet
- `aitbc agent-task status` --sign`, `--no-sign
- `aitbc agent-task status` --coordinator-url

## `agent-wallet` — 2 unexercised (+0 🔒)
- `aitbc agent-wallet rebalance` --earnings
- `aitbc agent-wallet stake` --contract

## `ai` — 38 unexercised (+10 🔒)
- `aitbc ai accept` --coordinator-url
- `aitbc ai accept` --format
- `aitbc ai cancel` --wallet
- `aitbc ai cancel` --coordinator-url
- `aitbc ai cancel` --format
- `aitbc ai distribution-stats` --coordinator-url
- `aitbc ai distribution-stats` --format
- `aitbc ai pay` --buyer-address
- `aitbc ai pay` --provider-address
- `aitbc ai pay` --offer-id
- `aitbc ai pay` --offer-quantity
- `aitbc ai pay` --currency
- `aitbc ai pay` --coordinator-url
- `aitbc ai pay` --rpc-url
- `aitbc ai pay` --chain-id
- `aitbc ai pay` --format
- `aitbc ai refund` --coordinator-url
- `aitbc ai refund-sweep` --limit
- `aitbc ai refund-sweep` --reason
- `aitbc ai refund-sweep` --coordinator-url
- `aitbc ai refund-sweep` --format
- `aitbc ai results` --coordinator-url
- `aitbc ai service list` --format
- `aitbc ai service service-status` --coordinator-url
- `aitbc ai service test` --coordinator-url
- `aitbc ai service test` --format
- `aitbc ai stats` --coordinator-url
- `aitbc ai stats` --format
- `aitbc ai submit` --offer-quantity
- `aitbc ai submit` --acceptance-window
- `aitbc ai submit` --min-reputation
- `aitbc ai submit` --tee-attestation-required`, `--no-tee-attestation-required
- `aitbc ai submit` --tee-enclave-id
- `aitbc ai submit` --auto-reinvest-pct
- `aitbc ai submit` --deterministic-decoding`, `--no-deterministic-decoding
- `aitbc ai submit` --chain-id
- `aitbc ai submit` --rpc-url
- `aitbc ai submit` --poll-interval

## `analytics` — 3 unexercised (+0 🔒)
- `aitbc analytics alerts` --format
- `aitbc analytics dashboard` --format
- `aitbc analytics optimize` --format

## `auth` — 6 unexercised (+5 🔒)
- `aitbc auth login` --wallet-address
- `aitbc auth login` --environment
- `aitbc auth login` --credential-name
- `aitbc auth logout` --environment
- `aitbc auth logout` --credential-name
- `aitbc auth status` --environment

## `blockchain` — 50 unexercised (+0 🔒)
- `aitbc blockchain backup` --compress
- `aitbc blockchain backup` --verify
- `aitbc blockchain block` --node-url
- `aitbc blockchain block` --output
- `aitbc blockchain block` --format
- `aitbc blockchain consensus slashing-history` --node-url
- `aitbc blockchain consensus slashing-history` --chain-id
- `aitbc blockchain consensus slashing-history` --format
- `aitbc blockchain consensus status` --node-url
- `aitbc blockchain consensus status` --chain-id
- `aitbc blockchain consensus status` --format
- `aitbc blockchain consensus validators` --node-url
- `aitbc blockchain consensus validators` --chain-id
- `aitbc blockchain consensus validators` --format
- `aitbc blockchain create` --node
- `aitbc blockchain create` --dry-run
- `aitbc blockchain delete` --confirm
- `aitbc blockchain height` --node-url
- `aitbc blockchain height` --db
- `aitbc blockchain height` --output
- `aitbc blockchain height` --format
- `aitbc blockchain info` --detailed
- `aitbc blockchain info` --metrics
- `aitbc blockchain info` --local
- `aitbc blockchain info` --node-url
- `aitbc blockchain instances` --node-url
- `aitbc blockchain instances` --island
- `aitbc blockchain list` --type
- `aitbc blockchain list` --show-private
- `aitbc blockchain list` --sort
- `aitbc blockchain list` --island
- `aitbc blockchain list` --node-url
- `aitbc blockchain migrate` --dry-run
- `aitbc blockchain migrate` --verify
- `aitbc blockchain monitor` --realtime
- `aitbc blockchain monitor` --export
- `aitbc blockchain monitor` --interval
- `aitbc blockchain remove` --migrate
- `aitbc blockchain restore` --node
- `aitbc blockchain restore` --verify
- `aitbc blockchain start` --node-url
- `aitbc blockchain start` --type
- `aitbc blockchain status` --chain-id
- `aitbc blockchain status` --node-url
- `aitbc blockchain status` --detailed
- `aitbc blockchain status` --local
- `aitbc blockchain stop` --node-url
- `aitbc blockchain sync-status` --node-url
- `aitbc blockchain sync-status` --all-chains
- `aitbc blockchain sync-status` --chain-id

## `bond` — 17 unexercised (+0 🔒)
- `aitbc bond appeal` --evidence
- `aitbc bond appeal` --coordinator-url
- `aitbc bond appeal` --format
- `aitbc bond create` --bond-id
- `aitbc bond create` --coordinator-url
- `aitbc bond create` --format
- `aitbc bond lock` --coordinator-url
- `aitbc bond lock` --format
- `aitbc bond release` --coordinator-url
- `aitbc bond release` --format
- `aitbc bond slash` --coordinator-url
- `aitbc bond slash` --format
- `aitbc bond status` --coordinator-url
- `aitbc bond status` --format
- `aitbc bond top-up` --bond-id
- `aitbc bond top-up` --coordinator-url
- `aitbc bond top-up` --format

## `bootstrap` — 1 unexercised (+0 🔒)
- `aitbc bootstrap bootstrap-env` --overwrite

## `bridge` — 42 unexercised (+5 🔒)
- `aitbc bridge attest` --header-file
- `aitbc bridge attest` --source-rpc
- `aitbc bridge attest` --height
- `aitbc bridge attest` --chain-id
- `aitbc bridge attest` --proposer
- `aitbc bridge attest` --target-rpc
- `aitbc bridge attest` --output`, `-o
- `aitbc bridge balance` --rpc-url
- `aitbc bridge confirm` --rpc-url
- `aitbc bridge deposits` --status
- `aitbc bridge deposits` --tx-hash
- `aitbc bridge deposits` --repo-root
- `aitbc bridge ingest-header` --source-rpc
- `aitbc bridge ingest-header` --target-rpc
- `aitbc bridge ingest-header` --chain-id
- `aitbc bridge ingest-header` --re-sign`, `--no-re-sign
- `aitbc bridge ingest-header` --proposer
- `aitbc bridge ingest-header` --output`, `-o
- `aitbc bridge lock` --asset
- `aitbc bridge lock` --source-chain
- `aitbc bridge lock` --issued-at
- `aitbc bridge lock` --nonce
- `aitbc bridge lock` --wallet-name
- `aitbc bridge lock` --rpc-url
- `aitbc bridge oracle-status` --rpc-url
- `aitbc bridge pending` --chain-id
- `aitbc bridge pending` --rpc-url
- `aitbc bridge proof` --source-chain
- `aitbc bridge proof` --block-height
- `aitbc bridge proof` --block-hash
- `aitbc bridge proof` --rpc-url
- `aitbc bridge register-validator` --admin-address
- `aitbc bridge register-validator` --epoch
- `aitbc bridge register-validator` --rpc-url
- `aitbc bridge security-status` --rpc-url
- `aitbc bridge sign-proof` --output`, `-o
- `aitbc bridge status` --transfer-id
- `aitbc bridge status` --rpc-url
- `aitbc bridge store-header` --admin-address
- `aitbc bridge store-header` --rpc-url
- `aitbc bridge unlock` --wallet-name
- `aitbc bridge unlock` --rpc-url

## `coin-requests` — 8 unexercised (+0 🔒)
- `aitbc coin-requests list` --sender
- `aitbc coin-requests reconcile` --rpc-url
- `aitbc coin-requests reconcile` --chain-id
- `aitbc coin-requests reopen` --rpc-url
- `aitbc coin-requests reopen` --chain-id
- `aitbc coin-requests request` --sender
- `aitbc coin-requests request` --recipient
- `aitbc coin-requests request` --request-id

## `config` — 6 unexercised (+0 🔒)
- `aitbc config check-keys` --strict
- `aitbc config edit` --global
- `aitbc config path` --global
- `aitbc config reset` --global
- `aitbc config set` --global
- `aitbc config unset` --global

## `contract` — 1 unexercised (+0 🔒)
- `aitbc contract call` --rpc-url

## `crosschain` — 21 unexercised (+9 🔒)
- `aitbc crosschain bridge` --rpc-url
- `aitbc crosschain bridge` --wait
- `aitbc crosschain bridge` --timeout
- `aitbc crosschain bridge-status` --rpc-url
- `aitbc crosschain bridge-status` --timeout
- `aitbc crosschain confirm` --source-chain
- `aitbc crosschain confirm` --rpc-url
- `aitbc crosschain pools` --rpc-url
- `aitbc crosschain rates` --from-token
- `aitbc crosschain rates` --to-token
- `aitbc crosschain rates` --rpc-url
- `aitbc crosschain stats` --rpc-url
- `aitbc crosschain status` --rpc-url
- `aitbc crosschain status` --wait
- `aitbc crosschain status` --timeout
- `aitbc crosschain swap` --min-amount
- `aitbc crosschain swap` --recipient
- `aitbc crosschain swap` --rpc-url
- `aitbc crosschain swap` --timeout
- `aitbc crosschain swaps` --user-address
- `aitbc crosschain swaps` --rpc-url

## `dashboard` — 4 unexercised (+0 🔒)
- `aitbc dashboard customer` --limit
- `aitbc dashboard customer` --wallet-limit
- `aitbc dashboard shop` --miner-id
- `aitbc dashboard shop` --limit

## `developer` — 1 unexercised (+0 🔒)
- `aitbc developer register` --format

## `dispute` — 31 unexercised (+0 🔒)
- `aitbc dispute active` --node-url
- `aitbc dispute active` --format
- `aitbc dispute arbitrator authorize` --revoke
- `aitbc dispute arbitrator authorize` --signature
- `aitbc dispute arbitrator authorize` --node-url
- `aitbc dispute arbitrator authorize` --format
- `aitbc dispute arbitrator list` --node-url
- `aitbc dispute arbitrator list` --format
- `aitbc dispute arbitrator queue` --node-url
- `aitbc dispute arbitrator queue` --format
- `aitbc dispute auto-adjudicate` --coordinator-url
- `aitbc dispute auto-adjudicate` --format
- `aitbc dispute evidence add` --node-url
- `aitbc dispute evidence add` --format
- `aitbc dispute evidence list` --node-url
- `aitbc dispute evidence list` --format
- `aitbc dispute evidence verify` --reject
- `aitbc dispute evidence verify` --node-url
- `aitbc dispute evidence verify` --format
- `aitbc dispute file` --node-url
- `aitbc dispute file` --format
- `aitbc dispute get` --node-url
- `aitbc dispute get` --format
- `aitbc dispute resolve` --coordinator-url
- `aitbc dispute resolve` --format
- `aitbc dispute user` --node-url
- `aitbc dispute user` --format
- `aitbc dispute vote` --node-url
- `aitbc dispute vote` --format
- `aitbc dispute votes` --node-url
- `aitbc dispute votes` --format

## `economics` — 2 unexercised (+0 🔒)
- `aitbc economics distributed` --cost-optimize
- `aitbc economics model` --type

## `edge` — 6 unexercised (+0 🔒)
- `aitbc edge gpu list-gpus` --architecture
- `aitbc edge gpu list-gpus` --edge-optimized
- `aitbc edge gpu list-gpus` --min-memory-gb
- `aitbc edge island join` --is-hub
- `aitbc edge serve submit-request` --escrow-id
- `aitbc edge transfer` --note

## `energy` — 29 unexercised (+9 🔒)
- `aitbc energy floor` --settlement-unit-scale
- `aitbc energy floor` --json-output
- `aitbc energy provider profile` --json-output
- `aitbc energy provider rate` --publish
- `aitbc energy provider rate` --ait-per-eur
- `aitbc energy provider rate` --observed-at
- `aitbc energy provider rate` --source-kind
- `aitbc energy provider rate` --wallet
- `aitbc energy provider rate` --wallet-path
- `aitbc energy provider rate` --json-output
- `aitbc energy provider register` --wallet-path
- `aitbc energy provider register` --json-output
- `aitbc energy suggest` --gpu-model
- `aitbc energy suggest` --tbp-watts
- `aitbc energy suggest` --gpu-count
- `aitbc energy suggest` --node-gpu-count
- `aitbc energy suggest` --cpu-watts
- `aitbc energy suggest` --platform-watts
- `aitbc energy suggest` --eur-per-kwh
- `aitbc energy suggest` --ait-per-eur
- `aitbc energy suggest` --margin-pct
- `aitbc energy suggest` --duration-seconds
- `aitbc energy suggest` --resource-id
- `aitbc energy suggest` --provider-address
- `aitbc energy suggest` --model-id
- `aitbc energy suggest` --wallet
- `aitbc energy suggest` --wallet-path
- `aitbc energy suggest` --register
- `aitbc energy suggest` --json-output

## `eth` — 7 unexercised (+0 🔒)
- `aitbc eth transfers` --address`, `-a
- `aitbc eth transfers` --since
- `aitbc eth transfers` --json
- `aitbc eth transfers` --log
- `aitbc eth transfers` --no-log
- `aitbc eth transfers` --rpc-url
- `aitbc eth transfers` --explorer-url

## `exchange` — 46 unexercised (+16 🔒)
- `aitbc exchange add-liquidity` --exchange
- `aitbc exchange create-pair` --min-order-size
- `aitbc exchange create-pair` --price-precision
- `aitbc exchange create-pair` --quantity-precision
- `aitbc exchange monitor` --real-time
- `aitbc exchange monitor` --interval
- `aitbc exchange node list` --exchange-url
- `aitbc exchange node register` --label
- `aitbc exchange node register` --chain-id
- `aitbc exchange node register` --exchange-url
- `aitbc exchange node set-payout` --wallet
- `aitbc exchange node set-payout` --chain-id
- `aitbc exchange node set-payout` --exchange-url
- `aitbc exchange order book` --exchange-url
- `aitbc exchange order cancel` --expires-in
- `aitbc exchange order cancel` --chain-id
- `aitbc exchange order cancel` --exchange-url
- `aitbc exchange order fund` --fee
- `aitbc exchange order fund` --print
- `aitbc exchange order fund` --wallet
- `aitbc exchange order fund` --rpc-url
- `aitbc exchange order fund` --exchange-url
- `aitbc exchange order my` --address
- `aitbc exchange order my` --exchange-url
- `aitbc exchange order place` --expires-in
- `aitbc exchange order place` --chain-id
- `aitbc exchange order place` --exchange-url
- `aitbc exchange prepay deposit` --wallet
- `aitbc exchange prepay deposit` --max-eth
- `aitbc exchange prepay deposit` --exchange-url
- `aitbc exchange prepay deposit` --eth-rpc-url
- `aitbc exchange register` --sandbox
- `aitbc exchange register` --description
- `aitbc exchange sell_admin status` --hub-url
- `aitbc exchange start-trading` --price
- `aitbc exchange start-trading` --base-liquidity
- `aitbc exchange start-trading` --quote-liquidity
- `aitbc exchange start-trading` --exchange
- `aitbc exchange verify` --db
- `aitbc exchange verify` --bridge-db
- `aitbc exchange verify` --rpc-url
- `aitbc exchange verify` --ait-rpc
- `aitbc exchange verify` --escrow-address
- `aitbc exchange verify` --bridge-address
- `aitbc exchange verify` --settlement
- `aitbc exchange verify` --json

## `exchange-island` — 2 unexercised (+9 🔒)
- `aitbc exchange-island buy` --wallet
- `aitbc exchange-island sell` --wallet

## `explorer` — 16 unexercised (+0 🔒)
- `aitbc explorer activity-timeline` --period
- `aitbc explorer activity-timeline` --chain-id
- `aitbc explorer block` --chain-id
- `aitbc explorer block-by-hash` --chain-id
- `aitbc explorer blocks-by-address` --chain-id
- `aitbc explorer chain-head` --chain-id
- `aitbc explorer latest-blocks` --offset
- `aitbc explorer latest-blocks` --chain-id
- `aitbc explorer network-stats` --chain-id
- `aitbc explorer non-empty-blocks` --offset
- `aitbc explorer non-empty-blocks` --chain-id
- `aitbc explorer provider-reputation` --chain-id
- `aitbc explorer search-transactions` --chain-id
- `aitbc explorer top-addresses` --chain-id
- `aitbc explorer transaction` --chain-id
- `aitbc explorer transaction-by-hash` --chain-id

## `genesis` — 9 unexercised (+6 🔒)
- `aitbc genesis info` --data-dir
- `aitbc genesis init` --proposer
- `aitbc genesis init` --register-service
- `aitbc genesis init` --service-url
- `aitbc genesis reset` --new-wallet
- `aitbc genesis reset` --data-dir
- `aitbc genesis reset` --etc-dir
- `aitbc genesis reset` --wallet-dir
- `aitbc genesis sync-from-hub` --data-dir

## `governance` — 20 unexercised (+9 🔒)
- `aitbc governance aggregate-votes` --format
- `aitbc governance close` --format
- `aitbc governance execute` --executor-address
- `aitbc governance execute` --wallet
- `aitbc governance execute` --format
- `aitbc governance execute-cross-chain` --format
- `aitbc governance get` --format
- `aitbc governance list` --status
- `aitbc governance list` --category
- `aitbc governance list` --proposer-id
- `aitbc governance list` --format
- `aitbc governance propagate` --format
- `aitbc governance proposal show` --format
- `aitbc governance propose` --params
- `aitbc governance propose` --wallet
- `aitbc governance propose` --format
- `aitbc governance status` --format
- `aitbc governance vote` --voting-power
- `aitbc governance vote` --wallet
- `aitbc governance vote` --format

## `gpu-onchain` — 9 unexercised (+9 🔒)
- `aitbc gpu-onchain allocate` --wait
- `aitbc gpu-onchain allocations` --format
- `aitbc gpu-onchain deregister` --wait
- `aitbc gpu-onchain deregister` --format
- `aitbc gpu-onchain register` --cuda-version
- `aitbc gpu-onchain register` --region
- `aitbc gpu-onchain register` --capabilities
- `aitbc gpu-onchain register` --wait
- `aitbc gpu-onchain register` --format

## `grant` — 4 unexercised (+0 🔒)
- `aitbc grant create` --format
- `aitbc grant disburse` --format
- `aitbc grant list` --offset
- `aitbc grant vote` --format

## `health` — 3 unexercised (+0 🔒)
- `aitbc health` --services
- `aitbc health` --timeout
- `aitbc health` --output

## `http` — 11 unexercised (+0 🔒)
- `aitbc http call` --method`, `-X
- `aitbc http call` --params
- `aitbc http call` --body
- `aitbc http call` --url
- `aitbc http call` --api-key
- `aitbc http call` --auth
- `aitbc http call` --timeout
- `aitbc http call` --idempotency-key
- `aitbc http call` --expect-status
- `aitbc http call` --output
- `aitbc http call` --format

## `ipfs` — 13 unexercised (+7 🔒)
- `aitbc ipfs download` --wait
- `aitbc ipfs download` --access-key
- `aitbc ipfs download` --rental-id
- `aitbc ipfs island subscribe` --duration
- `aitbc ipfs island subscribe` --quota
- `aitbc ipfs island subscribe` --fee
- `aitbc ipfs island subscribe` --rpc-url
- `aitbc ipfs island swarm-key` --coordinator-url
- `aitbc ipfs island swarm-key` --chain-id
- `aitbc ipfs island swarm-key` --rpc-url
- `aitbc ipfs island swarm-key` --api-key
- `aitbc ipfs island swarm-key` --output
- `aitbc ipfs island swarm-key` --bootstrap

## `liquidity-stake` — 6 unexercised (+0 🔒)
- `aitbc liquidity-stake` --wallet-name
- `aitbc liquidity-stake` --wallet-path
- `aitbc liquidity-stake` --rpc-url
- `aitbc liquidity-stake` --pool
- `aitbc liquidity-stake` --lock-days
- `aitbc liquidity-stake` --fee

## `market` — 106 unexercised (+10 🔒)
- `aitbc market cancel` --reason
- `aitbc market cancel` --output
- `aitbc market cancel` --format
- `aitbc market download` --access-key
- `aitbc market download` --cid
- `aitbc market download` --output-path
- `aitbc market download` --wait
- `aitbc market download` --output
- `aitbc market download` --format
- `aitbc market escrow create` --amount
- `aitbc market escrow create` --wallet
- `aitbc market exchange deposit-eth` --ait-address
- `aitbc market exchange deposit-eth` --bridge-address
- `aitbc market exchange deposit-eth` --gas
- `aitbc market exchange list-deposits` --status
- `aitbc market exchange list-deposits` --limit
- `aitbc market gpu buy` --settlement
- `aitbc market gpu buy` --wallet
- `aitbc market gpu buy` --wallet-path
- `aitbc market gpu buy` --energy-quote
- `aitbc market gpu buy` --max-ait
- `aitbc market gpu buy` --yes
- `aitbc market gpu buy` --json-output
- `aitbc market gpu quote` --duration-hours
- `aitbc market gpu quote` --gpu-count
- `aitbc market gpu quote` --max-ait
- `aitbc market gpu quote` --settlement
- `aitbc market gpu quote` --json-output
- `aitbc market gpu refund` --wallet
- `aitbc market gpu refund` --wallet-path
- `aitbc market gpu refund` --reason
- `aitbc market gpu refund` --yes
- `aitbc market gpu refund` --json-output
- `aitbc market gpu release` --yes
- `aitbc market gpu release` --json-output
- `aitbc market gpu status` --json-output
- `aitbc market hermes` --max-time
- `aitbc market hermes` --track
- `aitbc market hermes` --proposer
- `aitbc market hermes` --output
- `aitbc market hermes` --format
- `aitbc market host` --pin`, `--no-pin
- `aitbc market host` --proposer-id
- `aitbc market host` --output
- `aitbc market host` --format
- `aitbc market jobs` --service-type
- `aitbc market jobs` --state
- `aitbc market jobs` --buyer-address
- `aitbc market jobs` --offer-id
- `aitbc market jobs` --limit
- `aitbc market jobs` --output
- `aitbc market jobs` --format
- `aitbc market list` --provider
- `aitbc market list` --status
- `aitbc market list` --sort
- `aitbc market list` --mine
- `aitbc market list` --output
- `aitbc market list` --format
- `aitbc market match` --output
- `aitbc market match` --format
- `aitbc market offer` --description
- `aitbc market offer` --context-window
- `aitbc market offer` --gpu-name
- `aitbc market offer` --gpu-offer-id
- `aitbc market offer` --disk-quota-mb
- `aitbc market offer-disable` --output
- `aitbc market offer-disable` --format
- `aitbc market offer-list` --service-type
- `aitbc market offer-list` --status
- `aitbc market offer-list` --output
- `aitbc market offer-list` --format
- `aitbc market payment` --job-id
- `aitbc market payment` --payment-id
- `aitbc market process` --bitrate
- `aitbc market process` --output
- `aitbc market process` --format
- `aitbc market providers` --output
- `aitbc market providers` --format
- `aitbc market rate` --comment
- `aitbc market rate` --reviewer-id
- `aitbc market rate` --market-url
- `aitbc market ratings` --limit
- `aitbc market ratings` --offset
- `aitbc market ratings` --market-url
- `aitbc market run` --max-tokens
- `aitbc market run` --stream
- `aitbc market run` --language
- `aitbc market run` --task
- `aitbc market run` --transcript-format
- `aitbc market run` --media-format
- `aitbc market run` --codec
- `aitbc market run` --resolution
- `aitbc market run` --bitrate
- `aitbc market run` --max-time
- `aitbc market run` --days
- `aitbc market run` --pin`, `--no-pin
- `aitbc market run` --track
- `aitbc market run` --proposer
- `aitbc market run` --output
- `aitbc market run` --format
- `aitbc market sync-ratings` --limit
- `aitbc market transcribe` --language
- `aitbc market transcribe` --task
- `aitbc market transcribe` --output-format
- `aitbc market transcribe` --output
- `aitbc market transcribe` --format

## `messaging` — 88 unexercised (+36 🔒)
- `aitbc messaging dm inbox` --cursor
- `aitbc messaging dm inbox` --rpc-url
- `aitbc messaging dm keygen` --fee
- `aitbc messaging dm keygen` --confirm
- `aitbc messaging dm keygen` --rotate
- `aitbc messaging dm keygen` --rpc-url
- `aitbc messaging dm read` --rpc-url
- `aitbc messaging dm send` --fee
- `aitbc messaging dm send` --confirm
- `aitbc messaging dm send` --rpc-url
- `aitbc messaging hide` --topic
- `aitbc messaging hide` --rpc-url
- `aitbc messaging hide` --wait-timeout
- `aitbc messaging hide` --wait`, `--no-wait
- `aitbc messaging hide` --confirm
- `aitbc messaging hide` --fee
- `aitbc messaging list` --topic
- `aitbc messaging list` --author
- `aitbc messaging list` --query
- `aitbc messaging list` --limit
- `aitbc messaging list` --offset
- `aitbc messaging list` --cursor
- `aitbc messaging list` --include-hidden
- `aitbc messaging list` --rpc-url
- `aitbc messaging lock` --target
- `aitbc messaging lock` --rpc-url
- `aitbc messaging lock` --wait-timeout
- `aitbc messaging lock` --wait`, `--no-wait
- `aitbc messaging lock` --confirm
- `aitbc messaging lock` --fee
- `aitbc messaging mod-grant` --rpc-url
- `aitbc messaging mod-grant` --wait-timeout
- `aitbc messaging mod-grant` --wait`, `--no-wait
- `aitbc messaging mod-grant` --confirm
- `aitbc messaging mod-grant` --fee
- `aitbc messaging mod-revoke` --rpc-url
- `aitbc messaging mod-revoke` --wait-timeout
- `aitbc messaging mod-revoke` --wait`, `--no-wait
- `aitbc messaging mod-revoke` --confirm
- `aitbc messaging mod-revoke` --fee
- `aitbc messaging moderators` --rpc-url
- `aitbc messaging pin` --topic
- `aitbc messaging pin` --rpc-url
- `aitbc messaging pin` --wait-timeout
- `aitbc messaging pin` --wait`, `--no-wait
- `aitbc messaging pin` --confirm
- `aitbc messaging pin` --fee
- `aitbc messaging reputation` --rpc-url
- `aitbc messaging send` --reply-to
- `aitbc messaging send` --fee
- `aitbc messaging send` --confirm
- `aitbc messaging send` --wait`, `--no-wait
- `aitbc messaging send` --wait-timeout
- `aitbc messaging send` --rpc-url
- `aitbc messaging show` --rpc-url
- `aitbc messaging state` --rpc-url
- `aitbc messaging stats` --rpc-url
- `aitbc messaging subscribe` --from-cursor
- `aitbc messaging subscribe` --follow
- `aitbc messaging subscribe` --interval
- `aitbc messaging subscribe` --max-polls
- `aitbc messaging subscribe` --rpc-url
- `aitbc messaging topics` --offset
- `aitbc messaging topics` --rpc-url
- `aitbc messaging unhide` --topic
- `aitbc messaging unhide` --rpc-url
- `aitbc messaging unhide` --wait-timeout
- `aitbc messaging unhide` --wait`, `--no-wait
- `aitbc messaging unhide` --confirm
- `aitbc messaging unhide` --fee
- `aitbc messaging unlock` --target
- `aitbc messaging unlock` --rpc-url
- `aitbc messaging unlock` --wait-timeout
- `aitbc messaging unlock` --wait`, `--no-wait
- `aitbc messaging unlock` --confirm
- `aitbc messaging unlock` --fee
- `aitbc messaging unpin` --topic
- `aitbc messaging unpin` --rpc-url
- `aitbc messaging unpin` --wait-timeout
- `aitbc messaging unpin` --wait`, `--no-wait
- `aitbc messaging unpin` --confirm
- `aitbc messaging unpin` --fee
- `aitbc messaging vote` --topic
- `aitbc messaging vote` --rpc-url
- `aitbc messaging vote` --wait-timeout
- `aitbc messaging vote` --wait`, `--no-wait
- `aitbc messaging vote` --confirm
- `aitbc messaging vote` --fee

## `mining` — 6 unexercised (+0 🔒)
- `aitbc mining list` --wallet
- `aitbc mining list` --rpc-url
- `aitbc mining status` --wallet
- `aitbc mining status` --rpc-url
- `aitbc mining stop` --wallet
- `aitbc mining stop` --rpc-url

## `monitor` — 5 unexercised (+0 🔒)
- `aitbc monitor campaigns` --status
- `aitbc monitor sweepers` --config
- `aitbc monitor webhooks` --name
- `aitbc monitor webhooks` --url
- `aitbc monitor webhooks` --events

## `network` — 19 unexercised (+0 🔒)
- `aitbc network force-sync` --rpc-url
- `aitbc network force-sync` --admin-address
- `aitbc network gossip` --rpc-url
- `aitbc network heartbeat` --node-id
- `aitbc network heartbeat` --duration
- `aitbc network heartbeat` --rpc-url
- `aitbc network lease-status` --node-id
- `aitbc network lease-status` --rpc-url
- `aitbc network peers` --rpc-url
- `aitbc network set-sync-source` --env-file
- `aitbc network set-sync-source` --restart`, `--no-restart
- `aitbc network status` --rpc-url
- `aitbc network subscribe` --node-id
- `aitbc network subscribe` --transport
- `aitbc network subscribe` --chain-id
- `aitbc network subscribe` --rpc-url
- `aitbc network subscribers` --chain-id
- `aitbc network subscribers` --rpc-url
- `aitbc network test` --rpc-url

## `node` — 13 unexercised (+0 🔒)
- `aitbc node add` --timeout
- `aitbc node add` --max-connections
- `aitbc node add` --retry-count
- `aitbc node hub list-hubs` --redis-url
- `aitbc node hub register` --redis-url
- `aitbc node hub register` --hub-discovery-url
- `aitbc node hub unregister` --redis-url
- `aitbc node hub unregister` --hub-discovery-url
- `aitbc node island health` --node-url
- `aitbc node island island-info` --node-url
- `aitbc node island join` --rpc-url
- `aitbc node island list` --node-url
- `aitbc node island list-islands` --node-url

## `operations` — 11 unexercised (+9 🔒)
- `aitbc operations agent message` --rpc-url
- `aitbc operations ai status` --format
- `aitbc operations governance delegate` --format
- `aitbc operations governance execute` --format
- `aitbc operations governance get-proposal` --format
- `aitbc operations governance proposal` --params
- `aitbc operations governance proposal` --format
- `aitbc operations governance stake` --format
- `aitbc operations governance vote` --reason
- `aitbc operations governance vote` --format
- `aitbc operations governance voting-power` --format

## `platform` — 1 unexercised (+0 🔒)
- `aitbc platform init-platform` --template

## `plugin` — 3 unexercised (+0 🔒)
- `aitbc plugin create` --type
- `aitbc plugin list` --plugins-dir
- `aitbc plugin load` --plugins-dir

## `pool-hub` — 6 unexercised (+0 🔒)
- `aitbc pool-hub sla` --miner
- `aitbc pool-hub sla` --hours
- `aitbc pool-hub sla` --violations
- `aitbc pool-hub sla` --resolved
- `aitbc pool-hub sla` --pool-id
- `aitbc pool-hub sla` --pool-hub-url

## `prometheus` — 31 unexercised (+0 🔒)
- `aitbc prometheus alert-history` --path
- `aitbc prometheus alert-history` --since
- `aitbc prometheus alert-history` --alertname
- `aitbc prometheus alert-history` --state
- `aitbc prometheus alert-history` --node
- `aitbc prometheus alert-history` --last
- `aitbc prometheus alerts` --prometheus-url
- `aitbc prometheus alerts` --watch
- `aitbc prometheus alerts` --interval
- `aitbc prometheus alerts` --emit`, `--no-emit
- `aitbc prometheus alerts` --alert-log
- `aitbc prometheus alerts` --notify-url
- `aitbc prometheus alerts` --notify-format
- `aitbc prometheus alerts` --notify-topic
- `aitbc prometheus alerts` --notify-click
- `aitbc prometheus alerts` --notify-min-severity
- `aitbc prometheus alerts` --silence-file
- `aitbc prometheus alerts` --remind-interval
- `aitbc prometheus alerts` --metrics-file
- `aitbc prometheus check` --config
- `aitbc prometheus check` --rules
- `aitbc prometheus metric` --url
- `aitbc prometheus metric` --label
- `aitbc prometheus metric` --allow-remote
- `aitbc prometheus metric` --timeout
- `aitbc prometheus query` --prometheus-url
- `aitbc prometheus query` --time
- `aitbc prometheus query` --timeout
- `aitbc prometheus rules` --prometheus-url
- `aitbc prometheus series` --prometheus-url
- `aitbc prometheus targets` --prometheus-url

## `reputation` — 2 unexercised (+0 🔒)
- `aitbc reputation leaderboard` --region
- `aitbc reputation profile` --format

## `resource` — 13 unexercised (+0 🔒)
- `aitbc resource allocate` --gpu-count
- `aitbc resource allocate` --gpu-memory-gb
- `aitbc resource allocate` --storage-gb
- `aitbc resource allocate` --network-bandwidth
- `aitbc resource allocate` --optimization-target
- `aitbc resource allocate` --priority
- `aitbc resource optimize` --optimization-type
- `aitbc resource optimize` --current-accuracy
- `aitbc resource optimize` --current-latency
- `aitbc resource optimize` --current-throughput
- `aitbc resource status` --agent-id
- `aitbc resource status` --status
- `aitbc resource status` --limit

## `service` — 3 unexercised (+0 🔒)
- `aitbc service harden` --all
- `aitbc service harden` --read-write-paths
- `aitbc service harden` --no-restart

## `simulate` — 2 unexercised (+0 🔒)
- `aitbc simulate price` --delay
- `aitbc simulate run` --async-run

## `stake` — 2 unexercised (+0 🔒)
- `aitbc stake` --wallet-path
- `aitbc stake` --rpc-url

## `sync` — 8 unexercised (+0 🔒)
- `aitbc sync bulk` --import-url
- `aitbc sync bulk` --batch-size
- `aitbc sync bulk` --poll-interval
- `aitbc sync status` --node-url
- `aitbc sync status` --chain-id
- `aitbc sync status` --hub-url
- `aitbc sync status` --gap-threshold
- `aitbc sync status` --alert

## `system` — 14 unexercised (+1 🔒)
- `aitbc system check` --output
- `aitbc system check` --format
- `aitbc system env-names` --names
- `aitbc system env-names` --process
- `aitbc system env-names` --value
- `aitbc system env-set` --env-file
- `aitbc system env-set` --no-restart
- `aitbc system file-info` --field
- `aitbc system logs` --since
- `aitbc system logs` --grep
- `aitbc system logs` --priority`, `-p
- `aitbc system logs` --severity-pattern
- `aitbc system show` --properties
- `aitbc system status` --service

## `tee` — 9 unexercised (+0 🔒)
- `aitbc tee attest` --measurement
- `aitbc tee attest` --key-file
- `aitbc tee launch` --image
- `aitbc tee register` --agent-id
- `aitbc tee verify` --quote
- `aitbc tee verify` --attestation-id
- `aitbc tee verify` --measurement
- `aitbc tee verify` --zk-proof
- `aitbc tee verify` --mode

## `trade` — 40 unexercised (+0 🔒)
- `aitbc trade chains` --format
- `aitbc trade create` --format
- `aitbc trade discover` --region
- `aitbc trade discover` --gpu-model
- `aitbc trade discover` --format
- `aitbc trade get` --format
- `aitbc trade health` --format
- `aitbc trade history` --dest-chain
- `aitbc trade history` --format
- `aitbc trade list` --dest-chain
- `aitbc trade list` --limit
- `aitbc trade list` --format
- `aitbc trade lock-escrow` --api-key
- `aitbc trade lock-escrow` --timeout
- `aitbc trade lock-escrow` --format
- `aitbc trade match` --format
- `aitbc trade match-all` --format
- `aitbc trade refund` --node-url
- `aitbc trade refund` --api-key
- `aitbc trade refund` --format
- `aitbc trade register-chain` --format
- `aitbc trade search` --service-type
- `aitbc trade search` --min-price
- `aitbc trade search` --max-price
- `aitbc trade search` --format
- `aitbc trade settle` --node-url
- `aitbc trade settle` --api-key
- `aitbc trade settle` --format
- `aitbc trade settlement-status` --node-url
- `aitbc trade settlement-status` --api-key
- `aitbc trade settlement-status` --format
- `aitbc trade status` --format
- `aitbc trade subscription-status` --format
- `aitbc trade sync` --format
- `aitbc trade sync-status` --format
- `aitbc trade watch` --min-price
- `aitbc trade watch` --max-price
- `aitbc trade watch` --region
- `aitbc trade watch` --gpu-model
- `aitbc trade watch` --format

## `transactions` — 12 unexercised (+4 🔒)
- `aitbc transactions batch` --rpc-url
- `aitbc transactions estimate-fee` --rpc-url
- `aitbc transactions pending` --rpc-url
- `aitbc transactions search` --sender
- `aitbc transactions search` --recipient
- `aitbc transactions search` --use-explorer
- `aitbc transactions search` --rpc-url
- `aitbc transactions send` --rpc-url
- `aitbc transactions send` --type
- `aitbc transactions send` --payload
- `aitbc transactions send` --use-explorer
- `aitbc transactions status` --rpc-url

## `unstake` — 3 unexercised (+0 🔒)
- `aitbc unstake` --wallet-name
- `aitbc unstake` --wallet-path
- `aitbc unstake` --rpc-url

## `update` — 5 unexercised (+0 🔒)
- `aitbc update` --remote
- `aitbc update` --branch
- `aitbc update` --no-deploy
- `aitbc update` --output
- `aitbc update` --format

## `wallet` — 28 unexercised (+62 🔒)
- `aitbc wallet address` --name
- `aitbc wallet bridge float` --hub-url
- `aitbc wallet bridge sell lock` --hub-url
- `aitbc wallet bridge sell quote` --wallet-name
- `aitbc wallet bridge settlements` --state
- `aitbc wallet bridge settlements` --kind
- `aitbc wallet bridge settlements` --hub-url
- `aitbc wallet bridge status` --ait-tx-hash
- `aitbc wallet bridge status` --today
- `aitbc wallet bridge status` --24h
- `aitbc wallet bridge status` --hub-url
- `aitbc wallet eth-balance` --address
- `aitbc wallet eth-balance` --eth-rpc-url
- `aitbc wallet eth-send` --eth-rpc-url
- `aitbc wallet eth-send` --max-gas-gwei
- `aitbc wallet eth-send` --allow-contract
- `aitbc wallet eth-send` --confirm
- `aitbc wallet eth-send` --wait
- `aitbc wallet inspect` --field
- `aitbc wallet liquidity-claim` --fee
- `aitbc wallet liquidity-stake` --lock-days
- `aitbc wallet liquidity-stake` --fee
- `aitbc wallet liquidity-unstake` --fee
- `aitbc wallet send` --fee
- `aitbc wallet send` --wait
- `aitbc wallet send` --rpc-url
- `aitbc wallet staking-info` --address
- `aitbc wallet transactions` --limit

## `zk` — 8 unexercised (+0 🔒)
- `aitbc zk circuits` --coordinator-url
- `aitbc zk circuits` --format
- `aitbc zk health` --coordinator-url
- `aitbc zk health` --format
- `aitbc zk verify` --proof
- `aitbc zk verify` --public-signals
- `aitbc zk verify` --circuit
- `aitbc zk verify` --format
