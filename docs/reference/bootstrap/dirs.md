# AITBC Monorepo Directory Layout (Windsurf Workspace)

> One workspace for **all** AITBC elements (client · coordinator · miner · blockchain · pool‑hub · marketplace · wallet · docs · ops). No Docker required.

```
aitbc/
├─ .editorconfig
├─ .gitignore
├─ README.md                         # Top‑level overview, quickstart, workspace tasks
├─ LICENSE
├─ windsurf/                         # Windsurf prompts, tasks, run configurations
│  ├─ prompts/                       # High‑level task prompts for WS agents
│  ├─ tasks/                         # Saved task flows / playbooks
│  └─ settings.json                  # Editor/workbench preferences for this repo
├─ scripts/                          # CLI scripts (bash/python); dev + ops helpers
│  ├─ env/                           # venv helpers (create, activate, pin)
│  ├─ dev/                           # codegen, lint, format, typecheck wrappers
│  ├─ ops/                           # backup, rotate logs, journalctl, users
│  └─ ci/                            # sanity checks usable by CI (no runners assumed)
├─ configs/                          # Centralized *.conf used by services
│  ├─ nginx/                         # (optional) reverse proxy snippets (host‑level)
│  ├─ systemd/                       # unit files for host services (no docker)
│  ├─ security/                      # fail2ban, firewall/ipset lists, tls policy
│  └─ app/                           # app‑level INI/YAML/TOML configs shared across apps
├─ docs/                             # Markdown docs (specs, ADRs, guides)
│  ├─ 00-index.md
│  ├─ adr/                           # Architecture Decision Records
│  ├─ specs/                         # Protocol, API, tokenomics, flows
│  ├─ runbooks/                      # Ops runbooks (rotate keys, restore, etc.)
│  └─ diagrams/                      # draw.io/mermaid sources + exported PNG/SVG
├─ packages/                         # Shared libraries (language‑specific)
│  ├─ py/                            # Python packages (FastAPI, utils, protocol)
│  │  ├─ aitbc-core/                 # Protocol models, validation, common types
│  │  ├─ aitbc-crypto/               # Key mgmt, signing, wallet primitives
│  │  ├─ aitbc-p2p/                  # Node discovery, gossip, transport
│  │  ├─ aitbc-scheduler/            # Task slicing/merging, scoring, QoS
│  │  └─ aitbc-sdk/                  # Client SDK for Python integrations
│  └─ js/                            # Browser/Node shared libs
│     ├─ aitbc-sdk/                  # Client SDK (fetch/ws), typings
│     └─ ui-widgets/                 # Reusable UI bits for web apps
├─ apps/                             # First‑class runnable services & UIs
│  ├─ client-web/                    # Browser UI for users (requests, wallet, status)
│  │  ├─ public/                     # static assets
│  │  ├─ src/
│  │  │  ├─ pages/
│  │  │  ├─ components/
│  │  │  ├─ lib/                     # uses packages/js/aitbc-sdk
│  │  │  └─ styles/
│  │  └─ README.md
│  ├─ coordinator-api/               # Central API orchestrating jobs ↔ miners
│  │  ├─ src/
│  │  │  ├─ main.py                  # FastAPI entrypoint
│  │  │  ├─ routes/
│  │  │  ├─ services/                # matchmaking, accounting, rate‑limits
│  │  │  ├─ domain/                  # job models, receipts, accounting entities
│  │  │  └─ storage/                 # adapters (postgres, files, kv)
│  │  ├─ migrations/                 # SQL snippets (no migration framework forced)
│  │  └─ README.md
│  ├─ miner-node/                    # Worker node daemon for GPU/CPU tasks
│  │  ├─ src/
│  │  │  ├─ agent/                   # job runner, sandbox mgmt, health probes
│  │  │  ├─ gpu/                     # CUDA/OpenCL bindings (optional)
│  │  │  ├─ plugins/                 # task kinds (LLM, ASR, vision, etc.)
│  │  │  └─ telemetry/               # metrics, logs, heartbeat
│  │  └─ README.md
│  ├─ wallet-daemon/                 # Local wallet service (keys, signing, RPC)
│  │  ├─ src/
│  │  └─ README.md
│  ├─ blockchain-node/               # Minimal chain (asset‑backed by compute)
│  │  ├─ src/
│  │  │  ├─ consensus/
│  │  │  ├─ mempool/
│  │  │  ├─ ledger/                  # state, balances, receipts linkage
│  │  │  └─ rpc/
│  │  └─ README.md
│  ├─ pool-hub/                      # Client↔miners pool + matchmaking gateway
│  │  ├─ src/
│  │  └─ README.md
│  ├─ marketplace-web/               # Web app for offers, bids, stats
│  │  ├─ public/
│  │  ├─ src/
│  │  └─ README.md
│  └─ explorer-web/                  # Chain explorer (blocks, tx, receipts)
│     ├─ public/
│     ├─ src/
│     └─ README.md
├─ protocols/                        # Canonical protocol definitions
│  ├─ api/                            # OpenAPI/JSON‑Schema for REST/WebSocket
│  ├─ receipts/                       # Job receipt schema, signing rules
│  ├─ payouts/                        # Mint/burn, staking, fees logic (spec)
│  └─ README.md
├─ data/                             # Local dev datasets (small, sample only)
│  ├─ fixtures/                       # seed users, nodes, jobs
│  └─ samples/
├─ tests/                            # Cross‑project test harness
│  ├─ e2e/                            # end‑to‑end flows (client→coord→miner→wallet)
│  ├─ load/                           # coordinator & miner stress scripts
│  └─ security/                       # key rotation, signature verif, replay tests
├─ tools/                            # Small CLIs, generators, mermaid->svg, etc.
│  └─ mkdiagram
└─ examples/                         # Minimal runnable examples for integrators
   ├─ quickstart-client-python/
   ├─ quickstart-client-js/
   └─ receipts-sign-verify/
```

## Conventions

- **Languages**: FastAPI/Python for backends; plain JS/TS for web; no Docker.
- **No global venvs**: each `apps/*` and `packages/py/*` can have its own `.venv/` (created by `scripts/env/*`).
- **Systemd over Docker**: unit files live under `configs/systemd/`, with service‑specific overrides documented in `docs/runbooks/`.
- **Static assets** belong to each web app under `public/`. Shared UI in `packages/js/ui-widgets`.
- **SQL**: keep raw SQL snippets in `apps/*/migrations/` (aligned with your “no migration framework” preference). Use `psqln` alias.
- **Security**: central policy under `configs/security/` (fail2ban, ipset lists, TLS ciphers). Keys never committed.

## Minimal READMEs to create next

Create a short `README.md` in each `apps/*` and `packages/*` with:

1. Purpose & scope
2. How to run (dev)
3. Dependencies
4. Configs consumed (from `/configs/app`)
5. Systemd unit name & port (if applicable)

## Suggested first tasks (Way of least resistance)

1. **Bootstrap coordinator-api**: scaffold FastAPI `main.py`, `/health`, `/jobs`, `/miners` routes.
2. **SDKs**: implement `packages/py/aitbc-sdk` & `packages/js/aitbc-sdk` with basic auth + job submit.
3. **miner-node prototype**: heartbeat to coordinator and no‑GPU "echo" job plugin.
4. **client-web**: basic UI to submit a test job and watch status stream.
5. **receipts spec**: draft `protocols/receipts` and a sign/verify example in `examples/`.

