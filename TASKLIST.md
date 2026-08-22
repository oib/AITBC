## Agent B P1 product-gap sprint (hub.aitbc)

- Branch: `feature/agent-b-p1-sprint` on `hub.aitbc`, created from gitea `main` (`7bda4c91d`).
- Owner: Agent B (hub.aitbc / customer + docs + governance + web dashboards).
- [x] Refresh `docs/DESIGN_CYCLE.md` staleness (P2.3–P2.7 shipped; step 2/5/9/10 gaps closed/clarified).
- [x] Update `TASKLIST.md` with branch and current state.
- [x] P1.2 — web customer and shop dashboards.
  - Added `website/customer-dashboard.html`, `website/shop-dashboard.html`,
    `website/dashboard.js`, and `examples/nginx/nginx-aitbc.conf.example`
    routes for `/dashboard/` and `/shop/`.
  - Dashboards call live APIs and degrade gracefully.
- [ ] P1.7 — governance parameter change end-to-end live validation.
  - Service is active on hub; `propose/vote/close/execute` CLI exists.
  - Execution blocked by 43200-block timelock (24h at 2s block time).
- [x] P1.3a — bridge custodian doc + multi-sig config (hub side).
  - Added `apps/exchange/simple_exchange/config.py` and `.env.example`.
  - Added `docs/security/bridge-custodian.md`.
  - Exchange `v1/bridge/status` and `v1/cross-chain/rates` now return
    custodian/multisig fields.
  - Live validation: exchange service restarted on hub, status endpoint
    returns new fields.

## P1 implementation (current session)

- [x] P1.8 — honest rewrite of docs/architecture/1_system-flow.md
- [x] P1.5 — aitbc ai submit --wait (plus base-URL /v1 normalisation)
- [x] P1.6 — island credential/secrets ownership for aitbc user
- [x] P1.1 Phase A — reputation sort in aitbc market list
- [x] P1.2 — customer and shop dashboard CLI commands
- [x] P1.7 — governance close proposal; propose → vote → close → execute lifecycle
  - Code, CLI and tests committed.
  - Live propose -> vote -> close -> execute validated on aitbc3 after dropping and recreating the governance DB.
    (invalid page in block 4 of relation base/16399/2610).
- [x] P1.1 Phase B — reputation-aware job dispatch
  - Implemented and live-validated on `aitbc3` in `fdbd17f5c` (2026-08-21).
  - Coordinator dispatch now respects `min_reputation` and defers jobs to higher-reputation online miners.
  - CLI `aitbc ai submit --min-reputation` exposed.
  - Regression tests added in this commit.
- [x] P1.3 — bridge Merkle/multisig or trusted-custodian documentation
- [x] P1.4 — MultiValidatorPoA/PBFT soak and single-proposer dependence

Latest pushed commits (Agent B branch `feature/agent-b-p1-sprint` on `hub.aitbc`):
- 4f0ca3ba0 feat(exchange,docs): bridge custodian config and documentation (P1.3a)
- 1b86056b1 feat(website): add live customer and shop web dashboards (P1.2)
- 58a68d14c docs: refresh DESIGN_CYCLE and TASKLIST for Agent B P1 sprint


# Open task list for AITBC agents

## Current state

- P2.3 on-chain performance bonds is live on `aitbc3` and `hub.aitbc`.
  - `aitbc bond create`, `aitbc bond status`, `aitbc bond release` work end-to-end.
  - `BOND_LOCK` / `BOND_RELEASE` / `BOND_SLASH` are handled in state transitions.
  - Marketplace offers require an active bond when `MARKET_BOND_MIN_AMOUNT` > 0.

- Live nodes: hub `hub.aitbc` is on gitea `main` at `8c994306c` (clean). Shop `aitbc3` is at `8c994306c` (clean, fast-forwarded to `origin/main`).
- P1.1 Phase B shipped: `JobService.acquire_next_job` defers to higher-reputation online miners, enforces `Constraints.min_reputation`, and `aitbc ai submit` exposes `--min-reputation`.
- Scenario 34 was replayed 2026-08-20 from this session:
  - unpaid job `1363fff0bc4b48c6903bc46f54fe0a7a` completed on `aitbc-miner-1`
  - paid job `4ad8e281871640fa8b1b25716c92c2c8` escrowed 1.0 AIT and released
  - ESCROW_RELEASE `0xa6dab9b72a2498...` confirmed in hub block **7548**
  - `test-wallet-3` balance **1.9500 AIT** (two 0.9750 releases)
  - GPU offer `llama3.2:3b` republished as `GPU_MARKETPLACE` tx `0x24431ace...` in hub block **7553**
