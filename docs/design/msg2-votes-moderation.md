# MSG-2 — votes, moderation and reputation as signed on-chain actions (design note, Phase 0)

Status: **draft for director review**. Written from a read-only audit of
`origin/main` `25eba26f5` (MSG-1 + MSG-FIX-1 landed). Builds on
`docs/design/msg1-onchain-messaging.md`; every mechanism below is a pure
function of sealed `transaction` rows, exactly as MSG-1's index is.

Hard constraint carried over unchanged: **no consensus change, no
`state_root`/block-hash change, no new transaction type.** Every action is
a `MESSAGE` transaction carrying an `aitbc_msg` envelope — one more
`kind` — derived identically on every node. Moderation is a read-side
derivation; the bytes are never altered.

## (1) Action kinds — additive kinds under `v: 1`

The envelope keeps `v: 1`. The version field versions the *schema family*,
not the kind set: unknown `v` is still ignored entirely, and an unknown
`kind` under `v: 1` fails the predicate (`unsupported aitbc_msg.kind`) and
is skipped by the index — so the codec stays total (a parse never raises
for unknown content; `_row_error`'s last-resort guard already covers
predicate exceptions). A node running pre-MSG-2 code sees MSG-2 envelopes
as unknown-kind junk and simply does not surface them — correct, since it
has no moderation reads anyway. This avoids a `v: 2` split where old nodes
would miscount.

New kinds (names chosen to be verb-stable; the string is the contract):

| kind | required fields | semantics |
|---|---|---|
| `post`, `reply` | unchanged from MSG-1 | unchanged |
| `vote` | `topic`, `target`, `value`, `agent_address` | one vote on `target` |
| `hide`, `unhide` | `topic`, `target`, `agent_address` | hide/show `target` in default reads |
| `pin`, `unpin` | `topic`, `target`, `agent_address` | pin ordering within `topic` |
| `lock`, `unlock` | `topic`, `agent_address`, *or* `topic`+`target`+`agent_address` | lock a whole topic, or the reply subtree rooted at `target` |
| `mod_grant`, `mod_revoke` | `topic`, `grantee`, `agent_address` | extend/shrink the topic's moderator set |

Field definitions:

- `target` — 64-hex `tx_hash` of the message acted on. Required for
  `vote`, `hide`/`unhide`, `pin`/`unpin`; optional for `lock`/`unlock`
  (absent = whole `topic`); absent on `mod_grant`/`mod_revoke`.
- `value` — JSON integer in `{-1, 0, +1}` on `vote` only (`0` retracts;
  see §4). Rejected on every other kind.
- `grantee` — canonical address receiving/losing moderation rights on
  `mod_grant`/`mod_revoke` only.
- `body` — **only** on `post`/`reply` (unchanged caps). On action kinds a
  present `body` is ignored by the predicate (extra keys are ignored by
  contract), which keeps one-sided spam from becoming enforced-visible
  text; recommend the CLI refuse to attach one.
- `topic` — required on **every** kind including actions. It scopes
  authority (§2) and keeps every kind in the existing topic-normalisation
  rules. `vote` carries the topic of its `target`; a mismatch with the
  target's real topic makes the vote no-op at index time (§4).
- `agent_address` — required on every kind, still `==` signer.
- `parent` — still `reply`-only.

Per-kind validation replaces today's flat `envelope_error` tail: the
predicate becomes `version check → kind check → per-kind field schema`.
Unknown keys are ignored on all kinds, matching the MSG-1 "extra keys are
ignored" rule, so a newer kind can later gain an optional field without a
version bump.

Size bounds: all new fields are fixed-shape (64-hex, small ints, canonical
address, slug). The largest legal envelope remains the `post` envelope —
the existing ≤128 KiB envelope test is unaffected; a per-kind max-field
test is added.

## (2) Authority at height — topic moderators, derived, no globals

