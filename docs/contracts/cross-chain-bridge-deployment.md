# CrossChainBridge deployment runbook (BR-1)

The deployed `CrossChainBridge` is owned by a deployer key that was lost in
August 2026. It holds nothing and is marked deprecated in
`contracts/deployments-bridge-sepolia.json`. Its replacement must never repeat
that failure mode: the deployer key is disposable, ownership moves to the
2-of-3 Safe **in the same script run**, and the contract starts paused until
the Safe configures it.

## Preconditions

| item | source | notes |
|---|---|---|
| Deployer key | freshly generated, funded with ~0.05 ETH | disposable; never a Safe signer, never reused |
| `BRIDGE_OWNER_SAFE` | operator (O-8 signers) | the 2-of-3 Safe address; the script refuses without it |
| `BRIDGE_FEE_RECIPIENT` | operator | where bridge fees accrue; must **not** be the deployer |
| Network env | operator | `PRIVATE_KEY` + `ETH_RPC_URL`/Infura/Alchemy for the target network |
| Contract tests green | agent | `cd contracts && forge test` — 302 tests, incl. the Safe-ownership suite |

## Dry run (local chain only)

No real key, no network RPC — Hardhat's in-process chain funds its own
throwaway accounts:

```bash
cd contracts
npx hardhat accounts --network hardhat   # pick two throwaway addresses
BRIDGE_OWNER_SAFE=<account-1> BRIDGE_FEE_RECIPIENT=<account-2> \
  npx hardhat run scripts/deploy-bridge.js --network hardhat
```

The script asserts post-deploy state before recording anything:

- `owner()` is the Safe address — not the deployer;
- `paused()` is `true` — the bridge starts paused;
- `chainValidators(1)` is empty — validators/tokens exist only after the Safe
  sets them;
- a `deployments-bridge-<network>.json` record is written (owner, fee
  recipient, `pausedAtDeploy`, tx hash). For a local dry run the file is a
  throwaway artifact — delete it afterwards; it is not a deployment.

## Real deployment (operator, gated on O-8 signers)

1. Generate a fresh deployer key; fund it with ~0.05 ETH on the target network.
2. Confirm `BRIDGE_OWNER_SAFE` and `BRIDGE_FEE_RECIPIENT` with the operator —
   verify the Safe address on-chain (it must be a deployed Safe contract,
   `getThreshold() == 2`, `getOwners()` returns the three named signers).
3. Run the same command with `--network sepolia` (or the target network).
   The script pauses, hands over ownership and asserts the end state.
4. **Post-deploy checks** (read-only):
   - `owner()` reads back as the Safe;
   - a small deposit→withdraw round trip under the lock cap, driven through
     the Safe;
   - contract source verified on the block explorer;
   - address recorded in `contracts/deployments-bridge-<network>.json`
     (already written by the script — commit it) and `BRIDGE_CONTRACT_ADDRESS`
     set in the bridge env files;
   - `aitbc exchange bridge-status` green after the exchange restart
     (operator restart authority).
5. Destroy the deployer key material — it owns nothing after the handover.

## What the script deliberately refuses

- Missing or malformed `BRIDGE_OWNER_SAFE` / `BRIDGE_FEE_RECIPIENT` — fail fast
  rather than deploy an ownerless-configured bridge.
- `BRIDGE_FEE_RECIPIENT == deployer` — fees would accrue to a key that is
  thrown away.
- Any post-deploy assertion failing — the deployment is recorded only after
  the state reads back correctly; a failure leaves the contract deployed but
  unrecorded, which must be investigated rather than re-run blindly (a second
  run deploys a second contract — the Safe simply owns the first one as well).

## Pre-flight checks (ETH-3 lessons — apply to every Safe execution)

The Sepolia rehearsal found three failure modes, all fixed in the tooling
(`contracts/scripts/rehearsal/`). They are operator-day checks, not optional:

