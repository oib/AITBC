# Bridge CLI Options

**Level**: Advanced
**Prerequisites**: Scenario 20 Cross-Chain Transfer, Scenario 22 Bridge RPC Validation
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Bridge CLI Options

---

## Scenario Overview

> **Option-coverage scenario (BRIDGE-OPTS-1).** This play walks the
> previously unexercised `aitbc bridge` options — read-only query flags
> plus the money-path flags exercised only as far as they are free:
> parse-time refusals, wallet-resolution refusals, and node-side 4xx
> refusals. Nothing is signed by a real wallet, nothing is spent, and the
> operator-only `bridge-admin.sh` payout commands
> (`manual-payout` / `abandon-and-resign` / `write-off`) are **not** CLI
> options and are not touched.
>
> Played on node0 (checkout `59fcb78e1`) against the live bridge rpc on
> `localhost:8202`; the node's real chain id is `bc-2`.

### What You'll Learn

- Which `aitbc bridge` queries are free read-only calls
- Where each mutating command refuses when given a throwaway identity
- Which options pair together (`--issued-at` + `--nonce`,
  `--re-sign` + `--private-key`, `--signature` xor `--wallet-name`)

---

## Prerequisites

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A node with the bridge rpc reachable (default `http://localhost:8202/rpc`)

---

## Steps

### Step 1: Read-only queries (ok)

Query the locked balance and pending transfers for the node's own chain:

```bash
aitbc bridge balance --chain-id bc-2 --rpc-url http://localhost:8202/rpc
```

**Expected output:**

```
Bridge Balance
==============
{
  "success": true,
  "chain_id": "bc-2",
  "locked_amount": 0,
  "balances": {
    "bc-2": 0
  }
}
```

```bash
aitbc bridge pending --chain-id bc-2 --rpc-url http://localhost:8202/rpc
```

**Expected output:** `Pending Bridge Transfers` table, `[]` when empty.

> An unknown `--chain-id` is refused instead: `balance --chain-id
> ait-mainnet` returns `400 Bad Request` on `/rpc/bridge/balance/…`.

Oracle and security status take only `--rpc-url`:

```bash
aitbc bridge oracle-status --rpc-url http://localhost:8202/rpc
```

**Expected output:** `verification_mode`, `min_confirmations`,
`block_headers_total`, `release_enabled`, `multisig_enabled`.

```bash
aitbc bridge security-status --rpc-url http://localhost:8202/rpc
```

**Expected output:** table with `threshold`, `validators_configured`,
`current_epoch`, `require_merkle_proof`, `verification_mode`.

A transfer lookup for an id that does not exist is a clean refusal:

```bash
aitbc bridge status --transfer-id nosuch-bo1 --rpc-url http://localhost:8202/rpc
```

**Expected output:** `Failed to get bridge status: Client error '404 Not Found'`
(exit 2 — nothing written).

### Step 2: Proof and deposit-ledger flags (expected-refusal / ok)

`proof` builds a Merkle proof for a locked transfer; a transfer that was
never locked is refused by the node, so the anchor flags
(`--source-chain`, `--block-height`, `--block-hash`) are exercised for
free:

```bash
aitbc bridge proof --transfer-id nosuch-bo1 --source-chain bc-2 --block-height 1 --block-hash 0x0000000000000000000000000000000000000000000000000000000000000001 --output /tmp/bo1-proof.json --rpc-url http://localhost:8202/rpc
```

**Expected output:** `Failed to build bridge proof: Client error '400 Bad Request'`
(exit 2; no file written).

`deposits` reads the ETH-side deposit ledger through the bridge-monitor's
own admin listing. `--repo-root` points it at a checkout containing
`apps/bridge-monitor`:

```bash
aitbc bridge deposits --status funding --repo-root /opt/aitbc
```

**Expected output:** `no rows with status funding` (exit 0 — the ledger
read works even on a node without a monitor env; the list path only needs
the sources under `--repo-root`).

```bash
aitbc bridge deposits --tx-hash 0xabc123 --repo-root /opt/aitbc
```

**Expected output:** `no deposit row 0xabc123` followed by
`bridge ledger read failed (1)` — a missing
`/etc/aitbc/aitbc-bridge-monitor.env` surfaces as a warning on this
single-row lookup (recorded as noise, not a failure of the flag).

### Step 3: Lock flags — pair rule and wallet refusal (expected-refusal)

`--issued-at` and `--nonce` must be given together; with them set and no
`--signature` the node refuses the unsigned body:

```bash
aitbc bridge lock --target-chain t2-bo1 --sender 0x0000000000000000000000000000000000000001 --recipient 0x0000000000000000000000000000000000000002 --amount 1 --asset native --issued-at 1 --nonce n1 --rpc-url http://localhost:8202/rpc
```

**Expected output:** `Bridge lock failed: Client error '422 Unprocessable Content'`
(exit 2 — refused by the node, nothing locked).

`--wallet-name` resolves the wallet before any network call, so a wallet
that does not exist is a free refusal — `--source-chain` rides along:

```bash
aitbc bridge lock --target-chain t2-bo1 --sender 0x0000000000000000000000000000000000000001 --recipient 0x0000000000000000000000000000000000000002 --amount 1 --source-chain bc-2 --wallet-name nosuch-bo1 --rpc-url http://localhost:8202/rpc
```

**Expected output:** `Error: Wallet not found: nosuch-bo1` (exit 1 — aborts
before signing and before the network).

### Step 4: Confirm and unlock (expected-refusal)

`confirm` needs a proof file; a bogus transfer id and unsigned confirmer
are refused by the node:

