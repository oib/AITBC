# v17 activation runbook — `STATE_TRANSITION_V17_HEIGHT` (DRAFT)

> **Status: DRAFT — awaiting operator approval.** This playbook describes
> how the v17 pin would be armed; it authorizes nothing. The height `<H>`
> and the go/no-go are operator decisions.
>
> **Fleet status (2026-10-28, per Coder A): armed.** The pin is set —
> `STATE_TRANSITION_V17_HEIGHT=8900` in `blockchain.env` on all five
> hosts, confirmed in every running node's process environment; the
> restart wave completed with no seal gaps (order: node0 → hub1 → node1
> → node2 → hub). Activation expected at block 8900 — §4's post-checks
> apply then. The remainder of this document stays the reference for
> what the arming does and what the failure modes mean. Modelled on
> [v14-activation-runbook.md](v14-activation-runbook.md); read the
> mechanism first:
> [v17 resolution](../design/v9-unsigned-protocol-transfers.md#v17-resolution)
> (implementation `7f88f7381`).

Fleet: node0, node1, node2, hub1, hub — chain `bc-2`, RPC on
`127.0.0.1:8202`, chain DB at `/var/lib/aitbc/data/bc-2/chain.db` on every
host. Validators: hub, node1, node2, hub1 (attestation quorum
`MULTI_VALIDATOR_MIN_ATTESTATIONS=2`).

## 1. What activates at `<H>`

`get_block_version_for_height` checks v17 first; a block at height ≥ `<H>`
resolves to version 17 (`state/state_transition.py`). At v17 the v9
signature rule additionally admits unsigned protocol transfers carrying a
well-formed `payload.auth` — `STAKE_LOCK`, `STAKE_RELEASE`,
`BOUNTY_LOCK`, `BOUNTY_PAYOUT`, `BOUNTY_REFUND`
(`state/v9_policy.py:V17_PAYLOAD_AUTH_TX_TYPES` +
`payload_auth_shape`). The auth is re-verified for binding at apply in
both the sequential and pure/parallel paths and at remote attestation.
HTLC emissions and unsigned `AUTO_STAKE` carry no auth and stay rejected
— exactly as at v9.

Also at v17: the retired staking / agent-staking / bounty RPC handlers
are live again. They are gated by `protocol_transfers_active`
(`rpc/` surfaces call `raise_for_unarmed` → HTTP 410 while
`get_block_version_for_height(head+1) < 17`). The gate flips when the
head reaches **`<H>` − 1** — a transfer accepted then seals in the v17
block at `<H>`.

The pin itself: `state_transition_v17_height` in
`apps/blockchain-node/src/aitbc_chain/config.py` defaults to `None`
(unarmed). It is env-set as `STATE_TRANSITION_V17_HEIGHT` on every host —
unlike v4–v14 it is **not** a code-pinned literal yet (see §5).

## 2. Pre-checks (before setting anything)

All read-only:

- [ ] Every host on the same checkout at/after `7f88f7381`:
      `ssh $h 'cd /opt/aitbc && git rev-parse HEAD && git status --porcelain'`
- [ ] Pin currently unset everywhere — `fleet-config-check.sh`'s env-diff
      section lists `STATE_TRANSITION_V17_HEIGHT` and must show `<unset>`
      ×5; the effective-heights section must show `V17=None` ×5.
- [ ] Fleet green: heads equal and advancing, attestations fresh
      (≥2 per block), no `ChainDiverged`/`ServiceDown`/
      `AttestationValidatorSilent` firing.
- [ ] `<H>` chosen with headroom: head + margin for the full serial
      restart wave (§3) plus slack — the wave must be complete before
      any host produces at `<H>`.
- [ ] Operator go recorded (height + window).

## 3. Set + restart wave

Identical value, every host, before any restart:

1. Set `STATE_TRANSITION_V17_HEIGHT=<H>` in the env file(s) the node unit
   reads (`systemctl show -p EnvironmentFiles aitbc-blockchain-node` —
   typically `/etc/aitbc/blockchain.env`; the RPC unit shares the chain's
   env names on bc-2, so the same file arms it).
2. Verify the file value on all five before touching a service:
   `STATE_TRANSITION_V17_HEIGHT` identical ×5 via the drift check's env
   section.
3. Serial restart, one host at a time — the v14 wave order works:
   **node2 → hub1 → node1 → node0 → hub** — restarting
   `aitbc-blockchain-node` **and** `aitbc-blockchain-rpc` on each (the
   revived RPC gate is evaluated in the RPC process; an unrestarted RPC
   unit keeps 410-ing after `<H>`).
   - Per host: confirm service up + head advancing + attestations
     flowing before the next host. Never two validators in one window.
4. After the wave: the drift check's env-diff line for
   `STATE_TRANSITION_V17_HEIGHT` is `<H>` ×5 and its process-env section
   shows `V17=<H>(env)` ×5.

**Known wrinkle:** the drift checker's "effective transition heights"
section flags env presence for v4+ as "code-pinned; env shadows the pin"
— that rule predates the v15/v16/v17 env-pinned activation pattern. The
`V17=<H>(env)` FLAG lines during the armed window are **expected**; what
matters is that the value is identical fleet-wide (the `FAIL: effective
transition heights differ` line must NOT appear). Resolution: once v17
is proven live, commit the literal into `config.py` (as v13/v14 did via
`SHARED_ACTIVATION_HEIGHT`) and drop the env pins — a follow-up task,
not this runbook.

## 4. Post-checks (at/after `<H>`)

- [ ] **Version stamp:** `curl -s 127.0.0.1:8202/rpc/blocks/<H>` on all
      five → `state_transition_version: 17`, same block hash ×5; `<H>`−1
      stamps 14 (or the pre-H version). Every later block stamps 17.
- [ ] **No stamp-mismatch drift:** `block_version_stamp_mismatch_total`
      does not move on any host past baseline — an increment means some
      host resolved a different version for a sealed block (pin drift —
      §5(d)).
- [ ] **Revived RPCs live:** `POST /rpc/staking/stake` returns **410**
      while unarmed, then anything-but-410 (401/422/400) once the head
      reaches `<H>`−1 — 410 specifically is the retirement gate. Same
      probe applies to the agent-staking (`stake`, `top-up`, `unbond`,
      `complete`) and bounty (`deploy`, `verify`, `expire`) surfaces.
- [ ] **Attestation health:** attestations ≥ quorum per block; no
      `AttestationValidatorSilent`. An attester missing the pin resolves
      v9 rules for post-`<H>` heights and refuses to attest blocks
      carrying revived transfers — watch for it.
- [ ] **v9 shadow counters:** `v9_would_reject_*` may legitimately bump
      when a revived transfer seals — the shadow still pins what *v9*
      would have done. That is the historical record working, not a
      fault.
- [ ] First revived emission (optional smoke): a real
      `queue_protocol_transfer`-emitted auth tx (bounty payout, stake
      release) sealing under v17 is the live proof of the revival —
      record its tx hash + height if one occurs in the window.

## 5. Failure modes

### (a) Heads stop on ALL hosts

Capture first-rejected block + journals per host; deliberate halt is
already the state — preserve evidence, do not restart to "unstick".
(Same posture as v14 §3a.)

### (b) ONE host diverges/stops at `<H>`

Checks: its `STATE_TRANSITION_V17_HEIGHT` (file + `/proc/<pid>/environ`),
`git rev-parse HEAD`, `block_version_stamp_mismatch_total`, journal for
rejection lines. Most likely: missing/wrong pin or stale code. A single
host that resolved v9 rules for a block containing a revived transfer
applies different deltas than the fleet — treat as a straggler, capture,
do not "fix" the four to match it.

### (c) Unpinned proposer stamps a pre-17 version past `<H>`

The stamp is advisory (≥v8: the height-derived version applies), but the
proposer *resolves its own version when building the block* — a proposer
missing the pin builds a `<17` block, drops revived transfers from its
mempool view, and its aux/state roots are computed under the wrong rules
for that height. Symptom: a sealed block at ≥`<H>` stamped <17. Capture
the header; fix the host's pin; the chain is not at fault.

### (d) Revived RPC still 410 after head ≥ `<H>`−1

The RPC unit was not restarted (process env predates the pin) — restart
`aitbc-blockchain-rpc` on that host. Not a consensus event.

### (e) Attestation refusals on blocks carrying revived transfers

An attester missing the pin verdicts `missing_signature` on auth-bearing
txs and refuses the whole block. With quorum 2 of 4 validators the chain
still seals while ≤2 attesters are unpinned — but the margin is gone:
complete the wave before `<H>`.

### (f) Pin drift discovered mid-wave

Stop the wave immediately (before the next validator), restore the
file value to `<H>` on the drifted host, restart that host alone.
A host that reaches `<H>` unpinned will diverge the moment a revived
transfer seals — the drift check exists to catch exactly this; run it
before resuming.

## 6. Rollback — what can and cannot be undone

- **Before `<H>`:** unset `STATE_TRANSITION_V17_HEIGHT` (or raise `<H>`)
  on all five + the same serial restart wave. Nothing has activated.
- **After `<H>`:** sealed blocks stay sealed — and the pin is
  **permanent**. Removing it makes a host resolve `<17` when replaying
  history that contains revived transfers: it would apply v9 rules to
  blocks the fleet applied at v17 and diverge on replay. There is no
  post-`<H>` config brake; a sealed v17 block is history like any other
  activation rung.

## 7. Operator sign-off

- [ ] `<H>` chosen and recorded
- [ ] All five env files carry the identical pin; wave order agreed
- [ ] Pre-checks green (same checkout ×5, pin unset ×5, fleet healthy)
- [ ] **Decision: APPROVED / NOT APPROVED**

    Operator: ______________  Date: __________  Notes: ______________
