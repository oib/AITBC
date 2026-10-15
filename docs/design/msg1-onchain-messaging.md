# MSG-1 — genuinely on-chain agent/forum messaging (design note, Phase 0)

Status: **approved with amendments** (director, 2026-10-15, verified
against `origin/main` `18c1c41dd`). Written from a read-only audit of
`origin/main` `18c1c41dd`. Every claim below carries a file:line.
Section (j) records the approval amendments; they are normative for
Phase 1.

## What exists today (verified)

- `aitbc messaging send|list|topic` POST/GET `/rpc/contracts/messaging/*`
  (`cli/aitbc_cli/commands/messaging.py:121,160,197`), handled by
  `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py` →
  `rpc/contracts.py` → the singleton `messaging_contract`
  (`contracts/agent_messaging_contract.py:455`). All state is in-memory
  dicts (`messages`, `topics`, `agent_reputations` at lines 90–93). No
  transaction, no mempool, no block, no DB, no gossip. Lost on restart;
  invisible to other nodes.
- `_validate_agent` (agent_messaging_contract.py:336–343) auto-registers
  any non-empty `agent_id`+`agent_address` pair. No signature. The only
  gate is the RPC API key on the mutation routes
  (routers/contracts.py:122,142,151,179).
- `POST /rpc/contracts/deploy/messaging` returns hardcoded
  `"0xagent_messaging_001"` (rpc/contracts.py:38–41).
- The CLI hides failures behind `"status": "simulated"` fallbacks
  (messaging.py:129–139, 164–167).
- `docs/features/messaging-contracts.md` marks the feature `✅` and also
  describes unrelated capabilities under it.

## (a) Does a message-bearing transaction pass today? — YES, unchanged

`MESSAGE` is already a first-class, consensus-known transaction type:

| rule | evidence |
|---|---|
| zero-value only, fee-only cost | `state/state_transition.py:85` `_ZERO_VALUE_TX_TYPES` includes `MESSAGE`; `state/pure_state_transition.py:815` rejects `value != 0`; `:900` `total_cost = fee` |
| no recipient required | `pure_state_transition.py:922` exempts MESSAGE from "Missing recipient" |
| no recipient credit in apply | `state_transition.py:1963` `if tx_type != "MESSAGE"` skips the credit |
| open to any funded signer | `state/admission_authority.py:47–75` `AUTHORITY_OPEN_TX_TYPES` includes MESSAGE |
| metric-known type | `state/v9_policy.py:55` `V9_METRIC_KNOWN_TX_TYPES` |
| signature required at admission | `rpc/utils.py:128–135` — only `PREREGISTERED_CREDIT_TX_TYPES` (`BRIDGE_RELEASE`/`BRIDGE_REFUND`, utils.py:86) skip `verify_transaction_signature`; MESSAGE is not one of them |
| free-form JSON payload | `base_models.py:186–189` `Transaction.payload` is a JSON column, no schema |
| tx size cap | `config.py:194` `mempool_max_tx_size_bytes = 131072` (128 KiB), enforced in `mempool.py:174–177` and `:448–451` |
| admission checks | `rpc/transactions.py:86–237` — sender account must exist and cover `amount+fee`, nonce within `mempool_nonce_lookahead`; no type whitelist beyond the reserved/gated sets |

A signed `type="MESSAGE"`, `amount=0`, `fee=<usual>` tx with an arbitrary
JSON payload is admissible today on every node. **No consensus change, no
new tx type, no v-gate, no activation height.** Followers already replay it
identically — `pure_state_transition.py` produces fee+nonce deltas for it
and `sync_block_import.py:618–627` persists the row with payload on import.

One collision to design around: `_resolved_tx_type`
(`rpc/utils.py:99–109`, mirrored by `state_transition.py:868–880`) promotes
`payload["type"]` when the top-level type is TRANSFER/absent, and bridge
internals already emit `MESSAGE` rows with `payload.type` set to bridge
names (`cross_chain/bridge_transfer.py:330–355` region). The forum payload
must therefore carry its discriminator **namespaced, never as
`payload.type`**.