1. **Pin the Safe nonce to the expected value and refuse on timeout.**
   Track the expected nonce from your own sealed execs (the driver does
   this as `nextSafeNonce`) and pass it explicitly — `signAndExecute`
   in `contracts/scripts/rehearsal/lib.js` takes `expectedNonce`, polls
   `getNonce()` for it (`noncePollAttempts = 20` at `noncePollIntervalMs =
   1500`), and throws rather than sign if the replica never reports it.
   The pinned nonce goes into the Safe transaction as `options.nonce`, so
   a stale replica can only stall the run, never produce a `GS026`
   signature set. Never sign against an unchecked read — ETH-3's `GS026`
   was exactly a lagging replica answering with the previous nonce.
2. **Bound every `eth_getLogs` scan.** Public RPCs cap the range and prune
   history; scan in bounded windows from a known head, and use an archive
   endpoint for anything old. An unbounded scan silently returns partial
   or empty results.
3. **Read post-transaction state pinned to the receipt block, and poll
   for it.** A `latest`-block read immediately after `sendTransaction`
   can hit a node that has not indexed the block. The tooling reads with
   `blockTag` pinned to the sealed receipt's block (ETH-3d) and retries
   until the replica reports that block — `pollRead` in `lib.js`
   (`attempts = 20`, `intervalMs = 1500`). Assert on
   `receipt.status`/logs first, then read back.

## Configuration preflight

`scripts/ops/bridge_mainnet_preflight.py` checks the seven env knobs
(network name, resolved Chainlink feed, confirmation depth, AIT price
pins, staleness gate, payout cap) in two profiles:

- `--profile sepolia` — proves the *live testnet* configuration is
  coherent. Runnable today; should report PASS on the current fleet env.
- `--profile mainnet` (default) — on the current Sepolia configuration
  **every knob fails by design** (`ETH_NETWORK=sepolia`, the price pins
  are set, `BRIDGE_CONFIRMATIONS` resolves to 3 < 12, the staleness gate
  is unset or too loose). The script must go green on staged mainnet env
  files *before* any deployment — it is the same check the day-of run
  will repeat.

## Gap list — rehearsal bridge vs a mainnet bridge

| surface | current design | rehearsal evidence | missing / undecided |
|---|---|---|---|
| Constructor & fee recipient | `constructor(address _feeRecipient)` only; script refuses deployer-as-recipient and asserts owner=Safe, paused, no validators/tokens | Local dry run + BR-9 Sepolia deploy + ETH-3 | Mainnet fee recipient undecided (operator) |
| Validator set | `addValidator`/`removeValidator` are `onlyOwner` → Safe-managed flat list; `weight` is stored but each confirmation counts 1; per-chain `chainValidators` is a separate list | ETH-3 exercised owner calls through the Safe | Mainnet validator list undecided; BR-2/BR-3's chain-held validator set is **not** what this contract does — a param-driven set is a contract change |
| Confirmation binding | `confirmBridge` counts each confirmer and lets each overwrite `request.lockTxHash` — threshold can be reached on *different* lock hashes (defect 3 below) | Read on `origin/main`, untested | Honest-validator assumption; fix is an audit decision |
| Supported tokens | None at deploy; Safe calls `addSupportedToken` (bridgeLimit, feePercentage ≤ MAX_FEE 5%, whitelist flag) | Post-deploy assert probes `supportedTokens(Safe)` | Token list + per-token `bridgeLimit` undecided (operator) |
| Lock cap | Per-token `bridgeLimit` via `withinBridgeLimit`; `MAX_BRIDGE_AMOUNT` (1M) is declared but **never enforced** — see defects below | n/a | Cap values undecided; dead constant reported |
| Pause / emergencyWithdraw | `pause`/`unpause`/`emergencyPause`/`emergencyWithdraw` all `onlyOwner` → Safe; emergencyWithdraw sweeps to `owner()` (the Safe) | ETH-3 ran both end-to-end through the Safe on Sepolia | Mainnet pause drill not scheduled |
| Confirmations / finality | Contract: `minConfirmations` per chain (default 3; mainnet chain seeded at 12) counts *validator* confirms. Monitor: `BRIDGE_CONFIRMATIONS` env ≥12 mainnet (preflight knob) | ETH-3 ran the 3-confirmation path | Block-finality policy on mainnet undecided (operator) |
| Owner / signer hygiene | Deployer disposable and unfunded-after; Safe 2-of-3 owns everything; rehearsal keys lived in a keys dir, never on a node | BR-9/BR-11 + ETH-3 | Mainnet signers unnamed; hardware-key requirement undecided (operator) |
| Upgrade story | **None.** The contract is immutable — no proxy. A defect means redeploy + Safe re-point + operator env work | — | Accepted risk or audit decision (operator) |
| Monitoring before funds | authority-balance exporter + `AuthorityFloat*`/`BridgeAuthorityAccountMoved`/`SellEscrowFloat*` (SD-5), bridge-monitor stuck-payout/queue/low-float alerts, preflight script | Rules exist and are promtool-tested | `sell_escrow` watch needs its `AITBC_WATCH_ACCOUNTS` entry (operator env); validator-liveness monitor does not exist |
| Seeded chain | Constructor seeds `supportedChains[1]` active with `minConfirmations=12` and no bridge contract | Deploy script asserts validators/tokens empty; the seeded chain is by design | On a Sepolia deploy the seeded id is still `1` — harmless config data, noted |