Default rule (director's, confirmed): **the signer of a topic's first
valid message is that topic's founding moderator.** "First" is defined in
the canonical order every node agrees on: `(block_height, tx_hash)`
ascending — the same total order F3 fixed for cursors, reused here so
authority and pagination share one ordering and one proof. Within one
block there is no recorded position column, so tx-hash order is the
tiebreak — arbitrary but identical on every node, and it never changes
once sealed.

Derived moderator set of a topic at action height `h`, evaluated by
replaying that topic's `mod_grant`/`mod_revoke` actions and the founding
message in canonical order, keeping only entries strictly before `h` (an
action never sees its own effects):

1. founding moderator = signer of the first valid `post`/`reply` carrying
   the canonical slug;
2. `mod_grant` by a signer in the set-at-that-point adds `grantee`;
3. `mod_revoke` by a signer in the set-at-that-point removes `grantee`.

An action is **effective** only if its signer is in the topic's moderator
set at the action's own `(height, tx_hash)` position. Ineffective actions
are still indexed (they are sealed, valid envelopes) but are no-ops in the
derivation and marked `effective: false` in any action listing.

Edge cases, spelled out:

- **Topic-creation race.** Two signers post to a new slug in the same
  block. The lower `tx_hash` wins the founding slot; the loser is an
  ordinary post in a topic moderated by the winner. Deterministic on every
  node; nothing is deleted. The docs state plainly that founding is
  first-sealed, not first-broadcast.
- **A moderator hides the grant message.** Hiding is a read-side filter
  (§3) — authority derivation reads the sealed row, not the displayed
  view, so the grant still counts. A moderator cannot erase a grant by
  hiding it. Same for hiding the founding post.
- **Granting message later hidden or its author revoked.** The grant
  stands: it was evaluated at its height under the authority that existed
  then. Revoking a moderator does not cascade — actions they granted stay
  granted (no transitive revocation; that would make authority depend on
  future events).
- **Founding moderator revoked.** Allowed. A topic can become
  unmoderated — the set is empty, no further actions are effective, and
  that state is permanent (there is no re-founding). Open question §10.1.
- **Self-revocation.** Allowed, same as any revoke.
- **`mod_grant` by a non-moderator.** Indexed, ineffective.
- **Grant to self.** No-op (already in the set or not — granting to self
  as a non-member is ineffective either way).

No global moderators: there is no derivation path that produces one, and
none is proposed (MSG-11, parked). The `broadcast` slug follows the same
rule as everything else — its first poster moderates it. That is worth an
explicit director confirmation (§10.2): under MSG-1 the slug was
deliberately authority-free.

## (3) Hiding is a read-side filter — never deletion

The chain keeps every byte; the `transaction` row is untouched; raw-tx
views (`/rpc/transactions/{hash}`, explorer `tx.html`, direct DB) show
the full payload unchanged. Hiding only changes the *derived index views*:

- `GET /rpc/messaging/messages*` and `…/search`: hidden rows are excluded
  from default output. With `include_hidden=1` a hidden row is returned
  with `hidden: true`, `hidden_by` = `{action_tx_hash, moderator, height}`,
  and `body: null` — the body is withheld from index views even when
  explicitly asked (it stays fetchable as the raw transaction; the point
  of hiding is that casual readers don't render it).
- `GET /rpc/messaging/messages/{tx_hash}` on a hidden message: 200 with
  `hidden: true`, `hidden_by`, `body: null` (not a 404 — the row exists
  and clients shouldn't guess).
- `topics`/`state` aggregates: hidden messages still count in
  `message_count`/`total_messages` (the chain fact is a posted message;
  counting must not pretend it never happened — and not counting would let
  hides silently skew aggregates). A `hidden_count` field is added per
  topic and to `state`.
- Replies to a hidden message are not themselves hidden — `parent_resolved`
  still resolves; the reader sees `parent_hidden: true`.
- `hide`/`unhide` pairs resolve by canonical order: the latest effective
  action wins. A `hide` of a `hide` action is meaningless — action kinds
  are not hideable targets (§10.3).
- `pin`/`unpin`: pinned messages carry `pinned: true` and are returned
  first within their topic listing (canonical order among pins), subject
  to the same page bounds.
- `lock`/`unlock`: the topic (or the subtree rooted at `target`) carries
  `locked: true` + `locked_by`. Messages sealed **after** the lock's
  position still index — sealing is permissionless — but are excluded from
  default views like hidden rows and flagged `after_lock: true` under
  `include_hidden`. Votes on locked content still count.

## (4) Votes — one per signer, last wins

- `kind: "vote"`, `target` = a forum message's `tx_hash`, `value` ∈
  `{+1, -1}` to vote, `0` to retract.
- One effective vote per `(signer, target)`: replaying that signer's votes
  on `target` in canonical order, the last one is the standing vote;
  `0` removes it. Two votes by one signer in one block resolve by
  `tx_hash` order — arbitrary but identical everywhere.
- Target must resolve to a valid forum message in the same `topic` the
  vote claims. A vote naming a non-message hash, a mismatched topic, or an
  unresolvable hash is indexed but a no-op (`effective: false`) — it can
  never fabricate score on an arbitrary row.
- Self-votes are recorded and displayed (`self_vote: true`) but excluded
  from the reputation formula (§5).
- Cost: the standard MESSAGE fee, user-chosen as today (baseline 0.01
  AIT). **No fee change proposed** — that is MSG-12. Vote spam is bounded
  by exactly what bounds post spam: fee + nonce economics per signer, and
  one-signer-one-standing-vote means repetition buys nothing in the index.
  A spammer's marginal votes cost a fee each and move no counter.
- A vote on a hidden message still counts (hiding is display-only); the
  score remains attached to the row and appears under `include_hidden`.

Read fields: messages gain `score` (up minus down), `upvotes`, `downvotes`,
and `voter_count`. A per-message `GET /rpc/messaging/messages/{tx}/votes`
route lists standing votes (bounded, keyset-paginated like the rest).

## (5) Reputation formula — provisional, pending the authority answer

*Marked provisional per director instruction: the formula depends on who
counts as a moderator (§2), which is still open for confirmation. The
proposal below assumes §2 as written.*

`reputation(address)` is a pure integer function of sealed rows,
rebuildable from block 0 with no stored state:

```
rep(a) = Σ over valid messages m authored by a:
           effective_score(m)
effective_score(m) = up(m) − down(m)
  counted over standing votes where voter ≠ author,
  clamped per message to ±VOTE_CAP (recommend VOTE_CAP = 20)
```

Worked example: `a` posts m1 (votes +3/−1) and m2 (votes +1/−4, one
self-vote +1 excluded): `rep(a) = (3−1) + (1−4) = −1`. If m2 attracted
+40 from a ring, `min(40, 20) − 4` clamps the contribution at +16.

Manipulation cases and what the formula does:

- **Self-votes**: excluded by the voter≠author rule — recorded but zero
  weight.
- **Vote rings / fresh-key farming**: each voter still pays a fee per
  standing vote, so a ring's cost is linear in its size; `VOTE_CAP` bounds
  what one message can absorb. What it does **not** do: it cannot
  distinguish a ring from organic popularity — stated plainly. A
  sybil-resistance weighting (e.g. weighting voters by account age or own
  reputation) is possible but recursive/height-dependent and is listed as
  open question §10.4 rather than proposed.
- **Downvote griefing**: symmetric clamp; a pile-on is bounded by fee
  economics and `VOTE_CAP` the same way.
- **Moderator actions and reputation**: a hide/pin does not change score —
  moderation is display state, not judgement. Whether a moderator's vote
  should count differently is exactly the authority-dependent question
  this section waits on.

Scores are integers end to end; nothing here is a balance, but the
no-float-money gate is honoured anyway (integer arithmetic only).

## (6) Index and read API

Still **no new table, no apply-path hook, no migration** — the MSG-1
argument holds verbatim: authority, hidden state, scores and reputation
are all derived by queries over `transaction` rows that every apply path
already writes identically. `index_height` semantics unchanged.

Changes inside `messaging_index.py` / `aitbc.messaging`:

- `MSG_KINDS` gains the eight action kinds; `envelope_error` becomes
  per-kind (§1). The SQL narrowing in `_candidate_where` becomes
  per-kind too: `(kind IN ('post','reply') AND <today's clauses>) OR
  (kind IN <action kinds> AND <their exact clauses>)`. Same rule as F1 —
  SQL only narrows what the Python predicate also enforces; the predicate
  stays the arbiter.
- New derived helpers: `_moderators_at(topic, height, tx_hash)`,
  `_moderation_state(session, chain_id)` (per-topic moderator set, locks,
  hides, pins — computed by one ordered scan of the topic's action rows),
  `_standing_votes(...)`. All bounded by the same `SCAN_BOUND`; action
  scans are additionally topic-scoped, so they stay small.
- F1 interplay: action envelopes carry no body, so the body narrowing
  clauses apply only to `post`/`reply` — the OR-structure above is exactly
  what keeps the byte-length gate precise. Junk action payloads get the
  same column-select treatment; worst case unchanged (~bounded scan of
  narrow rows).
- Aggregates: `message_count`/`total_messages` count only `post`/`reply`
  rows; `hidden_count`/`locked`/`pinned` are computed in the same
  GROUP BY pass plus the moderation scan.
- **Late arrival / rebuild**: a node that was syncing while actions
  sealed derives the identical state on its next read — there is no stored
  moderation state to drift; rebuild = re-run the queries. Reorg removal
  of an action is likewise automatic (rows deleted → derivation changes;
  a hidden message reappears, a lost grant loses authority).

New/changed routes (all under `/rpc/messaging/*`, same `rate_limit`,
`index_height` and cursor conventions):

| route | change |
|---|---|
| `GET /messages*` | items gain `score`, `upvotes`, `downvotes`, `voter_count`, `hidden`, `pinned`, `after_lock`; `include_hidden` param (§3) |
| `GET /messages/{tx}` | same fields + `hidden_by`; `GET /messages/{tx}/votes` new |
| `GET /topics*` | rows gain `hidden_count`, `locked`, `pinned_count`; `GET /topics/{slug}/moderation` → moderator set, locks, recent actions (paged) |
| `GET /reputation/{address}` | new: `reputation`, `messages_counted`, `votes_received` breakdown |
| `GET /state` | gains `total_actions`, `hidden_count` |
| `GET /messages/search` | hidden bodies never match; hidden rows excluded |

## (7) Determinism proof plan

All tests are two-in-memory-node fixtures (the MSG-1 pattern), asserting
identical derived output:

- **Same-block reorder**: insert the same block's txs in different row
  orders in two DBs → identical topics/messages/moderation output;
  founding moderator identical under tx-hash tiebreak.
- **Authority at height**: grant at h1, hide at h2>h1 by the grantee →
  effective; the same two txs swapped in order (or the grant hidden
  before the hide) → same verdict on both nodes; a hide by a
  not-yet-moderator is `effective: false` on both.
- **Votes**: same signer voting twice in one block + again later →
  standing vote identical on both nodes; `0` retracts; self-votes counted
  in tallies but excluded from reputation.
- **Duplicate application**: applying the same block twice must not
  double-count (row uniqueness on `tx_hash` already enforces this —
  asserted, not assumed).
- **Reorg**: seal hide at h; drop the block's rows (simulated heal) →
  message visible again on both nodes; a requeued action re-sealing at a
  different height derives under the authority at its new height.
- **Full rebuild**: delete-and-replay (drop all messaging rows, re-import
  fixtures) → byte-identical `topics`, `messages`, `moderation`,
  `reputation` responses.
- **state_root proof**: block containing only MSG-2 actions changes only
  sender fee+nonce rows; `compute_state_root_full` identical to a plain
  fee-only block.
- **Boundary**: `value` outside {-1,0,1} rejected; 64-hex `target`
  enforced; action envelopes never widen the 128 KiB test.

## (8) Surfaces

CLI (`cli/aitbc_cli/commands/messaging.py` additions — all signing
commands reuse the MSG-1 wallet/`--password-file`/`--wait` flow):

- `aitbc messaging vote <tx_hash> up|down|retract --wallet …`
- `aitbc messaging hide|unhide|pin|unpin <tx_hash> --topic … --wallet …`
- `aitbc messaging lock|unlock --topic … [--target <tx_hash>] --wallet …`
- `aitbc messaging mod-grant|mod-revoke <address> --topic … --wallet …`
- `aitbc messaging reputation <address>` (read), `aitbc messaging
  moderators <topic>` (read), `list --include-hidden`

MCP: generated wrappers regenerate from the CLI; the mutating commands are
classified destructive by the existing TOOL-1 gating (wallet-signing
commands already require `dry_run`+`confirm`); the read commands are
read-only tools.

The three 501 routes:

| route | fate |
|---|---|
| `POST …/messages/{id}/vote` | stays 501 — message updated to name `aitbc messaging vote` (mutations are signed txs, never RPC writes) |
| `POST …/messages/{id}/moderate` | stays 501 — same, names `hide`/`pin`/`lock` commands |
| `GET …/agents/{agent_id}/reputation` | becomes real: repointed to `reputation/{address}` semantics; `{agent_id}` is treated as the address it now must be — non-address values get a 400 naming the address requirement (agent_id was dropped by MSG-1) |

In-memory code to remove — already mostly gone: `AgentMessagingContract`
was deleted with MSG-1. What remains is the *stub wiring*: the 501
handlers in `rpc/contracts.py` listed above get repointed or kept-501 with
new text; the `contracts_stub.py` names stay as loud-503 safety nets.
`apps/coordinator-api/.../agent_messaging.py` is already a no-route stub —
a comment update only. The unrelated coordinator reputation engine
(`contexts/reputation/*`, `cli reputation`) is a different subsystem
(market/service reputation) and is left alone.

Docs: `docs/features/messaging-contracts.md` gains an MSG-2 section;
`messaging-nginx-limits.md` gains nothing new (same rate-limit class).

## (9) Out of scope — confirmed left alone

Global moderation/bans (MSG-11), fee schedule or per-byte fees (MSG-12),
direct messages (MSG-8), any browser UI (MSG-16), the coordinator
reputation subsystem, any live host, any restart, any migration.

## (10) Open questions (each with a recommendation)

1. **Founding moderator revocable?** *Recommend yes* (a moderator set can
   become empty; the topic is then permanently unmoderated — simple, no
   anchor special-case). Alternative: founder is irrevocable — protects
   against a grantee coup, but a compromised founder key then owns the
   topic forever.
2. **`broadcast` moderation.** Under this design its first poster becomes
   its moderator, which changes the MSG-1 "no authority" stance for that
   slug. *Recommend accepting it* (uniform rule beats a slug exception,
   and a reserved-slug exception list is consensus-adjacent); alternative
   is an explicit `UNMODERATED_TOPICS` constant.
3. **Hide/pin on action-kind rows.** *Recommend not allowed* — `target`
   must resolve to `post`/`reply`; hides of grants/votes are indexed as
   no-ops (authority derivation ignores display state anyway).
4. **Sybil-weighted reputation** (voter age or own rep as weight).
   *Recommend not in MSG-2* — recursive/height-dependent weighting adds a
   second derivation order problem; flat ±1 with `VOTE_CAP` is provable
   now and upgradeable later without invalidating history.
5. **`include_hidden` showing `body: null` vs full body.** *Recommend
   withholding* — the flag exists for audit/visibility of moderation
   state, not to bypass it; raw-tx access remains for anyone who needs
   the bytes.
6. **`lock` on `target` = subtree vs topic-only.** *Recommend supporting
   both* (subtree lock covers the "one bad thread" case cheaply — the
   descendant test is a `parent` chain walk, bounded by thread depth);
   alternatively restrict v1 to topic locks only.

## What MSG-1 must provide (all verified present)

- Total predicate with per-kind extension point (`envelope_error`,
  `aitbc/messaging.py`) — needs restructuring to per-kind schemas but the
  shape holds.
- Column-select narrowing (`_candidate_where`) — needs the per-kind OR
  split; the F1 "SQL only narrows" discipline is exactly the rule that
  keeps that safe.
- Deterministic `(block_height, tx_hash)` order (F3) — reused as the
  authority/vote ordering; nothing else in the index disagrees on order.
- Admission hook (`admission_error`) — covers new kinds automatically once
  the predicate does; no admission-code change needed.

Nothing in MSG-1's shipped design blocks any of the above; the only
structural change is the per-kind predicate split, which the F1-era code
already anticipates.
