# ABS-346 — Inbound Webhook Engine + HMAC + Config-Driven Mapping Rules

**Parent:** ABS-230 (Phase-2 ops surface) · **Module:** `backend/packages/webhooks`
**Related:** ADR-A-0004 (human-provisioned secrets), ADR-A-0010 (one write path),
`docs/specs/ABS-229-agentic-backend-phase1-spec.md` §13.

## §1 Goal

External systems (e.g. a deploy pipeline signalling "deploy done") drive the workflow
through per-hook HMAC-authenticated endpoints whose mapping rules are configuration.
Matched actions run through the **same** transition engine + event log as `/agent/v1`
and `/api/v1` operations, so the orchestrator sees the change in its normal poll with
zero special plumbing (ADR-A-0010 — one write path, no parallel transition logic).

## §2 Endpoint

`POST /webhooks/:hook` — outside `/agent/*` and `/api/*`, so the server's bearer-auth
hook (`isGuarded`) skips it: a webhook authenticates by HMAC signature, not a token.
Registered in an **encapsulated** Fastify context with a raw-string body parser so the
HMAC is computed over the exact received bytes (the default JSON parser discards them);
the rest of the server keeps default JSON parsing.

Responses:

| Case | Status | Body |
|------|--------|------|
| Valid signature, rule applied | 200 | `{ matched, applied: true, action, … }` |
| Valid signature, no rule matched (documented no-op) | 200 | `{ matched: false }` |
| Valid signature, selector unresolved (blocked) | 200 | `{ matched: true, applied: false, reason: "selector_unresolved" }` |
| Missing/invalid signature | 401 | `{ error: "invalid_signature" }` |
| Unknown hook id | 404 | `{ error: "unknown_hook", hook }` |
| Malformed JSON | 400 | `{ error: "invalid_json" }` |
| Matched action the core rejects (illegal edge / CAS / bad kind) | core status (400/404/409) | core error body |

## §3 HMAC signature

HMAC-SHA256 over the raw body under the hook's per-hook secret. Header
`x-webhook-signature: sha256=<hexdigest>` (GitHub/Bitbucket convention). Verification is
constant-time (`crypto.timingSafeEqual`) and fails closed on a missing secret, missing
header, or length mismatch.

### #PATH_DECISION — replay / timestamp handling (closed in ABS-369)

Replay-window / timestamp-nonce protection was **deferred** in this story (below) and is
now **closed by ABS-369**. Original decision, retained for provenance:

- Providers in scope (deploy pipelines, forge PR hooks) deliver over TLS to a
  non-idempotent action set gated by the transition engine's own **compare-and-set**
  (`expect_from`). A replayed "deploy succeeded → Ready for Development" either repeats an
  already-applied state (CAS NOOP, 409, no double write) or is rejected as an illegal edge
  — so a naive replay cannot silently double-drive the workflow.
- `comment`-action rules had **no** CAS backstop: a captured, validly-signed request
  replayed N times appended N duplicate comments. That gap is what ABS-369 closes.

