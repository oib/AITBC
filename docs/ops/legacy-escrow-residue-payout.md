# Legacy escrow residue payout — Option A batch (ESCROW_RELEASE per account)

> Operator decision 2026-10-05: pay the legacy escrow custody residue out to
> the providers named in each job's sealed lock — one authority-signed
> `ESCROW_RELEASE` leg per account under current consensus. This document is
> the executable runbook for that batch. **Nothing here runs without the
> operator's explicit go.** Every submission is a chain write from the
> settlement authority `0x03DF9Ed3788E5BA3991e6788036f9D171f027716`.
>
> Sources: `TOPOLOGY/2026-10-04-fee-sink-design.md` §6/§9 (operator staging
> doc, not in this repo), `TOPOLOGY/2026-10-04-fee-sink-census-correction.md`
> (the C10 correction — the census must derive custody from `ESCROW_LOCK`
> **transactions**, not escrow rows alone), and the executed helper shape in
> `TOPOLOGY/2026-10-04-v2-repair-runbook.md`. Companion:
> `escrow-settlement-ops.md` (pipeline + detector mechanics).

## 0. Verified snapshot — head 35284, 2026-10-05 (re-run, do not trust)

The census below was verified read-only against hub's chain.db
(`sqlite3 mode=ro`) on 2026-10-05 at head 35284. **It is a snapshot, not an
input** — §1 re-derives every number at fire time and any account that fails
the proof is skipped.

**13 nonzero custody accounts, 2,362,184 units** — the tx-derived (C10-
corrected) census. The §6 row-derived census counted 12 / 2,361,284; the
difference is the row-less canary `canary-escrow-v9r3-1790797967` (900),
which has a sealed lock and no escrow row on any host. Whether the batch is
12 or 13 legs is the operator's call at fire time — the account is
admissible under the identical rule (sealed lock, owed legs sealed,
custody = remainder).

| # | job_id | custody account | residue | sealed lock@ | provider (lock payload) | escrow row on |
|---|---|---|---|---|---|---|
| 1 | `423712cc00d94246ba5b6136f06294e1` | `0x1d1eEE1e8C368f568da5fE83F5D3F4a32aBcaB7f` | 425,353 | 33483 | `0x4A5b3bf9…B5D2` | hub |
| 2 | `abfe8833b4dc4e19a0b4d2091b74bc23` | `0x6aB8ba72E3B21103E6f32157eAE51d3056792116` | 450,000 | 7224 | `0x4A5b3bf9…B5D2` | hub, node2 |
| 3 | `b0bca78d791d46b09888d7501a336f36` | `0x2B7A927fb220135F25152436eF1a80ab0e968417` | 450,000 | 7204 | `0x4A5b3bf9…B5D2` | hub, node2 |
| 4 | `b4009a3b888a4055a7f75455bd8d5a9a` | `0x19029EFedaFCa362630C12106C86b8cd5B849997` | 450,000 | 7969 | `0x4A5b3bf9…B5D2` | hub, node2 |
| 5 | `f05ada69aa4d46ad9d3681c98fd97f1a` | `0x71079672296db787bC03b7e7e3ED40184e2e9f9D` | 450,000 | 7306 | `0x4A5b3bf9…B5D2` | hub, node2 |
| 6 | `bd8b5dc5ab39412394c0513b06eb736c` | `0x0776a9A286BFF97706ac052C4003DA441E520E56` | 90,000 | 30818 | `0x4A5b3bf9…B5D2` | hub |
| 7 | `atask_20260913215708_e29a183e` | `0x3d7754875C8c913f3cecCcAB85317cC7E040b884` | 18,000 | 6015 | `0x4A5b3bf9…B5D2` | hub, node2 |
| 8 | `atask_20260914072023_936366a8` | `0x4AB2dac961Fb09Fe596f7fC6C2833D44f3a0db16` | 18,000 | 6577 | `0x4A5b3bf9…B5D2` | hub, node2 |
| 9 | `sw_job_20260914200636_207d09b8` | `0xBAe2112d67568dEcc872f4b7d67aec9f839796bB` | 9,000 | 7223 | `0x4A5b3bf9…B5D2` | node0 |
| 10 | `sw_job_20260914200726_a558bd8a` | `0x9473a7CC29C3E879Bca7F77ABeb0E93A376A9716` | 29 | 7223 | `0x4A5b3bf9…B5D2` | node0 |
| 11 | `sw_job_20260914200706_88d364d9` | `0x4CdFA5Dc5B98d850282F51fa13010a472c0baC5F` | 2 | 7223 | `0x4A5b3bf9…B5D2` | node0 |
| 12 | `canary-escrow-27260` | `0x748C863cF060bc9656cb79ECa61Fe0f6E5266f7a` | 900 | 27246 | `0x02B8F2C6…4c5B` | node2 |
| 13 | `canary-escrow-v9r3-1790797967` | `0x0ADfaDCb8483c8f23be4569852941caa175Da4C7` | 900 | 29702 | `0x02B8F2C6…4c5B` | **none** |

