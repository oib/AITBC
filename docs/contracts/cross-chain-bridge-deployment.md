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

## Recovery notes

- If `transferOwnership` ran but the record write failed, re-run the read-back
  checks manually (`owner()`, `paused()`, `chainValidators(1)`) and append the
  deployment entry by hand.
- A deployed-but-misconfigured bridge is harmless while paused: it holds no
  funds and the Safe can still configure it or, worst case, a redeploy costs
  only gas.