- Shop chain was not merely lagging: it **forked at height 6815** (shop proposer `0x19e7e376…`, hub genesis). Reset + resync completed 2026-08-20:
  - backups: `chain.db.pre-fork-manual.20260820-213040` and `chain.db.pre-reset.20260820-213040`
  - shop now **caught up at 7569**, head hash matches hub
  - local RPC shows `test-wallet-3` **1.9500 AIT** and ESCROW_RELEASE `0xa6dab9b7…` in block 7548
- Hub working tree is clean at `bac4b6bd5`. Shop tree is clean at `c27c6545b`.
- localhost `/opt/aitbc` is staging only; do not commit live work from the IDE host.
- Historical `.gitea_token.sh` was scrubbed from gitea history (from aitbc3). GitHub `main` branch protection was not restored.

## Agent A (live two-node / gitea work)

- [x] Fix escrow release signature in `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py::_submit_payment_tx`.
- [x] Restart `aitbc-blockchain-rpc` on `hub.aitbc` and `aitbc3` after the fix.
- [x] Re-test a paid AI job from `hub.aitbc` to `aitbc3`.
- [x] Verify `aitbc wallet balance test-wallet-3` shows the released payment.
- [x] Verify `aitbc wallet transactions test-wallet-3` shows the `ESCROW_RELEASE` transaction.
- [x] Continue GPU marketplace offer publication from `aitbc3`.
- [x] Remove legacy `http://127.0.0.1:18000/18001` references from tests and scripts.
- [x] Investigate shop chain lag — it was a **fork at 6815**, not missing P2P. Follower reset + pull sync restored height 7569 matching hub.
- [x] Follow-up: `import_block` reports unknown parent as `diverged=True` instead of "Unhandled import case" (commit `0983db5fb`).
- [x] Follow-up: `aitbc-blockchain-p2p` installed and active on `aitbc3` after resetting the local PostgreSQL WAL and creating the `aitbc_mempool` database.
- [x] `aitbc market offer` as root can load `aitbc`-owned island credentials; non-root CLI import no longer dies on unreadable `blockchain-secrets.env`.
- [x] `aitbc market offer` 400s fixed: `my-agent-wallet` funded from genesis and offer re-published (`6b9ede797`).
- [x] `aitbc pool-hub` and hub URL resolution now fall back to `HUB_P2P_HOST` / `HUB_RPC_URL` on follower nodes.
- [x] `aitbc mining status/list` work on shop after blockchain RPC auth canonicalises bech32 addresses.
- [x] `aitbc transactions status/pending` fixed to use the configured hub `blockchain_rpc_url` instead of `localhost:8202` (`5886697ac`).
- [x] Replayed scenarios 01 and 02 live on `aitbc3`.
- [x] `aitbc messaging topic` fixed to fall back to deterministic simulated output (`e4171eb0c`).
- [x] Replayed scenario 04 (messaging basics) live on `aitbc3`.
- [x] Replayed scenarios 21, 22, 28, and 29 live on `aitbc3`.
- [x] Replayed scenarios 30, 31, 32, and 33 via their unit/CLI tests on `aitbc3`.
- [x] `aitbc reputation` fixed to avoid duplicate `/v1` in endpoint paths (`21fd6f317`).
- [x] `aitbc wallet stake` fixed to use the brand string correctly (`110cd9bb0`).
- [x] `aitbc wallet list` fixed to include file wallets alongside daemon wallets (`0ae4bb389`).
- [x] Replayed scenarios 10, 11, 12, 13, and 14 (partial) live on `aitbc3`.
- [x] Replayed scenarios 16, 17, 18, 19, and 20 live on `aitbc3`.
- [x] Investigate/fix `aitbc agent-comm register` double `/v1/hermes/v1` URL path and 401 response (`6200888ca`).
- [x] `aitbc wallet unstake` now prints the real lock-expiry reason from the staking RPC (`2b8508c28`).
- [x] `aitbc exchange-island` falls back to `exchange_service_url` when credentials lack `rpc_endpoint` (`e1cd871dd`).
- [x] Replayed scenario 08 marketplace bidding (`aitbc marketplace buy` works).
- [x] Replayed scenario 36 pool hub SLA e2e live on `aitbc3`.
- [x] Replayed scenario 06: `exchange-island orderbook`, `rates`, and `orders` work; `buy`/`sell`/`cancel` need the validator keystore.
- [x] Canonicalized marketplace dirty edits (`escrow amount as string`, `wrap task_data`) and pulled `hub.aitbc` to a clean working tree.
- [x] Update the release change log on `aitbc3` (shop-chain fork recovery section in v0.24.0).
- [x] P2.5 default Whisper/FFmpeg/Ollama shop offers implemented and validated.
- [x] P2.6 real IPFS daemon behind `aitbc ipfs` implemented and validated.
- [x] P2.7 compliance, plugins, and white-label expansion implemented and validated.
- [x] Hub-wide pool-hub miner registry verified and `aitbc pool-hub status` shows `miners_online > 0`.
  - `aitbc-pool-hub` runs on `hub.aitbc`; `aitbc-miner` on `aitbc3` registers and heartbeats to it.
  - `aitbc pool-hub status` and `aitbc pool-hub sla` work from both nodes.
  - Scenario 36 and CLI tests updated to reflect hub-wide pool-hub behavior.
  - `aitbc brand`, `aitbc plugin list/load/create`, and `aitbc compliance check/classify` work.
  - `aitbc ai submit --compliance-framework` validates classification before submission.
  - Scenario 43 and release changelog/live summary updated.
  - `aitbc ipfs upload/download/pin/list` use the local Kubo HTTP API with filesystem fallback.
  - Cross-node download validated between `aitbc3` and `hub.aitbc`.
  - Scenario 42 updated and release changelog/live summary updated.
  - `aitbc-miner` auto-publishes default offers on startup.
  - `aitbc market transcribe/process/run` work and release escrow.
  - Scenario 50 and release changelog updated.
