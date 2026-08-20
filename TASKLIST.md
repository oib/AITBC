# Open task list for AITBC agents

## Current state

- gitea `main` is at `eec9f22ac` (wallet/explorer 404 fix merged).
- `hub.aitbc` and `aitbc3` are fast-forwarded to gitea `main`.
- Wallet 404 fix is committed, pushed, and live on both nodes:
  - `aitbc account get --address ait1fe2d63...` works.
  - `aitbc wallet transactions test-wallet-3` no longer 404s.
- On-chain payment transfer is fixed in PR #275 (`b5b16a7ff`):
  - `_submit_payment_tx` now signs the `ESCROW_RELEASE` transaction with `GENESIS_WALLET_PRIVATE_KEY` and creates the provider account if missing.
  - `aitbc wallet balance test-wallet-3` shows `0.9750 AIT`.
  - `aitbc wallet transactions test-wallet-3` shows a confirmed `ESCROW_RELEASE` tx.
- gitea `main` is now at `49b749cc0` (escrow signature + marketplace offer + qa-cycle token-source fix).
- `hub.aitbc` and `aitbc3` are fast-forwarded to gitea `main`.
- localhost `/opt/aitbc` has been reset to gitea `main`; the working tree is clean. A backup of the removed stale files is in `/home/oib/windsurf/aitbc/backups/stale_opt_aitbc_1787243778.tar.gz`.
- `qa-cycle.py` now reads `GITEA_TOKEN` from the environment or `~/.gitea_token` and no longer reads a repo file (pushed to gitea).
- A historical `.gitea_token.sh` exists in gitea commit `337c68013` (not on GitHub). The token inside has been rotated and is no longer current, but the file should still be scrubbed from gitea history.

## Agent A (live two-node / gitea work)

- [x] Fix escrow release signature in `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py::_submit_payment_tx`.
  - Sign the `ESCROW_RELEASE` transaction with the genesis wallet private key.
  - Ensure the transaction is accepted by `POST /rpc/transactions/marketplace`.
- [x] Restart `aitbc-blockchain-rpc` on `hub.aitbc` and `aitbc3` after the fix.
- [x] Re-test a paid AI job from `hub.aitbc` to `aitbc3`.
- [x] Verify `aitbc wallet balance test-wallet-3` shows the released payment.
- [x] Verify `aitbc wallet transactions test-wallet-3` shows the `ESCROW_RELEASE` transaction.
- [x] Continue GPU marketplace offer publication from `aitbc3`.
  - `llama3.2:3b` software offer published on-chain and in the hub marketplace service.
- [x] Remove legacy `http://127.0.0.1:18000/18001` references from tests and scripts.
  - Pushed in commit `22ba759f7`.
- [ ] Update the release change log on `aitbc3` if required by release process.

## Agent B (localhost / documentation / support)

- [x] Reset the localhost `/opt/aitbc` working tree to gitea `main` (`eec9f22ac`) and remove stale untracked files.
- [x] Update `/home/oib/.devin/plans/plan-fcbb1f8e38449237.md` with the latest state (wallet 404 fix done, escrow signature pending, GPU marketplace pending).
- [x] Patch `scripts/testing/qa-cycle.py` to read `GITEA_TOKEN` from the environment or `~/.gitea_token` (not from a repo file); pushed to gitea.
- [x] Create `cleanup_token_history.sh` in `/home/oib/windsurf/aitbc` with the `git filter-repo` / `git filter-branch` commands Agent A should run.
- [x] Keep `AGENTS.md` and `TASKLIST.md` in `/home/oib/windsurf/aitbc` accurate as the workspace evolves.
- [x] Summarize live two-node validation results and findings in `/home/oib/windsurf/aitbc/LIVE_VALIDATION_SUMMARY.md`.
- [x] Update documentation/scenarios:
  - Extended `docs/scenarios/34_hub_customer_node_e2e.md` with paid-job + escrow + on-chain settlement + GPU marketplace offer steps (commit `b18468450`).
- [x] Update `aitbc3:/opt/aitbc/docs/releases/v0.24.0/change.log` if a release note is required.
  - Added hub↔shop section and appended recent commits (commit `8bb3bfe7f`).
- [x] Scrub the historical `.gitea_token.sh` from gitea history.
  - Ran from `aitbc3` using `git-filter-repo` + force-push.
  - Bare backup created at `/var/backups/aitbc-git-history-1787250425`.
  - `git log --all -- .gitea_token.sh` on `aitbc3` now returns no commits.
  - Gitea tags and remaining branches (`main`, `release/v0.24.0`, `fix-*`, `cli-*`) were force-pushed.
  - GitHub `main` branch protection was temporarily removed and the rewritten `main` was force-pushed. Branch protection was not restored (per request).
- [ ] Keep `AGENTS.md`, `TASKLIST.md`, and `LIVE_VALIDATION_SUMMARY.md` in `/home/oib/windsurf/aitbc` accurate as the workspace evolves.
- [ ] Provide diffs / verification for Agent A when requested.
- [ ] Do not commit or push release work from the IDE host — only from `aitbc3` or `hub.aitbc`.

## Shared / unresolved decisions

- [x] Which agent owns the final end-to-end live validation (paid AI job + escrow + on-chain balance confirmation)?  → **Agent A** ran and confirmed the live flow.
- [x] Should `AGENTS.md` / `TASKLIST.md` be copied into the canonical repo (`aitbc3:/opt/aitbc`) and pushed to gitea?  → **Done** (commit `1074d22f9`); GitHub `main` still cannot be force-pushed.
- Who runs `git filter-repo` to remove the old `.gitea_token.sh` from gitea history, and when?  → **Done** from `aitbc3` (commit `662cf2394` / new main). GitHub `main` still protected.