Provider destinations (verified against lock payloads):

- `0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2` — node2's default wallet
  (named in `/etc/aitbc/aitbc-miner.env` on node2), 11 legs, Σ 2,360,384.
- `0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B` — hub's proposer/operator
  wallet (the same address that served as the v2 pooled escrow), the two
  canary legs, Σ 1,800. **Not** the settlement authority — the beneficiary
  pin below makes this the only admissible `to` for those two jobs anyway.

Authority account at snapshot: balance 33,487,005, nonce 23 (unchanged since
the 4-Oct v2 repair's nonces 10–22 sealed at blocks 34061–34077). The batch
costs the authority **fees only** — custody pays each leg's value — about
24,000 total at `fee = max(36, value//100)`. Headroom is not a constraint;
the nonce-sharing rules in §5 are.

## 1. Preconditions and census — re-run at fire time

All reads on hub, read-only. `DB=/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db`
(`sqlite3 -readonly` / `file:…?mode=ro`). The custody derivation is
`keccak("aitbc.escrow." + job_id)[:20]` checksummed —
`state/pure_state_transition.py:_escrow_address`; derive with
`venv/bin/python` + `eth_utils` on hub, or import `_escrow_address`
directly (the `scratch/fee-sink/census.py` pattern — note that script's
**row-only** union is exactly what the C10 correction supersedes).

The corrected census rule:

1. Collect every `job_id` from `ESCROW_LOCK` **transactions**
   (`SELECT payload FROM "transaction" WHERE type='ESCROW_LOCK'` →
   `payload.job_id`), **unioned** with `SELECT job_id FROM escrow` on every
   host's chain.db (rows are node-local: hub holds 8 of these jobs, node2 7,
   node0 3 — a single-host row read undercounts).
2. For each job: custody address, `account.balance`, lock value
   (`Σ ESCROW_LOCK.value`), sealed settlement legs (`Σ ESCROW_RELEASE` +
   `Σ ESCROW_REFUND` values naming the job in payload), the provider from
   the lock payload's `provider` field, the buyer from the lock tx's
   `sender`.
3. **Admissibility — required equality, not a bound** (legs can exceed the
   lock; the 2409 precedent paid 702,000 against a 360,000 lock):

   ```
   balance == lock_value − Σ sealed settlement legs
   ```

   For row-backed accounts the owning host's row must also read
   `released`/`refunded` (all-owed-legs-sealed). A row-less account is
   admissible on the tx-derived proof alone — `canary-escrow-v9r3` is the
   live example.
4. **Skip any account that fails the equality** or whose row status is not
   terminal. A nonzero account without a sealed lock, or with a settlement
   already sealed that the first pass missed, means the census is stale —
   abort, do not edit around it.
5. **Never hardcode amounts.** Each leg's `value` is the live custody
   balance at fire time; the table in §0 is a snapshot for sanity-checking
   only. If a re-run census differs from §0, the re-run wins.
6. Confirm for each account: the lock is sealed (its `block_height`
   resolves), the provider comes from that sealed lock's payload (never
   from the escrow row, never from memory), and no `ESCROW_RELEASE`/
   `ESCROW_REFUND`/pending mempool tx names the job already.

Also verify before anything is signed: head ≥ 35400 **and sealing
normally** (§5 ordering), proposer mempool empty of settlement txs
(`GET /rpc/mempool?chain_id=ait-hub.aitbc.bubuit.net`), authority nonce ==
expected serial (snapshot: 23 — a gap means a foreign authority tx exists;
STOP), and `aitbc_escrow_unlanded_settlements == 0` on all five hosts
(`/var/lib/prometheus/node-exporter/aitbc_escrow_settlements.prom`,
written minutely by `aitbc-escrow-settlements.timer` /
`scripts/monitoring/escrow-settlements-textfile.py`).

## 2. Signing helper — the 4-Oct v2-repair shape, recreated per run

One self-contained `/tmp` helper, rewritten from this spec for every run —
never committed, never persisted, deleted after the run along with any
artifacts it touched. It is **not** a general-purpose RPC submitter: it
builds exactly the authority-signed settlement transaction below and
nothing else.

- **Key**: source `/etc/aitbc/aitbc-blockchain-rpc-override.env` for
  `ESCROW_RELEASE_PRIVATE_KEY` (`set -a; . <file>; set +a`). The key never
  leaves that file — do not echo, print, log, or copy it; the helper reads
  it from the environment.
