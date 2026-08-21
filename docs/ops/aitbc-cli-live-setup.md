# AITBC CLI live two-node setup

This guide is for operators who want to run the `aitbc` CLI against the live two-node deployment (`hub.aitbc.bubuit.net` and `aitbc3`).

## 1. Which node to use

- `hub.aitbc` — customer operations (`market list`, `ai submit --wait`, `dashboard customer`, `governance`).
- `aitbc3` — shop / provider operations (`dashboard shop`, `market offer`, `miner` workflows).
- `aitbc` CLI executable is installed at `/usr/local/bin/aitbc` on both nodes.

## 2. Coordinator API URL

The public `/v1/` path on `hub.aitbc.bubuit.net` is routed to the **agent coordinator**, not the coordinator API. Use `/c/v1/` for job and payment endpoints.

```bash
aitbc config set coordinator_api_url http://hub.aitbc.bubuit.net/c/v1
```

On `aitbc3` use the same URL for shop dashboard / marketplace interactions:

```bash
aitbc config set coordinator_api_url http://hub.aitbc.bubuit.net/c/v1
```

## 3. Generate a JWT

The coordinator uses HS256 and the `JWT_SECRET` from `/etc/aitbc/aitbc-coordinator-api.env`.

### Client JWT (customer / dashboard)

```bash
JWT_SECRET=$(grep '^JWT_SECRET=' /etc/aitbc/aitbc-coordinator-api.env | cut -d= -f2)
JWT=$(python3 -c "
import jwt, datetime
print(jwt.encode(
    {'sub': 'customer-wallet', 'role': 'client', 'type': 'access', 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)},
    '$JWT_SECRET',
    algorithm='HS256'
))
")
echo "$JWT"
```

### Miner JWT (shop dashboard)

```bash
JWT_SECRET=$(grep '^JWT_SECRET=' /etc/aitbc/aitbc-coordinator-api.env | cut -d= -f2)
JWT=$(python3 -c "
import jwt, datetime
print(jwt.encode(
    {'sub': 'aitbc-miner-1', 'role': 'miner', 'type': 'access', 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)},
    '$JWT_SECRET',
    algorithm='HS256'
))
")
```

Store the token:

```bash
aitbc config set-secret client "$JWT"
```

The shop dashboard currently uses the `client` credential slot. If you need a different role, store the miner token in the same slot:

```bash
aitbc config set-secret client "$JWT"
aitbc dashboard shop --miner-id aitbc-miner-1
```

## 4. Typical customer flow

```bash
ssh hub.aitbc
aitbc config set coordinator_api_url http://hub.aitbc.bubuit.net/c/v1
aitbc market list --sort reputation
aitbc ai submit --wait --model llama3.2:3b --prompt "Say hello" --output json
aitbc dashboard customer
```

## 5. Typical shop flow

```bash
ssh aitbc3
aitbc config set coordinator_api_url http://hub.aitbc.bubuit.net/c/v1
aitbc dashboard shop --miner-id aitbc-miner-1
```

## 6. Governance flow

Governance operates on `hub.aitbc`:

```bash
ssh hub.aitbc
aitbc governance propose --title "Increase max concurrent" --description "Raise pool hub limit" --params '{"target_service":"poolhub","parameter_name":"max_concurrent","new_value":8}'
aitbc governance vote --proposal-id <id> --vote for
aitbc governance close --proposal-id <id>
# Wait for the execution timelock to elapse, then:
aitbc governance execute --proposal-id <id>
```

If the off-chain execution fix is not yet deployed, the service may require `GOVERNANCE_REQUIRE_EXECUTION_TIMELOCK=false` in `/etc/aitbc/aitbc-governance.env`. This should only be used in development.

## 7. Troubleshooting

### 405 Method Not Allowed

You are using the public `/v1/` URL. Set `coordinator_api_url` to `http://hub.aitbc.bubuit.net/c/v1`.

### 401 Authentication required

Generate and store a JWT as shown above.

### Negative `units` or `duration_ms` in a receipt

This was a known bug where `job.requested_at` was stored as a naive local time and later interpreted as UTC. It has been fixed in the receipt service by:

- storing `requested_at` and `completed_at` as UTC;
- preferring `execution_time` from the miner result for `duration_ms`;
- clamping `units` and `price` to non-negative values.

If you still see negative values, check that both `aitbc3` and `hub.aitbc` are running the same coordinator build.

### Governance execution fails with "no on-chain block height"

After the off-chain execution fix, proposals created with `enable_onchain_submission=false` will record a block height from the chain RPC at creation time. Until then, the timelock can be disabled only on a development node.
