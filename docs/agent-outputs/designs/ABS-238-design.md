# Design: ABS-238 — Server-seitiges Context-Packet + `get --brief`
## API Interface Design & Slot-Selector Architecture

**Artifact version**: 2026-07-16
**Design system**: `docs/design/DESIGN_SYSTEM.md` (template — see §8 Deviations)
**Story**: ABS-238 · Backend S6 · Parent epic: ABS-229
**Spec references**: `specs/ABS-229-agentic-backend-phase1-spec.md` §4/§6/§7/§12 (amended 2026-07-15) ·
`adrs/agentic/ADR-A-0021-agentic-delivery-backend.md` §(c)/§(f) ·
ABS-313 design-constraint (v3-Design-Constraint on ticket)
**Produced by**: ui-ux-design agent · 2026-07-16

---

## §1 Scope of This Design

ABS-238 delivers the server-side context-packet composition endpoint, the `get --brief`
brief-view variant, the adapter subcommands that expose both, the capability probe, and the
single-function modification to `build_packet()` in `scripts/orchestrator.sh` that adopts
the server packet when the adapter supports it.

The design document specifies:

| Area | Section |
|---|---|
| Slot-selector function architecture (v3-Design-Constraint) | §2 |
| `GET /items/:key/packet` — response format contract | §3 |
| `GET /capabilities` — capability probe format | §4 |
| `GET /items/:key?view=brief` (`get --brief`) — brief view | §5 |
| `build_packet()` modification — probe, fallback, kill-switch | §6 |
| Cache-key update for the new code path | §7 |
| Design-system deviations | §8 |
| Design Acceptance Criteria (testable, DAC-numbered) | §9 |

**Out of scope** (mirrors the ticket scope fence):
- Policy injection into packet (Phase 3, ABS-231)
- SSE/dashboard surfaces (ABS-234)
- Mock adapter changes (mock has no `packet` op by design — it is a fallback target)
- Any `orchestrator.sh` line outside `build_packet()` and the one-time probe helper
  (ADR-A-0010 / ADR-A-0021 §(f))

---

## §2 Slot-Selector Architecture (v3-Design-Constraint from ABS-313)

### 2.1 Rationale

Spec §6 [A-313] mandates that each packet slot is selected by its own encapsulated function.
Today the selectors read `comment.kind` (migration-format); in the ABS-313 schema amendment
they will read typed records. The encapsulation ensures the data source per slot can be
swapped without changing either:
1. the packet output format (the rendered text blocks consumed by seats), or
2. the adapter subcommand surface (`packet <id>` in `backend-tracker.sh`).

### 2.2 Slot-Selector Function Signatures

Each selector lives in `packages/core/src/packet/selectors/` as a standalone module with
its own unit-test file. Selectors accept a typed DB-query interface (dependency-injected),
never a raw DB handle.

```typescript
// packages/core/src/packet/selectors/handoff.ts
export async function selectHandoff(
  db: PacketDb,
  itemId: string
): Promise<CommentBlock | null>
// Returns: the latest comment row where kind = 'handoff', or null.
// Future: will read from typed HandoffRecord instead of comment.kind.

// packages/core/src/packet/selectors/transitionReason.ts
export async function selectTransitionReason(
  db: PacketDb,
  itemId: string
): Promise<CommentBlock | null>
// Returns: the latest transition EVENT reason (from event table, kind='transition').
// Fallback: if no transition event exists (imported v2 ticket), returns the latest
// comment row where kind = 'transition-reason'.
// Future: will read from typed TransitionRecord when ABS-313 schema lands; the
// event-first / comment-fallback logic moves into the typed record query.

// packages/core/src/packet/selectors/gateResults.ts
export async function selectGateResults(
  db: PacketDb,
  itemId: string,
  handoffAt: Date | null
): Promise<CommentBlock | null>
// Returns: the latest comment where kind = 'gate-results' AND at > handoffAt.
// Returns null when no handoff exists OR gate-results is not newer than the handoff.
// Future: will read from typed GateResultsRecord.

// packages/core/src/packet/selectors/decisions.ts
export async function selectDecisions(
  db: PacketDb,
  itemId: string
): Promise<CommentBlock[]>
// Returns: ALL comments where kind IN ('decision', 'bsa-decision'), ordered by
// `at` ASC (oldest first). Never empty; returns [] when no decisions exist.
// Future: will read from typed DecisionRecord.
```

