# AITBC CLI

Command-line interface for the AITBC network.

## Installation

```bash
pip install ./cli
aitbc --help
```

## Group catalog

| Group | Description | Key subcommands |
|-------|-------------|-----------------|
| `account` | Account information and management | `get`, `list` |
| `auth` | Authentication and session management | `login`, `logout`, `status` |
| `agent` | Agent SDK management commands | `cancel`, `capabilities`, `config-export`, `config-get`, `config-import`, `config-set`, `config-validate`, `create`, `discover`, `get-identity`, `inbox`, `job`, `jobs`, `list`, `register`, `register-identity`, `status`, `submit`, `subscribe`, `verify-identity`, `workflow` |
| `agent-comm` | Cross-chain agent communication commands | `collaborate`, `discover`, `list`, `monitor`, `network`, `receive`, `register`, `reputation`, `send`, `status` |
| `agent-msg` | Agent messaging commands (ping, send, receive, peers, request-coins). | `peers`, `ping`, `receive`, `request-coins`, `send` |
| `agent-wallet` | Agent-owned wallet, staking, and rebalancing commands. | `balance`, `rebalance`, `stake` |
| `ai` | AI job submission and inspection | `accept`, `cancel`, `distribution-stats`, `jobs`, `pay`, `refund`, `refund-sweep`, `results`, `service`, `stats`, `status`, `submit` |
| `analytics` | Chain analytics and monitoring commands | `alerts`, `dashboard`, `monitor`, `optimize`, `predict`, `summary` |
| `blockchain` | Multi-chain management commands | `add`, `backup`, `consensus`, `create`, `delete`, `info`, `instances`, `list`, `migrate`, `monitor`, `remove`, `restore`, `start`, `status`, `stop`, `sync-status` |
| `bond` | Provider performance bond lifecycle commands. | `appeal`, `create`, `lock`, `release`, `slash`, `status`, `top-up` |
| `bootstrap` | Bootstrap local development and configuration files. | `bootstrap-env` |
| `brand` | Show and manage white-label brand settings. | `list`, `show` |
| `bridge` | Cross-chain bridge management | `attest`, `balance`, `confirm`, `health`, `ingest-header`, `lock`, `oracle-status`, `pending`, `proof`, `register-validator`, `security-status`, `sign-proof`, `start`, `status`, `stop`, `store-header`, `unlock` |
| `cluster` | Cluster management and operations | `balance`, `status`, `sync` |
| `coin-requests` | Manage coin transfer requests. | `approve`, `execute`, `list`, `reconcile`, `reject`, `reopen`, `show` |
| `compliance` | Compliance policy, classification, and audit commands. | `check`, `classify`, `export-audit` |
| `confidential` | Confidential TEE-signed transaction commands. | `balance`, `send` |
| `config` | Manage CLI configuration | `check`, `check-keys`, `edit`, `environments`, `export`, `get`, `get-secret`, `import-config`, `path`, `profiles`, `reset`, `set`, `set-secret`, `show`, `unset`, `validate` |
| `contract` | Smart contract operations | `call`, `deploy` |
| `crosschain` | Cross-chain trading operations | `bridge`, `bridge-status`, `pools`, `rates`, `stats`, `status`, `swap`, `swaps` |
| `dashboard` | Operational dashboards for customers and shops. | `customer`, `shop` |
| `deploy` | Deploy and manage white-label platform configurations. | `deploy-brand` |
| `developer` | Developer registry commands. | `list`, `register` |
| `economics` | Economic intelligence, modeling, and OpenClaw DAO governance. | `distributed`, `market`, `model`, `propose`, `status`, `vote` |
| `edge` | Edge API commands for island, GPU, database, serve, and metrics operations | `balance`, `database`, `gpu`, `island`, `metrics`, `serve`, `status`, `transfer` |
| `exchange` | Exchange integration and trading management commands | `add-liquidity`, `create-pair`, `list`, `monitor`, `register`, `start-trading`, `status` |
| `exchange-island` | Exchange commands for trading AIT against ETH on the island | `buy`, `cancel`, `orderbook`, `orders`, `rates`, `sell` |
| `explorer` | Blockchain Explorer commands - access blockchain data via Explorer API | `activity-timeline`, `block`, `block-by-hash`, `blocks-by-address`, `chain-head`, `chains`, `latest-blocks`, `network-stats`, `non-empty-blocks`, `provider-reputation`, `search-transactions`, `top-addresses`, `transaction`, `transaction-by-hash` |
| `genesis` | Genesis block and wallet generation commands | `info`, `init`, `sync-from-hub`, `verify` |
| `governance` | Governance operations — on-chain proposals, voting, and execution | `aggregate-votes`, `close`, `execute`, `execute-cross-chain`, `get`, `list`, `propagate`, `propose`, `status`, `vote` |
| `gpu` | Local GPU service commands for hardware management | `discover`, `list-gpus`, `register`, `unregister`, `update` |
| `gpu-onchain` | GPU resource tracking commands (on-chain) | `allocate`, `allocations`, `list`, `query`, `register` |
| `grant` | DAO grant proposal commands. | `create`, `disburse`, `list`, `vote` |
| `ipfs` | Local content-addressed storage (IPFS-compatible surface). | `download`, `host`, `list`, `pin`, `rentals`, `token`, `unpin`, `upload` |
| `list` | Legacy wallet list alias |  |
| `market` | GPU and software offers published by shop miners | `cancel`, `escrow`, `exchange`, `hermes`, `list`, `match`, `offer`, `process`, `providers`, `rate`, `ratings`, `run`, `status`, `sync-ratings`, `transcribe` |
| `messaging` | Messaging system and forum operations | `list`, `send`, `topic` |
| `mining` | Mining operations commands | `list`, `start`, `status`, `stop` |
| `monitor` | Monitoring, metrics, and alerting commands | `alerts`, `campaign-stats`, `campaigns`, `dashboard`, `history`, `metrics`, `webhooks` |
| `network` | Peer connectivity and network operations | `force-sync`, `heartbeat`, `lease-status`, `peers`, `status`, `subscribe`, `subscribers`, `test` |
| `node` | Node management commands | `add`, `bridge`, `chain`, `chains`, `hub`, `info`, `island`, `list`, `monitor`, `node-info`, `remove`, `test` |
| `operations` | **Legacy** on-chain operations commands. Hidden from `aitbc --help`; prefer the top-level `aitbc ai`, `aitbc agent`, `aitbc governance`, and `aitbc market` groups. | `agent`, `ai`, `governance` |
| `oracle` | Local data oracle for agent data availability announcements. | `listings`, `store` |
| `performance` | Performance monitoring and optimization | `benchmark`, `optimize`, `tune` |
| `platform` | Scaffold white-label platform configurations. | `init-platform` |
| `plugin` | Scaffold and manage AITBC plugins. | `create`, `list`, `load` |
| `pool-hub` | Pool hub management for SLA monitoring and billing | `sla`, `status` |
| `prometheus` | Query Prometheus and inspect scrape targets, rules, and alerts. | `alerts`, `check`, `query`, `rules`, `series`, `targets` |
| `reinvest` | Autonomous reinvestment and capacity planning commands. | `policy`, `simulate` |
| `reputation` | Reputation management commands | `create-profile`, `feedback`, `leaderboard`, `metrics`, `profile`, `trust-score` |
| `resource` | Manage agent resource allocations via coordinator-api | `allocate`, `optimize` |
| `restart` | Restart all AITBC services for the current (or selected) role |  |
| `script` | Script execution and management | `list`, `run` |
| `security` | Security audit and monitoring | `audit`, `patch`, `scan` |
| `simulate` | Simulate blockchain scenarios and test environments | `ai-jobs`, `blockchain`, `network`, `price`, `result`, `run`, `status`, `wallets` |
| `start` | Start all AITBC services for the current (or selected) role |  |
| `stop` | Stop all AITBC services for the current (or selected) role |  |
| `sync` | Blockchain synchronization utilities | `bulk`, `status` |
| `system` | System management commands | `architect`, `audit`, `check`, `config`, `restart`, `status` |
| `trade` | Inter-chain trading operations | `chains`, `create`, `discover`, `get`, `health`, `history`, `list`, `lock-escrow`, `match`, `match-all`, `refund`, `register-chain`, `search`, `settle`, `settlement-status`, `status`, `subscription-status`, `sync`, `sync-status`, `watch` |
| `transactions` | Transaction management commands | `batch`, `estimate-fee`, `pending`, `search`, `send`, `status` |
| `update` | Pull the latest code and run scripts/deployment/update.sh. |  |
| `version` | Show version information |  |
| `wallet` | Manage your wallets and transactions | `address`, `backup`, `balance`, `bridge`, `create`, `delete`, `earn`, `export`, `fund`, `import-wallet`, `info`, `liquidity-claim`, `liquidity-stake`, `liquidity-unstake`, `list`, `multisig-create`, `multisig-propose`, `multisig-sign`, `request-payment`, `restore`, `rewards`, `send`, `spend`, `stake`, `staking-info`, `stats`, `switch`, `transactions`, `unstake` |
| `workflow` | Workflow management commands | `list`, `run`, `status`, `stop` |
| `zk` | Zero-knowledge proof commands. | `circuits`, `health`, `verify` |

## Market

`aitbc market` is the canonical group for GPU and software offers published by shop miners (Ollama, Whisper, FFmpeg, Hermes Agent). These are local/shop offers matched by the coordinator and executed on a provider's GPU.

Use `aitbc market` for AI jobs and local GPU offers.
