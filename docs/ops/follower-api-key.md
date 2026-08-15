# Which key goes in the public bootstrap file

The hub serves `https://hub.aitbc.bubuit.net/agent/blockchain.env` to the world. Every island
reads it unauthenticated, so anything in it is public — treat a value written there as
published the moment the file is saved, not when someone first fetches it.

## `FOLLOWER_API_KEY` — publish this one

It is accepted by exactly two endpoints:

- `POST /api/v1/agent/coin-requests/register`
- `POST /api/v1/agent/coin-requests/execute`

Both are bounded by the hub's own records rather than by the caller's word. `/execute` takes
the amount and destination from the stored row, so holding the key does not let anyone name a
payment (V23-62). `/register` writes rows the faucet policy has ruled on: one automatic grant
per agent *and* per destination wallet, counted canonically, up to `FAUCET_AUTO_APPROVE_MAX`
(V23-67). Everything else waits for an operator.

That is what makes it safe to publish. A holder can ask for a first grant to a wallet, which
is the point of a faucet, and cannot do anything else.

## `COORDINATOR_API_KEY` and `SECRET_KEY` — never publish these

The name suggests a coordinator credential. It is broader:

| Surface | What the key grants |
| --- | --- |
| `/coin-requests/register`, `/coin-requests/execute` | Same as the follower key. |
| `WS /api/v1/agent/messages/stream` | `agent_id` is a query parameter and the key is the only check, so the holder connects **as any agent**. That path reaches `request_coins_handler`, which signs and submits a treasury transfer on the spot rather than writing a row for review. |
| coordinator-api miner, settlement and marketplace routers | `require_miner_api_key` falls back to `COORDINATOR_API_KEY` when `miner_api_keys` is empty — the default. |

`_require_api_key` accepts `COORDINATOR_API_KEY` **or** `SECRET_KEY`, so withholding one while
publishing the other gains nothing. Check they are not the same value:

```bash
for k in COORDINATOR_API_KEY SECRET_KEY; do grep -m1 "^$k=" /etc/aitbc/blockchain-secrets.env | cut -d= -f2- | sha256sum | cut -c1-12; done
```

Two identical hashes mean publishing either one published both.

## Setting it up

1. Generate a follower key, distinct from every other key on the hub:

   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

2. Put it in the hub's private environment as `FOLLOWER_API_KEY` and restart the agent
   coordinator.
3. Put the **same value** in the public `blockchain.env`, and remove `COORDINATOR_API_KEY`
   from that file.
4. Rotate `COORDINATOR_API_KEY` and `SECRET_KEY`, since both have been published. Distribute
   the new values out of band to hub operators only.
5. Set `MINER_API_KEYS` explicitly so miner access stops depending on the coordinator key.
   Until you do, the coordinator logs a warning on every miner request that relies on the
   fallback.

## For island operators

Read `FOLLOWER_API_KEY` from the hub's bootstrap file and put it in your own
`/etc/aitbc/blockchain.env`. The CLI prefers it over the hub keys automatically. If you have
been given a `COORDINATOR_API_KEY`, you were given more authority than the work needs — ask
for a follower key instead.