### 2.3 `PacketDb` Interface

The injected database interface used by selectors — this is the contract that allows test
doubles (no real DB required in selector unit tests):

```typescript
// packages/core/src/packet/PacketDb.ts
export interface CommentBlock {
  at: Date;
  kind: string;
  actor: string;
  body: string;
}

export interface TransitionEvent {
  at: Date;
  from: string;
  to: string;
  reason: string;
  actor: string;
}

export interface PacketDb {
  // Latest comment matching kind predicate, or null
  latestComment(
    itemId: string,
    kinds: string[]
  ): Promise<CommentBlock | null>;

  // All comments matching kind predicate, ordered by at ASC
  allComments(
    itemId: string,
    kinds: string[]
  ): Promise<CommentBlock[]>;

  // Latest transition event for the item, or null
  latestTransitionEvent(
    itemId: string
  ): Promise<TransitionEvent | null>;

  // Count of comments NOT included in the packet
  omittedCommentCount(
    itemId: string,
    includedCommentIds: bigint[]
  ): Promise<number>;
}
```

### 2.4 Packet Composer

The composer is a single function that calls the four selectors and assembles the output.
It must not contain inline kind-matching — all filtering is delegated to the selectors.

```typescript
// packages/core/src/packet/composePacket.ts
export async function composePacket(
  db: PacketDb,
  item: WorkItemCore,  // frontmatter + body sections
  sections: string[]   // body sections in render order
): Promise<string>
// Calls all four selectors, assembles output per §3 format, returns the packet string.

export async function composePacketBrief(
  db: PacketDb,
  item: WorkItemCore,
  sections: string[]
): Promise<string>
// Assembles brief view per §5 format.
```

---

## §3 `GET /items/:key/packet` — Response Format Contract

Route: `GET /agent/v1/projects/:project/items/:key/packet`
Auth: bearer token (same as all `/agent/v1/` routes, Spec §4)
Response: `text/plain; charset=utf-8`

### 3.1 Output order (Spec §6, amended 2026-07-15)

The response body MUST contain the following blocks, in this exact order:

```
<slot 1: full YAML frontmatter>
---

<slot 2: all body sections verbatim (Goal / Scope / Acceptance Criteria / Definition of Done / Test Plan / ADR Context)>

## Comments

<slot 3: latest handoff block — full comment block header + body>

<slot 4: latest transition-reason block — rendered from latest transition EVENT or v2 fallback comment>

<slot 5: latest gate-results block — ONLY if newer than the latest handoff; omitted otherwise>

<slot 6: all decision + bsa-decision blocks, oldest first>

<slot 7: breadcrumb — ONLY when N > 0 omitted comments>
(N ältere Kommentare weggelassen — vollständige Historie: tracker get <key>)
```

### 3.2 Comment block rendering

Each included comment block follows the canonical mock format (Spec §5.3):

```
### <at-iso8601-Z> | kind: <kind> | actor: <actor>

<body>

```

(Blank line before and after the body block.)

Transition-reason blocks (slot 4) are synthesized from the event:
```
### <event.at-iso8601-Z> | kind: transition-reason | actor: <event.actor>

Transition: <event.from> -> <event.to>. Reason: <event.reason>

```
This is byte-identical to the block the mock writes (Spec §3/§5 golden constraint).

### 3.3 Decisions (`## Comments` section header)

The `## Comments` header is always emitted (even if handoff, gate-results, and
transition-reason are all absent), because decisions MUST always be included (AC §6).
If the item has zero comments of any kind, the section is present with no blocks below it
(not omitted).

### 3.4 Breadcrumb (slot 7)

The breadcrumb line is emitted iff `N > 0`, where N = total comments on the item MINUS the
comments included in the packet (slots 3–6):

```
(N ältere Kommentare weggelassen — vollständige Historie: tracker get <key>)
```

