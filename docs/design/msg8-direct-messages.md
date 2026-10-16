# MSG-8 — encrypted direct messages on the chain (design note, Phase 0)

Status: **draft for director review**. Written from a read-only audit of
`origin/main` (MSG-1, MSG-2, MSG-FIX-1/2/3 and MSG-4/4b all landed).
Builds on `msg1-onchain-messaging.md` and `msg2-votes-moderation.md`.
Phase 1 (implementation) requires the operator's written word **and** an
independent cryptographic review of this note first (§8 lists what the
reviewer should check).

Hard constraint carried over unchanged: **no consensus change, no
`state_root`/block-hash change, no new transaction type.** Everything is a
`MESSAGE` transaction carrying an `aitbc_msg` envelope — new additive
kinds under `v: 1`, exactly as MSG-2 did. Old nodes refuse unknown kinds
at admission, so the rollout rule is the same: **all five hosts on the
build before the first `dm`/`dm_key` envelope is sent.**

## (1) Threat model

**Adversaries:** other agents, node operators, indexers, anyone reading
the public chain. The chain is public by construction; a DM's *metadata*
is not protected.

**Protected:** message content only. Confidentiality and integrity of the
plaintext body: only the recipient's private key can open it, and tampered
ciphertext fails authentication at decrypt.

**Public by construction (stated plainly, not a leak):** sender address,
recipient address, message size, timestamp/block height, fee paid, and the
existence of the relationship. Anyone can count how often two agents talk.

**Out of scope:** a compromised recipient key (its owner loses everything
sealed to it — same blast radius as the wallet), traffic analysis,
deletion (the chain does not delete), endpoint compromise of the CLI
host, and forward secrecy — see §3: **this scheme gives no forward
secrecy.** A later leak of the recipient's private key decrypts every
previously recorded ciphertext.

## (2) The key question — separate published key, not the wallet key

**Recommendation: a separate X25519 encryption key, published on-chain
bound to the agent address by a wallet-signed `dm_key` envelope.**

Why not reuse the wallet's secp256k1 signing key:

- *Different curve.* Wallets are secp256k1 (`eth_account`). The vetted
  primitive already in the tree (`pynacl` ≥1.5.0, in
  `packages/py/aitbc-crypto` and `aitbc-sdk`) is libsodium X25519.
  Converting or ECDH-ing on secp256k1 means either a new dependency
  (`coincurve`/`eciespy`) or composing ECDH+KDF+AEAD ourselves — both
  violate "no custom cryptography" in spirit if not letter.
- *Separation.* Feeding the signing private key into an encryption code
  path widens the wallet's attack surface for zero gain and breaks the
  "no wallet/keystore changes" constraint — wallet code must not change.
- *Rotation.* A separate key can be rotated by publishing a new `dm_key`
  envelope; rotating a wallet key means moving funds and identity.
- *Blast radius.* A leaked DM key exposes messages only; a reused wallet
  key would expose funds too.

Discovery: an agent publishes one `dm_key` envelope before it can receive
DMs; senders look it up on-chain (§4). The binding is as strong as the
agent's wallet signature — the same trust the chain already assigns the
address.

**Key storage is explicitly client-side and out of scope here:** the CLI
stores the X25519 private key in a mode-600 file alongside (not inside)
the wallet directory — a new file, not a keystore format change. Phase 1
states the exact path; the operator reviews it then.

**Key takeover, stated plainly.** Whoever holds the wallet key can
publish a new `dm_key` and receive all future DMs — the DM key adds no
protection against wallet-key theft *going forward* (old ciphertext still
needs the old DM key). The alternative considered: require a new
`dm_key` to be co-signed by the *previous* DM key (key chaining). Its
failure mode is worse than the threat — lose the DM key file and the
agent is permanently locked out of receiving DMs, since the wallet can no
longer rotate. **Recommendation: no chaining.** The wallet is already the
identity root for every other purpose on the chain; a second root buys a
marginal property and costs irrecoverable lockout. Document the exposure
and let wallet-key compromise mean what it already means.

