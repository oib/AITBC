## P1 implementation (current session)

- [x] P1.8 — honest rewrite of docs/architecture/1_system-flow.md
- [x] P1.5 — aitbc ai submit --wait (plus base-URL /v1 normalisation)
- [x] P1.6 — island credential/secrets ownership for aitbc user
- [x] P1.1 Phase A — reputation sort in aitbc market list
- [x] P1.2 — customer and shop dashboard CLI commands
- [x] P1.7 — governance close proposal; propose → vote → close → execute lifecycle
  - Code, CLI and tests committed.
  - Live propose/close/execute blocked on aitbc3 by governance DB corruption
    (invalid page in block 4 of relation base/16399/2610).
- [ ] P1.1 Phase B — reputation-aware job dispatch
- [ ] P1.3 — bridge Merkle/multisig or trusted-custodian documentation
- [ ] P1.4 — MultiValidatorPoA/PBFT soak and single-proposer dependence

Latest pushed commits:
- 6191eaf3a feat(cli): aitbc dashboard customer and aitbc dashboard shop
- 5bfbcd7c9 feat(governance,cli): close proposal lifecycle for propose → vote → close → execute

## P1 implementation (current session)

- [x] P1.8 — honest rewrite of docs/architecture/1_system-flow.md
- [x] P1.5 — aitbc ai submit --wait (plus base-URL /v1 normalisation)
- [x] P1.6 — island credential/secrets ownership for aitbc user
- [x] P1.1 Phase A — reputation sort in aitbc market list
- [x] P1.2 — customer and shop dashboard CLI commands
- [x] P1.7 — governance close proposal; propose → vote → close → execute lifecycle
  - Code, CLI and tests committed.
  - Live propose/close/execute blocked on aitbc3 by governance DB corruption
    ().
- [ ] P1.1 Phase B — reputation-aware job dispatch
- [ ] P1.3 — bridge Merkle/multisig or trusted-custodian documentation
- [ ] P1.4 — MultiValidatorPoA/PBFT soak and single-proposer dependence

Latest pushed commits:
- 6191eaf3a feat(cli): aitbc dashboard customer and aitbc dashboard shop
- 5bfbcd7c9 feat(governance,cli): close proposal lifecycle for propose → vote → close → execute

# Open task list for AITBC agents

## Current state

- Live nodes: shop `aitbc3` is on gitea `main` at `0983db5fb` (*fix(sync): treat unknown parent as chain divergence*). Hub working tree still dirty and 2 commits behind `origin/main`.
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
- Hub working tree is still dirty (marketplace service edits + untracked HTML) and has not fast-forwarded. Shop tree is clean at `0983db5fb`.
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
