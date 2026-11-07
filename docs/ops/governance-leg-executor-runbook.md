# Unattended governance-leg executor runbook

> Codifies the pattern proven live on 2026-11-07 executing #752 legs 3–5
> (`/root/leg752-exec.sh` on hub, armed per operator ruling comment 17978).
> Use for any batch of timelocked governance proposals that must execute
> unattended at chain-derived eligibility heights.

## When to use

A set of proposals has passed voting and sits behind
`GOVERNANCE_TIMELOCK_BLOCKS` (live: 1290 blocks ≈ 24h at ~67s cadence).
Executing them by hand means polling head height for hours. The executor
script polls `/rpc/status`, derives the exact eligible height from the
chain's own refusal message, and submits sequentially.

## Preconditions

- Executor wallet funded for gas and registered (e.g.
  `gov-executor-d9cc` under `/var/lib/aitbc/wallets/`).
- `aitbc governance execute` must sign the **sealed `execution_payload`**
  verbatim — fixed in #1214 (`8b8b4803e`); older CLIs 400 on every execute.
- Gitea token at `/root/.gitea_token` (hub) for ledger posting.
- Run detached: `setsid /root/leg-exec.sh > /root/leg-exec.log 2>&1 &`
  (the script self-redirects to its log).

## Script behavior contract

1. **Sequential order** — proposals execute in the listed order, one at a
   time; never parallel (nonce collisions — see #752 leg-2 incident).
2. **Eligibility from chain state, not wall clock** — each attempt that
   returns `Timelock not expired: N blocks since voting ended` yields the
   exact remaining count; target head = current + N. The script polls
   `/rpc/status` every 120s until head ≥ target, then retries.
3. **Stop-on-first-refusal** — any non-timelock refusal (HTTP 400/500,
   validation error, signature failure) posts the refusal evidence to the
   issue and **halts the sequence**. A refusal is safe: no tx lands.
   Do not retry blindly — ledger first, diagnose, then re-arm.
4. **Seal verification** — after an accepted execute, poll
   `/rpc/governance/sealed-proposal/<id>` for `executed=true` +
   `execute_tx_hash` + `execute_block_height` (up to ~20 min). Post the
   seal tuple to the ledger.
5. **Ledger format** — every leg result posts to the tracking issue as
   `Coder: <lane>` with: leg number, proposal id, head at attempt,
   tx hash, seal block height, attempt count. Refusals include the raw
   error tail.
6. **Guards** — 400-attempt cap per leg, 20h deadline, `set -u`, all
   output to the log. A deadline/attempt-cap hit posts and halts.

## Operational rules

- **No service restarts or env edits while armed** — the executor assumes
  a stable chain; a restart wave mid-run can delay sealing past the
  deadline (legs have no expiry, but the window assumption breaks).
- Legs have **no execution expiry** — timelock is a floor only; missing
  an estimated window is not fatal, re-derive eligibility from the next
  refusal.
- Morning handoff must list: per-leg proposal id, execute head, tx hash,
  seal status, any refusal + reason.
- The script is per-batch: copy, update the proposal-id list, log path,
  and issue number; do not generalize it into a daemon.

## Known pitfalls (from live run)

- `--executor-address`, not `--executor` (CLI flag name).
- Mempool nonce-slot collision: if a prior tx from the same wallet sits
  unconfirmed, the next execute 400s — wait for seal, then retry (leg-2
  incident, resolved by sequencing).
- REST submit fan-out gap was fixed in #1215 (`4ad649af7`); pre-fix,
  REST-submitted txs only propagated on a proposer turn.