```bash
aitbc bridge confirm --transfer-id nosuch-bo1 --confirmer 0x0000000000000000000000000000000000000003 --proof-file /tmp/bo1-proof.json --rpc-url http://localhost:8202/rpc
```

**Expected output:** `Bridge confirm failed: Client error '422 Unprocessable Content'`
(exit 2).

`unlock` takes either `--signature` or `--wallet-name`; a wallet that does
not exist refuses before any broadcast:

```bash
aitbc bridge unlock --transfer-id nosuch-bo1 --sender 0x0000000000000000000000000000000000000001 --wallet-name nosuch-bo1 --rpc-url http://localhost:8202/rpc
```

**Expected output:** `Error: Wallet not found: nosuch-bo1` (exit 1).

### Step 5: Sign-proof output (ok — local only, throwaway key)

`sign-proof` is fully local: it signs the proof JSON with the given key
and writes `--output`. A throwaway key is enough — no network, no wallet:

```bash
aitbc bridge sign-proof --proof-file /tmp/bo1-proof.json --private-key 0x1111111111111111111111111111111111111111111111111111111111111111 --output /tmp/bo1-signed.json
```

**Expected output:** `Signed Bridge Proof` table, `success True`,
`signatures 1`.

### Step 6: Header store / ingest / attest (expected-refusal)

`store-header`, `ingest-header` and `attest` all POST to
`/rpc/bridge/block-headers`, which only accepts configured bridge
admins/validators — a throwaway key is refused with 403 after signing,
so every flag is exercised for free:

```bash
aitbc bridge store-header --proof-file /tmp/bo1-signed.json --admin-private-key 0x1111111111111111111111111111111111111111111111111111111111111111 --admin-address 0x0000000000000000000000000000000000000004 --rpc-url http://localhost:8202/rpc
```

**Expected output:** `Failed to store block header: Client error '403 Forbidden'`.

```bash
aitbc bridge ingest-header --source-rpc http://localhost:8202/rpc --target-rpc http://localhost:8202/rpc --height 5 --chain-id bc-2 --proposer 0x0000000000000000000000000000000000000005 --output /tmp/bo1-hdr.json
```

**Expected output:** `Failed to ingest block header: Client error '403 Forbidden'`.
Note `--output` writes the fetched header *before* the store attempt, so
`/tmp/bo1-hdr.json` exists even though the store was refused.

`--re-sign` demands `--private-key`; without it the CLI aborts before any
network call:

```bash
aitbc bridge ingest-header --re-sign --source-rpc http://localhost:8202/rpc --target-rpc http://localhost:8202/rpc
```

**Expected output:** `--private-key is required when --re-sign is set` (exit 4).

```bash
aitbc bridge attest --header-file /tmp/bo1-hdr.json --private-key 0x1111111111111111111111111111111111111111111111111111111111111111 --proposer 0x0000000000000000000000000000000000000005 --output /tmp/bo1-att.json --target-rpc http://localhost:8202/rpc
```

**Expected output:** `Failed to attest block header: Client error '403 Forbidden'`.

```bash
aitbc bridge attest --source-rpc http://localhost:8202/rpc --height 5 --chain-id bc-2 --private-key 0x1111111111111111111111111111111111111111111111111111111111111111 --target-rpc http://localhost:8202/rpc
```

**Expected output:** `Failed to attest block header: Client error '403 Forbidden'`.

### Step 7: Register-validator (expected-refusal)

Validator registration is admin-gated on the node; `--admin-address`,
`--epoch` and `--rpc-url` ride on the refused request:

```bash
aitbc bridge register-validator --chain-id bc-2 --address 0x0000000000000000000000000000000000000006 --public-key 0x020000000000000000000000000000000000000000000000000000000000000006 --private-key 0x1111111111111111111111111111111111111111111111111111111111111111 --admin-address 0x0000000000000000000000000000000000000004 --epoch 1 --rpc-url http://localhost:8202/rpc
```

**Expected output:** `Validator registration failed: Client error '403 Forbidden'`.

---

## Exit-class summary

| exit class | options |
|---|---|
| ok | `balance`/`pending`/`oracle-status`/`security-status`/`status` `--rpc-url` family, `pending --chain-id`, `deposits --status`/`--repo-root`, `sign-proof --output` |
| expected-refusal | `status --transfer-id` (404), `proof` anchor flags + `--rpc-url` (400), `deposits --tx-hash` (ledger rc 1), `lock --asset/--issued-at/--nonce` (422), `lock`/`unlock --wallet-name` (wallet not found, exit 1), `confirm --rpc-url` (422), `ingest-header --re-sign` (CLI abort, exit 4), `store-header`/`ingest-header`/`attest`/`register-validator` store and admin flags (403) |
| 🔒 by design | `confirm --confirmer-private-key`, `lock`/`unlock --wallet-password`, `ingest-header --private-key`, `register-validator --admin-private-key` |
| operator-only | `scripts/ops/bridge-admin.sh` `manual-payout` / `abandon-and-resign` / `write-off` — shell ops, not CLI options |

**Noise noted (not drift):** `deposits --tx-hash` on a node without
`/etc/aitbc/aitbc-bridge-monitor.env` prints the monitor's env-file
warning after the "no deposit row" line; the flag itself works.

---

## See Also

- **Scenario 20**: [Cross-Chain Transfer](./20_cross_chain_transfer.md)
- **Scenario 22**: [Bridge RPC Validation](./22_bridge_rpc_validation.md)
- **Scenario 75**: [Market Escrow & Jobs Options](./75_market_escrow_jobs_options.md)

---

*Last updated: 2026-10-26 (BRIDGE-OPTS-1 option coverage)*
*Version: 1.0*