- **Self-verify before signing anything**: derive the address from the key
  and require it == `0x03DF9Ed3788E5BA3991e6788036f9D171f027716` (the
  on-chain `escrow_settlement_authority` parameter, applied @30564).
  Refuse to run otherwise.
- **Nonce**: fetched live from `GET /rpc/accounts/{authority}` immediately
  before each submission — never hardcoded, never cached across legs.
- **Submit**: `POST http://127.0.0.1:8202/rpc/transactions/market` on hub.
- **Serial, one in flight**: wait for each leg's seal (§3) before building
  the next. The 4-Oct repair ran 13 legs this way at nonces 10–22, blocks
  34061–34077.

Transaction template (same shape the v2 repair used; `to` is the custody
→ provider leg):

```json
{
  "from": "0x03DF9Ed3788E5BA3991e6788036f9D171f027716",
  "to":   "<provider from the sealed lock payload>",
  "amount": <custody balance at fire time>,
  "fee": "max(36, amount//100)",
  "nonce": <live authority nonce>,
  "type": "ESCROW_RELEASE",
  "chain_id": "ait-hub.aitbc.bubuit.net",
  "payload": {
    "action": "escrow_release",
    "job_id": "<job>",
    "contract_id": "escrow_" + sha256("buyer:provider:job_id")[:16],
    "buyer_escrow_addr": "<lock tx sender>",
    "provider_escrow_addr": "<provider from lock payload>"
  }
}
```

Apply-time enforces the pins (`state/state_transition.py`, the
`ESCROW_RELEASE` branch): the sealed `ESCROW_LOCK` for `job_id` must exist
(tx lookup — a row-less job is fine, both canaries qualify); `to` must
equal the lock payload's `provider` (`_escrow_beneficiary`); the sender
must equal `escrow_settlement_authority`; custody balance must cover
`value`; the authority pays only `fee`. A leg naming the wrong provider is
refused at apply — there is no way to "aim" a residue leg elsewhere.

## 3. Verification — per leg and at batch end

Per leg, before building the next:

```bash
sqlite3 -readonly $DB "SELECT block_height,sender,recipient,value,fee,type \
  FROM \"transaction\" WHERE tx_hash='<submitted hash>';"
# expect: sender=authority, recipient=lock's provider, value=the account's
# residue, fee=max(36,value//100), one row, recent height
sqlite3 -readonly $DB "SELECT balance FROM account WHERE address='<custody>';"
# expect: 0
sqlite3 -readonly $DB "SELECT balance,nonce FROM account \
  WHERE address='0x03DF9Ed3788E5BA3991e6788036f9D171f027716';"
# expect: nonce +1, balance −fee only
```

At batch end:

- every targeted custody account reads balance `0` — re-run the §1 census
  and expect zero nonzero residue accounts;
- provider balances rose by exactly the released amounts
  (`0x4A5b3bf9…B5D2` +Σ of its legs; `0x02B8F2C6…4c5B` +1,800 if both
  canaries ran);
- `aitbc_escrow_unlanded_settlements` is still `0` on all five hosts (the
  residue legs add sealed txs without touching escrow rows — the detector
  checks stored claim hashes, which are unchanged);
- every submitted hash is sealed exactly once — no duplicate leg exists
  (`SELECT COUNT(*)` by tx_hash and by `instr(payload, job_id)`);
- heads agree fleet-wide (`/rpc/head` on all five) and the authority nonce
  advanced by exactly the number of legs submitted;
- mempool is empty of settlement types afterward.

The escrow rows keep `released` with their original `released_amount` —
the residue leg is intentionally invisible to the rows (same bookkeeping
position as a fee sweep). No row heal is required for correctness; if the
operator wants `released_amount` to reflect total paid-out, that is a
cosmetic per-host UPDATE, a separate decision.

## 4. Rollback and abort rules

**A sealed release cannot be undone.** There is no rollback path for a
sealed `ESCROW_RELEASE` — the block-2409 double-pay is still on the ledger.
A later compensating transaction is new money, not a rollback.

Abort **before signing anything** when:

- the §1 equality fails for the batch as a whole (re-run census disagrees
  with itself or with reality);
- an account's provider cannot be proven from its sealed lock;
- the helper's key→address self-check fails;
- head < 35400, v11 activation cannot be verified, or blocks are not
  sealing normally;
- any settlement tx is in flight (mempool or an unsealed submission) or a
  sealed settlement for a target job appears between census and fire;
- the authority nonce is occupied or moved unexpectedly (a foreign
  authority-signed tx exists);
- head, a lock's sealed status, or any target balance changed during
  preflight;
