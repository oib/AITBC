# Per-node Sepolia ETH wallets (ETH-1)

Operator decision 2026-10-13: each of `hub`, `hub1`, `node0`, `node1`,
`node2` gets its own Sepolia ETH wallet so the ETH↔AIT bridge can be
exercised end-to-end without touching the bridge wallet itself. This page
is the custody recipe; the buy/sell plays live in
[scenario 59](../scenarios/59_sepolia_buy_sell_ait.md).

## Hard rules

- **Never a chain validator key.** AITBC validator/PBFT keys are a
  different identity set (`VALIDATOR_SET`/`VALIDATOR_KEYS`); a Sepolia
  wallet key must never be copied into a validator slot or vice versa.
- **Never the bridge wallet.** The bridge wallet is `0x310dcE…8781`
  (`ETH_WALLET_ADDRESS` on hub, key `keys/kr0/eth_wallet.key` on the IDE
  host). Per-node wallets are *counterparties* to it, never copies or
  siblings of it.
- **Only the address is ever printed.** The commands below print the
  `0x…` address and nothing else. The private key never leaves the
  wallet file — not to stdout, not to a log, not into chat or a ticket.
- **No keys in env files.** There is deliberately **no**
  `SEPOLIA_PRIVATE_KEY` variable anywhere. If a service ever needs to
  sign with one of these keys it must read the wallet file — never an
  `*_PRIVATE_KEY` env entry under a generic or per-host name.
- **Address variables are public data.** The *addresses* may be carried
  in env files or inventory docs under per-host names
  (`SEPOLIA_ADDR_HUB`, `SEPOLIA_ADDR_HUB1`, `SEPOLIA_ADDR_NODE0`,
  `SEPOLIA_ADDR_NODE1`, `SEPOLIA_ADDR_NODE2`) — an address leaks nothing.
- Chain keys and ETH keys stay separate: the `sepolia` wallet is the
  node's Ethereum-side identity; on the AITBC side the same secp256k1
  key derives the same `0x` address, which is *also* a valid AIT wallet —
  that reuse is intended (it is how `aitbc wallet bridge deposit` binds
  ETH sender to AIT recipient) and is unrelated to validator identity.

## Creating a key on a host — prints the address only

Same custody pattern as the ops signer
([ops-signer-install-checklist.md](ops-signer-install-checklist.md)):
an encrypted wallet file in `/var/lib/aitbc/wallets/`, mode `0600`,
root-readable.

Run **on each host** as root:

```bash
cd /opt/aitbc
install -d -m 700 -o root -g root /var/lib/aitbc/wallets
AITBC_WALLET_DIR=/var/lib/aitbc/wallets \
  venv/bin/python -m aitbc_cli wallet create --name sepolia
chmod 600 /var/lib/aitbc/wallets/sepolia.json
AITBC_WALLET_DIR=/var/lib/aitbc/wallets \
  venv/bin/python -m aitbc_cli wallet --wallet-name sepolia address
```

- `wallet create` prompts twice for a password (typed, never echoed —
  the key is encrypted at rest), then prints `{name, type, address,
  path}`. No key material ever reaches stdout.
- `wallet address` re-prints only `{"wallet": "sepolia", "address":
  "0x…"}` — the line to copy into the inventory below.
- The unit-level `ProtectHome=yes` on some services makes `/root/.aitbc`
  invisible; that is why the file must land under
  `/var/lib/aitbc/wallets/` via `AITBC_WALLET_DIR`, not the CLI default.
- The password is an operator-side secret: keep it in the operator's
  password store under a per-host entry, not on the node.

## Custody inventory rows

Add these rows to the operational inventory
(`docs/design/key-custody-proposal.md`, new tier "T4 — per-node Sepolia
operational wallets") after each host is done:

| host | file (0600 root) | address | address variable | faucet target |
|---|---|---|---|---|
| hub   | `/var/lib/aitbc/wallets/sepolia.json` | `0x…` | `SEPOLIA_ADDR_HUB`   | 0.005 ETH |
| hub1  | `/var/lib/aitbc/wallets/sepolia.json` | `0x…` | `SEPOLIA_ADDR_HUB1`  | 0.005 ETH |
| node0 | `/var/lib/aitbc/wallets/sepolia.json` | `0x…` | `SEPOLIA_ADDR_NODE0` | 0.010 ETH |
| node1 | `/var/lib/aitbc/wallets/sepolia.json` | `0x…` | `SEPOLIA_ADDR_NODE1` | 0.005 ETH |
| node2 | `/var/lib/aitbc/wallets/sepolia.json` | `0x…` | `SEPOLIA_ADDR_NODE2` | 0.005 ETH |

## Faucet funding — operator action

Sepolia ETH is free testnet value from a public faucet (e.g. the Google
Cloud web3 faucet, the Alchemy Sepolia faucet, or a PoW faucet — pick any
that is dispensing). Funding is the operator's browser/wallet action;
there is no CLI command and none is wanted.

Per-role amounts (rationale):

- **node0 — 0.010 ETH**: it is the Scenario-A deposit side; the amount
  covers ~3 test deposits at 0.002 ETH plus gas (~100k gas each) with
  margin.
- **node2 — 0.005 ETH**: the Scenario-B *receiver* — receiving ETH needs
  no balance at all; the buffer lets node2 send it back or pay gas for a
  follow-up leg if ever needed.
- **hub, hub1, node1 — 0.005 ETH each**: readiness wallets with no
  scenario role yet; enough for a future smoke send.

Total faucet ask ≈ 0.030 Sepolia ETH.

## Reading a balance — read-only public RPC

`scripts/ops/sepolia_balance.py` is stdlib-only, uses no keys and reads
no environment variables. Both queries run at block tag `latest`
(confirmed state):

```bash
# on the host (or anywhere with outbound https):
cd /opt/aitbc
venv/bin/python scripts/ops/sepolia_balance.py 0x<node0-address>
# 0x…  0.01 ETH  nonce=0

# explicit endpoint + all five addresses + bridge float in one pass:
venv/bin/python scripts/ops/sepolia_balance.py \
  --rpc-url https://ethereum-sepolia-rpc.publicnode.com \
  $SEPOLIA_ADDR_HUB $SEPOLIA_ADDR_HUB1 $SEPOLIA_ADDR_NODE0 \
  $SEPOLIA_ADDR_NODE1 $SEPOLIA_ADDR_NODE2 \
  0x310dcE00270D0aC10CAccfBD636Ff07BD5648781
# --json for machine-readable rows
```

`nonce` is the confirmed outbound transaction count
(`eth_getTransactionCount` at `latest`); a pending send shows as a
balance drop before the nonce moves.

## What these wallets are *not* for

- No mainnet use, ever — the recipe and amounts above are Sepolia-only.
- No AITBC validator duty, no bridge duties, no payout/refund signing —
  those stay with the T1 authority set in the custody inventory.
- No service env wiring: nothing references `SEPOLIA_*` yet; any future
  consumer binds the *address* variable, never a key variable.
