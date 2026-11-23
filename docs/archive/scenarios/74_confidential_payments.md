# Confidential Payments

> **Retired (#2767).** This scenario covered a simulation, not a ledger
> payment. The CLI commands were removed; the examples below are retained
> for historical reference and must not be replayed. The TEE rail was
> retired separately in #2375.

**Level**: Intermediate
**Prerequisites**: Scenario 47 ZK Proofs for High-Value Jobs
**Estimated Time**: 10 minutes
**Last Updated**: 2026-11-23
**Version**: 1.1

**Legs**: 2

## Navigation Path

[Documentation Home](../../README.md) > [Agent Scenarios](../../scenarios/README.md) > *You are here*

breadcrumb: Home > Scenarios > Confidential Payments

---

## See Also

- **Previous Scenario**: [Contract Deploy & Call](../../scenarios/73_contract_deploy_call.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/confidential.py`

---

## Scenario Overview

> **Simulated path — permanent, not a degraded mode:** `aitbc confidential`
> builds a `ConfidentialWallet` locally, constructs and validates the
> commitment transaction in-process, and only then tries the API. There is
> no persistence layer behind it — output is the simulated/confidential-
> compute path, not ledger state. Label it `(Simulated)`.
>
> This is the feature, not a fallback: the TEE/enclave rail was removed
> entirely in #2375 (operator ruling — no enclave hardware will exist), so
> no real confidential-settlement path is planned. If one is ever wanted it
> would be a new design (the on-paper direction is the FHE service,
> `docs/development/fhe-service.md`), not a revival of this one.
>
> The API leg falls back to the simulated result **only** when the
> coordinator reports confidential settlement unavailable (HTTP 503).
> Auth failures — 401 invalid/expired token, 403 from an edge proxy —
> abort with the server error instead of simulating a send that never
> happened; refresh credentials (`aitbc auth login`) or fix the proxy
> rule before retrying.

This scenario covers `aitbc confidential`: a confidential send and balance
query using amount commitments rather than plaintext values.

### Use Case

A job payment where the amount itself should not be public: the CLI builds
the commitment transaction and exercises the confidential-payment path used
by scenario 46/47 jobs — on the permanent simulated rail described above.

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