- `aitbc_escrow_unlanded_settlements > 0` anywhere, or the textfile is
  stale on any host (detector not running ≠ detector clean).

During the batch:

- one account fails its precheck → **skip that account**, record why,
  continue only if the failure is provably account-local;
- a leg fails to seal within ~10 blocks → **stop the whole batch**: a
  still-pending tx can seal later and a same-nonce resubmit is how double
  payments happen; check the proposer mempool, determine whether the hash
  is pending or evicted, and do not resubmit without operator go;
- a nonce skips between legs → stop; determine which foreign transaction
  owns it before continuing.

## 5. Scheduling and nonce collision

- The batch signs with **the same authority key the settlement path
  uses** — `ESCROW_RELEASE_PRIVATE_KEY` in
  `/etc/aitbc/aitbc-blockchain-rpc-override.env`, which the rpc service's
  `/rpc/escrow/{job}/release` and `/rpc/transactions/market` routes also
  sign with. Anything that drives those routes — the market service's
  settlement sweeps on hub, a manual release call — draws from the same
  nonce sequence as this batch.
- **v11 ordering**: `STATE_TRANSITION_V11_HEIGHT=35400` is set fleet-wide;
  at snapshot head was 35284 (~116 blocks ≈ ~2h before activation, in line
  with the ~09:35 CEST estimate). **The batch must not run until height
  35400 has passed and been independently verified sealing normally** —
  not because Option A needs v11 (it runs under current consensus) but
  because the operator's sequencing decision keeps the batch clear of the
  consensus-boundary window and of any first-sweep activity.
- Serialize the legs; read the nonce live for each.
- **Nonce collision mechanics**: two signed txs sharing one nonce compete
  — at most one seals; the loser is dropped or stranded in a follower
  mempool and may seal *later* at the wrong moment (the 2409 double-pay
  was exactly a same-nonce duplicate landing late). If the batch and a
  live settlement collide: do not submit a competing tx, stop the batch,
  determine which transaction owns the contested nonce and whether it
  sealed, and resume only after the in-flight settlement resolves and the
  next expected nonce is confirmed. A collision that seals both copies is
  the duplicate-payment / unrecoverable-overpay case — that is why the
  nonce is read live and the run is serial.

## 6. Option A vs `ESCROW_FEE_SWEEP` — the post-v11 alternative

`ESCROW_FEE_SWEEP` (shipped in v0.25.9, gated by
`state_transition_v11_height`, env `STATE_TRANSITION_V11_HEIGHT=35400`)
lets the same authority sweep a settled custody account's residue to the
governed fee recipient instead of the provider. Payload needs only
`job_id`; custody is derived; `to` must equal the resolved
`escrow_fee_recipient`; value bounded by custody balance; authority pays
only the fee.

**State as verified (head 35284):** `STATE_TRANSITION_V11_HEIGHT` and
`ESCROW_FEE_RECIPIENT=0x716a56468DD4A11A91116920F9E8892BbDD7b1B8` (the
treasury — currently has no account row; first credit creates it) are set
in `/etc/aitbc/blockchain.env` on **all five** hosts. **But the on-chain
`escrow_fee_recipient` chain parameter is not set** — and at apply height
the resolver consults chain parameters only (the env is the
`block_height=None` bootstrap), so a sweep submitted today would be
refused even after 35400 until a governance execute sets the parameter.
"Fee sweep enabled" today means configured, not executable.

| | Option A — provider payout | Treasury sweep |
|---|---|---|
| legs | one `ESCROW_RELEASE` per account | one `ESCROW_FEE_SWEEP` per account |
| money to | provider named in the sealed lock | treasury `0x716a5646…b1B8` |
| consensus | works today (v3+ rules) | v11 + on-chain `escrow_fee_recipient` param |
| semantics | pays the owed counterparty — what escrow settlement means | redirects residue to protocol revenue |
| nonce/fleet | authority nonce, serial | authority nonce, serial — identical discipline |

History context for the choice: 11 of the 12 row-backed providers released
to `0x4A5b3bf9…` — node2's default wallet, an operator-owned address — and
the two canary legs name `0x02B8F2C6…`, the hub proposer wallet (also
operator-owned). So under Option A **all ~2.36M lands in operator wallets
either way**; the difference is bookkeeping honesty, not custody — Option A
records the residue as paid to the providers the locks name, a sweep
records it as treasury revenue.

**Recommendation: run Option A** — it needs no new consensus surface, no
governance step, works under the rules already proven by the 4-Oct repair,
and settles the residue to the parties the sealed locks actually name. The
sweep remains the right tool for *future* residue once its fee recipient
is governed on-chain — and for the 6 zero-balance open tx-only locks it is
a non-question either way. The decision stays the operator's; this runbook
executes whichever is named.
