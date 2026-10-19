# RESET-SEPOLIA-READ-1 — progress ledger (append only)

## 2026-10-19 — Phase 0 read (read-only; no transaction, no signing, no keys, nothing changed)

Reads: repo `465f39eeb`, hub env (names + public addresses only), `eth_call`/`eth_getLogs`/`eth_getBalance` against hub's configured Sepolia RPC (URL not printed), Etherscan V2 API (no key), MCP `get_eth_bridge_status_redacted` + `list_eth_bridge_withdrawals`. Host `date` at read time ~08:5x CEST. **Coder-reported until director-verified.**

### 1. What is deployed

`contracts/deployments-bridge-sepolia.json` lists two `CrossChainBridge` deployments:

- **Deprecated** `0x24403CCff489D9355A534D34d4F88bC5b3EcF6FA` (deployed 8 Jun, tx `0x5025…`): `owner()` = deployer `0x818018F3…` declared unrecoverable 2026-08-31 — every onlyOwner path permanently unreachable; unpaused and able to receive funds forever; `fleet-config-check` FAILs on it. Do not point deposits at it.
- **Current** `0xfbDd3Dc5ded99477D6bC0c2E267cE619B081e3e0` (deployed 16 Oct, tx `0xeedd…`): deployer `0x5f659B20…`, **owner = Safe `0xdd32618f…`**, feeRecipient `0x5f659B20…`. Record claims Safe ops on 16 Oct (AIToken support, unpause, deposit+confirm test, emergencyWithdraw sweep) — on-chain reads below are consistent.

Host config: `BRIDGE_CONTRACT_ADDRESS=0xfbDd3Dc5…` present in `/etc/aitbc/aitbc-bridge-monitor.env`, `aitbc-coordinator-api.env`, `exchange.env` on hub — repo address = deployed address. `BRIDGE_ETH_ADDRESS=0x310dcE00270D0aC10CAccfBD636Ff07BD5648781` is the deposit/payout EOA the monitor watches.

**Explorer verification: NOT verified** — Etherscan V2 `getsourcecode` returns empty `SourceCode`. All contract facts below are bytecode-level reads (public getters + events), matching `contracts/contracts/CrossChainBridge.sol` (595 lines, foundry+hardhat).

### 2. What the contract stores about this chain — the binding table

| stored | what it is | keyed on |
|---|---|---|
| `supportedChains(uint256)` | chain registry | **numeric uint256** — exactly one entry: `chainId=1, name="Ethereum", chainType=0` (ChainSupported event, block 11926614; getter confirms). **No AITBC registration; the string id never appears on-chain.** |
| `validators`/`activeValidators` | 3 validator EOAs, weight 1 each | **EVM addresses**: `0x5f659b20…`, `0xd7011e3e…`, `0x7bd56312…` (ValidatorAdded blocks 11926660-66) |
| `BridgeRequest` rows | per-request (source/target chainId uint256, tokens, recipient, hashes) | numeric ids + `lockTxHash` bytes32 — content-agnostic to AITBC's string id |
| `confirmBridge` signature | `keccak256(requestId, lockTxHash, block.chainid)` | **EVM chain id (11155111)**, not AITBC's string id |
| `merkleRoot` | single global root for `completeBridge` proofs | `0x0` — **never posted** |
| `processedTxHashes` | replay protection on `unlockTxHash` | tx-hash keyed, chain-agnostic |
| `requestCounter` | = **1** | the single 16-Oct test deposit |
| pause/upgrade | `paused()`=false; no proxy — **not upgradeable** | owner functions all `onlyOwner` (the Safe) |

The contract is **ERC20-only**: no `receive`/`payable` — it cannot hold ETH at all. Contract ETH balance 0, AIToken balance 0 (swept to Safe in the test).

**Answer for a new AITBC chain id: the contract binds nothing to it.** The string `ait-hub.aitbc.bubuit.net` exists only off-chain (monitor env, DBs, gossip). The on-chain links are: numeric id 1 (a placeholder label), the 3 validator EOA addresses, and lockTxHash contents — none of which the string rename touches.

### 3. How the contract learns about AITBC (and what breaks on new id + height 0)

