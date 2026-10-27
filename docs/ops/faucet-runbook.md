# Faucet runbook — the 3 AIT welcome grant

> The hub faucet pays a one-time **3 AIT** grant to a new node from a
> dedicated capped wallet. Requests are paid once *approved* under the
> coin-request policy — a fresh pair is auto-approved, then executed by a
> second call.
>
> The split exists because of 27 Oct: the faucet had been paused since
> 2026-09-09 with `GENESIS_PRIVATE_KEY` absent on hub (every execute
> answered 503), and it reopened the day the grant wallet landed under
> its own `FAUCET_*` env names — so the treasury key never has to sit in
> the paying service. (FAUCET-KEY-NAMING-1, #609; website wording #607.)
>
> **Env edits and executes need the operator's typed line.** Everything
> below is read-only unless marked otherwise; never run a coin request
> from this runbook without that line.

## Request flow

```text
node                CLI                     hub agent-coordinator
 |-- register ------>| POST /api/v1/agent/coin-requests/register
 |                   |                       -> coin_request_policy.decide()
 |                   |                          fresh pair -> APPROVED (automatic)
 |-- execute ------->| POST /api/v1/agent/coin-requests/execute
 |                   |                       -> claims row, signs from the
 |                   |                          faucet wallet, submits TRANSFER,
 |                   |                          writes tx_hash
```

- `aitbc coin-requests request` does register then execute in one step
  (`cli/aitbc_cli/commands/coin_requests.py:782-837`); a fresh
  sender/wallet pair is auto-approved at `routers/coin_requests.py:143`
  (`approval_mode="automatic"`, `approved_by="coin-request-policy"`).
- `/execute` pays the **stored row** — the body's amount/destination are
  ignored (`_warn_on_mismatch`, `routers/coin_requests.py:189-205`). One
  claim at a time; a failed send un-claims (`_release_claim`,
  `routers/coin_requests.py:338-351`).
- Auth: `x-api-key` with `FOLLOWER_API_KEY`, `COORDINATOR_API_KEY` or
  `SECRET_KEY` (`_require_api_key`, `routers/coin_requests.py:57-84`).
  `aitbc coin-requests approve` is a local-DB action only; hub-side
  approval for a non-auto request is an operator step.

## Which wallet is which

| env | wallet | read at |
|---|---|---|
| `FAUCET_PRIVATE_KEY`, `FAUCET_ADDRESS` | capped faucet wallet — the grant source | `aitbc/crypto/transaction_service.py:49-50` |
| `GENESIS_PRIVATE_KEY`, `GENESIS_ADDRESS` | treasury — fallback only | same lines |

`FAUCET_*` wins when both are set (`genesis_private_key = FAUCET_PRIVATE_KEY
or GENESIS_PRIVATE_KEY`). Public addresses already in repo docs: treasury
`0x4aF8F36d91ff6b0125D18A76f242184e4F083EE0`
(`docs/deployment/bc2-genesis/README.md`), faucet
`0xf8C907EFc56F9a13d2f5AB528355440F94Bb6b87`
(`docs/deployment/bc2-genesis/classes.json`). No key values anywhere.

## Grant identity and budgets

`coin_request_policy.py` (agent-coordinator):

- One grant per sender **or** wallet: `has_prior_grant()`
  (`:134-165`) matches on `sender` or the canonical wallet address and
  counts **APPROVED rows only** (executed or not).
- Ceiling 3 AIT: `DEFAULT_AUTO_APPROVE_MAX` (`:40`), env
  `COIN_REQUEST_AUTO_APPROVE_MAX` (`:83-90`; `0` disables auto-approve).
- Budgets: `DEFAULT_AUTO_BUDGET_PER_HOUR` 24 AIT (`:56`) and
  `DEFAULT_AUTO_BUDGET_PER_DAY` 60 AIT (`:57`), env
  `COIN_REQUEST_AUTO_BUDGET_PER_HOUR` / `_PER_DAY` (`:93-105`); the window
  sums only `APPROVED` + `approval_mode="automatic"` rows
  (`_auto_granted_since`, `:108-119`).
- `decide()` (`:168-223`) returns PENDING with a reason on ceiling=0,
  amount>ceiling, prior grant, or exhausted budget; else APPROVED.

A second grant path exists on the agent WebSocket (`agent_stream.py`)
with the same 3 AIT amount — its prior-grant check counts executed rows
because it signs immediately.

## Pause and open

- **Pause**: stop paying — clear `FAUCET_PRIVATE_KEY`/`FAUCET_ADDRESS`
  (operator's typed env edit, then the service restart that carries it).
- **Effect of a missing or blank key**: `TransactionService` falls back
  to `GENESIS_*`; if neither is set, `/execute` answers **503**
  "FAUCET_PRIVATE_KEY or GENESIS_PRIVATE_KEY not configured on this node"
  (`routers/coin_requests.py:261-271`; a blank string counts as missing).
  Register/approve still work — requests queue PENDING.
- **Soft pause without touching keys**: `COIN_REQUEST_AUTO_APPROVE_MAX=0`
  turns every request into a manual-approval PENDING.
- **Open**: set the `FAUCET_*` pair and restart; funded-balance check
  (`amount + fee` vs `get_balance`, `routers/coin_requests.py:273-276`)
  answers 400 when the wallet is empty.

## Grant test with a fresh wallet

Cost: exactly **3 AIT from the faucet wallet, one real transaction** on
the live chain — there is no dry-run flag.

1. Create a throwaway wallet on a test node (`aitbc wallet create` —
   key handling is operator scope).
2. `aitbc coin-requests request` from that node → auto-approves only if
   the sender *and* wallet are both never-seen (see grant identity).
3. Confirm: `aitbc coin-requests show <request_id>` carries a `tx_hash`;
   the faucet balance dropped by 3 AIT + `TRANSACTION_FEE` (10 units,
   `routers/coin_requests.py:43`).
4. A re-request from the same wallet must land PENDING — that is the
   prior-grant rule working, not a failure.

## Ledger DB

sqlite at `/var/lib/aitbc/data/agent_coin_requests.db` (default of
`get_db_path()`; override `AGENT_DB_PATH`, `aitbc/db/agent_db.py:19-25`).
Read-only inspection: `sqlite3 "file:...agent_coin_requests.db?mode=ro"`.

## Not covered here

- Key rotation (held for the v1 batch) — no rotation task runs from this
  document.
- Treasury moves — funding/refunding the faucet wallet is an operator
  action with its own go, not a runbook step.
