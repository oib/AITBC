# AITBC closed design cycle — current state, gaps, wish list

**Date:** 2026-08-22
**Scope:** live two-node network (`hub.aitbc` hub/customer + `aitbc3` shop/miner) on gitea `main`
**CLI:** `aitbc` 0.10.18 (`aitbc_cli.core.main:main`)
**Unit system:** 1 AIT = 3600 compute-seconds

This is the product picture used to keep `docs/scenarios/` honest. Scenarios are operator plays of **what the software actually does today**, not a catalog of planned releases. The wish list is what is missing to close the economic loop.

---

## 1. What AITBC is supposed to be

AITBC is a **decentralized marketplace for AI compute**. Tokens buy GPU time; GPU time produces verifiable results; results settle on-chain; reputation and governance feed the next job.

Three roles, two config axes (`BLOCKCHAIN_MODE` × `MARKET_ROLE`):

| Role | Typical node | Job |
|------|--------------|-----|
| **Hub** | `hub.aitbc` | Produce blocks, run coordinator / exchange / discovery / explorer |
| **Shop** | `aitbc3` | Advertise GPUs, run miner + edge, execute jobs, publish marketplace offers |
| **Client** | hub CLI or a follower | Hold AIT, submit jobs, trade, inspect results |

A single machine can combine roles. Services are selected by `setup.sh` from those two axes (see `docs/getting-started/setup-service-selection.md`).

The intended **closed cycle**:

```
tokens → discover compute → submit paid job → escrow
     → shop executes on GPU → result + receipt
     → ESCROW_RELEASE on-chain → reputation
     → provider restakes / relists → next job
```

That is the cycle the software design should close. Everything else (bridge, exchange, islands, TEE, ZK, DAO grants) either **feeds** that loop or is **parked until the loop is boring**.

---

## 2. What works today (live, 2026-08-20/21)

Proven on the two live nodes (see `LIVE_VALIDATION_SUMMARY.md` and scenario 34):

1. **Wallets.** `aitbc wallet create/list/balance/send/stake`. File wallets and daemon wallets merge in `wallet list`.
2. **Chain.** Hub produces blocks (PoA). Shop follows over P2P (`aitbc-blockchain-p2p`). After a fork at height 6815, shop was reset and heads match.
3. **Unpaid jobs.** Hub `POST /v1/jobs` (or `aitbc ai submit`) → shop miner completes on Ollama (`llama3.2:3b`).
4. **Paid jobs + escrow.** `aitbc --api-key $JWT ai submit --payment 1.0 --wallet genesis --provider-address …` → `payment_status: escrowed` → miner runs → `released` → `ESCROW_RELEASE` on-chain (0.975 AIT after fee).
5. **GPU marketplace offers.** `aitbc market offer ollama llama3.2:3b 0.001 --unit per_1k_tokens --gpu-device 0` writes a `GPU_MARKETPLACE` tx and a hub listing. `aitbc market list --service-type ollama` sees it.
6. **Local GPU inventory.** `aitbc gpu list-gpus` / `aitbc gpu discover` against `aitbc-gpu` (8101).
7. **Explorer / monitoring.** `aitbc explorer chain-head`, `aitbc explorer network-stats`.
8. **Pool hub.** `aitbc pool-hub status` / `sla` work from hub and shop; the shop miner registers and heartbeats with the **hub** pool hub, so `miners_online` is now `1` (or more).
9. **Bridge health + input validation.** `aitbc bridge health`; malformed `lock`/`confirm` return HTTP 422.
10. **Most beginner CLI groups** (`wallet`, `transactions`, `ai`, `mining`, `reputation`, `agent`, `agent-comm`, `ipfs`, `security`, `analytics`, `governance status`, `exchange-island` orderbook/rates) return live or honest-simulated data.

This is a **working inner loop**: a funded customer can buy a GPU inference job from a shop and the shop gets paid on-chain.

---

## 3. The cycle, step by step — implemented vs gap

