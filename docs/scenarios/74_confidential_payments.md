# Confidential Payments

**Level**: Intermediate
**Prerequisites**: Scenario 46 Confidential TEE Jobs, Scenario 47 ZK Proofs for High-Value Jobs
**Estimated Time**: 10 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Confidential Payments

---

## See Also

- **Previous Scenario**: [Contract Deploy & Call](./73_contract_deploy_call.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/confidential.py`

---

## Scenario Overview

> **Simulated path:** `aitbc confidential` builds a `ConfidentialWallet`
> locally, constructs and validates the commitment transaction in-process,
> and only then tries the API. There is no persistence layer behind it —
> output is the simulated/confidential-compute path, not ledger state.
> Label it `(Simulated)` exactly like the `tee` group.

This scenario covers `aitbc confidential`: a confidential send and balance
query using amount commitments rather than plaintext values.

### Use Case

A job payment where the amount itself should not be public: the CLI builds
the commitment transaction and settles it through the confidential-payment
path used by scenario 46/47 jobs.

### What You'll Learn

- `confidential balance` — the confidential wallet's committed balance
- `confidential send` — build, validate, and settle a committed payment

---

## Prerequisites

- `aitbc` on `$PATH`; a wallet id and recipient id
- The confidential-signing key configured for the CLI (the command derives
  it internally; it is not a plain `wallet` key)

---

## Steps

### 1. Check a confidential balance

```bash
aitbc confidential balance --wallet-id wallet-1
```

**Expected output:** the committed balance view for `wallet-1`
(simulated path — see the note above).

### 2. Send a confidential amount

```bash
aitbc confidential send --wallet-id wallet-1 --recipient-id recipient-1 --amount 10
aitbc --output json confidential send --wallet-id wallet-1 --recipient-id recipient-1 --amount 10
```

The command deposits the amount into the ephemeral wallet, produces the
commitment transaction (`tx_id`, `amount_commitment`), validates it, and
settles — reporting the simulated result plus any API response. Because
the wallet is seeded inside the command, `--amount` does not debit a
ledger; treat the flow as a demonstration of the commitment path, and do
not script real payouts against it.

---

## Cost Table

| Step | Spend |
|---|---|
| Entire scenario | 0 AIT — simulated commitment path |

---

## Verification

- `send` output includes `tx_id` and `amount_commitment` — proof the
  commitment transaction was constructed and validated.
- The amount never appears in plaintext in the commitment field.

## Troubleshooting

- Signing-key errors — the confidential key is missing/misconfigured; this
  is separate from `aitbc wallet` keys.
