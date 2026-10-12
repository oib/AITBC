# Bridge Sepolia rehearsal runbook (BR-9)

Rehearse the `CrossChainBridge` deploy on **Sepolia (chainId 11155111)** with a
throwaway 2-of-3 Safe before the real deployment (BR-1) is attempted. An agent
runs this runbook; every step is a script, not a web-UI walkthrough.

## Safety rules (hard constraints)

- **Sepolia only.** Every script refuses any chainId other than `11155111`.
- **Throwaway keys only.** The only keys used are
  `keys/rehearsal-sepolia/signer{1,2,3}` (KC-5). They hold Sepolia test ETH and
  must never be funded on mainnet. Scripts read them from the path in
  `REHEARSAL_KEYS_DIR` — which must end in `rehearsal-sepolia` — into memory
  only. Keys are never printed, logged, exported, passed as arguments, or
  written anywhere else.
- **The old deployer key is off limits.** The key that owns the old Sepolia
  bridge (`0x8180…3748`) is not used, derived from, funded from, or referenced
  by any step. Its 0.131 Sepolia ETH stays untouched. The rehearsal deployer
  is **signer1** (`0x5f659B20a89279c815B5b8b98b423E26E2737032`, operator
  decision).
- No Safe Transaction Service: signatures are collected and combined
  in-process by `safe-exec.js`.
- The rehearsal never appends to `contracts/deployments-bridge-sepolia.json` —
  `BRIDGE_DEPLOY_RECORD` redirects the deployment record to a scratch file.

## Prerequisites

1. `keys/rehearsal-sepolia/` populated (done — KC-5):

   | role | address |
   |---|---|
   | signer1 — deployer | `0x5f659B20a89279c815B5b8b98b423E26E2737032` |
   | signer2 | `0xD7011e3E289b2E0B6cAD0B9A29Ce18B0290e3D3C` |
   | signer3 | `0x7bD563129Fe0822BB413b8C20Cdda1187a7091D2` |

2. A repo checkout that contains the rehearsal commit, with `contracts/`
   installed: `cd contracts && npm ci` (node ≥ 24; on the IDE host install a
   runtime first, e.g. `~/.local/pipx/venvs/pre-commit/bin/nodeenv`).
   Run everything on the **IDE host** — the keys live here and must not be
   copied to any fleet node.

3. **Operator inputs (phase B only):**
   - **Sepolia ETH to signer1** `0x5f659B20a89279c815B5b8b98b423E26E2737032`.
     Local gas numbers (hardhat): Safe deploy ≈ 306,000, bridge deploy
     ≈ 2,588,000, one Safe exec ≈ 82,000 → ~3.0M gas total. At a conservative
     10 gwei that is ~0.03 ETH; send **0.05 ETH minimum, 0.1 ETH comfortable**
     (margin for price spikes and repeat runs).
   - **A public Sepolia RPC URL** — two endpoints that need no account
     (*verify at run time; public endpoints change*):
     `https://ethereum-sepolia-rpc.publicnode.com` or `https://sepolia.drpc.org`.

## Phase B — command list

```bash
# one-time per shell; no key material ever goes into the environment
export REHEARSAL_KEYS_DIR=/home/oib/windsurf/aitbc/keys/rehearsal-sepolia
export SEPOLIA_RPC_URL=<operator's Sepolia RPC URL>
cd <repo checkout>/contracts

# B1 — create the Safe (signer1 pays). stdout = Safe address only.
SAFE_ADDRESS=$(node scripts/rehearsal/safe-create.js)
echo "$SAFE_ADDRESS"

# B2 — deploy the bridge paused; ownership goes to the Safe in the same run.
#     The deployer key is read in-process from the key file; the record goes
#     to a scratch file, never deployments-bridge-sepolia.json.
BRIDGE_REQUIRE_CHAIN_ID=11155111 \
DEPLOYER_KEY_FILE=$REHEARSAL_KEYS_DIR/signer1.key \
BRIDGE_OWNER_SAFE=$SAFE_ADDRESS \
BRIDGE_FEE_RECIPIENT=$(cat $REHEARSAL_KEYS_DIR/signer1.address) \
BRIDGE_DEPLOY_RECORD=/tmp/rehearsal-deployments-sepolia.json \
ETH_RPC_URL=$SEPOLIA_RPC_URL \
npx hardhat run scripts/deploy-bridge.js --network sepolia
#   note the "CrossChainBridge deployed: 0x..." line
BRIDGE_ADDRESS=0x<deployed bridge>

# B3 — read-only owner check.
BRIDGE_OWNER_SAFE=$SAFE_ADDRESS BRIDGE_ADDRESS=$BRIDGE_ADDRESS \
  node scripts/rehearsal/verify-bridge-owner.js

# B4 — one owner-only call through the 2-of-3 Safe: setFeeRecipient(signer1),
#      signed in-process by signer2 + signer3. Negative checks (single-sig
#      must fail, direct EOA call must revert) run automatically first.
SAFE_ADDRESS=$SAFE_ADDRESS BRIDGE_ADDRESS=$BRIDGE_ADDRESS \
  node scripts/rehearsal/safe-exec.js
```

Expected results:

- B1 prints the Safe address; stderr shows owners matching the three signer
  files and threshold 2.
- B2 prints `Post-deploy state:` with `owner` = Safe, `paused: true`, no
  validators/tokens/request seeded, and writes the record to
  `/tmp/rehearsal-deployments-sepolia.json`.
- B3 prints `"verdict": "OK"`.
- B4 prints both negative checks refused-as-expected, then the execution tx
  hash and `feeRecipient` = signer1's address.

## Optional UI route (not used)

The Safe web UI (app.safe.global) can create the Safe and propose the same
transaction for the three browser wallets — kept only as a visual cross-check
of the script outputs. **Not used**: the rehearsal flow is fully scripted so
it can be replayed and audited.

## What phase A verified, what phase B must still show

Verified locally on hardhat (`test/RehearsalSafe.test.js`, 2/2): Safe v1.4.1
infra deploy, 2-of-3 Safe create via protocol-kit, bridge deployed paused and
owned by the Safe, `setFeeRecipient` executed with two locally collected
signatures, single-signature execution refused, direct EOA owner-call revert,
and the read-backs. `deploy-bridge.js` dry run green incl. the three new env
overrides; full hardhat suite 206/206 and forge 302/302.

Unverified until phase B (no chain RPC existed at phase A): the exact Sepolia
gas price, public-RPC reliability, and the deployed addresses of the real
Sepolia Safe infrastructure the protocol-kit resolves on chainId 11155111 —
the run asserts these itself via the chainId and owner guards.
