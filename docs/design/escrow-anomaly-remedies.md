# SD-6 — remedy options for two escrow anomalies (paper only)

**Status:** options paper. **Nothing here is proposed for execution.** Every
remedy below that moves value is a chain write and needs a separate operator
decision; the ledger-write option needs a fleet-coordinated DB write, also
operator-controlled. Facts were verified read-only (`mode=ro`) against
node2's chain.db at 2026-10-12; cross-host leg sets are identical.

## Item A — job `sw_job_ipfs_…46025c0e`: double release, 702000 paid on a 360000 lock

### Verified facts

- `ESCROW_LOCK` @2407, value 360,000, buyer `0x08aB…` → escrow, provider `0x4A5b…`.
- **Two** `ESCROW_RELEASE` legs in **block 2409**, each 351,000, sender
  `0x02B8F2C6` (the v2 settlement authority) → recipient `0x4A5b3bf9` (the
  provider — node2's shop wallet). Distinct `contract_id`s in the payloads —
  the v2 contract emitted two releases for one lock (the known R2 anomaly;
  SD-1 `--plan` already records it as `KNOWN ANOMALY` instead of aborting).
- 351,000 is exactly 97.5% of the lock — each leg looks like "the" release;
  the fee leg does not exist separately here (pre-v3 custody era, lock
  height 2407 < 5470: the 2.5% convention was not yet segregated).
- The local `escrow` ledger row recorded `released_amount = 702000` — the
  bookkeeping *knows* about both legs; the money really moved.
- Current balances (2026-10-12): authority `0x02B8…` ≈ 35,999,640,000
  (nonce 90), provider `0x4A5b…` ≈ 3,324,715,099.
- **Who bore the loss:** the settlement authority paid 351,000 twice — the
  authority's float is short, the buyer was not debited extra. Both
  affected accounts are operator-controlled (authority on hub, shop wallet
  on node2).

### Options

| option | mechanism | cost | consensus impact | who signs |
|---|---|---|---|---|
| A1 — do nothing (documented anomaly) | none; the SD-1 plan record plus this paper are the documentation | 0 | none | nobody |
| A2 — documented write-off | a fleet-coordinated `escrow`/`job_payments` ledger annotation marking the 351,000 as a written-off authority loss (the SD-1 repair tooling's write phase covers this class); **no chain movement** — money stays with the provider | operator DB write ×5 hosts, plus care that all five converge on the same annotation | none (off-chain bookkeeping only) | nobody (DB op) |
| A3 — voluntary refund transfer | the provider wallet sends 351,000 back to the authority as an ordinary signed transfer (both are the operator's keys; this is *not* a clawback — no consensus machinery exists or is needed for an involuntary one) | one tx fee; trivial signing | none — a normal user-signed transfer | the provider wallet (`0x4A5b…`, operator's node2 key) |

### Recommendation — Item A

**A2** (documented write-off), folded into whatever ledger-repair batch the
operator approves under SD-1. The anomaly is already the canonical
double-settlement on record; the amount is small and both sides are the
operator's own accounts, so A3 is optional housekeeping the operator can do
anytime with a plain wallet send — it does not need a design decision and is
not part of this paper's request.

## Item B — ~4,387,500 auto-stake principal stranded in the stake escrow

### Verified facts

- `STAKE_LOCK` @7306, value **4,387,500**, sender `0x4A5b3bf9` → stake escrow
  `0x52917d68…`, payload `{"source": "auto_stake", "stake_id": "1"}` — an
  unsigned protocol transfer that sealed because 7306 < 30400 (pre-v9).
- Stake escrow balance today: **exactly 4,387,500** (nonce 4 — four 1-unit
  outbound releases for unrelated 1-unit test stakes). The principal is
  intact and unmoved.
- The `stake` ledger row (id 1, address `0x4A5b3bf9`, amount 4,387,500,
  `locked_until` 2026-10-14, status `active`) still shows active.
- The only release path that ever existed was `POST /rpc/staking/unstake` →
  `queue_protocol_transfer` STAKE_RELEASE — **retired by BNT-2** (unsigned
  protocol transfers cannot seal at v9; the RPC now answers 410 and would
  have queued an unsealable tx before that). The escrow address is keyless;
  no wallet can sign for it.

### Options

| option | mechanism | cost | consensus impact | who signs |
|---|---|---|---|---|
| B1 — do nothing (documented lock) | none; principal stays in escrow, staker stays debited | 0 | none | nobody |
| B2 — documented write-off | mark the stake row `void`/unrecoverable on each host, note the 4,387,500 as a permanent escrow balance (economic burn); no chain movement | operator DB write ×5 hosts | none (off-chain bookkeeping) | nobody (DB op) |
| B3 — revival-path release | if/when the operator picks a BNT-1 revival (a new consensus height admitting `payload.auth`, or a rule letting the staker sign the STAKE_RELEASE leg — the staker *holds* a key, unlike the escrow), unstake stake id 1 through the un-retired path | a consensus change: new activation height + implementation + fleet deploy + rpc restart for the un-retired surface | **real** — same decision the BNT-1 options paper already queues | the staker (`0x4A5b…`, operator's node2 key) |

### Recommendation — Item B

**B1 now, folded into the BNT-1 revival decision later** (i.e., prefer B3
over B2 whenever that decision lands). The funds are the operator's own, no
third party is harmed, and a permanent write-off (B2) destroys value that a
planned revival can restore cleanly — B2 stays the fallback if the operator
decides protocol transfers stay dead forever. Do not build a bespoke
one-off release path: any signature-exemption special-casing a specific
escrow is strictly more dangerous than the general revival the operator is
already being asked to choose.

## Cross-cutting notes

- Both anomalies are self-inflicted (operator accounts on both sides), so
  urgency is bookkeeping hygiene, not customer remediation.
- Anything beyond A1/B1 requires an explicit operator word: DB writes for
  A2/B2, a signed transfer for A3, a consensus change + deploy for B3.