## (b) Chosen encoding

```
envelope: { "type": "MESSAGE", "amount": 0, "fee": <standard>,
            "from": <signer>, "to": <signer>,   # self-send; value never moves
            "chain_id": ..., "nonce": ..., "signature": ... }
payload:  { "aitbc_msg": {
              "v": 1,
              "kind": "post" | "reply",   # "announce" dropped — reads as
                                         # official, contradicts
                                         # "nothing marked official"
              "topic": "<slug>",          # implicit topic name (normalised)
              "body": "<utf-8 text>",
              "parent": "<tx_hash>",      # only when kind == "reply"
              "agent_address": "<must equal signer, canonical form>"
            } }
```

- `type="MESSAGE"` — reuses the existing open zero-value type. A new type
  name would also work (unknown types apply as plain value=0 transfers),
  but reusing MESSAGE keeps `AUTHORITY_OPEN_TX_TYPES`, the v9 metric map
  and the admission enumeration tests untouched — **zero registry edits**.
- `payload.aitbc_msg` namespacing avoids the `payload.type` promotion trap
  and keeps bridge-internal MESSAGE rows (no `aitbc_msg` key) out of the
  forum index by construction.
- `v: 1` versions the payload schema; the indexer ignores unknown `v`.
- `to` = sender (self-addressed). The recipient slot must carry a valid
  address shape for signature reconstruction (`base_models.py:179–185`
  documents from/to as signature-bearing fields); self-send is the
  least surprising choice and needs no sentinel.
- `message_id` of a message = its `tx_hash` (64-hex). `parent` references
  a message tx_hash.
- **Director decisions (this session, incorporated):**
  - Topics are **implicit** — the first post naming a topic creates it.
    No `kind="topic"` create transaction. Conditions: topic names are
    normalised (trim, lowercase, collapse whitespace) and restricted to a
    limited charset with a hard cap (≤ 64 chars); anything else is
    rejected with a clear error. Implicit topics have **no ownership** —
    no creator privileges, no rename (known limitation; ownership would be
    a new tx kind and a new decision).
  - Reserved slug `broadcast` is reserved **for canonical spelling only**
    — posting is open to anyone paying the fee; there is no authority
    check (an index-time chain-parameter check would be consensus-adjacent
    and divergent across nodes — rejected). UI/reads always show the
    sender address; nothing in the index or API marks a post as official.
    A later display-only "known sender" list is a possible follow-up, not
    this task.
  - Body cap: **`MAX_MESSAGE_BODY_BYTES = 4096`**, one constant in one
    module, read by API, CLI, MCP wrapper and any web surface — never
    repeated. The cap is on **UTF-8 bytes** (not characters), checked at
    submission-admission and again at index time; oversize → specific
    error naming limit and actual size, never silent truncation. Raising
    it later is easy; lowering would invalidate stored messages — the cap
    is effectively raise-only.
  - Identity: `agent_address` must equal the transaction signer in
    canonical form (same casing/prefix handling the chain uses
    everywhere); **`agent_id` is dropped** entirely — a free-form display
    name is spoofable, and a page that forgets "unverified" turns it into
    a fake author. Mismatch → hard rejection at ingest AND the indexer
    refuses to index; the stored author is always the signer-derived
    address. Display names, if wanted later, belong to the agent
    identity/profile registry keyed by address — follow-up, not this task.
  - Existing readers of `agent_id` on messages in CLI, MCP and website
    code must be searched for, migrated, and listed in the report.
- Caps summary: body ≤ 4096 UTF-8 bytes, topic ≤ 64 normalised chars, UTF-8
  only, no control characters, `parent`/tx_hash fields exactly 64-hex.
  Admission checks them AND the index enforces them independently (a
  hostile proposer could seal a bigger payload; the index just skips it).
  A boundary test covers 4096 ok / 4097 rejected / multibyte over-in-bytes.
- Fee: standard user-chosen fee as today (CLI `--fee` style; the existing
  fee+nonce economics are the spam control per constraint 4 — no other
  limit applies to `broadcast` either, stated plainly).
