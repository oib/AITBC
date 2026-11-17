# Block-scoped `Account` state (DEV-3)

Status: **prototype on branch `dev/block-scoped-account`** — not merged.
Supersedes the section-9 draft in `docs/DESIGN_CYCLE.md` (2026-09) with the
post-V-2/V-3/V-4/BNT-2 reality: what that draft proposed is already built and
running, behind an env flag. This document designs the remaining piece —
making the semantics a property of the block version (a v15 rung) so they
cannot diverge by configuration.

## 1. Premise check (2026-10-13, `origin/main` `45f41ce9a`)

Section 9 described RPC paths that mutate `Account.balance`/`Account.nonce`
outside block application. Current state, checked file by file:

| §9 claim | today |
|---|---|
| `faucet_request` in `rpc/accounts.py` credits at RPC time | **Gone.** No `faucet` symbol exists under `apps/blockchain-node/src/`. Faucet payouts moved to `agent-coordinator`'s `coin_requests.py`, which builds a **signed** `TRANSFER` and posts it to `/rpc/transaction` — a normal mempool transaction that applies at block time on every node. Already block-scoped by construction. |
| `bridge_transfer.py` mutates at RPC time | **Flag-gated.** `initiate_transfer` (~line 159), `confirm_transfer` (~line 332), `refund_transfer` (~line 524) each guard the mutation with `settings.block_scoped_preregistered_transactions` (added v0.24.1, `config.py:359`, default `False`). |
| Orphan `Transaction` rows (`status='confirmed', block_height=None`) | **Clean.** `transaction` on the fleet shows 0 rows with `block_height IS NULL`, 0 `status='pending'`; 5 `BRIDGE_LOCK` + 1 `BRIDGE_REFUND`, all sealed. |
| Proposer never sees the txs | **Fixed the same way.** Under the flag the RPC writes only a mempool entry + `CrossChainTransfer`; `propose` applies `BRIDGE_RELEASE`/`BRIDGE_REFUND` at block time (`poa.py` ~2171) and BRIDGE_LOCK through normal apply; import applies every tx and creates the sealed `Transaction` row. |

The fleet runs `BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS=true` in
`/etc/aitbc/blockchain.env` on all five hosts — the production path is
already the §9 goal: every `account` mutation happens exactly once, at block
apply.

## 2. The residual bug: the remediation is env-gated, not consensus-gated

`block_scoped_preregistered_transactions` defaults `False` in code and is a
process-local flag. A node that runs flag-off while the fleet runs flag-on —
fresh deploy before `blockchain.env` carries the flag, a lost env line, a
second island bootstrapped from these docs — executes a *different state
transition* for the same logical request:

- flag-on host: RPC writes nothing to `account`; the block's apply debits.
- flag-off host: RPC debits `sender` immediately **and** creates a
  `Transaction(status='confirmed', block_height=None)`.

Concrete divergence scenario, `account` is committed table #1:

1. Operator calls `/bridge/lock` on a flag-off node (or a flag-off node
   serves the RPC for any reason — misconfig, migration, fresh node).
2. `sender.balance` drops on that node at height N; every other host keeps
   the old value until the lock seals at height N+k.
3. If the flag-off node *proposes* an intermediate block N+1, its
   `state_root` — and at ≥v14 its **`aux_state_root`** over the 13-table
   committed set — is computed over the already-debited `account`. Every
   follower recomputing the fingerprint gets a different value.
4. At ≥v14 the import path treats that as `sync_aux_root_rejected` —
   **the block is refused**, not just counted: one env drift escalates to a
   consensus stall the first time anyone uses the bridge after H.
   Below v14 the same divergence is silent: `state_root` mismatch on the
   same path (or silent skew if validation is off), and the `account`
   fingerprint mismatch persists until the lock seals.

The same exposure exists in reverse: a flag-on node inside a flag-off fleet
never pre-registers the `Transaction`, so the proposer's `existing_tx_map`
path misses and double-apply protection depends entirely on which side is
consistent. Consensus semantics must not depend on an env convention.

## 3. The change — one rung, three call sites, one import invariant

`state_transition_v15_height` (default `V13_HEIGHT_NOT_ARMED`, env override
`STATE_TRANSITION_V15_HEIGHT`) joins the ladder above v14. The rule:

