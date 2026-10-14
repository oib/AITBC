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

A lagging RPC is not proof either (ETH-14b): an *absence-only* view (no
receipt, no tx, nonce not pending) on a row whose intent is younger than
`ETH_RELEASE_ABSENCE_GRACE_SECONDS` (default `600`) reports `unknown`,
never `not_sent` — so a still-in-flight release can never trigger a
refund. A status-0 receipt stays `not_sent` at any age.

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
- `ETH_RELEASE_ABSENCE_GRACE_SECONDS` — how long an absence-only RPC view
  on a just-broadcast release reads `unknown` instead of `not_sent`
  (default `600`; covers `releasing`, `releasing_retry` and sell-escrow
  releases — they share `_compose_release_outcome`).

## Operator commands

```bash
cd /opt/aitbc
PYTHONPATH=/opt/aitbc/apps/wallet/src:/opt/aitbc/packages/py/aitbc-sdk/src:/opt/aitbc/packages/py/aitbc-crypto/src \
    venv/bin/python -m wallet_app.bridge.withdraw_admin <command> [args]
```

Environment comes from the unit's env files by default
(`/etc/aitbc/blockchain.env`, `blockchain-secrets.env`, `node.env`,
`exchange.env`, `aitbc-wallet.env` — repeatable `--env-file` overrides).
Files apply in unit order with **later files overriding earlier ones**
(systemd `EnvironmentFile` semantics); an already-exported shell variable
still wins over every file — that is the documented way to pick the RPC
pair below.
Two independent Ethereum RPC endpoints are mandatory for anything
mutating: `ETH_RPC_URL` plus `--verify-rpc` or `ETH_VERIFY_RPC_URL`.

**Load the env before python starts.** `wallet_app.settings` requires
`COORDINATOR_API_KEY` at *import* time, so `PYTHONPATH=... venv/bin/python
-m wallet_app.bridge.withdraw_admin` fails without the unit's environment
already in the shell. Run in a subshell that sources the files first —

```bash
(
cd /opt/aitbc
set -a
. /etc/aitbc/blockchain.env
. /etc/aitbc/blockchain-secrets.env 2>/dev/null   # a line with an unquoted
. /etc/aitbc/node.env                            # '&' misparses under a
. /etc/aitbc/exchange.env                        # plain source — silence it;
. /etc/aitbc/aitbc-wallet.env 2>/dev/null        # the needed vars still load
set +a
export PYTHONPATH=/opt/aitbc/apps/wallet/src:/opt/aitbc/packages/py/aitbc-sdk/src:/opt/aitbc/packages/py/aitbc-crypto/src
export ETH_RPC_URL=https://sepolia.drpc.org
export ETH_VERIFY_RPC_URL=https://sepolia.gateway.tenderly.co
venv/bin/python -m wallet_app.bridge.withdraw_admin <command> [args]
)
```

Endpoints in output are always shown as `scheme://host` — a keyed RPC
URL's credential path is never printed or stored (ETH-15).

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

### Choosing the proof endpoints

The release-fate proof calls `eth_getBalance` at `block−1` — it needs an
**archive-capable** endpoint for releases older than ~120 blocks. Known
good (keyless public endpoints, used for the ETH-14 recovery):

- `https://sepolia.drpc.org`
- `https://sepolia.gateway.tenderly.co`

Endpoints known to fail this leg: `sepolia-rpc.publicnode.com` is pruned
(`-32000 historical state is not available`), and the service's Infura URL
intermittently returns `-32603 Internal error` on the same call. A refusal
whose detail mentions `historical state` or `-32000` means that endpoint
is **not archive-capable** — swap in an archive endpoint, do not retry
the same pair.

Note: `ETH_RPC_URL` serves both the proof bundle and (with `--confirm`)
the **broadcast** — pick an endpoint you want the signed transaction
sent through. The verify endpoint is proof-only.

## Failure modes to remember

- A retry whose broadcast threw but whose hash may exist stays
  `releasing_retry`; the resume pass resolves it against the chain, and a
  second `release-retry` refuses until the first is proven reverted or
  never mined (in the never-mined case the resend reuses the same free
  nonce — the floating blob and the resend are mutually exclusive).
- `status` is read-only and safe to run anywhere with view of the DB;
  mutating commands should run on hub only, as the operator, with the
  unit's env files.