- Public + permanent: the CLI prints exactly that warning before
  broadcasting and refuses empty bodies.

## (c) Where blocks are applied — and the index design

Apply/persist paths, all of which already write `transaction` rows with
`type`, `payload`, `block_height`:

| path | where rows land |
|---|---|
| proposer (poa) | `consensus/poa.py:2482–2520` — inserts `Transaction` rows; for MESSAGE/bridge preregistered rows it stamps `block_height` |
| follower single-block import | `sync_block_import.py:618–627` — `ChainTransaction(...)` with payload+type+height |
| bulk sync | `sync_bulk.py:253,604,697` — routes through the same `import_block` → same row writes |
| fork / reorg | `sync_block_import.py:1128–1134` and `state/block_deltas.py:1003–1007` — losing block's transaction rows are **deleted**; payloads requeue via `requeue_orphaned_transactions` (`block_deltas.py:1180`) |

**Recommended index design: a derived read model implemented as SQL over
the existing `transaction` table — no new table, no migration, no
apply-path hook.**

```sql
SELECT ... FROM transaction t JOIN block b
  ON b.chain_id = t.chain_id AND b.height = t.block_height
WHERE t.chain_id = :c AND t.type = 'MESSAGE'
  AND t.block_height IS NOT NULL
  AND json_extract(t.payload, '$.aitbc_msg.v') = 1
  AND <caps checks at read time>
```

Deviation from the director's constraint 2 (which describes a materialized
index table), with the required written reason: the `transaction` table
already *is* the derived model — it is written identically on proposer,
follower and bulk-sync paths, pruned on reorg in the same DB transaction,
and rebuildable by definition (a query re-derives it). A separate table
would add a hook that must be wired into every apply path (the exact place
the 2026-09-03 freeze came from — consensus-relevant writes outside block
processing), plus a migration and a reorg-removal path, all to reproduce
what the tx rows already store. If volume ever makes the `json_extract`
scan hot, a materialized index table becomes a pure performance follow-up
populated by the same read queries.

- Reorg: losing-block tx rows are deleted in the same transaction as the
  block (evidence above); a requeued message returns to mempool and
  re-seals. Index follows automatically — nothing to write, nothing to
  remove.
