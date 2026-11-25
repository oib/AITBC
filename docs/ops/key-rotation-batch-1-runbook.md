# KEY-ROTATION-BATCH-1 runbook — batched key rotation at bc reset 2 genesis

Issue: #413 (parked, `owner/operator`). Scope per the 25 Oct operator card
answer 3A and the #410 R8 ruling (31 Oct): **all authority keys rotate at the
bc-3 genesis** — this absorbs the parked batch rotation. The operator rotates,
signs and decides; the director directs no key action.

Interlocks: `BC-RESET-2-PLAN-1` (#410, closed — decisions final),
`SEPOLIA-REDEPLOY-1` (#411, closed — Sepolia bridge redeployed once after the
EVM keys rotate). Execution sequencing lives in
`docs/deployment/reset2-runbook.md` — this document is the key-handling
procedure only; chain/reset mechanics stay there.

## Hard rules

- **No key material in repo, logs, chat, tickets or this file.** Addresses and
  env-var *names* only. `scripts/maintenance/key-audit.py` derives addresses from keys
  without printing them — use it for every custody check.
- Each validator holds **exactly its own key** in `validator-secrets.env`
  (last `EnvironmentFile`, wins): `VALIDATOR_KEYS={"<own addr>":"<key>"}`,
  `PROPOSER_ID=<own addr>`, `PROPOSER_KEY=<own key>`. Keys never appear in
  shared unit env files or on a second host.
- A signing wallet is named by the operator before any signing attempt; stop
  at an encrypted or watch-only wallet and ask.
- Old keys are retired only after the new set is verified live; `.bak-*` /
  `.pre-*` env backups still carry old key material — sweep them at cutover
  (`key-audit.py` lists backup files too, flagged `"backup": true`).

## Key inventory to rotate

### A. PBFT validator keys (4 validators: hub, hub1, node1, node2; node0 is follower)

Current set (KR-5, address-sorted production order): node1 `0x19f0…`,
hub `0x2aD5…`, hub1 `0x5E8E…`, node2 `0xE894…` — full addresses in
`VALIDATOR_SET` on each host's `blockchain.env` / `validator-secrets.env`.

Per validator host, at genesis staging:

1. Generate a fresh proposer key offline (operator custodian); derive the
   address — that address is the validator's new identity.
2. Stage `validator-secrets.env` with `VALIDATOR_KEYS`, `PROPOSER_ID`,
   `PROPOSER_KEY` for the **new** address only.
3. The new `VALIDATOR_SET` (all four new addresses) and
   `TRUSTED_PROPOSERS` (= genesis + four validators) go into the genesis
   parameters — see reset2-runbook §A.2.
4. `key-audit.py --find-address <new addr>` must hit exactly the intended
   `validator-secrets.env`; `--report` verdict `ok` with zero mismatches.

### B. Sepolia EVM signer keys (the "three signer keys" of the 20 Oct card)

Key-bearing env sites observed on hub (confirm the exact trio against the
card answer at execution — candidates below; names only):

| env file | variable(s) | role |
|---|---|---|
| `aitbc-bridge-monitor.env` | `BRIDGE_PAYOUT_PRIVATE_KEY` (+`BRIDGE_PAYOUT_ADDRESS`) | bridge payout signer |
| `aitbc-coordinator-api.env` | `ENERGY_OPERATOR_KEY` | energy oracle operator |
| `aitbc-coordinator-api.env` | `AGENT_ECONOMICS_OPERATOR_KEY`, `BOND_SLASH_PRIVATE_KEY` | coordinator authorities — include if in the card's three |
| `bridge-validator-keys.env`, `ops-signer.env`, `aitbc-wallet.env`, `bridge-reg-run.env` | per-file keys | bridge validator / ops signer / wallet — enumerate with `key-audit.py` before staging |

For each: generate fresh key → fund the new address if it needs gas/balance
→ update env + matching `*_ADDRESS` var → restart only after the reset-2
window → verify first signed action on-chain.

### C. Safe owners (2-of-3, contract kept per ruling 5b)

The current Sepolia bridge Safe keeps its contract; only **owners are
swapped**. Operator signs the `swapOwner`/`addOwnerWithThreshold`-
sequence transactions client-side. Post-swap verify: `eth_getOwners` +
`getThreshold` against the Safe address (`BRIDGE_SAFE_ADDRESS` /
deployments record) return exactly the three new owner addresses and
threshold 2. Old owner keys retire after on-chain confirmation.

## Sequencing (inside reset-2)

1. **Pre-genesis:** all new keys generated + custodied; `key-audit.py
   --find-address` zero-miss for every new address; custody table §2 of
   reset2-runbook complete (no repeat of bc-2's lost `governance_executors`).
2. **Genesis build:** new `VALIDATOR_SET`/`TRUSTED_PROPOSERS` baked in;
   `ESCROW_FEE_RECIPIENT` = treasury SOT value (fresh custodied key — bc-2's
   burn address does not carry).
3. **Cutover:** envs staged per host class (reset2-runbook §A.3); validators
   rejoin per `AGENTS/validator-operations.md`; first sealed block is the
   PoNR.
4. **Post-cut:** Safe owner swap signed; `SEPOLIA-REDEPLOY-1` pattern —
   bridge redeploys once after EVM keys rotate; bridge locks stay paused at
   genesis (`BRIDGE_LOCKS_PAUSED=true`), unpause is a separate gated step.
5. **Retirement:** old validator/EVM keys destroyed or moved to cold
   custody; `.bak-*` env sweep; `key-audit.py --report` final `ok`.

## Done when (from the row)

Operator confirms the new validator set and Safe owners are live on the
reset-2 genesis; old keys retired; **no key material in repo, logs or
chat**. Verify: `key-audit.py --report` clean + `VALIDATOR_SET` on all four
validator hosts matches genesis + Safe `getOwners`/`getThreshold` on-chain.
