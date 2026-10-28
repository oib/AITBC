# BNT-1 — protocol transfers that cannot seal at v9

**Status:** audit + options paper; no consensus code. BNT-2 (operator
decision 2026-10-12) took option 3 — the five RPC surfaces refuse up front
with HTTP 410 (the HTLC mutators raise `RetiredProtocolTransfer`) and the
handler bodies are removed outright; apply code and the replay pins below
are untouched. Pinned by strict-xfail cases in
`tests/unit/test_v9_type_coverage_replay.py`
(`test_protocol_transfer_production_shape_seals_at_v9[*]`).

## The mechanism

`aitbc_chain.protocol_escrow.queue_protocol_transfer` is the single
emitter for every protocol-escrow movement (stake, bounty, HTLC). By
design it sets **no top-level `signature`**: a protocol escrow address is
derived from a keccak label and has no private key, so a release leg can
never be sender-signed — and the emitter does not sign the lock legs
either, even though the user holds that key. Authorization travels in
`payload.auth = {signer, message, signature}` instead, which
`StateTransition.validate_transaction` re-verifies **after** the v9 rule.

`v9_signature_verdict` (`state/v9_policy.py`) requires a top-level
signature for every type except `BRIDGE_LOCK/RELEASE/REFUND`. Since
`state_transition_v9_height = 30400` every protocol transfer therefore
rejects at apply with `v9 signature rule: missing_signature`, before the
payload-auth check is ever reached. There is no mempool pre-check, so the
failure is silent until seal time: the RPC returns a tx hash, the row sits
`pending`, the proposer skips it.

## Audit table — every caller of `queue_protocol_transfer`

Sealed counts from `chain.db` (`mode=ro`, `query_only`), node2 and hub
identical, head 44701, 2026-10-12.

| caller | tx type | top-level signature at emission | `payload.auth` | sealed < 30400 | sealed ≥ 30400 | last height |
|---|---|---|---|---|---|---|
| `rpc/staking.py` stake | STAKE_LOCK | **no** | user-signed | 5 (all STAKE_LOCK) | **0** | 11073 |
| `rpc/staking.py` unstake | STAKE_RELEASE | **no** | user-signed | 4 (all STAKE_RELEASE) | **0** | 11042 |
| `rpc/agent_staking.py` stake | STAKE_LOCK | **no** | operator-signed | (in the 5) | **0** | — |
| `rpc/agent_staking.py` top-up | STAKE_LOCK | **no** | operator-signed | (in the 5) | **0** | — |
| `rpc/agent_staking.py` release | STAKE_RELEASE | **no** | none | (in the 4) | **0** | — |
| `rpc/escrow_routes.py` AUTO_STAKE | STAKE_LOCK | **no** | none | 1 (`source=auto_stake` @7306) | **0** | 7306 |
| `rpc/bounty.py` create | BOUNTY_LOCK | **no** | operator-signed | 0 | **0** | never |
| `rpc/bounty.py` verify/payout | BOUNTY_PAYOUT | **no** | operator-signed | 0 | **0** | never |
| `rpc/bounty.py` expire | BOUNTY_REFUND | **no** | operator-signed | 0 | **0** | never |
| `contracts/htlc_contract.py` lock | HTLC_LOCK | **no** | none | 0 | **0** | never |
| `contracts/htlc_contract.py` claim | HTLC_CLAIM | **no** | none | 0 | **0** | never |
| `contracts/htlc_contract.py` refund | HTLC_REFUND | **no** | none | 0 | **0** | never |

Zero unsealed (`block_height IS NULL`) rows of any of these types exist
on either host — nothing is stuck in a queue today; the features simply
have not been invoked since v9.

## Which features are dead today

- **User staking** (`/rpc/staking/stake`, `/unstake`): dead at v9 — a lock
  queues, never seals, the local `stake` row shows active with no funds
  moved. Last live use: block 11073.
- **Agent staking** (lock / top-up / release): dead, same mechanism.
- **AUTO_STAKE reinvestment** (escrow release hook): dead; silently skips.
- **Bounties** (create / payout / refund): dead; never worked under v9 and
  never sealed under any version.
- **HTLC swaps** (lock / claim / refund): dead; never sealed under any
  version.

Unaffected: all bridge types (exempt), escrow, bond (sender-signed), GPU,
governance, liquidity, receipt, transfer, message — i.e. everything that
*has* sealed under v9.

## Options

### 1. Admit `payload.auth` in the v9 signature rule (consensus change)

`v9_signature_verdict` returns `None` when the type is a protocol-transfer
type **and** `payload.auth` is present and well-formed; the existing
`_verify_payload_auth` binding check (party, amount, stake/bounty id,
chain) remains the authorization. Gated behind a new version height
(v14-style) so sealed history replays identically.

- Pros: restores every feature above except AUTO_STAKE and HTLC (they
  emit no auth); smallest code change; keeps the keyless-escrow design.
