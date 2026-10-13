# Key custody proposal — plaintext keys on the operator workstation (K-4)

Status: proposal, 2026-10-12. Nothing here has been executed; every step
that needs a passphrase or moves value is marked **operator** and is
deliberately not automated.

This document contains **no key material**: no private keys, no
mnemonics, no passwords, and no long hex strings. Keys are identified by
path and derived address only.

## Inventory (IDE workstation, 2026-10-12)

Scope scanned: `/opt/aitbc`, `/home/oib/windsurf/aitbc` (incl. `keys/`
and `backups/`). Every plaintext key found lives under
`keys/` or `backups/`; the `/opt/aitbc` checkout holds none. All key
files are already `600`/`700` after this round's tightening pass.

### Tier T0 — treasury

| file | address | on-chain balance |
|---|---|---|
| `keys/treasury_cold.key` | `0x34FFfAd1…` (`escrow_fee_recipient`) | **≈ 999,997,592 AIT** |

The single largest concentration of value in the fleet sits in one
67-byte plaintext file on one workstation. `keys/treasury_offline.key`
(20 bytes, opaque non-hex content) is **not** a usable copy — no
verified offline/encrypted copy of the treasury key was found in scope.

### Tier T1 — live authority and validator keys (`keys/kr0/`)

| file | address | role |
|---|---|---|
| `validator_hub.key` | `0x2aD5…` | live PBFT validator |
| `validator_node1.key` | `0x19f0…` | live PBFT validator |
| `validator_node2.key` | `0xE894…` | live PBFT validator |
| `validator_hub1.key` | `0x5E8E…` | live PBFT validator |
| `executor_new.key` | `0xFa80…` | governance executor (≈268 AIT) |
| `settlement_authority.key` | `0x1174…` | escrow settlement authority (≈0.9 AIT) |
| `settlement_signer.key` | `0x63C0…` | settlement signer |
| `bond_slash_authority.key` | `0x9aCC…` | bond slash authority (≈300 AIT) |
| `bridge_release_authority.key` | `0xCA78…` | bridge release authority |
| `bridge_payout.key` | `0x356d…` | bridge payout float (≈747 AIT) |
| `eth_wallet.key` | `0x310d…` | ETH-side wallet (bridge ops) |
| `hub1_bridge_validator.key` | `0x39D1…` | bridge validator |

Thirteen live keys in plaintext on one host: validator compromise stalls
consensus; executor/authority compromise can move funds or parameters.

### Tier T2 — funded service/test wallets

| file | address | on-chain balance |
|---|---|---|
| `keys/node1-service_accounts-*.json` | 11 embedded keys | **≈ 1,000,000 AIT each** |
| `backups/genesis-wallet.json`, `backups/temp-agent.json` | `0x9Ea1…` (hub1 retired validator wallet) | ≈ 1,000,000 AIT |
| `keys/executor_offline.key` | `0x04fE…` | ≈ 4,998 AIT |
| `keys/validator_hub_old.key`, `keys/keystore_genesis.json` (pbkdf2, encrypted) | `0x02B8…` | ≈ 1,000 AIT |
| `keys/executor2_offline.key`, `kr0/validator_*.key` balances | `0xD9CC…` etc. | ≈ 1,000 AIT each |
| `keys/governance_proposer.key` | `0xD816…` | ≈ 100 AIT |
| `keys/escrow_fee_recipient.json`, `backups/fleet-20261004/hub-wallets/treasury.json` | `0x716a…` (old fee recipient) | 99,457 units |
| `keys/bridge_release_old.key` | `0x2b0F…` | 50 AIT |

The service-account JSON and the two wallet JSONs hold **plaintext
`private_key` fields** — each account carries a faucet-scale test
balance. Other `*_old` keys derive to empty or dust accounts.

### Other items noted (not plaintext keys)

- `keys/keystore_genesis.json` — pbkdf2-encrypted keystore of
  `0x02B8…` (already protected).
- Password files exist in `keys/` and inside backup tarballs — counted,
  never opened.
- `keys/bridge-reg-blobs/*.json` — address+pubkey+signature only; public.
- Backup tarballs (`backups/fleet-2026*/`, `keys/keystore-pre-removal-*`,
  `keys/kr7-bak-custody/`) — per-host keystore/env archives, all mode
  600. They replicate the same material in compressed form.

### Planned tier T4 — per-node Sepolia operational wallets (ETH-1)

Operator decision 2026-10-13: one dedicated Sepolia ETH wallet per host,
for ETH↔AIT bridge scenario work only. Keys are created *on* the host
(encrypted wallet file, `0600` root, `/var/lib/aitbc/wallets/
sepolia.json`); only the address is ever recorded. Recipe:
[docs/ops/node-sepolia-wallets.md](../ops/node-sepolia-wallets.md).

