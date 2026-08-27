# Validator / Recovery Key Rotation Process (G6)

**Version**: v0.24.0-g6
**Last Updated**: 2026-08-25
**Status**: Committed process; live key material is *not* in git.

---

## What this is

This document defines the canonical, operator-reviewed process for rotating the
blockchain validator private key and the recovery key used to restore a
validator's signing capability after a host compromise, hardware failure, or
planned hand-off.  It deliberately does **not** contain the live key itself.

The live key material lives only in host-local secrets under `/etc/aitbc/`
and, if used, an external secrets manager.  The repository contains only the
process, an annotated environment template, and an audit log entry convention.

## Why the live key must not be committed

- Private keys in git are recoverable from any clone, forever, even after
deletion (`git revert`/`git filter-repo` are not free on a published public
mirror).
- AITBC has a GitHub public mirror (`oib/AITBC`); an accidental commit of a
validator key to Gitea would be mirrored and exposed.
- `/etc/aitbc/validator-key-rotation.env.example` in this directory is the
**only** git-tracked form; it contains placeholders, never values.

## Key roles

| Role | Example env var | Purpose | Where it lives |
|---|---|---|---|
| Validator private key | `VALIDATOR_PRIVATE_KEY` | Signs proposed blocks and bridge multi-sig messages. | Host `/etc/aitbc/blockchain.env` or secrets manager. |
| Validator address | `VALIDATOR_ADDRESS` / `VALIDATOR_PUBLIC_KEY` | Public identity in `VALIDATOR_SET`. | Git-tracked template + live config. |
| Recovery / admin key | `BRIDGE_ADMIN_PRIVATE_KEY`, `ESCROW_RELEASE_PRIVATE_KEY` | Bridge admin, escrow release, validator recovery. | Host `/etc/aitbc/blockchain.env` or secrets manager. |
| Genesis / settlement key | `GENESIS_PRIVATE_KEY`, `GENESIS_WALLET_PRIVATE_KEY` | Chain bootstrap and escrow settlement. | Hub only, host-local. |

## Rotation process

### 1. Announce and freeze block production

1. Choose a maintenance window.
2. Notify operators on `aitbc1` and `hub.aitbc`.
3. Confirm all chain services are healthy:
   `systemctl is-active aitbc-blockchain-node` on both hosts.

### 2. Generate the new keypair

Run from an operator workstation (not a shared repo checkout):

```bash
python3 - <<'PY'
from aitbc.crypto.crypto import generate_keypair
priv, pub, addr = generate_keypair()
print(f"private_key={priv}")
print(f"public_key={pub}")
print(f"address={addr}")
PY
```

Do **not** save this output in a shell history file.  Write it directly into
your password manager or secrets manager.

### 3. Stage the new validator

1. Add the new public address to `VALIDATOR_SET` in `/etc/aitbc/blockchain.env`
on every node that needs to know the validator set (hub, aitbc1, aitbc3).
2. Keep the **old** key active until the new one has produced at least one block.
3. Restart `aitbc-blockchain-node` on the affected node with the new
`VALIDATOR_PRIVATE_KEY`.

### 4. Confirm the new key is signing

```bash
ssh aitbc1 'curl -s http://localhost:8202/rpc/chain/latest'
ssh hub.aitbc 'curl -s http://localhost:8202/rpc/chain/latest'
```

Verify that the `proposer` in the latest block is the new validator address or
that attestations include it.

### 5. Retire the old key

1. Remove the old address from `VALIDATOR_SET` on all nodes.
2. Remove the old `VALIDATOR_PRIVATE_KEY` from the host's env file.
3. Restart `aitbc-blockchain-node` on the node whose key was rotated.

### 6. Record the rotation

Append to `SECRET_ROTATION_LOG.md` in this directory (do **not** include the
private key):

```markdown
## 2026-08-25 — Validator key rotation for <node>

- Rotated address: `0x<...>` (public only)
- Old address: `0x<...>` (public only)
- Reason: planned recovery / incident recovery / host migration
- Nodes touched: hub.aitbc, aitbc1
- Services restarted: aitbc-blockchain-node
- Operator: <name>
```

## Emergency: restore a lost validator key

If the only copy of a validator private key is lost and it is not recoverable
from the other host:

1. The validator set must be updated on-chain or in the operator config.
2. If the remaining validators still have quorum, follow the rotation process
above to introduce a new validator and retire the lost one.
3. If quorum is lost, the chain must be recovered from the latest trusted backup
or a coordinated hard-fork must be executed.  This is a human/operational
procedure, not a single CLI command.

## What goes in git

- This process document (`validator-key-rotation.md`).
- The environment template (`validator-key-rotation.env.example`).
- The public `VALIDATOR_SET` list used at chain start (no private keys).
- Any migration scripts that read the live key from the host at runtime
(`scripts/migrate_validator_set.py`).

## What does NOT go in git

- `VALIDATOR_PRIVATE_KEY`.
- `GENESIS_PRIVATE_KEY`, `GENESIS_WALLET_PRIVATE_KEY`.
- `ESCROW_RELEASE_PRIVATE_KEY`.
- `BRIDGE_ADMIN_PRIVATE_KEY`.
- Any exported wallet JSON or keystore.
- Shell history containing key material (clear after rotation).

## Related files

- `docs/operations/SECRET_ROTATION.md`
- `docs/operations/SECRET_ROTATION_LOG.md`
- `docs/operations/validator-key-rotation.env.example`
- `docs/security/bridge-custodian.md`
- `apps/blockchain-node/src/aitbc_chain/consensus/poa.py`