| Step | Intended | Today | Gap |
|------|----------|-------|-----|
| 0. Acquire AIT | Fiat/BTC on-ramp, or faucet | Genesis wallet / manual `wallet send`; `aitbc wallet fund` now calls `/rpc/faucet` and accepts bech32 or 0x addresses. Exchange `buy` still keystore-gated. | Customer onboarding |
| 1. Discover compute | Marketplace UI + CLI, reputation-ranked | `aitbc market list`, `aitbc gpu list-gpus`. Web UI defaults to mock. Reputation not used in matching. | UX + matching quality |
| 2. Submit paid job | One CLI command, JWT or wallet-native auth | `aitbc auth login` stores a coordinator JWT; `aitbc ai submit` falls back to it. `--api-key` still accepted. | Auth UX |
| 3. Escrow | On by default, payment escrow live | Live paid jobs **do** escrow and release. `escrow_enabled` defaults to `True` and `STATUS.md` no longer lists `False` | Done |
| 4. Match to miner | Stake + reputation + capacity | Shop miner registers and heartbeats to the **hub** pool hub; `aitbc pool-hub status` shows `miners_online > 0` from both nodes | Done |
| 5. Execute | Ollama / Whisper / FFmpeg on edge | Ollama inference live. Whisper/FFmpeg services exist, not in the default shop loop | Optional services |
| 6. Verify result | ZK / TEE attestation | Result is trusted coordinator receipt. ZK circuits exist, not wired. TEE CLI exists, not wired | Verifiable compute |
| 7. Settle | Signed `ESCROW_RELEASE` | Live, genesis-signed. Fee ~2.5% | Operator-key coupling (genesis signs release) |
| 8. Reputation | Auto-update + ratings in matching | `aitbc reputation *` works against coordinator. Not fed back into dispatch | Closed-loop reputation |
| 9. Reinvest | Auto-stake / capacity | `aitbc wallet stake`, `aitbc reinvest` commands exist; not automatic | Autonomy (v0.12+ roadmap) |
| 10. Govern | Token-weighted votes change params | `aitbc governance status` live. Propose/vote via `aitbc operations governance` against RPC; execution not proven end-to-end on hub | Live governance loop |
| Sync | Followers never fork | Shop forked at 6815; `import_block` now treats unknown parent as divergence; P2P is up; `aitbc sync status --hub-url` alerts on gap/hash mismatch | Operational health |
| Cross-chain | BTC/ETH ↔ AIT, HTLC | Bridge RPC + `aitbc bridge *`. Merkle proof and multi-sig default **off**. Exchange is `simple_exchange` on 8106 | Production bridge defaults |

---

## 4. Current software map (maturity)

Legend: **live** = running on hub and/or shop · **partial** = code complete, flags/defaults off or not in the job loop · **sim** = CLI falls back to deterministic simulation · **parked** = roadmap / archived

### Live inner loop

| Piece | Port / unit | CLI | Notes |
|-------|-------------|-----|-------|
| Blockchain node + RPC | 8202 | `aitbc chain`, `aitbc explorer`, `aitbc transactions` | Hub binds 8202 to localhost; public path is nginx |
| P2P / sync | 8200 | `aitbc network`, `aitbc sync` | Shop P2P now active |
| Coordinator API | 8203 | `aitbc ai` | JWT Bearer required for jobs |
| Wallet daemon | 8108 | `aitbc wallet`, `aitbc account` | |
| Miner | systemd `aitbc-miner` | `aitbc mining` | Heartbeats to shop coordinator |
| GPU service | 8101 | `aitbc gpu` | |
| Edge | 8111 | `aitbc edge` | |
| Marketplace | 8102 / hub `/v1/marketplace` | `aitbc market`, `aitbc marketplace` | **`market`** = GPU/software bundles (live). **`marketplace`** = chain listings (separate, older) |
| Explorer | 8100 | `aitbc explorer` | |
| Pool hub | 8210 / `/pool-hub/` | `aitbc pool-hub` | |

### Live but beside the inner loop

| Piece | Port | CLI | Notes |
|-------|------|-----|-------|
| Exchange | 8106 | `aitbc exchange-island`, `aitbc exchange` | `simple_exchange` + API key. Paths are `/api/orders`, not `/v1/exchange/*` |
| Governance | 8105 | `aitbc governance`, `aitbc operations governance` | Dual CLI groups |
| Agent coordinator | 8107 | `aitbc agent-comm`, `aitbc agent-msg` | Hub-only |
| Trading | 8109 | `aitbc trade` | Inter-chain offers |
| Event bridge | 8205 | `aitbc bridge start/stop` | Not the lock/confirm RPC |
| IPFS surface | local files | `aitbc ipfs` | Filesystem CID store, not a real IPFS daemon |
| Oracle | local files | `aitbc oracle` | Announces local CIDs |

### Partial / simulated / parked