**ABS-369 mechanism (#PATH_DECISION).** A `comment` (and any) action is made idempotent
against replay by two additive gates in `runHook`:

1. **Signed-timestamp skew gate.** When a request carries a timestamp header
   (`x-webhook-timestamp`, configurable via `WEBHOOK_TIMESTAMP_HEADER`), the timestamp is
   **authenticated** by folding it into the HMAC material — the signature is computed over
   `${timestamp}.${rawBody}`, so the timestamp cannot be altered without invalidating the
   signature. A timestamp outside `WEBHOOK_REPLAY_SKEW_SECONDS` (default 300) of now is
   rejected `403 stale_timestamp` before any action runs. Requests with no timestamp keep
   the legacy body-only signing contract (backward compatible).
2. **Delivery-id nonce cache.** The delivery id is the verified **signature itself** —
   byte-identical for a captured replay, and already bound to timestamp + body + secret. A
   bounded in-process TTL set (`NonceCache`, TTL = skew window) records each seen delivery
   id after a definitive non-error outcome; a second delivery within the window is an
   idempotent no-op (`200 { matched:true, applied:false, reason:"replayed" }`). The set
   prunes expired entries on every access, so it cannot grow unbounded: an entry that has
   evicted is, by construction, older than the skew window and is refused by gate (1).

   *Alternative considered:* a separate payload-derived idempotency-key header, keyed
   independently of the signature. **Rejected** — it adds a header the signer must also
   bind for no extra safety over reusing the signature the server already verifies.

**Single-instance assumption (#PLAN_UNCERTAINTY, resolved).** The nonce cache is
in-process; the single-shipper deployment runs one process, so this is sufficient.
Distributed/multi-instance nonce sharing is a separate future concern if the shipper scales
out. `transition`-action idempotency remains guaranteed by the CAS path (regression-guarded).

HMAC integrity of the body is the authentication gate for this story (AC#1); the ABS-369
gates layer replay protection on top of it.

## §4 Configuration & env convention (env prereqs)

Secrets are **human-provisioned** (ADR-A-0004, human-only boundary #4): the module uses a
secret handed to it, never generates or persists one.

- `WEBHOOKS_CONFIG` — rule definitions, **carrying no secrets**. Inline JSON (starts with
  `[`) or a path to a JSON file. A `HookDefinition` is `{ name, orgKey, projectKey, rules }`.
- `WEBHOOK_<NAME>_SECRET` — the HMAC secret for hook `<name>` (uppercased), e.g. hook
  `deploy` → `WEBHOOK_DEPLOY_SECRET`. A hook whose secret env var is unset is **skipped**
  with a warning; the loader never invents one.
- Unset `WEBHOOKS_CONFIG` → empty registry; the route still mounts and every request gets
  `404 unknown_hook`.
- `WEBHOOK_REPLAY_SKEW_SECONDS` (ABS-369) — **config, not a secret.** Bounded skew window
  for the signed-timestamp replay gate. Default `300`. Doubles as the nonce-cache TTL.
- `WEBHOOK_TIMESTAMP_HEADER` (ABS-369) — **config, not a secret.** Header carrying the
  signed unix-seconds timestamp. Default `x-webhook-timestamp`. Lower-cased for lookup.

## §5 Mapping rules

A rule is `{ match, target, action }`:

- `match: { path, equals? }` — dotted path into the payload; fires when the value
  deep-equals `equals`, or (no `equals`) when the value is merely present. First matching
  rule wins.
- `target` (entity selector), **always resolved inside the hook's own (org, project)**:
  - `{ item: "ABS-1" }` — a constant key fixed in config; the payload cannot influence it.
  - `{ path: "deployment.ticket" }` — key read from the payload, validated against the key
    grammar `^[A-Za-z][A-Za-z0-9]*-\d+$`, then resolved only within the hook's project.
- `action`:
  - `{ type: "transition", to, expectFrom? }` → core `transition()`, actor `webhook:<hook>`.
  - `{ type: "comment", kind, body? | bodyPath? }` → core `postComment()`, actor
    `webhook:<hook>`.

### §5.1 Selector scoping / injection hardening (AC#5)

- Payload traversal (`getPath`) reads only own enumerable properties of plain objects and
  array indices; `__proto__` / `constructor` / `prototype` segments and descent into a
  scalar yield `undefined` (prototype-pollution safe).
- A payload-derived key that fails the grammar, is not a string, or names an item outside
  the hook's (org, project) resolves to nothing → the rule is a **blocked no-op**; no write,
  no event. A payload can never escape the selector to touch an unintended item.

## §6 One write path

`runHook` calls the existing `transition()` / `postComment()` core services — the same
functions `/agent/v1` and `/api/v1` use. No new transition logic; events and comments carry
`actor=webhook:<hook>`, and transitions publish to the same event bus (SSE), so a
webhook-driven change is indistinguishable downstream from an agent/human one.

## §7 Acceptance evidence

`backend/packages/webhooks/test/webhooks.test.ts` (10 tests, run against live Postgres):
HMAC accept/reject (AC#1, unit + HTTP), transition rule → engine + event actor (AC#2),
comment rule → actor (AC#3), unmatched no-op writes nothing (AC#4), cross-project selector
+ prototype-pollution shape blocked, fixed-selector immune to payload redirection (AC#5),
end-to-end over HTTP through the route + raw-body HMAC, and `loadHooks` env wiring (AC#6).
Module wired in `backend/apps/server/src/server.ts` (AC#6).