- Cons: consensus change → new version height, tag, fleet restart batch;
  AUTO_STAKE / HTLC / agent-release need an auth added at emission first
  or stay dead; "signature present" becomes "auth present" for 5 types —
  the rule gets a second shape.

### 2. Sign the envelope at emission

Lock legs: the emitter attaches the user's (or operator's) wallet
signature as the top-level `signature` — same as every other user tx.
Release legs: the sender is a keyless escrow, so a top-level signature
*cannot* recover to it; the only way is a new exemption list entry
analogous to BRIDGE_* with the authority signature verified at apply
(`bridge_signature`-style). That is option 1 in disguise for the release
legs.

- Pros: lock legs become ordinary signed txs — no consensus change for
  them; one authorization model.
- Cons: release legs still need a consensus change; the RPC layer must
  obtain a full tx signature from the user (the current request-signature
  flow signs a message, not the tx), which changes every staking/bounty
  client.

### 3. Accept the features as dead

Remove or disable the five RPC surfaces (staking, agent staking,
auto-stake, bounty, HTLC) so they refuse up front instead of returning a
tx hash that never seals; keep the apply code for historical replay.

- Pros: no consensus change; honest UX today; the chain is already in
  this state de facto.
- Cons: staking (consensus staking + agent economy) and bounties are
  product features; the `stake`/`bounty_contract` local rows written by
  the RPC before queueing already desynchronize from chain truth on every
  call.

### Recommendation (agent A, not a decision)

Option 1 for release legs + option 2 for lock legs is the coherent end
state, but that is two changes. The minimal honest step now is **option 3
for AUTO_STAKE and HTLC** (no auth emitted, no users) and **a decision on
option 1 for staking + bounty**. Whatever is chosen, the RPC handlers
should stop writing local rows before the lock seals (SD-1 lesson).

## v17 resolution — option 1 implemented (staking + bounty)

The operator chose **option 1 for staking and bounty** and **option 3 for
HTLC and AUTO_STAKE** — the split the recommendation proposed. The revival
is a new state-transition version, not a v9 amendment:

- **`STATE_TRANSITION_V17_HEIGHT`** (`config.py`) pins activation. Default
  unset = unarmed; every validator must carry the same pin
  (`fleet-config-check.sh` watches it).
- At `block_version >= 17`, `v9_signature_verdict` admits an unsigned
  `STAKE_LOCK`, `STAKE_RELEASE`, `BOUNTY_LOCK`, `BOUNTY_PAYOUT`, or
  `BOUNTY_REFUND` only when `payload.auth` has the well-formed shape
  (`V17_PAYLOAD_AUTH_TX_TYPES` + `payload_auth_shape` in `v9_policy.py`).
  Unsigned HTLC and AUTO_STAKE emissions carry no auth and stay rejected
  at every version.
- `StateTransition._verify_payload_auth` then re-verifies the evidence
  cryptographically at apply — signature over the canonical message plus
  `_payload_auth_binds_transfer` field binding (party, amount, stake /
  bounty / submission ids, chain, action) — in **both** the sequential
  `apply_transaction` path and the pure/parallel `compute_state_delta`
  path (STAKE_LOCK and all three bounty types route through the pure
  path; only STAKE_RELEASE is sequential-only).
- Remote attestation performs the identical checks before signing —
  an attester never attests a block its own apply would reject.
- Orphan requeue (`block_deltas._admit_orphan`) re-admits an unsigned
  auth-bearing protocol transfer after fork healing once the auth still
  verifies — the same "proved itself in a block" carve-out bridge credits
  already had.
- The retired RPC handlers (consensus staking, agent staking, bounty)
  are restored and refuse with HTTP 410 while
  `protocol_transfers_active(session, chain_id)` is false — i.e. until
  the *next* block height resolves v17. No transfer is queued that
  cannot seal.
- Public transaction submission still requires a top-level signature;
  `queue_protocol_transfer` remains the only source of unsigned
  protocol transfers.
- v9–v16 replay is unchanged: the strict-xfail production-shape pins in
  `test_v9_type_coverage_replay.py` explicitly replay *at* v9 and keep
  failing there by design; a parallel `test_v17_*` section replays the
  same fixtures at v17 and seals the seven auth-bearing emissions.

## Verifying

```bash
venv/bin/python -m pytest tests/unit/test_v9_type_coverage_replay.py -k protocol_transfer
# 11 xfailed (production shape, pinned AT v9) + v17 section: 7 auth-bearing
# emissions seal deterministically, 4 no-auth emissions stay rejected
venv/bin/python -m pytest apps/blockchain-node/tests/test_v9_signature_rules.py
# 63 passed — includes TestV17PayloadAuth / TestV17Attester / TestV17Policy
```

## Related

- [escrow-anomaly-remedies.md](escrow-anomaly-remedies.md) — SD-6 options
  paper for the two concrete anomalies this audit surfaced (the
  …46025c0e double release and the stranded auto-stake principal).
