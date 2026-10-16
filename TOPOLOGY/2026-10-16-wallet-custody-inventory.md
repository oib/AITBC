# Wallet custody inventory — 2026-10-16

WALLET-CUSTODY-1. Read-only inventory of every file wallet the `aitbc` CLI
and services resolve: `/root/.aitbc/wallets` (operator shell) and
`/var/lib/aitbc/wallets` (service accounts `aitbc`/`aitbc-wallet`, per
`cli/aitbc_cli/utils/wallet_paths.py`). No key, password or `.pw` content
was read; files were classified by JSON structure only (a `crypto`/`kdf`
block or an `encrypted: true` flag = encrypted; a bare `private_key`
field without either = plaintext; no `private_key` field at all =
watch-only/address-only). Balances/nonces are chain reads from the hub
RPC (`/rpc/account/<address>`); 1 AIT = 36,000,000 units.

| host | file (dir) | owner:mode | address | encrypted | `.pw` file | balance (AIT) | nonce | signs in a service/schedule |
|---|---|---|---|---|---|---|---|---|
| hub | `/var/lib/aitbc/wallets/default.json` | aitbc:640 | `0x02B8F2C6…4c5b` | watch-only (no key field) | — | 999,990.00 | 90 | no (address-only copy of the genesis address) |
| hub | `/var/lib/aitbc/wallets/ait-sell-escrow.json` | aitbc:600 | `0x40c7181b…1a07` | **plaintext** | — | 4.96 | 4 | yes — escrow settlement path (`aitbc-escrow-settlements` timer) |
| hub | `/var/lib/aitbc/wallets/ops.json` | aitbc:600 | `0xa7aD19da…51AF` | yes (`encrypted` flag) | `/root/.aitbc/wallets/.ops.pw` 600 | 50.00 | 1 | yes — `OPS_WALLET_PATH` env on hub |
| hub | `/var/lib/aitbc/wallets/sepolia.json` | aitbc:600 | `0xA556E238…74C` | yes (`encrypted` flag) | `/root/.aitbc/wallets/.sepolia.pw` 600 | 0 (no account) | — | yes — ETH/Sepolia lane wallet |
| hub | `/root/.aitbc/wallets/treasury.json` | root:600 | `0x716a5646…b1B8` | yes (`encrypted` flag) | `/root/.aitbc/wallets/.treasury.pw` 600 | 0.0028 | 0 | no service reference found |
| hub | `/root/.aitbc/wallets/ipfsbuyer.json` | root:600 | `0x4059cf2e…4443` | **plaintext** | — | 4.76 | 6 | no service reference found |
| hub1 | `/var/lib/aitbc/wallets/default.json` | aitbc:640 | `0x02B8F2C6…4c5b` | watch-only (no key field) | — | (same as hub — same address) | — | no |
| hub1 | `/var/lib/aitbc/wallets/sepolia.json` | root:600 | `0x86FAA186…01C` | yes (`encrypted` flag) | `/root/.aitbc/wallets/.sepolia.pw` 600 | 0 (no account) | — | yes — ETH/Sepolia lane wallet |
| hub1 | `/root/.aitbc/wallets/agentbuyer.json` | root:644 | `0x493890fa…5eDf` | **plaintext** | — | 4.38 | 5 | no service reference found |
| node0 | `/var/lib/aitbc/wallets/default.json` | aitbc:640 | `0x08aB8011…435` | **plaintext** | — | 95.62 | 89 | yes — `aitbc-wallet` daemon `WALLET_DIR` (CLI default) |
| node0 | `/var/lib/aitbc/wallets/sepolia.json` | root:600 | `0xF1C83cd9…584` | yes (`encrypted` flag) | `/root/.aitbc/wallets/.sepolia.pw` 600 | 18.87 | 0 | yes — ETH/Sepolia lane wallet |
| node1 | `/var/lib/aitbc/wallets/default.json` | aitbc:640 | `0xBdDF2791…4F7` | **plaintext** | — | 99.94 | 10 | yes — `aitbc-wallet` daemon `WALLET_DIR` (16 Oct vote smoke signer) |
| node1 | `/var/lib/aitbc/wallets/sepolia.json` | root:600 | `0xFdE0fBa0…754c1` | yes (`encrypted` flag) | `/root/.aitbc/wallets/.sepolia.pw` 600 | 0 (no account) | — | yes — ETH/Sepolia lane wallet |
| node2 | `/var/lib/aitbc/wallets/default.json` | aitbc:640 | `0x4A5b3bf9…5D2` | **plaintext** | — | 75.32 | 89 | yes — `aitbc-wallet` daemon + `aitbc-miner` (active on node2) |
| node2 | `/var/lib/aitbc/wallets/sepolia.json` | root:600 | `0xCf171914…26E3` | yes (`encrypted` flag) | `/root/.aitbc/wallets/.sepolia.pw` 600 | 0.46 | 4 | yes — ETH/Sepolia lane wallet |
| node2 | `/root/.aitbc/wallets/canary9.json` | root:644 | `0xF4924759…B7Df` | **plaintext** | — | 4.95 | 18 | no service reference found |
| node2 | `/root/.aitbc/wallets/v4probe.json` | root:644 | `0x9061496D…8920` | **plaintext** | — | 0 (no account) | — | no service reference found |

