# bc-2 Sepolia bridge redeploy — operator checklist

`SEPOLIA-REDEPLOY-PREP-1` (#355). Everything here is **the operator's own
action**: this document names commands, calldata shapes and verification
reads; it never holds a key, and every send is the operator's line. The
redeploy supplies the contract that `BRIDGE_CONTRACT_ADDRESS` points at
for the F5 unpause (`bc2-reset-runbook.md` §F).

Dry-run evidence (2026-10-21, node2, hardhat network at `ccfb4cda8`,
throwaway addresses — nothing touched Sepolia):

- `deploy-bridge.js --network hardhat` — deploy → pause →
  `transferOwnership(safe)` in one run; post-deploy assertions green
  (`owner == Safe`, `paused`, no seeded validator, no seeded token,
  `requestCounter == 0`); record written to a scratch path.
- `RehearsalSafe.test.js` — **7/7 passing**: the full 2-of-3 owner flow
  incl. one-signature refusal, wrong-owner-set refusal, stale Safe-nonce
  recovery (GS026), event-query chunking under an `eth_getLogs` cap,
  and `pollRead` convergence/refusal behavior.

## 0. Givens and boundaries

- The deployed units run `uvicorn aitbc_chain.app:app` for RPC and
  `aitbc_chain.main` for the node — the bridge contract lives entirely
  on the EVM side; nothing here restarts an AITBC unit (F5 owns that).
- `contracts/scripts/deploy-bridge.js` is the deploy path; it **fails
  closed** — deployer-owned or unpaused end-state is a thrown error, not
  a warning.
- `contracts/deployments-bridge-sepolia.json` is the record file. Its
  first entry (`0x2440…F6FA`) is deprecated — its deployer-owner key is
  unrecoverable; **never point deposits there** (the reason an
  offline-held Safe owns the new contract). The BR-1 entry
  (`0xfbDd3Dc5…`, Safe `0xdd32…aC7`) is the previous activation, not
  automatically the bc-2 deployment.
- Keys discipline: the deployer key is **disposable** — used once, then
  thrown away; it is never a Safe signer. `DEPLOYER_KEY_FILE` keeps it
  out of env/argv/shell history. Signer keys are the operator's custody;
  rehearsal scripts read them only from a `rehearsal-sepolia`-suffixed
  dir (`lib.js` path guard).

## 1. Order vs the operator's EVM signer rotation

Rotation is entirely the operator's action; the order matters:

1. **Operator rotates the EVM signer keys first** — the *final* signer
   addresses must exist before anything below, because they seed both
   the Safe owner set and the contract validator list.
2. **Safe exists with the rotated signers** — either the existing 2-of-3
   Safe (`0xdd32…aC7`) re-keyed via `swapOwner` execs, or a fresh Safe
   (`scripts/rehearsal/safe-create.js` for rehearsal shape). The
   deployment takes whichever Safe address the operator names via
   `BRIDGE_OWNER_SAFE`.
3. Deploy + handover (§3).
4. Safe execs: validators, token support (§4).
5. `BRIDGE_CONTRACT_ADDRESS` fleet update (§6).
6. Contract `unpause()` Safe exec — timed with F5: recommended **same
   window as F5**, flag flip last, so the bc-2 admission gate opens only
   after every EVM-side read is verified.

## 2. Pre-sign checks (before the deploy tx)

- [ ] `assertSepolia`: provider chain id is `11155111` —
      `BRIDGE_REQUIRE_CHAIN_ID=11155111` also hard-refuses a wrong-network
      deploy.
- [ ] `BRIDGE_OWNER_SAFE` is a valid address and the Safe **already
      exists**: `eth_getCode` non-empty, `getOwners()` returns exactly
      the three named signers, `getThreshold()` == 2.
- [ ] `BRIDGE_FEE_RECIPIENT` is a valid address and is **not** the
      deployer.
- [ ] `DEPLOYER_KEY_FILE` points at the disposable key file (mode 0600);
      `BRIDGE_REQUIRE_CHAIN_ID` is set — the key file is refused before
      it is opened on a wrong chain.
- [ ] `BRIDGE_DEPLOY_RECORD` points at the real record
      `contracts/deployments-bridge-sepolia.json` (default for sepolia);
      a rehearsal must override it to a scratch path.
- [ ] Deployer holds enough Sepolia ETH for deploy + pause + transferOwnership
      (~2.6 M gas for the deploy per the hardhat measurement).

## 3. Deployment transaction (one operator command)

```bash
cd /opt/aitbc/contracts && \
  DEPLOYER_KEY_FILE=<rehearsal-free path> \
  BRIDGE_OWNER_SAFE=<safe-address> \
  BRIDGE_FEE_RECIPIENT=<payout-address> \
  BRIDGE_REQUIRE_CHAIN_ID=11155111 \
  npx hardhat run scripts/deploy-bridge.js --network sepolia
```

Constructor: `CrossChainBridge(address _feeRecipient)` — the script then
`pause()`s and `transferOwnership(safe)` in the same run and **asserts**
the end-state; any deviation throws before the record is written.

## 4. Operator-signed Safe transaction list (activation)

All target the deployed `CrossChainBridge` at `<bridge-address>`; every
call is `onlyOwner` so each is a Safe exec (signers 2-of-3, executor any
signer). `<nonce>` = the Safe's next nonce at sign time.

| # | target | function signature (calldata) | args |
|---|---|---|---|
| S1 | `<bridge>` | `addValidator(address,uint256)` | `<evm-signer-1>`, `1` — Safe nonce `<n>` |
| S2 | `<bridge>` | `addValidator(address,uint256)` | `<evm-signer-2>`, `1` — Safe nonce `<n+1>` |
| S3 | `<bridge>` | `addValidator(address,uint256)` | `<evm-signer-3>`, `1` — Safe nonce `<n+2>` |
| S4 | `<bridge>` | `addSupportedToken(address,uint256,uint256,bool)` | `<aitoken-address>`, `<bridgeLimit>` (BR-1 used 1 000 000 AIT), `<feePercentage>` in bps (BR-1 used 100), `<requiresWhitelist>` (BR-1 used `false`) — Safe nonce `<n+3>` |
| S5 | `<bridge>` | `unpause()` | — Safe nonce `<n+4>` — **hold for the F5 window** |

Not needed for bc-2: `addSupportedChain` — bc-2 is not a contract-side
chain; the constructor already seeds the EVM target config (chain 1).
`setFeeRecipient`, `removeValidator`, `emergencyWithdraw`,
`emergencyPause`, `updateMerkleRoot` exist as owner calls but are not
part of the activation.

Pre-sign checks per exec: Safe nonce read converges (the stale-nonce
path in `lib.js` retries; a nonce that never reaches the expected value
refuses to sign); calldata matches the table; each exec is simulated/
estimate-able before signatures.

## 5. Post-deploy reads (all read-only, no key)

- `eth_getCode(<bridge>)` non-empty.
- `owner()` == `<safe>` — `verify-bridge-owner.js` prints this with
  `paused`, `feeRecipient`, `requestCounter` in one JSON line.
- `paused()` == `true` until S5 lands.
- Per validator: `validators(<signer>).isActive == true`; `chainValidators`
  for chain 1 reflects the three signers.
- `getThreshold()` on the Safe == 2; `getOwners()` == the rotated set.
- `supportedTokens(<aitoken>).isActive`, `.bridgeLimit`, `.feePercentage`
  match the S4 args.
- Record: the script appends the new deployment entry to
  `deployments-bridge-sepolia.json`; mark the BR-1 entry deprecated in a
  follow-up repo edit (it stays factual history — `deprecated: true` +
  reason), matching the file's existing convention.
- `unpause-precheck.py` already implements the code/owner/threshold
  reads against these addresses for the F5 gate.

## 6. `BRIDGE_CONTRACT_ADDRESS` update checklist (after deploy)

Measured carriers — **edit each only on the operator's word**:

- `aitbc-bridge-monitor.env` on **hub** — the only file carrying the
  name today; `aitbc-bridge-monitor` restarts on the F5 line.
- `aitbc-exchange.env` on hub — **not carried today**;
  `simple_exchange/config.py` reads the name with a `""` default, so the
  exchange's bridge status shows an empty contract without it. Adding it
  is an operator-named env edit if the status is wanted (runbook F5).
- `deployments-bridge-sepolia.json` — script-written entry; mark the
  BR-1 row deprecated (repo edit).
- Doc note: `deploy-bridge.js`'s printed "next steps" name
  `blockchain.env` + `aitbc-exchange` — that hint predates the measured
  inventory; the carrier is `aitbc-bridge-monitor.env`.
- Any new file the operator adds the name to is a scope expansion the
  owed sheet's anchored greps should then cover.

## 7. Withdraw-leg note

There is **no `completeBridge` path on Sepolia** by construction:
`initiateBridge` forbids same-chain targets while `completeBridge`
requires `target == block.chainid`. The withdraw leg is the owner
`emergencyWithdraw(token, amount)` sweep to the Safe — proven end-to-end
in the BR-1 record (`0xbed1…83869`). The bc-2-side withdrawal direction
is a chain-side lock, not an EVM call.

## 8. Out of scope (restating the gates)

No real key is touched by this document or its dry runs; no Sepolia
transaction is sent until the operator runs §3–§4; the signer rotation
itself is operator custody work; `BRIDGE_CONTRACT_ADDRESS` edits are
operator-named env changes; the F5 flag flip waits for this document's
reads plus `unpause-precheck.py` GO.