`<key>` is the item key (e.g. `ABS-238`). N is computed by `PacketDb.omittedCommentCount`.

### 3.5 Byte-stability contract

The packet response is deterministic for a given item state. Two calls to
`GET /items/:key/packet` with the same `updated` timestamp produce byte-identical responses.
Timestamps in comment blocks are ISO-8601 Z, second precision (Spec §5.5).

### 3.6 No byte cap

The server-composed packet has no byte cap (unlike the `build_packet()` legacy path which
truncates at `ORCH_PACKET_MAX_BYTES`). Composition replaces truncation; the packet size is
bounded by the selected slots, not the full comment history.

---

## §4 `GET /capabilities` — Capability Probe Format

Route: `GET /capabilities`  
(Note: this route is at the server root, **not** under `/agent/v1/projects/:p/` — it is
project-independent. Auth: bearer token.)

Response: `text/plain; charset=utf-8`

```
packet
brief
```

One capability token per line, no trailing spaces. Phase 1 emits exactly `packet` and `brief`
on separate lines. Unknown adapters (mock, jira) do not implement this route.

### 4.1 Adapter subcommand

`backend-tracker.sh capabilities` → `GET /capabilities` verbatim output (printed, exit 0).

Unknown response (non-200) → exit non-zero (treated as "capability not available" by the
caller).

### 4.2 Probe behavior in `build_packet()`

The probe MUST fire at most once per `build_packet()` run. The result is stored in a
run-scoped shell variable `_ORCH_PKT_CAP_RESOLVED` and reused for subsequent calls within
the same orchestrator process invocation. If `ORCH_PACKET_MODE=full`, the probe is skipped
entirely and the legacy path is used (§6.2).

---

## §5 `GET /items/:key?view=brief` — Brief View (`get --brief`)

Route: `GET /agent/v1/projects/:project/items/:key?view=brief`  
Adapter: `backend-tracker.sh get --brief <id>`

Response: `text/plain; charset=utf-8`

### 5.1 Output contents

The brief view includes, in order:

1. Full YAML frontmatter (identical to full `get`)
2. Goal section body (verbatim: `## Goal\n\n<body>`)
3. Acceptance Criteria section body (verbatim: `## Acceptance Criteria\n\n<body>`)
4. Latest handoff comment block (full block, same rendering as packet slot 3)

No `## Comments` header wrapping the handoff block; the handoff block is emitted directly
after the AC section.

### 5.2 Intended consumers

- Dedup gate (orchestrator intake classifier): the frontmatter + Goal + AC provides enough
  signal for title-similarity and AC dedup without embedding the full comment history.
- Intake classifier: same use case.

### 5.3 Adapter behavior

```bash
# backend-tracker.sh snippet
get_brief() {
    local key="$1"
    curl_get "$BASE_URL/agent/v1/projects/$TRACKER_PROJECT/items/$key?view=brief"
}
```

`get --brief <id>` maps to the `?view=brief` query parameter. Exit codes follow the same
HTTP-to-adapter mapping as `get` (Spec §7 error table).

---

## §6 `build_packet()` Modification in `scripts/orchestrator.sh`

### 6.1 Scope constraint (ADR-A-0010 / ADR-A-0021 §(f))

The diff to `scripts/orchestrator.sh` is bounded to `build_packet()` and a single
`probe_packet_capability()` helper function immediately preceding it. No other function,
variable initialization block, or call site in `orchestrator.sh` is modified.

### 6.2 Kill-switch (ORCH_PACKET_MODE)

| Value | Behavior |
|---|---|
| unset or `packet` | Use server packet if probe returns support; else full-dump fallback |
| `full` | Always use legacy full-dump path (probe skipped) |

`ORCH_PACKET_MODE=full` is the ABS-111 escape: default-on new behavior with an `ORCH_*`
kill-switch restoring the prior path byte-identically.

### 6.3 Probe helper