> **`block_version >= 15` ⇒ pre-registered bridge mutations are deferred to
> block apply, unconditionally.** Below 15 the env flag decides (fleet runs
> it true; a flag-off node below 15 keeps today's behaviour for replay).

| file | change |
|---|---|
| `config.py` | `state_transition_v15_height` — sentinel default, env override, same pattern as v13/v14. |
| `state/state_transition.py` | v15 rung in `get_block_version_for_height` (checked before v14); new `block_scoped_preregistered(block_version)` helper = `version >= 15 or flag`. |
| `cross_chain/bridge_transfer.py` | the three `getattr(settings, …)` sites become `self._block_scoped(session, chain_id)` — resolves `get_block_version_for_height(head+1)` so the RPC decision matches what the sealing block will do (identical to the admission pattern `rpc/transactions.py` already uses for version-scoped door checks). |
| `consensus/poa.py` | the `BRIDGE_RELEASE`/`BRIDGE_REFUND` apply-at-propose gate becomes `block_scoped_preregistered(block_version)`. |
| `sync_block_import.py`, `state_transition.py` apply paths | **unchanged** — apply is already version-deterministic; followers always apply BRIDGE_* effects at block time and the persistent `(chain_id, tx_hash)` replay check refuses a second application. |

Nothing else mutates `account` outside apply: faucet is a signed `TRANSFER`;
`Transaction`/`CrossChainTransfer` row-shape differences between RPC-created
and apply-created rows are **not** in the V-3 committed set (the 13 tables
are all apply-written) — row-content parity is nice-to-have, not consensus.

## 4. Transaction status model

| status | who writes it | meaning |
|---|---|---|
| (no row) | block-scoped RPC | the tx exists only as a mempool entry (+ `CrossChainTransfer` pending); the sealed record does not exist yet |
| `pending` | mempool/policy tables only | queued, not sealed — `transaction.status='pending'` stays unused by these paths (0 rows on the fleet today) |
| `confirmed` + `block_height=H` | apply path (propose/import) | the single canonical record, created once at seal on every node |

The legacy flag-off rows (`confirmed`, `block_height=None`) are an RPC-era
artifact; the proposer's `existing_tx_map` stamps them at seal.

## 5. Migration of existing orphan records

Current fleet state needs no migration: 0 rows with `block_height IS NULL`
or `status='pending'` on `transaction`. For any chain with leftovers, the
§9 cleanup stands: seal the orphans against the height their RPC ran at
(synthetic anchor `block_height=<height of the block containing the matching
hash>`), or, where the matching `MempoolEntry` still exists, delete it so no
proposer re-applies. After v15, apply's persistent replay check treats such
rows as already-sealed — a synthetic anchor is sufficient.

## 6. How import treats pre-registered transactions

Followers hold no `CrossChainTransfer` and no `transaction` row for a
block-scoped BRIDGE_* tx — the block's tx list *is* the registry. On import
every tx goes through `validate_transaction` → `apply_transaction`:

- `BRIDGE_LOCK` debits `sender` (`value+fee`, nonce+1) — the locked value
  lives in `CrossChainTransfer`, never in an account.
- `BRIDGE_RELEASE`/`BRIDGE_REFUND` credit `recipient`/`sender` — magic
  senders (`bridge_release`/`bridge_refund`) never get accounts.
- The sealed `Transaction` row is written once, by apply, with
  `block_height=H` — identical shape on every node where it matters
  (committed fields); envelope/payload decoration can differ, it is not
  committed.
- A second application of the same `tx_hash` fails the persistent replay
  check (`Transaction` already persisted → "replay attack") — so a tx that
  sealed once cannot double-apply, and a pre-registered legacy row still
  resolves through `existing_tx_map` on propose.

## 7. Replay safety of the rung itself

The rung changes *which component* mutates, never *what* the mutation is:
below v15 a flag-off node's RPC-time mutation is replayed byte-identically
because the flag-off code path is preserved (it is the replay path for the
flag-off era). `tests/unit/test_v15_block_scoped.py` pins:

- `get_block_version_for_height` unchanged below the armed height and
  correct at/above it;
- `block_scoped_preregistered(v)` = flag below v15, always true at ≥v15;
- `initiate_transfer` defers all mutation at ≥v15 with the flag off, and
  keeps the legacy mutation below v15 with the flag off;
- one `apply_transaction` on two independent databases produces identical
  `account` rows; a second application is refused.

`test_historical_replay.py` covers the "identical hashes across the v14
boundary with the prototype" requirement: the rung defaults to 2**62, so
every sealed era replays under its own rules with no flag involvement.

## 8. Activation proposal (operator decides)

- **Proposed rung:** `state_transition_v15_height` — a height **to be
  chosen by the operator**, recommended ≥ 4 weeks of headroom after the
  earliest plausible merge (the fleet must all carry the code first, then a
  6-hour margin gate as in ACT-1). No default height is proposed in code —
  the sentinel keeps it parked.
- **Pre-checks at H−320:** all five hosts on the merged SHA, env flag still
  true (it stays the below-v15 behaviour and the kill-switch), shadow
  fingerprints equal at 20 shared heights, validator set unchanged,
  mempool draining.
- **Verification at H:** blocks ≥H stamp `state_transition_version` 15; a
  read-only `initiate_transfer` dry-run (or the existing flag-on path — they
  are behaviourally identical) produces no `account`/`transaction` row
  before seal on every node; aux roots equal.
- **Rollback:** `STATE_TRANSITION_V15_HEIGHT=V13_HEIGHT_NOT_ARMED` on all
  five + serial restart **before H** — same as the ACT-1 cancel path. After
  H the rung is sealed history: a cancel would itself be a divergence, so
  post-H rollback is re-pointing the fleet forward, not unpicking.
- **Env flag after H:** `BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS` becomes
  vestigial (its effect is implied at ≥v15). Keep it set until the fleet is
  past the margin gate, then it may be retired from `blockchain.env` in a
  normal env pass — the code keeps honouring it below v15 for replay.
