# Agent-signed message envelopes (v2.0 design)

**Status:** design — **not implemented**. Deferred work item from the 2026-09-14
operator decisions; this document is the agreed shape for when v2.0 picks it up.
Do not treat anything here as live behavior.

**Applies to:** `apps/agent-coordinator` (`/api/v1/agent/messages/*`,
`/v1/agents/*`), `apps/miner/agent_task_executor.py`,
`cli/aitbc_cli/commands/agent_task.py` + `agent-comm`.

---

## 1. Problem

Today `sender` in `POST /api/v1/agent/messages/send` is a self-asserted string.
The endpoint is publicly proxied on the hub (`/api/v1/agent/messages/` →
`127.0.0.1:8107`) with no authentication, and `AgentMessage` has no signature
field (`protocols/communication.py`). Anyone who can reach the route can send a
message claiming any `sender_id`, including a registered provider or buyer.

In the paid-delegation protocol (scenario 54) this means a third party can, for
example:

- send a `task_quote` as `aitbc-miner-1` with a hostile price,
- send a `task_accept` as the buyer to lock in a bad quote,
- send a fake `task_result` / `task_paid` to confuse either side.

The escrow checks (`escrow.agent == provider_wallet`, `escrow.task_id ==
task_id`) still gate money movement, so forged negotiation messages cannot
directly steal funds — but they can grief, wedge the state machine, or race the
honest party. Sender spoofing also affects non-payment traffic (`agent-msg`,
`agent-comm`, coordination messages).

## 2. Goals / non-goals

**Goals**

- Every stored message is attributable to a registered agent identity backed by
  a chain key: hold the key → the signature verifies → the sender field is
  honest.
- Verification at two layers: coordinator ingress (first line) and recipient
  re-verification (defense in depth — a compromised coordinator that tampers
  with stored envelopes is detectable).
- Rollout that does not break live agents: advisory → enforce.
- Reuse `aitbc.crypto.signature_recovery` / `recover_signer` — the repo's
  canonical secp256k1 convention — not a new signature stack.

**Non-goals**

- Confidentiality. The existing RSA `MessageEncryptor`
  (`encryption/message_encryption.py`) is a separate layer and stays as-is.
- Authorization/policy (who is *allowed* to talk to whom) — separate concern.
- Consensus/block signing — `consensus_signing.py` already covers that domain.
- Sybil resistance: registering many agents with many keys stays possible;
  signatures bind messages to identities, they do not rate identity creation.

## 3. Identity model

The chain wallet address is the root of agent identity. `agent_id` remains the
routing/display identifier; the registry gains a cryptographic binding:

```
agent_id  →  identity_address  (secp256k1, EVM-style 0x…)
```

**Registration attestation.** `POST /v1/agents/register` accepts (and in enforce
mode requires) two new fields:

```json
{
  "agent_id": "aitbc-miner-1",
  "identity_address": "0x…",
  "identity_proof": "0x…"   // signature by identity_address over the binding claim
}
```

`identity_proof` signs the canonical JSON of
`{"agent_id", "identity_address", "chain_id", "registered_at", "nonce"}` (see
§4 for canonicalization). The coordinator recovers the signer and requires it
to equal `identity_address`. This prevents a squatter binding *their* key to
*your* `agent_id` — the binding is only created by the key holder.

- The executor already publishes its wallet in registry `metadata.wallet`
  (`agent_task_executor.py`); v2.0 promotes this to the first-class
  `identity_address` field rather than a metadata convention.
- Re-registration with the same `agent_id` but a different
  `identity_address` is a **rotation event** (§7), not a silent overwrite.
- Agents that never authenticate (read-only directory entries, test fixtures)
  may keep `identity_address = null` in advisory mode only.

**Signing key vs wallet key.** Two options, both EVM-compatible:

1. **Wallet key directly** — operator-run agents (CLI on hub1/node0) already
   load wallet keystores (`load_wallet_for_payment`). Simplest; a compromised
   agent key = compromised funds.
2. **Dedicated agent signing key** (recommended for daemons) — a secp256k1 key
   generated per agent, stored in `/var/lib/aitbc/agent_keys/` `0600`,
   registered once. Compromise revokes the identity binding, not the wallet.
   The executor should prefer this; the CLI may use the wallet key since it is
   operator-invoked anyway.

## 4. Envelope format

`AgentMessage` and `SendMessageRequest` gain three fields:

```json
{
  "id": "msg_…",
  "sender_id": "aitbc-miner-1",
  "receiver_id": "buyer-hub1.aitbc.bubuit.net",
  "message_type": "task_quote",
  "timestamp": "…",
  "payload": { … },
  "ttl": 300,
  "signer": "0xProviderAddr",
  "signature": "0x…",
  "signature_version": "aitbc-msg-v1"
}
```

**Signed payload** — canonical JSON (sorted keys, compact separators, UTF-8) of
the full envelope *minus* `signature`, hashed and prefixed for domain
separation:

```
digest = keccak256("aitbc-agent-msg-v1:" + canonical_json(envelope_minus_sig))
signature = secp256k1_sign(digest, agent_key)
```

The domain prefix is mandatory: without it a message signature could be
replayed as a transaction signature (or vice versa) since both use secp256k1
over keccak digests. `signature_version` names the scheme so future format
changes are not ambiguous; unknown versions are rejected in enforce mode.

**Why sign the whole envelope, not just `payload`:** `sender_id`,
`receiver_id`, `message_type`, `timestamp`, and `id` are all attacker-useful
(re-targeting a quote to a different task, replaying into a different
correlation). Everything but `signature` is inside the signed bytes.

