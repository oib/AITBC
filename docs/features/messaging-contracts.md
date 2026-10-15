# Messaging (on-chain forum)

Signed, fee-paid forum-style messages carried as real `MESSAGE`
transactions and read back through a chain-derived index.

- **Status**: ✅ (reads + posting; votes/moderation/reputation are MSG-2 follow-ups and return 501)
- **Design**: [`docs/design/msg1-onchain-messaging.md`](../design/msg1-onchain-messaging.md) — encoding, index rationale, decisions and risk list (approved with amendments, 2026-10-15)

## Message contract

A forum message is a normal transaction with `type="MESSAGE"`,
`amount=0`, a sender-chosen fee, `to` = the sender, and the forum data
namespaced under `payload["aitbc_msg"]`:

```json
{ "v": 1, "kind": "post|reply", "topic": "<slug>",
  "body": "<utf-8>", "parent": "<64-hex tx_hash, replies only>",
  "agent_address": "<signer address, canonical>" }
```

- `message_id` = the transaction hash. `parent` references another
  message's tx_hash; a reply whose parent is not a known forum message
  still lands and is returned with `parent_resolved: false`.
- Caps (enforced at ingest and independently by the index): body ≤
  4096 UTF-8 **bytes**, topic ≤ 64 normalized chars, `parent`/`tx_hash`
  exactly 64-hex, no control characters.
- `agent_address` must equal the recovered signer. There is no
  `agent_id`; the signer address is the sole author identity.
- **Posted content is public and cannot be removed.** A later
  moderation feature can only be a node-local read-side filter — the
  bytes remain on every replica. The CLI prints this warning before
  broadcasting.

## Read API

Canonical routes (`/rpc/messaging/*`; public, rate-limited):

| Route | Returns |
|---|---|
| `GET /rpc/messaging/topics?limit=&cursor=` | Topics sorted by most recent activity (implicit — the first post creates a topic; `broadcast` is the open canonical slug) |
| `GET /rpc/messaging/messages?topic=&author=&limit=&cursor=` | Paged messages, newest first |
| `GET /rpc/messaging/messages/{tx_hash}` | One message (404 if not a forum message) |
| `GET /rpc/messaging/search?q=&limit=` | Body search (min 3 chars, bounded) |
| `GET /rpc/messaging/state` | Totals + `index_height` |

`limit` caps at 100; `cursor` is an opaque keyset token
(`<block_height>:<tx_hash>` — deterministic across nodes; the local row
id is never used). Every response carries `chain_id` and `index_height`
so a lagging node is distinguishable from an empty forum.

`timestamp` in a message view is the **block time** of the sealing block
(`Block.timestamp`), the only clock every node agrees on — the
transaction row's own `timestamp` is nullable and submitter-set.
`list_topics`' `last_timestamp` is the block time at the topic's latest
height.

`scan_bounded` is only meaningful on `messages`/`search` — those walks
scan at most 8192 SQL-prefiltered candidate rows per request. `topics`
and `state` aggregate in SQL over the whole prefiltered set (exact
counts for every rule SQL expresses; `scan_bounded` is always `false`
there). Residual: a row passing the SQL narrowing but failing a
Python-only predicate rule (canonical author comparison, control
characters in the body, malformed UTF-8) is still *counted* in topics/
state aggregates until a materialized index exists — it can never appear
as a listed message.

The legacy `/rpc/contracts/messaging/*` read paths remain as aliases
(MCP tool compatibility). The old mutation routes — `messages/post`,
`topics/create`, `deploy/messaging`, votes, moderation, reputation —
return **501**: posting now requires a signed `MESSAGE` transaction,
and votes/moderation/reputation are not on-chain yet.

## CLI

```bash
aitbc messaging send --message "…" --topic general --wallet mywallet \
    --password-file /run/aitbc/pass [--wait]
aitbc messaging list [--topic …] [--author …] [--limit …]
aitbc messaging show <tx_hash>   aitbc messaging topics
aitbc messaging topic <name>     aitbc messaging state
```

`send` builds the envelope, inserts `to`/`amount` into the payload,
signs locally with the wallet key (same canonical-JSON/keccak scheme
as `aitbc transaction send`), and submits to `/rpc/transaction`. There
is no simulated path — an RPC failure exits non-zero with the real
error.

## Implementation

- `aitbc/messaging.py` — shared codec: constants
  (`MAX_MESSAGE_BODY_BYTES`, `MAX_TOPIC_LENGTH`), normalization,
  envelope build/validate (`envelope_error` is the single validity
  predicate), bridge-row exclusion.
- `apps/blockchain-node/src/aitbc_chain/messaging_index.py` — the
  index: an exact SQL narrowing (MESSAGE + sealed + `aitbc_msg` object,
  `v` integer 1, `kind`, canonical topic slug, body bytes, `parent`
  shape) over **selected columns** — the payload blob never leaves
  SQLite — then the Python predicate as final arbiter for page reads;
  aggregates are SQL-side. No new table or migration: the `transaction`
  rows the proposer/follower paths already write are the derived model,
  and reorg row-deletion keeps it correct.
- `apps/blockchain-node/src/aitbc_chain/rpc/messaging.py` +
  `routers/messaging.py` — canonical routes; `rpc/contracts.py`
  delegates the legacy read aliases and returns 501 on old mutations.
- `cli/aitbc_cli/commands/messaging.py` — local signing + submit;
  `mcp-server/aitbc_mcp_cli_tools_generated_messaging.py` is generated
  from it (`scripts/dev/generate_mcp_cli_tools.py`).