## Surprises and notes

- **`hub /var/lib/aitbc/wallets/ait-sell-escrow.json` is plaintext** and is
  the key for the sell-escrow address the SD-5 alert watches (178,560,000
  units ≈ 4.96 AIT on the chain side). It sits next to the encrypted ops
  wallet and is `aitbc:600` — plaintext, but not world-readable.
- **`hub`/`hub1` `default.json` carry no `private_key` at all** — they are
  watch-only copies of the genesis address `0x02B8F2C6…4c5b` (~999,990
  AIT), consistent with the O-7b finding that the key is gone from hub's
  node env. No key to protect; nothing to encrypt.
- `hub /root/.aitbc/wallets/treasury.json` is a *different* address
  (`0x716a5646…b1B8`, ~0.0028 AIT) from the genesis `0x02B8…` — already
  encrypted.
- All five `sepolia.json` files and hub `ops.json`/`treasury.json` carry
  the `encrypted: true` flag with matching `.pw` files at
  `/root/.aitbc/wallets/.<name>.pw` (mode 600). No `.pw` content read.
- `node0/node1/node2` `/var/lib/aitbc/wallets/default.json` are the
  plaintext workhorse wallets the CLI resolves through `aitbc-wallet`'s
  `WALLET_DIR`; node1's signed the 16 Oct vote smoke.
- `node2` env sets `AITBC_DEFAULT_WALLET=my-agent-wallet` — no
  `my-agent-wallet.json` exists on node2 (dangling default).
- Root-dir plaintext wallets on node2 (`canary9`, `v4probe`) and hub1
  (`agentbuyer`) are mode 644 — world-readable on the box. Small
  balances; node2 `v4probe` has no on-chain account at all.
- Nonce note: `node0 default` nonce 89 and `node2 default` nonce 89 —
  different wallets, coincidentally equal.

## Per-wallet recommendation (inventory only — operator decides)

- `ait-sell-escrow.json` (hub): **recommended: encrypt** — holds the
  escrow-signing key for a watched float; plaintext on a service
  account. (Or accept: it is `aitbc:600` on a single-operator fleet.)
- `default.json` (node0/node1/node2): **recommended: encrypt** — each
  holds ~75–100 AIT and signs via the wallet-daemon path; plaintext.
  (Or accept: the same files have been plaintext since deployment.)
- `ipfsbuyer.json` (hub), `agentbuyer.json` (hub1), `canary9.json`,
  `v4probe.json` (node2): **recommended: accept** — small balances,
  no service binding; at most tighten modes 644→600.
- `hub`/`hub1` `default.json` (watch-only `0x02B8…`): **recommended:
  accept** — no key material in the file.
- `sepolia.json` (all hosts), `ops.json`, `treasury.json` (hub):
  **already encrypted** — accept as-is.

Operator decision (16 Oct): accept plaintext — inventory documents the
state; no encryption or rotation performed by this task.
