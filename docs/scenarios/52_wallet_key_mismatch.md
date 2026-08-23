# Wallet Key Mismatch Recovery

**Level**: Intermediate
**Prerequisites**: [Scenario 01 Wallet Basics](./01_wallet_basics.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-23
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Wallet Key Mismatch Recovery

---

## See Also

- **Previous Scenario**: [Scenario 49 Auto Reinvest Escrow](./49_auto_reinvest_escrow.md)
- **Feature Documentation**: [Wallet key mismatch guidance](../../AGENTS.md#wallet-key-mismatches)
- **Closed cycle**: [DESIGN_CYCLE.md](../DESIGN_CYCLE.md) operations gap #12

---

## Scenario Overview

A wallet file contains a private key that does **not** derive to the address the node or the user expected. This scenario is the operator recovery play for that mismatch. It does **not** provide a way to reverse an address to a key — that is impossible — and it does not ask you to search for other people's backups.

> **Operator play:** This is a data-integrity recovery scenario, not a code bug. The fix is documented operator procedure.

### Use Case

A shop or hub node logs a `wallet key mismatch` warning, a `wallet info` command shows an unexpected address, or an escrow release fails because the configured `ESCROW_RELEASE_PRIVATE_KEY` does not match the expected `ESCROW_RELEASE_ADDRESS`. The operator must decide whether the original key is recoverable and how to migrate funds or signing duties to a correct wallet.

### What You'll Learn

- How to confirm a key/address mismatch with `aitbc wallet info`
- Why a public address cannot be reversed to a private key
- How to recover if the original seed/backup is available
- How to deprecate a mismatched wallet and create a fresh, backed-up one if the original is lost
- Where to record the finding for the live validation summary

---

## Prerequisites

### Knowledge Required

- How AITBC addresses are derived from secp256k1 private keys
- The difference between a wallet file, a seed phrase, and an address

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- Access to the node where the wallet is stored

### Setup Required

- A wallet that is known or suspected to have a key/address mismatch
- A safe place to store any recovered seed phrase or private key

---

## Step-by-Step Workflow

### Step 1: Confirm the mismatch

Run `aitbc wallet info` for the wallet in question:

```bash
aitbc wallet info --name suspect-wallet
```

Compare the printed `address` with the address the node expects, e.g. from `ESCROW_RELEASE_ADDRESS`, a coordinator config, or `aitbc wallet list`.

If the addresses differ, the stored private key does not control the expected address. Do **not** attempt to "fix" this by deriving a key from the address.

### Step 2: Record the mismatch

Create or append a finding in `LIVE_VALIDATION_SUMMARY.md` or your local runbook. Include:

- Wallet name and file path
- The address the system expected
- The address the stored key actually derives to
- The service or scenario where the mismatch was detected
- Whether the original seed/backup is available

### Step 3: Check for an original seed or backup

Look for an original backup in the places that are documented for the node:

- `~/.aitbc/wallets/<wallet-name>.json`
- `/var/lib/aitbc/wallets/`
- Wallet daemon key store
- The seed phrase written down during wallet creation
- Off-node backups managed by the operator

> **Important:** Only search for backups you already know exist and that you are authorized to access. Do not bulk-search the node for secrets.

### Step 4: Recover with the correct key

If the original seed or private key is found:

1. Create a new wallet file with the correct key:

   ```bash
   aitbc wallet import-wallet --name recovered-wallet --private-key 0x...
   ```

2. Verify the address matches the expected one:

   ```bash
   aitbc wallet info --name recovered-wallet
   ```

3. Migrate balances, escrow signing duties, or coordinator config to the recovered wallet.
4. Remove or archive the mismatched wallet file.

### Step 5: Deprecate the mismatched wallet if the original is lost

If the original seed or private key is **not** found, the funds controlled by the original key are not recoverable. Do **not** try to brute-force or reconstruct the key.

1. Create a new wallet with a fresh, safely-backed-up seed:

   ```bash
   aitbc wallet create --name fresh-wallet
   aitbc wallet backup --name fresh-wallet --output /secure/backup/path/fresh-wallet.json
   ```

2. Derive or copy the new address into the relevant config (`ESCROW_RELEASE_ADDRESS`, coordinator wallet, etc.).
3. Fund the new wallet and update services to use it.
4. Mark the old, mismatched wallet as deprecated in your runbook.

### Step 6: Verify the live path

For an escrow release signer:

```bash
aitbc wallet info --name recovered-wallet
# should match ESCROW_RELEASE_ADDRESS in /etc/aitbc/blockchain.env or coordinator config
```

For a customer or provider wallet, run a small test transaction to prove the address is now correct.

---

## Validation

- `aitbc wallet info` for the recovered or replacement wallet matches the expected address.
- The relevant service config (`blockchain.env`, coordinator env, etc.) points at the correct wallet.
- A test `aitbc wallet balance` or `aitbc ai submit` succeeds with the corrected wallet.
- The mismatch is recorded in the operator live-validation log.

---

## Cleanup

- Archive the mismatched wallet file with a clear `MISMATCHED` marker.
- Store the new seed/private key only in the approved backup location.
- Update `LIVE_VALIDATION_SUMMARY.md` with the resolution.

---

## Important safety notes

- **Do not** run `aitbc wallet restore` from an address. Addresses are not seed data.
- **Do not** search `/etc/aitbc/*.env` or the filesystem for other people's private keys unless you have explicit authorization.
- **Do not** attempt to regenerate a missing key by hashing the address or by brute force. Any "recovered" key produced that way is a new, unrelated wallet.
- The recommended response is the same as the guidance in [AGENTS.md](../../AGENTS.md): record, check for an original backup, recover from that backup, or deprecate and replace.