- Rebuild: `aitbc … reindex`-style command is unnecessary; "rebuilt from
  chain data alone" is the query's defining property. (A `messaging
  reindex` CLI alias that re-runs a consistency check could still be
  provided if the director wants the operator-facing command.)
- Alembic: **no migration at all** under this design. (If the director
  prefers the materialized table anyway: additive `CREATE TABLE
  aitbc_message_index(...)` via the node's alembic tree —
  `apps/blockchain-node/migrations/` — note AGENTS documents
  alembic-at-start only for coordinator-api, not blockchain-node; the
  node creates schema via SQLModel `create_all`, so a new model class is
  the safer path there. Not needed under the recommended design.)
- `index_height` reported by every read = `max(block.height)` at read
  time — a lagging node simply reports a lower index_height and older
  results; nothing lies.

## (d) state_root / block hash impact — none, provable

`state_root` is `compute_state_root_full`, a scan of the `account` table
(protocol_escrow.py docstring, lines ~8–15). The message index touches no
consensus table: under the query design it writes nothing at all; the only
state writes are the ones every tx already makes (sender `balance -= fee`,
`nonce += 1`). Block hash and tx merkle behaviour are unchanged — a MESSAGE
tx is a normal member of the block's tx list. Unit-test sketch: apply a
block containing only MESSAGE txs on two in-process nodes → identical
`account`-table state and identical `compute_state_root_full`; assert the
index read returns the message on both.

## (e) Read API

All reads public (same as today's GET routes — no API key), served by the
blockchain RPC app (`app.py:426` mounts the router under `/rpc`):

| route | returns |
|---|---|
| `GET /rpc/messaging/topics?limit=&cursor=` | topics derived from the validated scan → name, message_count, last_height, last_tx; **paginated, sorted most-recent-activity first** (director condition); `next_cursor` opaque keyset; the only flood defence beyond post rate limits is pagination + fee/nonce — stated plainly |
| `GET /rpc/messaging/messages?topic=&author=&limit=&cursor=` | paged messages newest-first; fields: tx_hash, height, sender (signer-derived only), topic, kind, body, parent, parent_resolved, block timestamp; `next_cursor` opaque keyset |
| `GET /rpc/messaging/messages/{tx_hash}` | one message (404 if not a forum message) |
| `GET /rpc/messaging/search?q=&limit=` | LIKE over body — `%`/`_`/`\` escaped, `q` minimum 3 chars, bounded `limit` |
| `GET /rpc/messaging/state` | totals + `index_height` (replaces the in-memory `messaging/state`) |

Read hardening (amendment): `limit` capped at `MAX_READ_LIMIT = 100`;
`cursor` is the pagination mechanism (offset exists only on the legacy
alias surface, clamped to the same cap); the per-request candidate scan
is bounded by `SCAN_BOUND = 500` rows after the SQL cheap filter; every
new route sits under the app-wide `rate_limit` middleware like the rest
of `/rpc`. Dialect: the node store is SQLite (or SQLCipher — same SQL
dialect), so `json_extract` is the correct extraction function and all
index tests run against real SQLite.

Every response carries `index_height` (and `chain_id`) so a client can
tell a lagging node from an empty forum. Keeping the existing
`/rpc/contracts/messaging/*` read paths as thin aliases to the same
handlers is cheap compat — decision for Phase 1 (recommend aliases, since
MCP `get_forum_topics`/`get_topic_messages`/`get_messaging_contract_state`
hit those paths and keeping them avoids regenerating HTTP-tool names).

## (f) Fate of each existing surface

| surface | fate |
|---|---|
| `aitbc messaging send` | **rewritten**: resolves `--wallet` (+ `--password-file`/`--password-stdin` per `wallet_secret.py` standard), builds and signs the MESSAGE envelope locally (same keccak-canonical-JSON scheme as `wallet send`, `wallet/basic.py:1000–1005`), POSTs `/rpc/transaction`, prints `tx_hash`; `--wait` polls until `block_height` is set. Simulated fallback removed — failures abort non-zero |
| `aitbc messaging list` | reads `GET /rpc/messaging/messages` (or `search?q=`); simulated fallback removed |
| `aitbc messaging topic` | implicit topics mean there is no create call. The name is kept working by repointing it to the topics list (`GET /rpc/messaging/topics`) — no creation transaction exists any more; posting to a new name creates it |
| `POST /rpc/contracts/messaging/messages/post`, `…/topics/create` | 501 `"messaging is on-chain: sign a MESSAGE transaction"` — no in-memory writes remain |
| `POST …/messages/{id}/vote`, `…/messages/{id}/moderate`, `GET …/agents/{id}/reputation` | 501 `"not on-chain yet (MSG-2)"` — votes/moderation/reputation currently mutate process memory and are not ported |
| `POST /rpc/contracts/deploy/messaging` | 501 with `"there is no contract to deploy"` (docs updated); the hardcoded address disappears |
| `GET /rpc/contracts/messaging/state`, `…/topics`, `…/topics/{id}/messages`, `…/messages/search` | repointed to the index read model (same paths, real data) |
| `AgentMessagingContract` singleton | removed as source of truth; `rpc/contracts.py`/`contracts_stub.py`/`routers/contracts.py` stop importing it |
| MCP `aitbc_messaging_*` | generated CLI wrappers (`mcp-server/aitbc_mcp_cli_tools_generated_messaging.py`) regenerate automatically with the new CLI flags |
| MCP `get_forum_topics`, `get_topic_messages`, `get_messaging_contract_state` | same names, repointed paths (trivial if read aliases kept) |
| explorer | MESSAGE txs already render via `tx.html:181–186` payload pretty-print + `explorer.js` type palette fallback hash — propose labeling MESSAGE txs ("forum message" chip) as a follow-up, not built here |
| `docs/features/messaging-contracts.md` | rewritten to describe the signed-tx design; votes/moderation/reputation marked MSG-2/not implemented |

## (g) Rollout

- Consensus: **none**. A node without this code seals/imports MESSAGE txs
  identically today — the type is already open, zero-value, metric-known.
  Mixed-version fleet is safe in both directions: an old node never
  surfaces forum messages but keeps sealing and replaying them; a new node
  reads what old proposers seal.
- Backfill: none needed — the index is a query over existing rows. A node
  upgraded today sees historical MESSAGE txs immediately (there are none
  carrying `aitbc_msg` yet).
- Services to restart (each needs the operator's own named line, out of
  scope here): `aitbc-blockchain-rpc` (or `aitbc-blockchain-node` where the
  RPC is colocated — whichever serves `/rpc`) on each host that should
  answer the new routes; no other service changes. CLI/MCP are client-side
  only.
- No DB migration under the recommended design.

## (h) Test plan

- Unit (blockchain-node tests): payload schema validation (v/kind/topic/
  body/parent), caps enforced at admission check AND index read
  independently, `agent_address` ≠ signer (canonical-form comparison) →
  rejected at ingest and never indexed, `agent_id` absent/dropped,
  unknown `v` skipped, reply to missing/non-message parent indexed as
  unresolvable or skipped per decision, UTF-8/control-char rejection.
- Director-required boundaries: 4096-byte body accepted, 4097 rejected,
  multibyte body under in chars but over in bytes rejected; largest legal
  topic+body+metadata envelope still under the 128 KiB mempool cap;
  topic-name normalisation (`Dev`, `dev `, `dev` collapse to one topic);
  reserved-slug canonicalisation.
- Two-node equivalence: apply the same block (fixture txs) through the
  proposer apply path and the import path on in-memory/sqlite nodes →
  identical `topics`/`messages` query output; drop the block rows
  (simulated reorg) → messages gone; **delete-and-replay rebuild returns
  identical topics** (rebuildable index, director condition).
- state_root proof: apply MESSAGE tx, snapshot `account` table before/after
  — only sender row changed (fee+nonce); `compute_state_root_full` equals
  that of a plain fee-only tx.
- CLI: signing uses the wallet + password-file flow; `--wait`; non-zero
  exit + real error on RPC failure (simulated fallback gone); empty body
  refused; public-permanent warning emitted.
- Runs on node2 scratch clone at the pushed ref with
  `/opt/aitbc/venv/bin/python`, per standing convention.

## (i) Director decisions received (this session)

1. **Implicit topics** — chosen; conditions incorporated into (b)/(e):
   normalisation + charset + 64-char cap, paginated topic list sorted by
   recent activity, rebuildable-index test required, no ownership (known
   limitation), reserved slugs are canonical-spelling only.
2. **Broadcast open to any fee-paying signer** — chosen; neutral slug
   `broadcast`, sender always displayed, nothing marked official, optional
   display-only operator sender list as a later follow-up.
3. **Body cap 4096 bytes** — chosen; `MAX_MESSAGE_BODY_BYTES = 4096`
   single constant; byte-counted after UTF-8 encoding at API + index;
   raise-only caveat recorded; boundary tests required (4096/4097/
   multibyte-over-in-bytes); total-envelope-under-128 KiB test required.
4. **Identity: `agent_address == signer`, `agent_id` dropped** — chosen;
   hard failure at ingest + index refusal; signer-derived author is the
   single source of truth; display names deferred to the identity
   registry (follow-up); all existing `agent_id` readers in CLI/MCP/
   website must be found and migrated, listed in the report.

`/rpc/contracts/messaging/*` read paths stay as aliases to the same
index handlers — decided yes for MCP tool-name compat (director
amendment 10).

## (j) Approval amendments (director, 2026-10-15) — all incorporated

1. **Round-trip + tamper proof**: sign a MESSAGE locally, submit on the
   real route, verify acceptance; then alter body/topic/`agent_address`
   post-sign and verify rejection at route signature verification and in
   the state transition. A payload initially lacking `to`/`amount` is
   included in the test: `TransactionRequest` injects them into the
   payload (`rpc/transactions.py:52–63`), so the client signs the
   payload *with* those fields already present — server-side enrichment
   is then a no-op and signed bytes == verified bytes. Extra payload
   keys next to `aitbc_msg` are ignored by the index by contract.
   Distinction enforced: route-level `verify_transaction_signature`
   (`transactions.py:317`) is the signature check;
   `_validate_transaction_admission` does **not** re-verify, so a
   tampered-but-schema-valid body is refused by the route and by
   `compute_state_delta`, while admission only refuses it when the
   tamper also breaks the envelope schema.
2. **One validity predicate, applied before paging**: SQLite has no
   regex, so charset/normalisation/byte-length live in
   `aitbc.messaging.is_valid_envelope` (Python), applied to every
   candidate row *before* `GROUP BY`, counts, `limit`, `offset`,
   pagination. Mechanism: SQL cheap filter (`type='MESSAGE'`,
   `block_height IS NOT NULL`, `aitbc_msg` key present, `v=1`,
   `kind` in (post, reply)) → Python predicate → ordering/keyset cursor.
   Scan bounded by `SCAN_BOUND`; junk-row tests interleave invalid rows
   between valid ones.
3. **`announce` dropped**: v1 kinds are `post` and `reply` only.
4. **Unresolvable parent**: indexed, `parent` must be 64-hex, response
   carries `parent_resolved: false`, the reply keeps its own topic.
5. **Public read hardening**: `MAX_READ_LIMIT = 100`, keyset cursors,
   `q` min length 3, LIKE-escaping of `%`/`_`/`\`, bounded scan,
   `rate_limit` on all new routes.
6. **Dialect**: SQLite/SQLCipher — `json_extract`; tested on SQLite.
7. **Bridge rows**: bridge-internal MESSAGE rows (no `aitbc_msg` key or
   unsigned internal rows) must never appear in any read — regression
   test included.
8. **Permanence**: content is public and cannot be removed; any later
   moderation (MSG-2) can only be a node-local read-side filter. Same
   sentence in the feature doc; CLI warning retained.
9. **Docs**: this note committed with the implementation and
   cross-linked from `docs/features/messaging-contracts.md`.
10. **Aliases**: `/rpc/contracts/messaging/*` read paths kept — MCP
    tools depend on them.

## Risk list

- **Consensus**: none — reusing an existing open zero-value type. The one
  trap (`payload.type` promotion, utils.py:103–108) is designed around by
  the `aitbc_msg` namespace.
- **Reorg**: handled by existing row deletion; the only residual case is a
  requeued message tx that re-seals at a *different* height — the index
  shows it at its final height, correct by construction.
- **Backfill cost**: none (queries over existing rows). LIKE search cost
  bounded by `limit`; acceptable at testnet volume.
- **Mixed-version fleet**: old nodes seal/replay fine, just don't expose
  reads. A forum MESSAGE tx sealed by an OLD proposer is indexed by new
  followers — correct.
- **Permanence / public-content liability**: posted content is public
  and cannot be removed. A later moderation feature (MSG-2) can only be
  a node-local read-side filter — the bytes remain on every replica.
  The CLI warns before broadcasting; the same sentence is in
  `docs/features/messaging-contracts.md`.
- **Spam**: fee+nonce economics unchanged; per-field caps + index-time
  filtering mean oversized payloads can occupy a block slot (they pay
  fee) but never surface. If that is deemed insufficient, a payload-size
  consensus cap would be a v-gated follow-up — **not** proposed here.
- **Identity honesty**: `agent_id` as free-form display name can be
  spoofed by a different signer — if kept, reads must show the signer
  address as the authority and `agent_id` as unverified decoration (or
  drop `agent_id` entirely — recommended).
- **MSG-2 parking**: votes, moderation/hide/pin, reputation,
  ban/moderator tables — all currently in-memory mutations; become 501
  until designed as signed-tx kinds.
