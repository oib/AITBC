# Withdrawal release runbook — AIT→ETH releases (ETH-9/ETH-14)

> Covers `eth_withdrawals` rows on hub (`aitbc-wallet` bridge monitor,
> `BRIDGE_ENABLED=true` + release key there only). Sepolia.

## Statuses and what the machine does with them

| status | meaning | who moves it next |
|---|---|---|
| `pending` | recorded, release not attempted yet | monitor poll |
| `releasing` | intent persisted (nonce + deterministic `eth_tx_hash`), broadcast attempted | resume pass every poll: proven `sent` → `completed`; proven `not_sent` → `failed` + AIT refund; `unknown` → stays |
| `completed` | a status-1 receipt for the recorded hash exists at `BRIDGE_RELEASE_CONFIRMATIONS` depth | terminal |
| `failed` | release provably never sent and refund submit failed, or refund path errored | operator |
| `refunded` | AIT refund broadcast done (`refund_tx_hash`) | terminal |
| `needs_review` | release outcome unverifiable (RPC failures, foreign nonce consumption) | resume pass keeps re-checking; parks forever until provable |
| `releasing_retry` | operator `release-retry` broadcast in flight | resume pass: `sent` → `completed`; `not_sent` → `needs_review_release` (parked, **never auto-refunded**) |
| `needs_review_release` | a retried release proved unsent — deliberate operator decision point | only `release-retry` (again, under proof) or `mark-review` |

The golden rule (ETH-14): a broadcast echo is never payment proof.
`completed`/`released` is written **only** on a status-1 receipt at the
required confirmation depth, and `releasing`/`releasing_retry` rows are
re-verified every poll — a reverted or dropped release can no longer be
recorded as paid.

## Release gas policy (post-Glamsterdam)

Since Sepolia's Glamsterdam activation (2026-10-06, EIP-8037 state-gas) a
transfer to a previously unseen account estimates at ~207k gas — a static
100k limit deterministically reverts, which is how ETH-14 happened.

- `ETH_WITHDRAW_GAS` — **unset by default now**. When set it is an explicit
  override (documented escape hatch), rejected unless `0 < value <=
  ETH_WITHDRAW_GAS_MAX`.
- `ETH_WITHDRAW_GAS_MARGIN` — multiplier over `eth_estimateGas` (default
  `1.25`).
- `ETH_WITHDRAW_GAS_MAX` — hard cap (default `300000`).
- floor is 21,000. An estimate error or an over-cap result raises before
  signing — the row then lands `failed` + refund via the normal
  `not_sent` path, never a blind broadcast.

## Operator commands

```bash
cd /opt/aitbc
PYTHONPATH=/opt/aitbc/apps/wallet/src:/opt/aitbc/packages/py/aitbc-sdk/src:/opt/aitbc/packages/py/aitbc-crypto/src \
    venv/bin/python -m wallet_app.bridge.withdraw_admin <command> [args]
```

Environment comes from the unit's env files by default
(`/etc/aitbc/blockchain.env`, `blockchain-secrets.env`, `node.env`,
`exchange.env`, `aitbc-wallet.env` — repeatable `--env-file` overrides).
Two independent Ethereum RPC endpoints are mandatory for anything
mutating: `ETH_RPC_URL` plus `--verify-rpc` or `ETH_VERIFY_RPC_URL`.

- `status <ait_tx_hash>` — dump the ledger row, every recorded release
  attempt, the monitor's verify verdict, and the per-RPC proof bundle.
- `release-retry <ait_tx_hash>` — **dry-run default**: prints the two-RPC
  proof bundle (receipt `status=0x0` at depth, recorded nonce consumed,
  receiver gained nothing in the failed block — or hash absent + nonce
  still free for a never-sealed retry), the sealed-AIT-leg check, and the
  exact planned send (`amount_eth`, `eth_address` and nonce taken from the
  row — the amount is never re-quoted). `--confirm --note "…"` performs
  it: attempt row + `retry_count` bump persist BEFORE broadcast
  (`resolved_by`/`resolved_at`/`operator_note` + hash + nonce), the row
  goes `releasing_retry`, then the command waits for a verified receipt:
  `sent` → `completed`; `not_sent` → `needs_review_release`.
- `mark-review <ait_tx_hash> --note "…" --confirm` — the refund lane
  (option B): moves an eligible row to `needs_review`; the next monitor
  poll re-proves `not_sent` and refunds the AIT. Use when a retry cannot
  land (float too low, estimate over cap) or a retry provably reverted.

Eligibility, enforced in the same run before any send: `completed` rows
whose recorded release proves failed, and `needs_review_release` rows.
Anything monitor-owned (`releasing`, `releasing_retry`, `needs_review`),
already-`refunded`/refund-recorded, or `failed` is refused — never race
the machine, never double-compensate.

## Failure modes to remember

- A retry whose broadcast threw but whose hash may exist stays
  `releasing_retry`; the resume pass resolves it against the chain, and a
  second `release-retry` refuses until the first is proven reverted or
  never mined (in the never-mined case the resend reuses the same free
  nonce — the floating blob and the resend are mutually exclusive).
- `status` is read-only and safe to run anywhere with view of the DB;
  mutating commands should run on hub only, as the operator, with the
  unit's env files.