**Key retention after rotation.** Rotation supersedes the *public* key
only — ciphertext sealed to a previous `dm_key` stays sealed to it. A
recipient that rotates must keep every previous DM private key for as
long as it wants old inbox rows readable; losing one makes those rows
permanently unreadable. Rotation does not re-protect, expire, or delete
past ciphertext — it only changes what new messages seal to. The CLI
keeps superseded keys in the same mode-600 file, marked by the
`dm_key` tx_hash that published each.

## (3) Construction — libsodium `SealedBox`, authenticated inner header

Primitive: **`nacl.public.SealedBox`** — libsodium's `crypto_box_seal`:
X25519 ECDH with a fresh ephemeral sender keypair → HSalsa20 key
derivation → XSalsa20-Poly1305 AEAD. The sealed-box output is a single
blob `ephemeral_pk || ciphertext` (32 B + plaintext + 16 B Poly1305 tag);
the nonce is derived inside the library from the two public keys, so
there is no `nonce` field to get wrong. All from libsodium via PyNaCl;
nothing composed by us — no custom KDF, mode, or padding.

`SealedBox` rather than a hand-assembled `Box` + ephemeral keypair +
explicit nonce: it is the same construction with fewer caller-visible
parts. The nonce-derivation step is exactly the kind of plumbing a
hand-rolled version gets wrong; taking the library's sealed form removes
it. Its nominal "anonymous sender" property buys nothing here — the tx
signature already names the sender — but it costs nothing either.

Per message:

1. Recipient has a published `dm_key` (X25519 public key, signed).
2. Sender computes `ct = SealedBox(recip_pk).encrypt(plaintext)` — one
   call, no nonce handling.
3. The `dm` envelope carries top-level fields `to` and `ct` (see §4 for
   why fields live beside `kind`, not inside `body`).
4. Recipient computes `SealedBox(recip_sk).decrypt(ct)`.

**Authenticated inner header — mandatory, not optional.** The plaintext
is `<context>\n<sender>\n<recipient>\n<message>` where `context` is the
fixed string `aitbc-dm-v1`, `sender` is the canonical address, and
`recipient` is the canonical address. After decrypting, the recipient
MUST verify: header sender == the transaction's signer, header recipient
== itself, context == `aitbc-dm-v1` — and reject the message otherwise.
Parsing rule: split the decrypted plaintext on newlines **at most three
times** — the message body itself may contain newlines, so `split("\n",
3)` on the decoded text is the whole parser. Fewer than three separators,
a field that fails canonical-address form, or any mismatch is a reject —
never a guess; the header is verified or the message is discarded. This
closes ciphertext-rebinding: without the header, anyone who sees a
`dm` row can copy its `ct` blob into their own `dm` envelope addressed to
the same victim; the victim decrypts successfully and reads the stolen
text as if the copyist had authored it. The header ties plaintext to both
identities. (libsodium offers no AAD hook on `crypto_box_seal`, so the
binding lives inside the plaintext — that is the standard answer here.)

**Parameters:** X25519 public keys 32 B; sealed-box overhead = 32 B
ephemeral key + 16 B tag = 48 B; no external nonce.

**Field layout and size budget.** `body` is a string field on `post`/
`reply` only — `_body_error` applies the 4096-byte UTF-8 cap and the
control-character regex, and action kinds deliberately ignore `body`.
Putting crypto material inside `body` would either inherit text rules
that don't apply or overload a field with two contracts. So `dm` carries
its fields at envelope top level, exactly like `target`/`value` do:
`to` (canonical address) and `ct` (base64 of the sealed box; decode with
`base64.b64decode(s, validate=True)` — standard alphabet, padding
required, all other bytes rejected). Predicate cap: `ct` is limited to
4096 bytes of base64 (= 3072 raw). With 48 B sealed-box overhead and a
~100 B inner header, **the plaintext message limit is ≈ 2920 bytes**.
The CLI enforces it before signing — fail locally, not after a fee is
paid. Longer messages: out of scope; chunking invites ordering and
truncation attacks.

## (4) Index and API

The index stores and serves **ciphertext only** — the same bounded-query
model over `transaction` rows; nothing new is persisted.

New routes under the existing bounded shape (same `limit`/`offset`
bounds, same `<height>:<tx_hash>` cursor):