```bash
# probe_packet_capability — fires once per process invocation (cached in
# _ORCH_PKT_CAP_RESOLVED). Returns "packet" when the adapter supports it, "full"
# otherwise.  Never called when ORCH_PACKET_MODE=full.
probe_packet_capability() {
    if [ -n "${_ORCH_PKT_CAP_RESOLVED:-}" ]; then
        printf '%s' "$_ORCH_PKT_CAP_RESOLVED"; return
    fi
    local cap="full"
    if tracker capabilities 2>/dev/null | grep -qx "packet" 2>/dev/null; then
        cap="packet"
    fi
    _ORCH_PKT_CAP_RESOLVED="$cap"
    printf '%s' "$cap"
}
```

### 6.4 Modified `build_packet()` control flow

```
build_packet(ticket, from, to, role, pf):

  1. If ORCH_PACKET_MODE=full  → pkt_mode = "full"
     Else                       → pkt_mode = probe_packet_capability()

  2. Compute cache sig (§7 — includes pkt_mode)

  3. If cache hit (meta matches sig) → copy cache → return

  4. Build header (unchanged: role/ticket_id/from_status/to_status/resume/tracker_cmd/note)

  5. If pkt_mode = "packet":
       dump = tracker packet "$ticket"   ← server-composed packet body
       Write to cache:
         printf '%s\n\n=== TICKET ===\n' "$header"
         printf '%s\n' "$dump"
         (no truncation; no =LATEST HANDOFF= section — packet already includes handoff)

  6. Else (pkt_mode = "full", legacy path):
       dump  = tracker get "$ticket"
       handoff = extract_latest_handoff(dump)
       [existing truncation + LATEST HANDOFF logic — byte-identical to pre-ABS-238]

  7. Write sig to meta; copy cache to pf
```

**Key difference from legacy**: in `packet` mode the `=== LATEST HANDOFF ===` section is
NOT appended (the server packet already includes the handoff in its slot 3). The
`=== TICKET ===` header marker is retained to preserve the spawn packet format that seats
parse (the ABS-238 BE developer must confirm with the System Architect that seats parse
`=== TICKET ===` correctly when the handoff appears inline rather than as a separate section).

### 6.5 Fallback matrix

| Adapter | `capabilities` output | Effective `pkt_mode` |
|---|---|---|
| `backend-tracker.sh` (Phase 1) | contains "packet" | `packet` |
| `mock-tracker.sh` | unknown / no op → exit non-zero | `full` (fallback) |
| `jira-tracker.sh` | unknown / no op → exit non-zero | `full` (fallback) |
| Any adapter with `ORCH_PACKET_MODE=full` | probe skipped | `full` |

---

## §7 Cache-Key Update

The existing cache key (signature stored in `$PACKETS_DIR/<ticket>.meta`) is extended to
include `pkt_mode`:

```
updated=$updated|from=$from|to=$to|role=$role|resume=$resume|wmode=$wmode|tracker_cmd=$TRACKER_CMD|max_bytes=$ORCH_PACKET_MAX_BYTES|pkt_mode=$pkt_mode
```

`pkt_mode` is `"packet"` or `"full"` (the resolved value, not the env var). This ensures
that switching `ORCH_PACKET_MODE` or upgrading to a backend adapter that now supports
`packet` invalidates the cache even if the ticket's `updated` timestamp is unchanged.

`max_bytes` is retained in the signature for backward compatibility (the legacy path still
uses it) and to invalidate any cached full-dump packet when `ORCH_PACKET_MAX_BYTES` changes.

---

## §8 Design-System Deviations

### Deviation 1 — All visual design tokens are unresolved (pre-existing; same as ABS-234)

`docs/design/DESIGN_SYSTEM.md` is a starter template with all `{{PLACEHOLDER}}` tokens
unresolved. ABS-238 is a backend API and orchestrator integration story — it has no new
UI surfaces. All design elements are API response formats (plain text) and function
interfaces (TypeScript). Visual design tokens are therefore not applicable to this story.

**Required action**: same as filed in ABS-234 §7 Deviation 1. The System Architect should
resolve the template tokens before any UI-surface design story requires concrete values.

### Deviation 2 — No UI library components (expected for backend story)

