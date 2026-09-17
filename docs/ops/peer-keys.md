# Peer keys for island joining

Followers authenticate `POST /rpc/subscribe`, `POST /rpc/heartbeat`, and
`DELETE /rpc/lease/{node_id}` with an `X-API-Key` peer key. Two kinds exist:

## Fleet peer keys (operator-managed)

`BLOCKCHAIN_RPC_API_KEY_PEERS` in `/etc/aitbc/blockchain-secrets.env` is a
comma-separated list of trusted keys for the operator's own fleet. They are
**unbound** — any of them can manage any node's lease. They are loaded into a
frozenset at service start, so editing the list needs a
`systemctl restart aitbc-blockchain-rpc`.

## Issued peer keys (self-serve)

`POST /rpc/join {"node_id": "..."}` is public and issues a fresh key bound to
that node_id. Properties:

- **Bound**: the key only authorizes lease operations for its own `node_id`;
  any other node_id gets 403. This is what makes self-serve issuance safe —
  a leaked issued key can disturb only its own lease.
- **Hash-only storage**: the hub stores `sha256(key)` in
  `/var/lib/aitbc/data/peer_keys.db`; the plaintext is returned once.
- **Collision-safe**: a `node_id` that already has an active key gets `409`.
  Re-issuing requires an operator revocation first, so a node_id cannot be
  silently hijacked.
- **Capped**: rate-limited at the route plus per-IP and total issuance caps
  (`MAX_KEYS_PER_IP_PER_DAY`, `MAX_TOTAL_KEYS` in `peer_keys.py`).

Issued keys never reach `verify_rpc_api_key` routes (governance, chain
control, settlement, contracts, GPU) — the two dependencies stay separate.

## Operator commands

```bash
scripts/ops/manage-peer-keys.sh list           # active issued keys
scripts/ops/manage-peer-keys.sh list --all     # include revoked
scripts/ops/manage-peer-keys.sh show <node_id> # one node's record
scripts/ops/manage-peer-keys.sh revoke <node_id>  # revoke; node can re-join
```

## When to revoke

Revoke when a node_id was claimed by the wrong party, a joiner lost their key
(re-join after revoke issues a fresh one), or a node's key is suspected
leaked. Revoking does not disturb the node's existing lease immediately —
the lease expires on its own TTL — but the key can no longer extend it.