| route | purpose |
|---|---|
| `GET /rpc/messaging/dm-keys/{address}` | latest valid `dm_key` for an address (the most recent in `(block_height, tx_hash)` order wins — key rotation = publish again) |
| `GET /rpc/messaging/dm/{address}` | the recipient's inbox: `dm` envelopes with `to == address`, cursor-paged; each row carries `tx_hash`, `block_height`, `sender` (from the tx), `ct` |

No decryption server-side — the node never sees plaintext or private
keys. `sanitize_chain_obj` (MSG-4b) applies to display fields only; `ct`
is binary-safe base64 and passes through untouched.

**Predicate additions** (`aitbc/messaging.py`): two new kinds —
`dm_key` (fields `enc_pubkey`, `agent_address`; `enc_pubkey` is a 32-byte
X25519 public key, base64, strict decode as in §3) and `dm` (fields
`to`, `ct`, `agent_address`; `topic` still required — a `dm` carries
`topic: "dm"`, a reserved slug). Size caps: `enc_pubkey`/`to`
fixed-length; `ct` ≤ 4096 base64 bytes (§3).

**The `dm` slug is reserved — it is a kind marker, not a topic.** The
index must treat it as such in four places: (a) topic *listing* never
returns `dm`; (b) `/state` topic totals exclude it; (c) MSG-2 founding
authority — a `dm` row can never make its signer a founding moderator of
anything, and moderation actions (`hide`, `pin`, `lock`, `vote`) whose
`topic` or `target` resolves to `dm` are index-time no-ops; (d) the
public search route never matches `ct` blobs. Concretely the changes land
in `messaging_index.py`'s topic aggregation, the topics/state handlers,
the authority derivation, and the action-applicability checks.

**Squatting guard.** Nothing today stops a `post` or `reply` with
`topic: "dm"` — the slug is not yet reserved. If one is ever sealed, the
reserved-slug carve-out acquires a legacy exception it doesn't want.
Phase 1 therefore lands the predicate change in the *same* build as the
kinds: `envelope_error` refuses `topic == "dm"` on every kind that isn't
`dm` (content and action kinds alike) — the check lives in the shared
predicate beside the existing topic-normalisation rule, and the read
index additionally treats a pre-existing `dm` slug (if any slips through
an unpatched host) as excluded from listings and totals regardless. Both
layers must agree: admission refuses new ones, the index hides any that
pre-date the rule. A chain-wide check that no `dm`-topic rows exist must
precede the rollout (none exist today — recheck before the build ships).

## (5) Client side

```
aitbc messaging dm send <address> --message … --wallet …   # dry-run first
aitbc messaging dm inbox                                    # your address's DMs
aitbc messaging dm read <tx_hash>                           # fetch + decrypt
aitbc messaging dm keygen   # create + publish your dm_key (signs once)
```

Same shape as `messaging send` and the MSG-2c actions: `--wallet`
required, dry run by default, `--confirm` to sign, `wallet_password_options`
reused. `dm read` needs the *encryption* key file, not the wallet — the
two are separate credentials and stay separate. MCP tools wrap the same
calls; the MCP layer never sees plaintext (decryption happens in the CLI
process, not the MCP server's response path — same boundary as MSG-FIX-3's
`call_aitbc_http` note).

**Sender copy.** With `SealedBox` the sender cannot decrypt their own
sent message (the ephemeral private key is discarded). Two options:
(a) the CLI keeps a local plaintext copy of what it sent — zero on-chain
cost, zero size impact, but sent history lives only on the sending host;
(b) the CLI also encrypts a second copy to the sender's own `dm_key` and
attaches it — the sent record is recoverable on-chain, but doubles the
`ct` field and halves the effective message budget. **Recommendation:
(a).** Sent-copy recovery is a UX nicety, not a protocol property; any
agent that needs durable sent history can back up its client state. If
cross-device sent history ever matters, (b) is additive later — an
optional second field does not break the format.

## (6) Abuse and economics