## Go/no-go table

| # | precondition | owner | status | evidence needed |
|---|---|---|---|---|
| 1 | Mainnet decision | **operator only** | parked (12 Oct) | the operator's word |
| 2 | Three named signers + 2-of-3 Safe on mainnet | **operator only** | not started | Safe deployed, `getThreshold()==2`, owners = named signers |
| 3 | Disposable deployer funded (~0.05 ETH mainnet) | **operator only** | not started | funding tx; key never lands on a node |
| 4 | Audit decision (audit vs accepted risk) | **operator only** | undecided | audit report or signed acceptance |
| 5 | Deploy script: paused + Safe-owned + refuse-bad-env | repo | **done** (`4fac4085ef`) | this doc's asserts |
| 6 | Contract suites green on the deploy commit | repo | re-run this task | forge + hardhat counts below |
| 7 | Preflight `mainnet` profile green on staged env | repo + operator | fails by design today | `bridge_mainnet_preflight.py` PASS on staging envs |
| 8 | Fee recipient, token list, validator list, caps | **operator only** | undecided | values in the day-of checklist |
| 9 | Monitoring before funds: exporter + rules live, incl. `sell_escrow` watch | repo + operator | rules shipped (SD-5), env entry pending | `aitbc_authority_*` series for all roles |
| 10 | Validator-liveness monitor | repo | **missing** | new monitor or accepted gap |
| 11 | BR-2/BR-3 chain-held validator set | repo | **not in this contract** | contract change or accepted design |
| 12 | Pause drill on the real deployment | operator | not scheduled | executed pause/unpause through the Safe |

### Known defects (reported, not fixed here)

- `CrossChainBridge.sol:27` — `MAX_BRIDGE_AMOUNT` (1M tokens) is declared
  but never enforced: `initiateBridge` (line ~164) checks only the
  per-token `bridgeLimit`. Proposed fix (not applied): either add
  `require(amount <= MAX_BRIDGE_AMOUNT)` beside the per-token cap, or
  delete the constant. Decide with the audit question.
- `validators[].weight` is stored but never used in confirmation
  counting (`confirmBridge` line ~259 increments by 1) — weighted
  validators are a contract change if mainnet wants them.
- `confirmBridge` (lines ~258–260): every confirmer counts toward the
  threshold AND overwrites `request.lockTxHash` with the hash *they*
  signed — nothing checks that confirmers agree on the same lock hash.
  Each signature is bound to `(requestId, lockTxHash, chainid)`, so each
  validator is bound to the hash it chose, but the validators are not
  bound to each other: the 2-of-3 threshold can be reached on two
  different lock hashes, with the last confirmer's value winning the
  stored field. This relies on validators being honest and agreeing.
  Proposed fix (not applied — audit decision): require the supplied
  `lockTxHash` to equal the first confirmation's stored value
  (`request.confirmations == 0 || request.lockTxHash == lockTxHash`),
  or track confirmations per hash.

## Recovery notes

- If `transferOwnership` ran but the record write failed, re-run the read-back
  checks manually (`owner()`, `paused()`, `chainValidators(1)`) and append the
  deployment entry by hand.
- A deployed-but-misconfigured bridge is harmless while paused: it holds no
  funds and the Safe can still configure it or, worst case, a redeploy costs
  only gas.
