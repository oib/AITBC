# MSG-2 — votes, moderation and reputation as signed on-chain actions (design note, Phase 0)

Status: **accepted with amendments** (director review; answers to §10
incorporated verbatim in §10 and the referenced sections). Written from a
read-only audit of `origin/main` `25eba26f5` (MSG-1 + MSG-FIX-1 landed). Builds on
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
once sealed. **Stated plainly: the tx-hash tiebreak is grindable** — a
signer can vary a harmless field until its hash orders where it wants,
so it can win a same-block founding race or make its own second vote
the "last" one. It matters only for same-block races and is accepted as
a limitation; nothing cross-block is grindable.

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

**Director amendment — the authority scan must not truncate silently.** A
topic-scoped scan bounded by `SCAN_BOUND` lets a non-moderator bury real
grants under paid ineffective envelopes. The scan therefore runs in two
phases:

1. **Founding moderator** — a pure SQL aggregate: the minimum
   `(block_height, tx_hash)` over the topic's valid `post`/`reply` rows.
   Aggregates are exact, not scan-bounded (the F2 fix already made topic
   aggregates SQL-side).
2. **Fixpoint over moderator-signed actions** — iterate: collect the
   `mod_grant`/`mod_revoke` rows signed by *current* set members (one
   bounded query per signer, canonical order), apply them in canonical
   order under the set-at-that-position rule, repeat until the set stops
   changing. Each iteration can only add signers that an earlier
   iteration's actions authorised, so it converges; a defensive pass cap
   (64) raises rather than truncates. Envelopes from non-members never
   enter the scan at all — spam costs them fees and moves nothing.

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
- **Founding moderator revoked.** Allowed, with the director's rule: a
  `mod_revoke` that would leave the set **empty** is ineffective (marked
  `effective: false`, no state change). A topic can never become
  unmoderated by a revoke, including self-revoke — to abandon a topic a
  moderator must grant to someone else first.
- **Self-revocation.** Allowed, subject to the same non-empty rule.
- **`mod_grant` by a non-moderator.** Indexed, ineffective.
- **Grant to self.** No-op (already in the set or not — granting to self
  as a non-member is ineffective either way).

No global moderators: there is no derivation path that produces one, and
none is proposed (MSG-11, parked). The `broadcast` slug follows the same
rule as everything else — its first poster moderates it (director
decision: uniform rule, no slug exception). Because existing topics get
moderators retroactively, **Phase 1 must ship a read-only report of every
live topic and its would-be founder**, taken from
`/rpc/messaging/topics`, before activation — so we see who gains the
authority before it exists.

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
  action wins. `hide`/`pin` targets must resolve to a `post`/`reply`
  (director decision) — action kinds are not hideable targets.
- `pin`/`unpin`: **amended** — pinning does not reorder the main list.
  The `<height>:<tx_hash>` cursor must stay monotone, so a topic listing
  returns pinned messages as a separate `pinned` array beside `messages`
  (each entry carrying `pinned: true` + `pinned_by`), while `messages`
  stays in canonical order and keeps paging correctly.
- `lock`/`unlock`: the topic (or the subtree rooted at `target`) carries
  `locked: true` + `locked_by`. A lock applies at the action's **sealed
  canonical position** — messages ordered after it are `after_lock`
  (excluded by default, shown flagged under `include_hidden`), earlier
  ones are unaffected. A lock never blocks `unlock`, `mod_grant`,
  `mod_revoke`, or any moderation action — moderation actions always apply
  regardless of lock state. Votes on locked content still count.
  Unlock scope (operator decision, rule (b)): a row sealed while its
  topic (or an ancestor thread) was locked keeps `after_lock = true`
  permanently — an unlock clears only rows sealed after it, and rows
  sealed before any lock are never flagged. A second `lock` while an
  interval is open does not move its start; an `unlock` with no open
  interval is a no-op.
  Subtree-lock walk is bounded (`LOCK_WALK_LIMIT = 512` descendants
  walked per root, across all of that root's intervals, in canonical
  order): a reply beyond the bound is treated as outside the locked
  subtree — visible, not flagged. Stated as the fail-open side of a
  deliberate bound so reads never hang on a giant thread.

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
- **Vote/score aggregates are exact, never scan-bounded** (director
  amendment — same class of bug as F2): the standing vote per
  `(signer, target)` is computed in SQL — a `ROW_NUMBER() OVER
  (PARTITION BY signer, target, topic ORDER BY block_height DESC, tx_hash DESC)`
  — the claimed topic is in the partition, so a wrong-topic vote (a sealed
  no-op per the rule above) occupies its own partition and can never
  displace the voter's valid vote on the same target
  window over the topic's valid `vote` rows (SQLite ≥3.25; a MAX-join
  equivalent exists if ever needed), then `sum`/`count` over the rn=1
  survivors. A bounded Python scan that silently understates a score is
  not acceptable; where exactness is impossible the field must carry an
  explicit `truncated` flag.
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
**Reputation gates nothing in v1** (director decision): it is a display
field only and must never feed authority, visibility, or admission.

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
- New derived helpers: `_moderators_at(topic, height, tx_hash)`
  (the fixpoint scan of §2 — moderator-signed rows only, iterated to
  convergence, never truncated silently), `_moderation_state(...)`,
  `_standing_votes(...)` (exact SQL window aggregate of §4). Message-list
  scans stay under `SCAN_BOUND`; authority and vote derivations do not —
  they are aggregates/fixpoint queries, exact by construction.
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

## (10) Open questions — decided (director, verbatim answers)

1. **Founding moderator revocable?** — "yes, with one rule: a
   `mod_revoke` that would leave the moderator set empty is ineffective.
   A topic can never become permanently unmoderated by a revoke,
   including self-revoke. To abandon a topic, grant to someone first."
   (Incorporated in §2.)
2. **`broadcast` moderation.** — "accept the uniform rule, no slug
   exception. Before activation, Phase 1 must include a read-only report
   of every live topic and its would-be founder, taken from
   `/rpc/messaging/topics`. Existing topics get moderators retroactively,
   so we need to see who." (Incorporated in §2.)
3. **Hide/pin targets.** — agreed: must resolve to `post`/`reply`.
4. **Reputation weighting.** — agreed: flat ±1 with `VOTE_CAP`, no sybil
   weighting; "reputation gates nothing in v1. It is display only, and
   must never feed authority." (Incorporated in §5.)
5. **`include_hidden`.** — agreed: withholds the body.
6. **Lock forms.** — agreed: both forms supported; depth/bound and
   beyond-bound behaviour stated in §3.

Plus three amendments applied throughout: authority scan is a fixpoint
over moderator-signed rows, never truncated (§2); vote/score aggregates
are exact SQL, or carry an explicit `truncated` flag (§4); pinned
messages move to a separate `pinned` response list so cursors stay
monotone (§3); locks never block moderation actions and apply at the
lock's sealed position (§3); the tx-hash tiebreak's same-block
grindability is stated plainly and accepted (§2).

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