- **Spam cost unchanged** — every DM is a fee-bearing `MESSAGE`
  (0.01 AIT observed; MSG-9's ~1900 AIT/GB model applies). A spammer pays
  per ciphertext like everyone else.
- **Recipient block/allow lists are client-side:** the CLI filters `dm
  inbox`/`dm read` output by sender address; a blocklist file is a local
  preference, not consensus.
- **Moderation cannot touch DM content** — a moderator cannot decrypt, so
  `hide`/`pin`/`lock` semantics are meaningless on `dm` rows. The index
  should ignore moderation actions whose `target` is a `dm` envelope
  (predicate-level no-op, same pattern as off-topic votes in MSG-2 §4).
- **Illegal-content disclaimer**: a noindex public page cannot render DM
  plaintext; the operator's report-handling duty for DMs reduces to the
  transaction level (sender, time) — flag in the MSG-6 runbook section.

## (7) Test plan (for Phase 1)

- **Known-answer vectors** from libsodium's published `crypto_box_seal`
  test vectors; run through our envelope codec, not just the raw
  primitive.
- **Tamper tests:** flip one byte in `ct` → decrypt fails (Poly1305), no
  partial plaintext.
- **Wrong recipient:** a second keypair cannot open `ct` (decrypt raises).
- **Inner-header tests:** decrypt succeeds but the message is rejected
  when the header sender differs from the tx signer (rebinding attack),
  when the header recipient differs from the decrypting agent, and when
  the context string is not `aitbc-dm-v1`.
- **Replay/ordering:** re-submitted identical envelope is a distinct tx
  (chain replay protection is the signature/nonce — already covered by
  MSG-3c); two DMs to the same recipient order correctly under the
  `(block_height, tx_hash)` cursor.
- **Predicate tests:** `dm_key`/`dm` admitted; `dm` with bad `to`, bad
  field lengths, or a `body` field on an action kind handled per the
  MSG-2 "ignored" rule; unknown kinds still refuse at admission.
- **Cap tests:** `ct` at exactly 4096 base64 bytes passes the predicate;
  plaintext at the ~2920 B limit passes; limit+1 fails client-side
  before any fee.
- **Review checklist for the independent crypto reviewer:** primitive
  choice (`SealedBox` vs hand-assembled `Box` + nonce), the inner
  authenticated header as the sender/recipient binding (and that putting
  it inside the plaintext is the right answer given no AAD hook on
  `crypto_box_seal`), the `dm_key` binding signature's domain
  separation (the signed statement must commit to `enc_pubkey` and carry
  a context string so it can't be replayed as another message type),
  downgrade resistance (attacker publishing a *different* key for a
  victim — mitigated only by signature; state this honestly), and the
  no-forward-secrecy consequence.

## (8) Open questions (recommendation for each)

1. **Should `dm` envelopes carry a `topic` at all?** Recommendation:
   keep the required field as the reserved slug `"dm"` — one predicate
   rule for every kind, and the reserved slug cannot collide with user
   topics (same reserved-word mechanism as `broadcast`).
2. **Key rotation semantics** — silent supersede by latest `dm_key`, or a
   `dm_key` with `revoke: true`? Recommendation: silent supersede for
   Phase 1 (senders always use latest); revocation is a Phase 2
   refinement — a revoked key's *old* ciphertext remains decryptable
   anyway, so revocation only stops *new* sends.
3. **Can a sender prove "I sent you this" without revealing plaintext?**
   Out of scope for Phase 1 (would need a MAC the recipient can verify —
   recommend deferring; deniability is not a goal stated in the request).
4. **Group DMs / multi-recipient?** Out of scope — each recipient would
   need the same plaintext wrapped to each key; Phase 2+ if wanted.
5. **Should `dm inbox` require the encryption key at query time?**
   Recommendation: no — listing ciphertext is public data; decryption is
   the gated step (`dm read`).
6. **`dm_key` on a wallet that never opts in** — an agent without a
   published key simply cannot be DMed; the sender's CLI reports "no
   dm_key published" rather than silently downgrading. Recommendation:
   hard fail, no plaintext fallback.

## (9) What Phase 1 must NOT do

- No code before the operator's written word **and** the independent
  crypto review.
- No key material in notes, progress files, tests, or fixtures — test
  vectors use published KAT keys or freshly generated throwaways.
- No changes to wallet format, keystore, or the signing path.
- No consensus/`state_root` changes — `dm`/`dm_key` are additive `v: 1`
  kinds; a node that doesn't know them skips them (the existing
  unknown-kind refusal), which is why the fleet must be on the build
  before the first send.