| Piece | State |
|-------|--------|
| Multi-validator PoA / PBFT | Code present, default false; soak test added (1000 rounds + partition/PBFT). Single-proposer mode still active. |
| Bridge merkle proofs / multi-sig | Implemented, production defaults false |
| ZK circuits (`apps/zk-circuits`) | Ceremony keys exist; not in job verification |
| TEE / confidential | CLI `aitbc tee`, `aitbc confidential` — not in job pipeline |
| Agent SDK IPFS/oracle | Wraps `aitbc ipfs` / `aitbc oracle` |
| Messaging | `aitbc messaging` often simulated on shop |
| Bond / reinvest / economics / grants / plugin / platform / compliance | CLI groups exist; roadmap v0.11–v0.16 |
| Marketplace web | Mock-first (`VITE_MARKETPLACE_DATA_MODE`) |
| `ai-engine`, whisper, ffmpeg | Optional, not auto-enabled |
| PeerTube transcoder | Archived |
| STATUS.md rows v0.11–v1.0 | Planned; many already have CLI shells |

Architecture docs (`docs/architecture/1_system-flow.md`, `active_apps.md`) still mention `aitbc-cli.sh`, Tendermint `26657`, and v0.5.0 dates. Treat `README.md` + this file + `docs/getting-started/setup-service-selection.md` as the current picture.

---

## 5. Scenario vs CLI inventory

There are **36** scenario files under `docs/scenarios/` plus this design note.

**Rule:** every scenario play is driven by `aitbc`. Curl, `journalctl`, and `pytest` are allowed only as **validation** after the CLI step, never as the primary play.

| Band | Role | CLI-first? |
|------|------|------------|
| 01–20 | Beginner feature plays | Yes (11 was SDK-only; now CLI `ipfs`/`oracle` first) |
| 21–27 | Operator / live shop verification | Rewritten onto `aitbc start/system/bridge/ai/gpu/market/mining` |
| 28–33 | Hardening that lives in tests | CLI probe first; `pytest` as named verification |
| 34, 36 | Two-node product path | Yes (`ai`, `market`, `wallet`, `bridge`, `exchange-island`, `pool-hub`) |
| 35 | Background-task logging | `aitbc system` / `aitbc agent-comm` + journal validation |

CLI groups **without** a dedicated scenario (do not invent plays for them until they are in the live loop): `bond`, `bootstrap`, `cluster`, `coin-requests`, `confidential`, `contract`, `deploy`, `developer`, `economics`, `grant`, `performance`, `platform`, `plugin`, `reinvest`, `resource`, `script`, `tee`, `trade`, `workflow`.

Duplicate CLI surfaces to be honest about:

- `aitbc market` vs `aitbc marketplace` vs `aitbc operations marketplace`
- `aitbc governance` vs `aitbc operations governance`
- `aitbc ai` vs `aitbc operations ai`
- `aitbc gpu` (local service) vs `aitbc gpu-onchain` vs `aitbc edge gpu`

Scenarios use the **live** group: `market` for shop GPU offers, `ai` for jobs, `governance` for service status, `operations governance` only where the RPC vote path is required.

---

## 6. Gaps that keep the cycle from closing

### Product / economics

1. No real customer on-ramp (BTC→AIT `buy` still keystore-gated; no faucet play).
2. Reputation is queryable but does not rank miners or offers.
3. No automatic provider reinvestment or performance bonds (CLI shells only).
4. Fee market is fixed; dynamic pricing was deprecated in v0.5.0.
5. ~~Hub pool does not see shop miners (`miners_online: 0`).~~ Fixed — shop miner heartbeats to hub pool hub.
6. Result verification is “coordinator says COMPLETED”, not ZK/TEE.

### Operations / trust

7. Hub RPC/coordinator/exchange bind `127.0.0.1` — customers reach them via nginx or SSH tunnel. Scenario 34 must say so.
8. Shop already forked once; follower divergence handling is new (`0983db5fb`) and needs soak + alerting.
9. `ESCROW_RELEASE` is signed with the **genesis** key — settlement is not yet a provider/coordinator key ceremony.
10. JWT for jobs is not `aitbc login`; operators scrape `/etc/aitbc/aitbc-coordinator-api.env`.
11. Island credential file ownership vs `blockchain-secrets.env` root:600 still fights `aitbc market offer` as root.
12. Wallet key mismatches cannot be recovered from an address (see `AGENTS.md`).

### Docs / CLI honesty

13. Architecture system-flow still shows `aitbc-cli.sh` and Tendermint 26657.
14. ~~`STATUS.md` escrow/bridge defaults disagree with the live paid-job path.~~ Fixed — `escrow_enabled` default is `True` in `config.py` and `STATUS.md`.
15. Dual command groups confuse operators (`market`/`marketplace`, `governance`/`operations governance`).
16. Many CLI groups simulate when the service is hub-only; scenarios must label **live vs simulated**.
17. Intermediate 21–35 were written as bug tickets (A3, B12…) not operator plays.

---

## 7. Wish list (prioritized)

