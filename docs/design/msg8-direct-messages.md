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

## (3) Construction — libsodium `crypto_box`, ephemeral sender keypair

Primitive: **`nacl.public.Box`** — X25519 ECDH → HSalsa20 key derivation →
XSalsa20-Poly1305 AEAD. All from libsodium via PyNaCl; nothing composed by
us — no custom KDF, mode, or padding.

Per message:

1. Recipient has a published `dm_key` (X25519 public key, signed).
2. Sender generates a fresh ephemeral X25519 keypair per message,
   `ct = Box(eph_sk, recip_pk).encrypt(plaintext, random_nonce())`.
3. Envelope `body` carries a JSON object:
   `{ "to": <recipient canonical address>, "epk": <ephemeral pubkey>,
      "nonce": <24 B>, "ct": <ciphertext> }` — binary fields base64
   (`-` no padding variants rejected at parse; use `base64.b64decode`
   with `validate=True`).
4. The recipient derives `Box(recip_sk, epk).decrypt(ct, nonce)`.

The ephemeral-key design (rather than `SealedBox`) is chosen deliberately:
the tx signature already authenticates the sender, and `SealedBox`'s
anonymity buys nothing — sender address is public metadata anyway. Using
a plain `Box` with an ephemeral sender key keeps the construction the
textbook ECIES hybrid while preserving the option of sender-attributed
plaintext (a `from` field inside the ciphertext, if wanted later).

**Parameters:** X25519 public keys 32 B; nonce 24 B (`randombytes`, never
reused — it is per-message random, ephemeral key means reuse is
cryptographically impossible anyway); Poly1305 tag 16 B embedded in `ct`.

**Size budget.** Body cap is 4096 UTF-8 bytes (`MAX_MESSAGE_BODY_BYTES`).
Envelope overhead: `epk` 32 B + `nonce` 24 B + tag 16 B = 72 B binary
→ ~96 B base64, plus JSON keys/`to` (~80 B). **Plaintext limit ≈ 3900
bytes**; the CLI must enforce it before signing (fail locally, not after
a fee is paid). Longer messages: out of scope — chunking invites ordering
and truncation attacks; a future `v: 1` kind can address it deliberately.

## (4) Index and API

The index stores and serves **ciphertext only** — the same bounded-query
model over `transaction` rows; nothing new is persisted.

New routes under the existing bounded shape (same `limit`/`offset`
bounds, same `<height>:<tx_hash>` cursor):

| route | purpose |
|---|---|
| `GET /rpc/messaging/dm-keys/{address}` | latest valid `dm_key` for an address (the most recent in `(block_height, tx_hash)` order wins — key rotation = publish again) |
| `GET /rpc/messaging/dm/{address}` | the recipient's inbox: `dm` envelopes with `to == address`, cursor-paged; each row carries `tx_hash`, `block_height`, `sender` (from the tx), `epk`, `nonce`, `ct` |

No decryption server-side — the node never sees plaintext or private
keys. `sanitize_chain_obj` (MSG-4b) applies to display fields only; `ct`,
`epk`, `nonce` are binary-safe base64 and pass through untouched.

**Predicate additions** (`aitbc/messaging.py`): two new kinds —
`dm_key` (fields `enc_pubkey`, `agent_address`; `enc_pubkey` is a 32-byte
X25519 public key, base64) and `dm` (fields `to`, `epk`, `nonce`, `ct`,
`agent_address`; `topic` still required — a `dm` carries `topic: "dm"`,
a reserved slug; it does not appear in topic listings). Size caps:
`enc_pubkey`/`epk`/`nonce` fixed-length; `ct` bounded by the body cap.

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

- **Known-answer vectors** from libsodium's published `crypto_box` test
  vectors (fixed `eph_sk`/`nonce`/`pk` → fixed `ct`); run through our
  envelope codec, not just the raw primitive.
- **Tamper tests:** flip one byte in `ct`, `nonce`, `epk` → decrypt fails
  (Poly1305), no partial plaintext.
- **Wrong recipient:** a second keypair cannot open `ct` (decrypt raises).
- **Replay/ordering:** re-submitted identical envelope is a distinct tx
  (chain replay protection is the signature/nonce — already covered by
  MSG-3c); two DMs to the same recipient order correctly under the
  `(block_height, tx_hash)` cursor.
- **Predicate tests:** `dm_key`/`dm` admitted; `dm` with bad `to`, bad
  field lengths, or a `body` field on an action kind handled per the
  MSG-2 "ignored" rule; unknown kinds still refuse at admission.
- **Cap tests:** plaintext at exactly the ~3900 B limit passes;
  limit+1 fails client-side before any fee.
- **Review checklist for the independent crypto reviewer:** primitive
  choice (crypto_box vs hand-rolled ECIES), nonce reuse impossibility
  under ephemeral keys, the `dm_key` binding signature's domain
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