- Flow (contract side): `initiateBridge` (Sepolia→target) locks ERC20 → validators `confirmBridge(requestId, lockTxHash, sig)` → `completeBridge` on target requires `block.chainid==targetChainId` + Merkle proof vs `merkleRoot`. There is **no header ingestion, no state-root verification** — the "attestation" is validators vouching for a lockTxHash off-chain.
- `completeBridge` can never run on a single-chain deployment (initiate forbids target==block.chainid) — the deploy record notes this; `merkleRoot=0` confirms the completion path is unused.
- **Production deposits don't use the contract**: monitor watches EOA `0x310d…` for incoming ETH (status via MCP: deposit_address=EOA, fee 0.5%, min 0.001 ETH, auto_poll). The two completed withdrawals were paid as raw ETH sends from the payout wallet (ledger `eth_withdrawals` ×2 completed).
- **What breaks under new AITBC id + height 0**: nothing on the contract. Off-chain: the monitor's `chain_id` env and any lock-hash→request mapping in `bridge_deposits.db`/`bridge_outbound` rows refer to the old chain's tx hashes — those are archive-time rows, not contract state.

### 4. Options for the new chain

- **Nothing (recommended-if-validators-stay)**: contract needs zero changes; the string id is invisible to it. All re-pointing is off-chain env work (`CHAIN_ID`, any target-mapping config in monitor/coordinator/exchange envs).
- **Re-point**: only needed if the bridge-signer EVM keys rotate under D4 — `removeValidator`/`addValidator` ×3 via the Safe (**2-of-3 owner signatures**). Optionally register a properly-named `supportedChain` entry (cosmetic).
- **Redeploy**: cosmetic only (clears requestCounter residue and the deprecated-sibling confusion); costs a deploy tx + Safe wiring + `BRIDGE_CONTRACT_ADDRESS` env updates + monitor restart. Not needed functionally.
- In-flight/old funds: contract holds nothing; old contract `0x24403C…` is ownerless-but-fundable — deposits must keep pointing at the EOA/never at it. The EOA float (~0.0531 ETH) is the monitor wallet — unaffected by the chain cut.

### 5. Balances and open items

- Contract `0xfbDd…`: ETH 0, AIToken 0, requestCounter 1, merkleRoot 0, unpaused, owner=Safe.
- Deposit/payout EOA `0x310d…`: **ETH 53,053,666,887,156,947 wei ≈ 0.0531 ETH**; AIToken 0.
- Open items (monitor-side, unchanged from the drain list): `eth_deposits` non-terminal ×2 (`funding`, `exchange_prepay`), `bridge_deposits` failed×1, `bridge_sell_quotes` locked×1, `eth_withdrawals` 2 completed, `bridge_outbound` 5-row log.
- Deprecated contract `0x24403C…`: balances not re-read (ownerless; fleet-config-check already FAILs it).

### 6. Roles ↔ keys (list only — no action proposed)

- **Safe owners (2-of-3)** `0xdd32618f…`: `0x5f659b20…`, `0xd7011e3e…`, `0x7bd56312…` — **the same three keys are the contract's validators.** One keyset governs both admin and attestation.
- feeRecipient = `0x5f659b20…` (signer1).
- These are **EVM keys, distinct from the PBFT validator set** (`0x2aD5…/0xE894…/0x19f0…/0x5E8E…`) — the D4 rotation ordering question is whether the bridge-signer keys rotate in the same wave.
- `BRIDGE_ETH_ADDRESS` `0x310d…` = monitor's deposit/payout wallet (custody not read).

### 7. Recommendation

**Nothing-to-do on the contract** for a new AITBC chain id — the binding analysis shows no string-id coupling anywhere. The only contract-side action that could ever be needed is validator-set rotation *if* the three EVM signer keys rotate under D4 (a 2-of-3 Safe call, off critical path). The deploy record + on-chain state agree; the redeploy option exists but buys only cosmetic cleanliness.

**Unknowns remaining:**
- Where the monitor maps its AITBC string chain id to the contract's numeric `targetChainId` when instructing depositors (probably monitor-side config/usage text — a repo grep for the deposit-instructions payload would settle it; `get_eth_bridge_deposit_instructions` exists but wasn't needed to reach the conclusion).
- Whether the source will ever be verified on the explorer (nice-to-have; affects nothing functional).
- Whether the three EVM signer keys are in the D4 rotation scope (operator's call).

### CLI/MCP gaps

- `eth_getLogs` on the configured RPC caps at 50,000 blocks and returns "pruned history unavailable" for some windows — worked around with tight ranges.
- Etherscan V1 endpoint deprecated; V2 works keyless at low rate.
- No single "bound-chain-id + validator set" read exists — suggest `get_eth_bridge_status_redacted` grow a `contract_state` section (paused, owner, validators, supportedChains, requestCounter, merkleRoot).

**No transaction was sent, nothing was signed, no wallet or key was touched, nothing changed on any host.**