ABS-238 has no UI/SPA component surfaces. `{{UI_LIBRARY}}` token is irrelevant for this
story. The SPA surfaces driven by this story's data are the existing Ticket Detail Drawer
(ABS-234) and Kanban board — no new UI surfaces are introduced.

---

## §9 Design Acceptance Criteria (ABS-238)

> These ACs are the **Design Test contract** (QAS-Design seat). Each must be
> verifiable against the running ABS-238 backend implementation + orchestrator.

**Design artifact**: `docs/agent-outputs/designs/ABS-238-design.md`
**Design system**: `docs/design/DESIGN_SYSTEM.md` (template, placeholder tokens — see §8)

---

### Schema Conformance

- [ ] **DAC-1 — Slot-selector isolation**: The four slot selectors
  (`selectHandoff`, `selectTransitionReason`, `selectGateResults`, `selectDecisions`) exist
  as separate TypeScript modules in `packages/core/src/packet/selectors/`, each with its
  own unit-test file. Verify: `find packages/core/src/packet/selectors/ -name "*.ts"` lists
  at least 4 selector files and 4 matching `*.test.ts` files. Each test file exercises its
  selector with a `PacketDb` mock double (no real DB) and passes in isolation:
  `pnpm --filter @core test -- selectors`.

- [ ] **DAC-2 — Packet response format**: `GET /items/ABS-XXX/packet` for a ticket
  containing all comment kinds (handoff, gate-results, decision, bsa-decision,
  transition-reason via backend-native event AND a v2-imported comment row) returns a
  response matching the §3.1 ordering contract:
  (1) frontmatter, (2) body sections, (3) latest handoff block, (4) latest transition-reason
  block, (5) gate-results block (if newer than handoff), (6) all decision/bsa-decision blocks
  oldest-first, (7) breadcrumb iff N > 0.
  Verify: byte-diff of the response against a manually composed golden fixture; diff must be
  empty.

- [ ] **DAC-3 — Transition-reason slot: event-first, v2-fallback**:
  For a backend-native ticket where the latest transition was performed via the backend
  transition service, the transition-reason block in the packet is rendered from the
  transition event (not a comment row).
  For an imported v2 ticket where the only transition record is a `kind: transition-reason`
  comment row, the packet uses that comment row.
  Verify using two golden fixtures: one backend-native (confirms event source), one v2-import
  (confirms comment fallback). Both fixtures pass the same packet golden-diff test.

- [ ] **DAC-4 — Capability probe response**: `GET /capabilities` returns a plain-text
  response containing the line `packet` (matched by `grep -x "packet"`). The adapter
  subcommand `backend-tracker.sh capabilities` produces the same output. Verify:
  `bash scripts/backend-tracker.sh capabilities | grep -cx "packet"` equals `1`.

- [ ] **DAC-5 — `get --brief` contents**: `GET /items/:key?view=brief` returns exactly:
  full frontmatter + `## Goal` section + `## Acceptance Criteria` section + latest handoff
  block. No other comment blocks are present.
  Verify: the brief response for a fixture with 10 comments contains exactly 1 handoff block
  and 0 decision/gate-results/transition-reason blocks (grep-count assertions in the
  conformance suite).

---

### Accessibility

*(No new UI surfaces — DAC-6 and DAC-7 are interaction-protocol ACs, not visual ACs.)*

- [ ] **DAC-6 — Decisions always included**: For a ticket with zero decisions, the packet
  response contains the `## Comments` section header with no decision blocks below it (not
  omitted). For a ticket with 3 decisions (2 `decision` + 1 `bsa-decision`), all 3 blocks
  appear in the packet in chronological order. Verify via grep-count on the two fixtures.

- [ ] **DAC-7 — Breadcrumb correctness**: For a ticket whose total comment count exceeds the
  sum of comments included in the packet (handoff + gate-results-if-newer + all decisions +
  transition-reason), the breadcrumb line
  `(N ältere Kommentare weggelassen — vollständige Historie: tracker get <key>)` appears
  at the end of the response with the correct numeric N.
  For a ticket where every comment is included in the packet, no breadcrumb line is emitted.
  Verify using two golden fixtures with differing N values.

