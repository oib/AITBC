# First ESCROW_FEE_SWEEP observation — read-only checker

> Companion to `legacy-escrow-residue-payout.md` (Option A batch) and the
> design note `TOPOLOGY/2026-10-04-fee-sink-design.md`. v11 is live since
> block 35400 (`STATE_TRANSITION_V11_HEIGHT`, env-pinned on every node);
> `escrow_fee_recipient` = the treasury `0x716a56468DD4A11A91116920F9E8892BbDD7b1B8`
> (written at 35411 via `v11-set-escrow-fee-recipient`);
> `ESCROW_FEE_SWEEP_ENABLED=true` on hub's RPC only. Until the first
> settlement lands, the sweep path has unit-test coverage only — this is how
> to verify the first real one without touching keys or writable state.

## 1. When to run it

The route offers a sweep right after each settlement's final leg, and again
through the retry surface for already-released escrows. Run the checker when
any of these fire:

- an `ESCROW_FEE_SWEEP` appears in the chain (`SELECT ... WHERE type='ESCROW_FEE_SWEEP'`),
- an `escrow sweep` log/metric line reports `submitted`,
- or as a post-mortem when a settlement left residue the sweep did not take.

## 2. Take read-only snapshots — never open the live DB

On each host you want to compare (hub plus any followers that imported the
block):

```bash
ssh <host> 'sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
    ".backup /tmp/chain-<host>.db"'
scp <host>:/tmp/chain-<host>.db /tmp/
```

`.backup` is consistent and read-only against the live file; the checker
itself opens with `mode=ro` and writes nothing.

## 3. Run

```bash
cd /opt/aitbc    # or any checkout containing scripts/ops/first-sweep-check.py
python3 scripts/ops/first-sweep-check.py --latest /tmp/chain-hub.db
python3 scripts/ops/first-sweep-check.py --job-id sw_job_… \
    /tmp/chain-hub.db /tmp/chain-node2.db /tmp/chain-node1.db
```

`--latest` takes the newest sealed sweep; `--job-id` verifies the sweep for a
specific job. Multiple DB arguments enable the cross-host agreement check.
The script is stdlib-only — any `python3` works, no venv needed.

## 4. What it verifies (one `PASS`/`FAIL`/`SKIP` line each)

| check | proves |
|---|---|
| `sweep.sealed` | the sweep sealed and names the job in `payload.job_id` |
| `sweep.signer` | signer is the `escrow_settlement_authority` in force *at the sweep's height* (a later rotation does not rewrite history) |
| `sweep.recipient` | pays the governed `escrow_fee_recipient` at that height |
| `sweep.value` | `value == lock − released − refunded` — the exact remainder the settlement legs left |
| `custody.zero` | the derived custody account (`keccak("aitbc.escrow.<job>")`, EIP-55, first 20 bytes — embedded, no eth_utils needed) reads 0 — the detector read |
| `recipient.delta` | recipient balance equals its full tx-ledger replay (the sweep contributed exactly `value`); `SKIP` when the account has non-ledger flows (minted genesis etc.) |
| `authority.delta` | authority balance equals its custody-aware replay — the sweep cost it exactly `fee`, never the value; `SKIP` on non-ledger flows |
| `authority.nonce` | authority's account nonce equals its sealed send count |
| `cross-host` | same `tx_hash` at the same `block_height` with identical sender/recipient/value/fee on every DB given |

Exit code 0 = all PASS/SKIP; 1 = any FAIL. The script never reads or prints
a key — only addresses.

## 5. Expected output shape

```text
## chain-hub.db
  PASS sweep.sealed: 0x7f3a… sealed at height 35442 for job sw_job_…
  PASS sweep.signer: signer 0x03DF9Ed3788E… vs authority 0x03DF9Ed3788E…
  PASS sweep.recipient: pays 0x716a56468DD4… vs governed 0x716a56468DD4…
  PASS sweep.value: value=20000 vs lock(1000000) − released(900000) − refunded(80000) = 20000
  PASS custody.zero: custody 0x… balance=0 (detector reads 0)
  PASS recipient.delta: recipient balance … equals full ledger replay — sweep credited exactly 20000
  SKIP authority.delta: authority balance … vs ledger replay … — non-ledger flows present; fee debit not isolated
  PASS authority.nonce: authority nonce 42 vs 42 sealed sends
  PASS cross-host: 3 hosts agree: 0x7f3a… at height 35442
```

`authority.delta` will often SKIP: the authority wallet is used for payouts,
proposals and repairs that never touch the `transaction` table as sealed
rows — the replay then cannot isolate the fee debit and the checker says so
instead of guessing.

## 6. Known gaps the checker exists because of

The review that shipped this script found the sweep leg is **not guaranteed
to seal on the settle-time attempt**: the route signs the sweep with the
authority's *sealed* nonce while its own release leg is still pending on the
same `(authority, nonce)` mempool slot, and the sweep's fee can never outbid
the release that occupies it — so the settle-time submission is rejected by
design and the sweep only lands via the retry path (or a re-driven release
call). A settlement that completes without a sealed sweep is therefore
**expected today**, not an alarm — run the checker to confirm the residue is
still in custody, and the retry path will offer the leg the next time the
released escrow is re-driven.