### P0 — close the inner loop until it is boring

| # | Wish | Why |
|---|------|-----|
| P0.1 | `aitbc auth login` so jobs do not require ad-hoc Python JWT | Shipped as CLI wallet-signed login against `/v1/login` (Phase 2) |
| P0.2 | Shop/follower miner registers with the **hub** pool hub; `aitbc pool-hub status` shows `miners_online ≥ 1` | Shipped: `/v1/miners/register` and `/v1/miners/heartbeat` in pool-hub; production miner registers and heartbeats to the hub (Phase 7) |
| P0.3 | Non-genesis settlement key for `ESCROW_RELEASE` | Shipped: `ESCROW_RELEASE_PRIVATE_KEY` / `ESCROW_RELEASE_ADDRESS` env vars; derived key signs the on-chain release tx, falling back to `GENESIS_WALLET_PRIVATE_KEY` (Phase 8) |
| P0.4 | Production defaults that match live: escrow on; document nginx as the public RPC, not rebinding 8202 | Shipped: `escrow_enabled` defaults to `True` in `apps/blockchain-node/src/aitbc_chain/config.py`; `STATUS.md` updated. Scenario 34 documents nginx/SSH-tunnel as the public path and warns against raw `:8202`; escrow release is live (Phases 1, 8) |
| P0.5 | Follower soak: no more silent forks; `aitbc sync status` / `aitbc network status` alert on divergence | Shipped: `aitbc sync status --hub-url` with `--alert` and `--gap-threshold` (Phase 3) |
| P0.6 | One on-ramp play: `aitbc wallet fund` against `/rpc/faucet` with bech32/0x support | Shipped: CLI path to the live faucet (Phase 4) |
| P0.7 | Collapse or clearly alias `market` vs `marketplace` in `--help` and scenarios | Shipped: updated group docstrings, `cli/README.md` disambiguation, help-output tests (Phase 5) |

### P1 — make the loop trustless and operable

| # | Wish | Why |
|---|------|-----|
| P1.1 | Wire reputation into dispatch and `aitbc market list` sort | Closes step 8 |
| P1.2 | Customer and shop dashboards (job history, earnings, GPU util) talking to live APIs | Mock web UI is not a product |
| P1.3 | Enable merkle proofs / multi-sig on bridge **or** document the hub as a trusted custodian | STATUS.md vs production |
| P1.4 | Soak MultiValidatorPoA; drop single-proposer | Soak test added; single-proposer `PoAProposer` still active by default because `multi_validator_consensus_enabled` is `False` |
| P1.5 | `aitbc ai submit --wait` that polls until `released` and prints the escrow tx | Shipped: `--wait` with `--timeout` and `--poll-interval` (Phase 6) |
| P1.6 | Island credential / secrets file ownership that works for `aitbc` as `aitbc` user | Scenario 34 GPU offer workaround |
| P1.7 | Governance e2e: `propose` → `vote` → `execute` changes a live parameter | Group 17 is command-shaped, not cycle-shaped |
| P1.8 | Honest architecture rewrite of `1_system-flow.md` (CLI → coordinator 8203 → miner → Ollama 11434 → escrow) | Stale docs train the next agent wrong |

### P2 — expand the product after the loop is closed

| # | Wish | Why |
|---|------|-----|
| P2.1 | ZK proof required for high-value jobs (circuits already in tree) | Verifiable compute |
| P2.2 | TEE attestation path (`aitbc tee`) for confidential jobs | Roadmap v0.14 |
| P2.3 | Performance bonds + slashing (`aitbc bond`) | Roadmap v0.12 |
| P2.4 | Auto reinvest (`aitbc reinvest`) from released escrow | Provider growth |
| P2.5 | Whisper / FFmpeg in the default shop offer set (`aitbc market offer whisper` / `ffmpeg`) | Services exist |
| P2.6 | Real IPFS daemon behind `aitbc ipfs` (today: `/var/lib/aitbc/ipfs`) | Content addressing that leaves the node |
| P2.7 | Compliance / plugin / white-label — only after P0/P1 | Roadmap v0.15–v0.16; do not pretend they are in the cycle |

---

## 8. How to use this file

- **Scenarios** play the **live** columns in §3 and §4 with `aitbc`.
- **Wish list** items are not scenarios until they ship.
- When a scenario play hits a CLI bug, **fix the CLI** and keep the scenario in sync (that is how `--currency` landed on `aitbc ai submit`).
- Do not add scenarios for parked CLI groups just to raise the count.

---

*Last updated: 2026-08-22 (Phases 1–8 shipped; pool-hub and escrow drift fixed)*
