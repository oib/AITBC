# Messaging index operability runbook (MSG-6)

The forum/messaging index is **derived state**: a read-side query over the
sealed `transaction` rows, rebuilt on every read. It cannot be corrupted by
a restart, and it has no table of its own to repair. Everything below is
read-only diagnosis; never "fix" a symptom by restarting first — a restart
changes nothing the index derives and destroys the evidence.

## Metrics

All exported from each node's `/metrics` endpoint, prefix `aitbc_messaging_`:

| metric | kind | meaning |
|---|---|---|
| `aitbc_messaging_index_height{chain_id}` | gauge | sealed block height the index has read |
| `aitbc_messaging_chain_head_height{chain_id}` | gauge | local chain head |
| `aitbc_messaging_index_lag_blocks{chain_id}` | gauge | head − index height |
| `aitbc_messaging_messages_total{chain_id}` | gauge | valid post/reply rows in the index |
| `aitbc_messaging_actions_total{chain_id}` | gauge | valid MSG-2 action rows |
| `aitbc_messaging_checkpoint_height{chain_id}` | gauge | latest digest checkpoint (multiples of 1000) |
| `aitbc_messaging_index_digest{chain_id, checkpoint, digest}` | gauge | value always 1; the digest is a label |
| `aitbc_messaging_reads_total{route}` | counter | successful `/rpc/messaging/*` reads |
| `aitbc_messaging_read_errors_total{route}` | counter | failed reads (4xx and 5xx) |
| `aitbc_messaging_rejected_total{reason}` | counter | envelopes refused at admission, coarse reason |

The checkpoint digest is a SHA-256 over the valid messaging envelopes at or
below the checkpoint height, in canonical `(block_height, tx_hash)` order,
computed lazily at scrape/read time and cached per (chain, checkpoint,
index-head hash). Two nodes that sealed the same rows derive the same
digest; row insertion order and rowids never enter.

The same numbers are available without Prometheus:

```bash
aitbc messaging stats            # snapshot incl. checkpoint digest
aitbc messaging state            # totals + index height
```

## Alerts (`aitbc-messaging` group in `scripts/monitoring/aitbc_rules.yml`)

### MessagingIndexLag (info)

The derived index is more than 50 blocks behind the local head for 10m.
The index reads the same `blocks`/`transaction` tables as the node, so a
lag means either the scrape is reaching a stale process or the node itself
is behind on sync.

First three commands:

```bash
aitbc messaging stats                                # index vs head, per node
aitbc node info --node-id <id>                        # sync state of node <id>
ssh <host> 'journalctl -u aitbc-blockchain-node -n 100 --no-pager'   # sync errors
```

### MessagingIndexDigestMismatch (critical)

Two nodes report different `aitbc_messaging_index_digest` values for the
same `chain_id` and `checkpoint` — at least one node derived different
forum state from rows that should be identical. This is a real divergence
signal, not a capacity wobble.

Do **not** restart anything and do not re-seal or "repair" the database.
First, find which topics differ:

```bash
# On each disagreeing node — the full digest first:
aitbc messaging stats                                # whose digest is odd?
aitbc messaging topics --limit 100                   # topic sets
sqlite3 /opt/aitbc/data/<chain_id>/chain.db \
  "select block_height, tx_hash from \"transaction\" where type='MESSAGE' order by block_height, tx_hash" \
  | diff - <(ssh <other-host> 'sqlite3 /opt/aitbc/data/<chain_id>/chain.db \
      "select block_height, tx_hash from \"transaction\" where type='"'"'MESSAGE'"'"' order by block_height, tx_hash"')
```

The last command diffs the raw sealed rows; if the rows match but the
digests differ, the divergence is in the derivation code — compare each
node's checkout commit (`git -C /opt/aitbc rev-parse HEAD`). If the rows
differ, the divergence is in sync/sealing, and this runbook ends — that is
a chain-level incident, not a messaging one.

**Expected mismatch during a rollout:** the digest covers envelope
validity and canonical order, so during a rollout that adds envelope
kinds (like the MSG-2 action kinds), old builds judge the new kinds
invalid and derive a different digest — a mismatch is EXPECTED until the
whole fleet runs the same build. Before treating it as real divergence,
compare `git rev-parse --short HEAD` and the `aitbc-blockchain-rpc`
start time on every host (the index and /metrics live in the rpc
service); a uniform fleet with matching digests is what proves the
rollout is done. Note also what the digest does *not* cover:
derived moderation state (hidden/pinned/locked views) — it detects
different sealed input or different validity code, not different
moderation computation.

### MessagingReadErrors (info)

More than 0.1 read errors/s for 15m on one route. 4xx (bad cursor, bad
slug, rate limit) and 5xx count together.

```bash
ssh <host> 'journalctl -u aitbc-blockchain-node -n 200 --no-pager | grep -i messaging'
aitbc messaging list --limit 1                       # does a trivial read work?
aitbc messaging list --cursor 'not-a-cursor'         # is it just bad cursors?
```

### MessagingVolumeSpike (info)

Last hour's message growth is above 50 and over 3× the trailing 6h hourly
rate. Usually a spam run; possibly genuine growth.

```bash
aitbc messaging list --limit 20                      # newest rows, look for a pattern
aitbc messaging stats                                # totals jumping?
aitbc messaging topics                               # one hot topic or spread?
```

Moderation (`aitbc messaging hide` as a topic moderator) is the response to
spam; the alert itself is informational and needs no action.

## What is deliberately not alerted on

- Admission rejections are counted (`aitbc_messaging_rejected_total{reason}`)
  but have no alert — a misconfigured client spamming invalid envelopes is
  a client bug, and the fee cost already deters it. Watch the counter if a
  real client reports rejects.
- The digest is only meaningful *between* nodes. A single node changing
  digest across a re-scrape is expected when the checkpoint rolls forward.

## Reports of illegal or abusive content

Who handles them, and what the response can and cannot do, is drafted in
[docs/policy/public-content-policy.md](../policy/public-content-policy.md).
Contact: the `CONTACT_EMAIL` value in `/etc/aitbc/website.env` on the hub
(currently `andreas.fleckl@bubuit.net`), also shown on the messages page.