**Encrypted messages:** sign the *outer* envelope including the ciphertext
(`content` = ciphertext blob for `encrypt=true`). The coordinator can then
authenticate without reading plaintext. True end-to-end inner signatures
(sign-then-encrypt) are a v2.1 consideration; the delegation protocol uses
`encrypt=false` today and is fully covered by outer-envelope signing.

## 5. Verification

**Coordinator ingress (`POST /send`)**, behind config
`AGENT_MSG_SIGNATURE_MODE` = `disabled | advisory | enforce`:

1. Parse `signature`, `signer`, `signature_version`.
2. Recover the signer address via `recover_signer`-equivalent over the
   canonical envelope.
3. Require `recovered == signer` (EIP-55-insensitive via `canonical_address`).
4. Look up `sender_id` in the registry; require
   `agent.identity_address == signer`.
5. Timestamp within `±max(300s, ttl)` of now; reject future-dated beyond skew.
6. `id` / `message_id` dedup (already implemented for idempotency).

Failure handling: `advisory` → accept, log `msg_sig_verify=fail`, stamp
`signature_status` on the stored record; `enforce` → HTTP 403 with
`invalid_signature` / `identity_mismatch` / `stale_timestamp`.

**Recipient re-verification:** inbox/history return the stored envelope
verbatim (including `signature`/`signer`), so the receiver can re-run the same
check. `agent_task_executor` and `agent_task` should verify inbound envelopes
and ignore `signature_status=invalid` messages in enforce mode. This is what
makes coordinator tampering *detectable* rather than silently authoritative.

## 6. Replay protection

- `id` (server- or client-generated) + `message_id` dedup: a literal replay of
  the same envelope returns the existing record (already the case).
- `timestamp` window check bounds how long a captured envelope stays valid.
- `correlation_id`/`task_id` inside typed payloads bind messages to a specific
  negotiation — a replayed `task_quote` for an old task is ignored by the
  state machine even if the signature is valid.
- Optional later hardening: per-sender monotonic nonce in the signed fields.
  Not required for v2.0; the timestamp+dedup+task-binding combination covers
  the realistic replay window.

## 7. Rotation and compromise

- **Rotation:** `PUT /v1/agents/{agent_id}/identity` with `new_address`,
  `new_proof` (signed by new key over the binding claim) **and**
  `rotation_proof` (signed by the *old* key over
  `{agent_id, old_address, new_address, timestamp}`). Both signatures verify →
  binding updated; history keeps the old address for past messages.
- **Compromise:** operator sets agent `inactive` (existing endpoint) and clears
  `identity_address`; all further envelopes fail verification. If the signing
  key was the wallet key (option 1 in §3), wallet rotation is a separate,
  bigger operation — the reason dedicated keys are recommended.
- **Old messages:** signatures on historical messages verify against the
  `signer` value embedded in each envelope, so post-rotation verification of
  old traffic still works; registry lookup applies only to *new* sends.

## 8. Rollout plan

| Phase | Mode | What lands |
|---|---|---|
| A | `advisory` | Schema fields, signing in executor + `agent-task`/`agent-msg` CLI, coordinator verifies-and-logs, `signature_status` on stored records |
| B | `enforce` for `task_*` types | Money-path messages must verify; other types still advisory. Registration attestation required for new agents |
| C | `enforce` for all | `sender_id` must be registry-bound to `signer`; unsigned sends rejected |

Config flag `AGENT_MSG_SIGNATURE_MODE` (env `AGENT_MSG_SIGNATURE_MODE`),
default `disabled` in code, staged via env per node. Hub's coordinator is the
only enforcement point that matters while it is the sole coordinator.

## 9. Implementation map (for v2.0 pickup)

| File | Change |
|---|---|
| `aitbc/crypto/` | `sign_agent_envelope(dict) -> str`, `verify_agent_envelope(dict, sig, expected) -> bool` — thin wrappers over `signature_recovery` + canonical-JSON + domain prefix |
| `protocols/communication.py` | `AgentMessage.signature/signer/signature_version`; `signing_payload()` returning the canonical signed dict |
| `routers/messages.py` | `SendMessageRequest.signature/signer/signature_version`; ingress verify hook; `signature_status` in stored record and inbox/history responses |
| `routers/agents.py` + `routing/agent_discovery.py` | `identity_address` field, registration attestation, `PUT /{id}/identity` rotation |
| `config.py` | `AGENT_MSG_SIGNATURE_MODE`, timestamp-skew constant |
| `apps/miner/agent_task_executor.py` | sign outbound envelopes; verify inbound; ignore invalid |
| `cli/aitbc_cli/commands/agent_task.py`, `agent.py` (`agent-msg`) | sign with wallet/dedicated key; `--no-verify` escape hatch for advisory debugging |
| `apps/agent-coordinator/tests/` | spoofed sender rejected, tampered payload rejected, replay rejected, rotation honored, advisory-mode passthrough |

## 10. Open questions

- Should `agent_id` eventually *derive from* the identity address
  (`agent-<addr[:12]>`) instead of being a free string bound to it? Keeps one
  namespace but breaks existing ids.
- Do we want an HTTP-layer API key *in addition* to envelope signatures for
  `/send` (defense for the coordinator's own resource use, orthogonal to
  sender authenticity)?
- Multi-key agents (active + standby key) — deferred unless rotation pain
  shows up.
- Whether `identity_address` should be provable on-chain
  (`/rpc/identity/register` exists) vs registry-only. On-chain attestation is
  stronger but adds a write per registration; start registry-only.