---

### Responsive / Integration

- [ ] **DAC-8 — Bounce regression (≤32 KB AC correctness)**: A ticket fixture with
  comment history totalling >32 KB (the prior byte-cap threshold) produces a packet response
  that includes the full `## Acceptance Criteria` section without truncation.
  Verify: `wc -c < <(backend-tracker.sh packet <fixture-key>)` is ≤ 32768 bytes (packet is
  compact), AND `grep -c "## Acceptance Criteria"` equals `1` in the response.

- [ ] **DAC-9 — ORCH_PACKET_MODE=full kill-switch byte-parity**: With
  `ORCH_PACKET_MODE=full` and `TRACKER_CMD=scripts/backend-tracker.sh`, `build_packet()`
  produces output byte-identical to the pre-ABS-238 `build_packet()` for the same ticket
  and `ORCH_PACKET_MAX_BYTES`. Verify: run the new `build_packet()` with `ORCH_PACKET_MODE=full`
  vs. the baseline implementation; byte-diff must be empty.

- [ ] **DAC-10 — Adapter fallback (mock/jira)**: With `TRACKER_CMD=scripts/mock-tracker.sh`
  and `ORCH_PACKET_MODE` unset, `build_packet()` uses the legacy full-dump path (probe
  returns `full`). Verify: `_ORCH_PKT_CAP_RESOLVED` is `full` after the first
  `build_packet()` call; the packet file content matches the pre-ABS-238 baseline for the
  same ticket.

---

### Key User Flows

- [ ] **DAC-11 — Probe fires once per orchestrator run**: In a single orchestrator
  process invocation that spawns 3 different tickets, `tracker capabilities` is called
  exactly once. Verify by counting `capabilities` invocations in the orchestrator
  bash trace (`set -x` in a test wrapper) for a 3-ticket dry-run.

- [ ] **DAC-12 — Cache byte-stability**: Two successive `build_packet()` calls for the
  same ticket (same `updated` timestamp) produce byte-identical packet files without a
  second `tracker packet` or `tracker get` call (cache hit). Verify: instrument
  `tracker` calls in a test run; confirm the packet-fetch call fires exactly once for
  the first call and is absent for the second.

- [ ] **DAC-13 — Orchestrator existing tests unbroken**: All tests in
  `tests/test-orchestrator.sh` (and `tests/orchestrator.d/*.sh`) pass with no new failures
  after the `build_packet()` change. Verify: `bash tests/test-orchestrator.sh` exit 0.

---

## §10 Summary Table

| Design area | Driven by ABS-238 artefact | AC |
|---|---|---|
| Slot-selector function isolation | §2 architecture + `packages/core/` modules | DAC-1 |
| Packet response format (Spec §6 order) | §3 format contract | DAC-2 |
| Transition-reason: event-first + v2 fallback | §2.2 `selectTransitionReason` | DAC-3 |
| Capability probe format | §4 route + adapter subcommand | DAC-4 |
| `get --brief` contents | §5 brief view | DAC-5 |
| Decisions always included | §3.3 + §2.2 `selectDecisions` | DAC-6 |
| Breadcrumb correctness | §3.4 breadcrumb logic | DAC-7 |
| Bounce regression (AC truncation fix) | §3.6 no byte cap | DAC-8 |
| Kill-switch byte-parity | §6.2 ORCH_PACKET_MODE=full | DAC-9 |
| Adapter fallback (mock/jira) | §6.5 fallback matrix | DAC-10 |
| Probe fires once per run | §4.2 + §6.3 | DAC-11 |
| Cache byte-stability | §7 cache-key update | DAC-12 |
| Existing orchestrator tests | §6.1 scope constraint | DAC-13 |

**Design-system deviations**: 2 reported (see §8). Both are pre-existing (no project-specific
values set); ABS-238 has no new UI surfaces so neither deviation requires immediate resolution.

**Next**: Ready for Development (be-developer implements the backend packet endpoint,
selector modules, adapter subcommands, and orchestrator `build_packet()` modification).
QAS-Design verifies DAC-1 through DAC-13 against the running implementation.