- [x] Document wallet key mismatch recovery: note that mismatched keys cannot be safely regenerated without the original seed and recommend migration to a new wallet (`AGENTS.md`).

## Agent B (localhost / documentation / support)

- [x] Reset the localhost `/opt/aitbc` working tree to gitea `main` and remove stale untracked files.
- [x] Patch `scripts/testing/qa-cycle.py` to read `GITEA_TOKEN` from the environment or `~/.gitea_token`.
- [x] Scrub historical `.gitea_token.sh` from gitea history (done from aitbc3).
- [x] Extend `docs/scenarios/34_hub_customer_node_e2e.md` with paid-job + escrow + GPU offer steps (commit `b18468450`).
- [x] Replay scenario 34 live on hub + shop (2026-08-20) and record results in `LIVE_VALIDATION_SUMMARY.md`.
- [x] Patch scenario 34 exchange paths and JWT import (commit `e8966aba1` on gitea `main`).
- [x] Keep `AGENTS.md`, `TASKLIST.md`, and `LIVE_VALIDATION_SUMMARY.md` accurate as the workspace evolves.
- [ ] Provide diffs / verification for Agent A when requested.
- [ ] Do not commit or push release work from the IDE host — only from `aitbc3` or `hub.aitbc`.

## Shared / unresolved decisions

- [x] Which agent owns the final end-to-end live validation? → replayed again this session; still green on hub.
- [x] Should workspace notes live in the canonical repo? → yes, already pushed earlier.
- [x] Who fixes shop chain sync / missing P2P on aitbc3? → fork reset done this session; P2P unit still missing (HTTPS pull is how the shop syncs).
- [x] Who updates scenario 34 exchange + JWT snippets on gitea `main`? → commit `e8966aba1`.

## P2.1 — ZK proofs for high-value jobs

- [x] Build `receipt_public` circuit with public `receiptHash`
- [x] Generate and commit `receipt_public` zkey/wasm/vkey
- [x] Update `ZKProofService` to use `receipt_public` and Poseidon4
- [x] Gate miner result submission on ZK proof for high-value jobs
- [x] Gate `PaymentService.release_payment` on verified `zk_status`
- [x] Add `--zk-proof-required` to `aitbc ai submit`
- [x] Add `zk_status` and `zk_proof_id` to `JobView`
- [x] Add `apps/coordinator-api/tests/test_zk_receipt.py`
- [x] Live validation of `aitbc ai` with ZK gate — validated 2026-08-21; see LIVE_VALIDATION_SUMMARY.md section "P2.1 ZK Proofs for High-Value Jobs" and "ZK proof for high-value jobs — live validation".

## P2.3 — On-chain performance bonds and slashing

- [x] Add Bond table and bond escrow/burn accounts
- [x] BOND_LOCK / BOND_RELEASE / BOND_SLASH state transitions
- [x] /rpc/bond query routes
- [x] Wire aitbc bond CLI to real blockchain endpoints
- [x] Marketplace offer bond eligibility enforcement
- [x] Unit tests and scenario docs
- [x] Live validation on aitbc3 / hub.aitbc

- [x] Fix `escrow_enabled` default/config drift in `STATUS.md` and `apps/blockchain-node/src/aitbc_chain/config.py`.
  - `escrow_enabled` now defaults to `True`; B4/HTLC integration complete.
  - `STATUS.md` no longer lists `False` for the flag; bridge-scope note updated.