| host | address | custody | faucet target |
|---|---|---|---|
| hub   | `SEPOLIA_ADDR_HUB`   (TBD at creation) | host-local, no IDE copy | 0.005 ETH |
| hub1  | `SEPOLIA_ADDR_HUB1`  (TBD at creation) | host-local, no IDE copy | 0.005 ETH |
| node0 | `SEPOLIA_ADDR_NODE0` (TBD at creation) | host-local, no IDE copy | 0.010 ETH |
| node1 | `SEPOLIA_ADDR_NODE1` (TBD at creation) | host-local, no IDE copy | 0.005 ETH |
| node2 | `SEPOLIA_ADDR_NODE2` (TBD at creation) | host-local, no IDE copy | 0.005 ETH |

These keys are never chain validator keys and never the bridge wallet;
no `*_PRIVATE_KEY` env variable exists for them anywhere.

## Custody tiers

**T0 — treasury (`0x34FFfAd1…`).** One plaintext file must not stay the
only copy. Proportionate custody: an **encrypted copy on offline,
air-gapped storage** (a dedicated USB stick kept physically separate
from the workstation), plus a recorded checksum of the *ciphertext*
(never of the key). The plaintext file on the workstation remains the
working copy until the operator confirms the offline copy restores.

**T1 — live authority/validator keys.** These must exist on the
validators/hosts that run them, but `kr0/` on the workstation is the
master set. Proportionate custody: **one encrypted archive of `kr0/`**
on the same offline medium as T0 (or a second stick), refreshed after
every rotation. Day-to-day host copies stay in `/var/lib/aitbc`
keystores, mode 600, service-owned.

**T2 — funded service/test wallets.** ≈ 12,000,000 AIT of
faucet/test value across the service-account JSON and the retired hub1
validator wallet. These are testnet-commodity funds, but an attacker
could drain them to grief the fleet's faucet economics. Proportionate
custody: keep them where they are (600/700 is now uniform), add them to
the same encrypted archive, and consider unwinding unused 1M-AIT
balances back to the treasury or faucet wallet (operator decision — a
chain write, out of scope here).

**T3 — retired/empty keys.** Keep for audit; no extra custody needed.
If the operator prefers, the whole tier can move into the encrypted
archive and be deleted from the live dir — that deletion is the
operator's, not the agent's.

## How the encrypted copy is made and proven

Recommended tooling: `age -p` (passphrase-encrypted, small, auditable)
or `gpg -c --cipher-algo AES256`. `eth-account` keystore JSON
(`Account.encrypt`) is an alternative per-key format; for a directory
archive, `age -p` on a tar is simplest.

**Operator steps (passphrase never touches an agent):**

1. On the workstation, create the archive:
   ```bash
   cd /home/oib/windsurf/aitbc
   tar cf - keys | age -p > keys-$(date +%Y%m%d).tar.age
   # type the passphrase at the prompt; it never appears on the command line
   ```
2. Record the checksum of the *ciphertext* — safe to store anywhere:
   ```bash
   sha256sum keys-*.tar.age >> keys/SHA256SUMS
   ```
3. Copy the `.tar.age` file (not the plaintext) to offline USB media;
   store the media separately from the workstation.
4. Prove the copy *before* trusting it, on any machine:
   ```bash
   age -d keys-*.tar.age | tar -tf - | head    # lists names only
   ```
5. **Test spend** (the verify step): restore `treasury_cold.key` from
   the archive on a scratch path, derive the address in memory and check
   it equals `0x34FFfAd1…`, then sign one small test transfer (e.g.
   0.01 AIT) to an address the operator controls — for example the
   faucet wallet — and confirm it seals. A successful small spend proves
   the archive decrypts to the controlling key.
6. Only after the test spend seals: decide whether the workstation
   plaintext stays (working copy) or the dir is pruned to the archive.

## Faucet discipline (carried from the task)

Keep faucet funds small and topped up from the treasury on a schedule,
so a faucet compromise has a bounded cost. Concrete form: faucet wallet
holds ≤ an agreed ceiling; a periodic operator-run top-up uses the
treasury key on the workstation; the offline archive is only ever opened
for restore drills.

## What an agent may and may not do here

Agents may: inventory, derive addresses, read balances, tighten modes,
keep this document current. Agents may not: create the encrypted copy,
type or store the passphrase, make the test spend, move any funds, or
delete key material. Those are the operator's steps, in order, above.
