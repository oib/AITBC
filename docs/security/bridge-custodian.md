# AITBC bridge custodian model

## Current state

The AITBC bridge operates in **trusted-custodian mode**: users deposit ETH to a
hub-controlled Sepolia address and receive AIT on the AITBC chain. AIT→ETH
withdrawals are explicitly disabled in the current release.

The repository **does** contain a bridge contract —
`contracts/contracts/CrossChainBridge.sol`. The live Sepolia deployment is
SEPOLIA-REDEPLOY-2 (`0x29D59bb1Ceb83A894Cc5a41dd99eb80f28A38ed9`, Safe-owned,
wired as `BRIDGE_CONTRACT_ADDRESS`; see
`contracts/deployments-bridge-sepolia.json` and
[cross-chain-bridge-deployment.md](../contracts/cross-chain-bridge-deployment.md)).
Its bytecode predates `d338967f3` (#1463 EIP-712 validator signatures), so it
still verifies the legacy signature format — see the deployment doc's defect
list before changing off-chain signing.

Three earlier instances are **deprecated** and must not receive deposits:
`0x24403CCff489D9355A534D34d4F88bC5b3EcF6FA` (owner is the unrecoverable
deployer key `0x818018F3…`, declared 2026-08-31 — every `onlyOwner` path is
permanently unreachable while it stays unpaused),
`0xfbDd3Dc5ded99477D6bC0c2E267cE619B081e3e0` (BR-1 instance replaced by
SEPOLIA-REDEPLOY-1 on 2026-10-21), and
`0xFBAF71e0Cfb4f691ffFa5c0c54428abD841E7076` (SEPOLIA-REDEPLOY-1, replaced
by SEPOLIA-REDEPLOY-2 on 2026-11-08). `fleet-config-check.sh` FAILs if any
deprecated address appears in live config — the sweep derives the set from
`deployments-bridge-sepolia.json`, so newly-deprecated entries are covered
automatically.

ETH→AIT bridging remains a custodial payout on top of the contract deposit
flow: the monitor watches the deposit address and pays AIT from a payout
wallet. AIT→ETH withdrawals are explicitly disabled in the current release.

## Trust assumptions

| Actor | Responsibility |
|-------|----------------|
| Hub operator | Controls the Ethereum deposit address and the payout wallet's float. |
| Bridge monitor | Prices each inflow, signs and submits the AIT payout, holds the signed envelope until it seals, and exposes operator commands (`status`, `manual-payout`, `abandon-and-resign`, `write-off`). |
| Exchange service | Accepts `BRIDGE_ETH_ADDRESS` from the environment, returns instructions, records deposits. |
| Customer | Sends ETH only after verifying the deposit address through an authenticated channel. |

### Payout wallet exposure

Payouts come from a **dedicated payout wallet** (`BRIDGE_PAYOUT_ADDRESS` /
`BRIDGE_PAYOUT_PRIVATE_KEY`), not from a mint — the wallet holds a bounded
float and the monitor refuses a payout that would exceed
`BRIDGE_MAX_PAYOUT_FRACTION` of it (and the absolute `BRIDGE_MAX_PAYOUT_AIT`
ceiling when set). Consequences of that design:

- The payout key is loaded in an internet-facing hub process. It is a hot key:
  keep the float small, alert on it (`BRIDGE_LOW_FLOAT_AIT`), and do not reuse
  it for treasury funds.
- `BRIDGE_FUNDING_SOURCES` inflows (operator float top-ups) are recorded as
  `FUNDING` rows and are never paid out — the match is on the Ethereum-side
  sender address, case-insensitive.
- A `SUBMITTED` ledger row owns a signed envelope whose nonce may still land;
  the monitor never re-signs while it could. Manual sends from the payout
  account bypass the ledger and can strand or double a payout — they are
  forbidden; use the admin commands.

## Multisig upgrade path

The exchange reads the following environment variables and reports them in
`/v1/bridge/status` and `/v1/cross-chain/rates`:

- `BRIDGE_CUSTODIAN_MODE` — `true` while the hub is the custodian.
- `BRIDGE_MULTISIG_ENABLED` — `false` by default.
- `BRIDGE_MULTISIG_THRESHOLD` — number of signatures required to release funds.
- `BRIDGE_SIGNERS` — comma-separated list of authorized signer Ethereum addresses.
- `BRIDGE_SAFE_ADDRESS` — optional Gnosis Safe / multi-sig contract address.

These values are **public configuration**, not secrets.  The actual signing keys
must be stored in the operator's secret manager (e.g. HashiCorp Vault, a HSM, or
Devin Cloud secrets) and never committed to the repository.

### Enabling multisig releases

1. Set `BRIDGE_MULTISIG_ENABLED=true`.
2. Set `BRIDGE_MULTISIG_THRESHOLD` to the minimum number of required signatures.
3. Set `BRIDGE_SIGNERS` to the public addresses of the authorized signers.
4. Set `BRIDGE_SAFE_ADDRESS` to the on-chain safe or custody contract.
5. Do **not** set `BRIDGE_WITHDRAW_ENABLED=true` until the multi-sig release
   flow is implemented and live-validated.

The release flow is:

1. User requests AIT→ETH withdrawal.
2. Exchange checks that `BRIDGE_WITHDRAW_ENABLED` is not set.
3. When enabled, the exchange requires `threshold` signatures from members of
   `BRIDGE_SIGNERS` over the release transaction.
4. Once signed, the exchange submits the release to the safe / custody contract.

This section remains a specification; the target design for the replacement
deployment is a `CrossChainBridge` owned by a 2-of-3 Safe whose signers are
three separate people on separate devices — the deployer key is disposable.

## Security checklist

- [x] Deposit address is published through an authenticated, integrity-protected channel.
- [x] Withdrawals are disabled until the multisig release flow ships.
- [x] Multisig keys are generated by operators and never stored in Git.
- [ ] Replacement `CrossChainBridge` deployed with a Safe owner (2-of-3 signers) — supersedes the lost-owner contract.
- [ ] Payout wallet float kept to an operational minimum; `BRIDGE_MAX_PAYOUT_*` caps set.
- [ ] Funding-source senders configured in `BRIDGE_FUNDING_SOURCES` so top-ups don't take the deposit path.
- [ ] A monitoring alert fires when `BRIDGE_WITHDRAW_ENABLED` changes from `false`.

## References

- `apps/bridge-monitor/README.md` — payout lifecycle, ledger states, admin commands, env knobs.
- `docs/architecture/bridge-threat-model.md` — threat model incl. nonce collision and head-of-line blocking.
- `contracts/contracts/CrossChainBridge.sol` — bridge contract source.
- `contracts/deployments-bridge-sepolia.json` — deployment record (deprecated instance, lost owner).
- `apps/exchange/simple_exchange/config.py` — bridge configuration loader.
- `apps/exchange/simple_exchange/handlers/bridge.py` — bridge endpoints.
