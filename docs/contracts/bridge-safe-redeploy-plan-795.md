# CrossChainBridge Safe redeploy plan — #795 planning gate

**Status: DRAFT for operator review. No execution authorized by this document.**
Any contract deployment, Safe execution, or env change requires the operator's
explicit go on the day-of checklist below.

## Why a redeploy is needed

The live Sepolia deployment `0xFBAF71e0Cfb4f691ffFa5c0c54428abD841E7076`
(SEPOLIA-REDEPLOY-1, 2026-10-21) predates two verified contract fixes:

- `503e08e53` — owner-set `requiredConfirmations` clamped to the live
  validator set (replaces constant quorum 3 + dead per-chain
  `minConfirmations`), and the CONFIRMED-expiry exit in `cancelBridge`.
- `d215d1a8c` — `confirmBridge` lockTxHash agreement, `MAX_BRIDGE_AMOUNT`
  enforcement, fee-forfeit pin.

The contract is **immutable** (no proxy) — the only way to carry the fixes
is a new deployment. Facts 1+2 of the #795 audit go live with this redeploy.

## Current state — why now is the cheap window

- SEPOLIA-REDEPLOY-1 is **still paused**: `unpause()` is staged at Safe nonce
  20 and held for the operator's F5 line. `requestCounter = 0` — it has never
  processed a bridge request.
- Because nothing is in flight, a redeploy carries **zero stranded-request
  risk**. Once unpaused, the old contract's CONFIRMED requests could never
  exit (the very defect being fixed) — so redeploying *before* unpause is
  strictly safer than unpause-then-replace.
- Recommendation: **SEPOLIA-REDEPLOY-2 on current `main` bytecode, before
  the F5 unpause**. The mainnet deployment (go/no-go table row 1, still
  parked) will deploy from the same fixed source and inherits everything —
  this plan is the rehearsal for that day-of run too.

## Preconditions (gate checklist)

| # | item | owner |
|---|---|---|
| 1 | Contract suites green on the deploy commit — `cd contracts && forge test` + `npx hardhat test` | agent (re-run at deploy commit) |
| 2 | Safe `0xdd32618fa14eeeC4731882C958Ac80b194EA5aC7` verified: threshold 2, three named signers | operator |
| 3 | Disposable deployer key generated + funded (~0.05 Sepolia ETH); never a Safe signer | operator |
| 4 | `BRIDGE_FEE_RECIPIENT` confirmed — same as REDEPLOY-1 (`0x5f659B…`) unless operator changes it | operator |
| 5 | Validator set for the new contract — default: reuse the three REDEPLOY-1 validators; quorum `q` to be ruled (see Open questions) | operator |
| 6 | Token list — default: AIT `0x87fCf1bB…`, bridgeLimit 1M, fee 100bps, no whitelist | operator |
| 7 | `BRIDGE_CONTRACT_ADDRESS` cutover plan acknowledged (hub env + bridge-monitor restart) | operator |

## Redeploy order

1. **Pre-flight reads** (read-only): confirm `0xFBAF…` still `paused()` and
   `requestCounter == 0`; confirm no other env points at it.
2. **Deploy** via `contracts/scripts/deploy-bridge.js` (dry-run on hardhat
   first): asserts `owner()==Safe`, `paused()==true`, empty
   `chainValidators(1)`; writes `deployments-bridge-sepolia.json` entry.
3. **Safe configuration execs** (new nonce sequence — derive fresh, do NOT
   reuse the staged nonce-20 plan which targeted the old contract):
   `addValidator` ×3 → `addSupportedToken` (AIT) →
   **`setRequiredConfirmations(q)`** → `unpause()`.
   Order matters: quorum must be set before unpause so the first request
   cannot confirm under a stale default.
4. **Cutover**: update `BRIDGE_CONTRACT_ADDRESS` in
   `/etc/aitbc/aitbc-bridge-monitor.env` on hub → restart
   `aitbc-bridge-monitor` → verify config-status + ledger head.
5. **Post-deploy verification** (read-only then one live smoke):
   `owner()`/`paused()`/`validators()`/`supportedTokens()`/`requiredConfirmations()`
   read-backs pinned to receipt blocks; source verified on Sepolia explorer;
   one deposit→confirm→complete round trip through the Safe path (the
   REDEPLOY-1 rehearsal already proved this flow end-to-end).
6. **Retire old**: mark `0xFBAF…` `deprecated` in the deployments JSON with
   reason "superseded by SEPOLIA-REDEPLOY-2 before activation"; leave it
   paused forever — it holds nothing and can never be unpaused usefully.
7. Destroy deployer key material.

## Test plan

- **Pre-deploy**: full `forge test` + `npx hardhat test` on the deploy
  commit (expect ≥303 forge / ≥218 hardhat per recent runs).
- **New-path coverage already pinned**: quorum clamp
  (`setRequiredConfirmations` bounds + confirm-time re-clamp), CONFIRMED
  expiry exit, lockTxHash agreement, MAX_BRIDGE_AMOUNT cap, fee-forfeit.
- **Sepolia smoke**: the round trip above; additionally exercise
  `cancelBridge` on a PENDING request past `BRIDGE_TIMEOUT` if a cheap
  test deposit is acceptable — the CONFIRMED-expiry path needs a real
  24h `COMPLETION_TIMEOUT` wait, so its live proof is deferred to the
  first organic expiry or a deliberate test request (operator's call;
  forge pins cover the logic meanwhile).

## Risks

- **Safe nonce sequencing**: the staged nonce-20 unpause plan targeted the
  old contract — a fresh exec batch needs a re-derived nonce map; ETH-3's
  `GS026` lesson applies (pin expected nonce, never sign against an
  unchecked replica read).
- **Validator identity reuse**: same three validator EOAs on the new
  contract — fine (identities are keys, not contract-bound), but the
  relayer/monitor config must not assume the old address.
- **Cutover atomicity**: between env update and monitor restart the
  monitor reads the old (paused, empty) contract — harmless, it just sees
  zero activity; no funds at risk either way.
- **Imminent-unpause race**: if the operator's F5 line lands before this
  redeploy, the old contract activates WITH the defects — the plan's value
  is entirely in beating that window. If F5 fires first, fallback = let it
  run and schedule REDEPLOY-2 anyway (in-flight requests then need the
  drain analysis this plan currently avoids).
- **Mainnet inheritance**: mainnet deploys from `main` — verify the deploy
  commit still carries `503e08e53`+`d215d1a8c` at that time (it will,
  history is append-only).

## Rollback

- **Pre-cutover**: do nothing — old contract stays paused, env unchanged.
  A failed deploy leaves an unused paused contract; record and move on.
- **Post-cutover**: prefer forward-fix. Repointing env back to `0xFBAF…`
  restores the *defective* build — only acceptable if the new contract
  itself is broken AND no requests exist on it (`requestCounter==0`
  check). Any request on the new contract strands the same way the old
  one's CONFIRMED requests would have — hence cutover only after smoke.

## Open questions for the operator

1. **Quorum `q` for 3 validators**: `q=2` tolerates one validator drop
   (liveness) vs `q=3` maximizes collusion resistance. The clamp makes
   either safe; recommendation `q=2` matching the Safe's own 2-of-3 shape.
2. **Timing vs F5**: confirm REDEPLOY-2 lands before the staged unpause,
   or rule that F5 proceeds and REDEPLOY-2 follows with drain handling.
3. **CONFIRMED-expiry live proof**: accept forge-pin-only coverage on
   Sepolia, or schedule a deliberate 24h test request.
