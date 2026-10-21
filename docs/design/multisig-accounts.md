# Multisig accounts — design

`MULTISIG-ACCOUNTS-1` (#356). Design only — no node or CLI code in this
document. Prior art: `RESET-TREASURY-MULTISIG-1` (progress ledger), which
proved the current chain cannot spend from a multisig address and ruled
multisig **out of scope for the bc-2 reset itself**. This document is the
post-reset design for real on-chain multisig accounts.

## 1. Current behavior — evidence

The chain today is single-signature end to end:

- **Exactly one 65-byte signature** per transaction:
  `aitbc/crypto/signature_recovery.py:33` (`SIGNATURE_LENGTH = 65`);
  `:62–63` raises `SignatureMalformed` for any other length.
- **One signature → one address → must equal sender**:
  `apps/blockchain-node/src/aitbc_chain/rpc/utils.py:162`
  (`verify_transaction_signature` → `verify_signature`,
  `signature_recovery.py:131`); the consensus call site is
  `apps/blockchain-node/src/aitbc_chain/state/state_transition.py:1477–1479`
  (`signature = tx_data.get("signature")` → `verify_transaction_signature`).
- **Unsigned is rejected**:
  `apps/blockchain-node/src/aitbc_chain/state/v9_policy.py:36,123–127` —
  any `tx_type` outside `V9_UNSIGNED_ALLOWED_TX_TYPES` returns
  `"missing_signature"`. On bc-2 every gate activates at height 1, so all
  blocks are v14 and a signature is always required.
- **The existing "multisig" CLI is not real**:
  `cli/aitbc_cli/commands/wallet/multisig.py:46` invents a random
  `secrets.token_hex(20)` address — no keypair, no chain object; `:168`
  appends signer *address strings* to a local JSON list. Nothing is
  signed or submitted.
- **Real threshold cryptography already exists but is proof-scoped**:
  `aitbc/bridge/multisig.py:1–3,73` implements M-of-N secp256k1
  verification — but over the **validator set** for bridge proofs, not
  over account signer sets. The building block (`check_threshold`,
  per-signature `recover_address`) is reusable in shape.
- **An unspendable address passes every genesis check**:
  `genesis_builder.py:61–74` + `scripts/ops/check-alloc-file.py`
  validate EIP-55 form only; a multisig-style derived address would be
  accepted into an allocation file today.
- **The version-gate mechanism exists and already carries height into
  admission**: `state_transition.py:906` (`get_block_version`), `:958`
  (`get_block_version_for_height`), and
  `state/admission_authority.py:92–117` already plumbs `block_version` /
  `block_height` into the admission path — the hook a multisig gate
  needs.

## 2. Design

### 2.1 Signer-set account rule

A **multisig account** is defined by `(sorted_signers, threshold)`:

- `sorted_signers` — a set of normal secp256k1 account addresses,
  de-duplicated and sorted (the same address-sort convention used by
  `multi_validator_poa.py`'s validator ordering, so ordering is
  deterministic across all nodes).
- `threshold` — `1 <= m <= len(sorted_signers)`.
- Spending from the account requires `>= threshold` **distinct** valid
  signatures, each from a different member of `sorted_signers`, each
  recovering over the transaction digest.
- Receiving is unrestricted — it is a normal account with a balance;
  only the *spend* path is gated.

### 2.2 Deterministic address derivation

```
preimage = "aitbc-multisig-v1" || 0x3A || uint8(m) || 0x3A ||
           concat(sorted_lowercase_signer_addresses, sep=0x2C)
address  = EIP-55( keccak256(preimage)[12:] )
```

Properties:

- **Deterministic** — the same `(signers, threshold)` derives the same
  address on every node and in the CLI; no registry read is needed to
  verify an envelope's claimed signer set (recompute and compare).
- **Existing addresses untouched** — derivation is only ever applied to
  *new* multisig accounts; no existing address changes.
- **EIP-55-shaped** — a 20-byte keccak tail like any account, so it
  passes the genesis/allocation checks (`genesis_builder.py:61–74`) and
  every `0x[a-fA-F0-9]{40}` validation in the codebase.

**Why a keyless derived address is safe (the 160-bit argument).** A
secp256k1 address is `keccak256(uncompressed_pubkey)[12:]` — 160 bits.
To steal from a multisig account an attacker needs a *private key*
whose pubkey hashes to the same 160-bit tail. That is a second-preimage
attack on Keccak-256 truncated to 160 bits: ~2^160 work — identical to
grinding a key for *any* existing funded address, and 2^32× harder than
a 128-bit collision search. There is no structural shortcut: nothing in
the msig preimage maps back into ECDSA key space, so the attacker cannot
do better than generic preimage search.

**Is the domain prefix enough to keep it out of the normal address
space?** Strictly, no — both domains emit a 160-bit keccak tail, so
accidental overlap is *possible* with probability ~2^-160 per pair, i.e.
negligible. But the prefix is still load-bearing for a different
reason: **chosen-input injection**. Without a domain tag, the msig
preimage could be crafted to *be* a 64-byte uncompressed pubkey — the
attacker picks `signer` bytes equal to their own public key, derives
`keccak(pubkey)[12:]`, and obtains a "multisig" address they fully
control with one key. With the `"aitbc-multisig-v1"` tag, no preimage
can ever be a bare pubkey, so *by construction* a derived address can
never be the address of a secp256k1 key someone holds — the only
remaining collision path is the generic ~2^160 second-preimage. The
prefix also makes the address **self-describing**: admission can detect
"sender is signer-set-scoped" without a registry lookup, which is what
lets apply-time pick the multisig verify path cleanly.

### 2.3 Wire format

A versioned transaction variant — no change to the single-signature
shape for normal accounts:

```jsonc
{
  "type": "transfer",                // any existing spend-type tx
  "sender": "0x<derived-msig-addr>",
  "signature": "",                    // present (v9 policy satisfied), empty
  "payload": {
    // ... normal payload ...
    "auth": {
      "scheme": "msig-v1",
      "signers": ["0x…", "0x…", "0x…"],   // sorted, exactly the derived set
      "threshold": 2,
      "signatures": ["0x<65-byte sig>", "0x<65-byte sig>"]
    }
  }
}
```

Rationale: `payload.auth = {"signer","message","signature"}` is already
the established envelope for embedded auth
(`state_transition.py:1252–1274`); `payload.auth` with `scheme: msig-v1`
extends that pattern instead of inventing a second one. Keeping
`signature` present-but-empty preserves `tx_data.get("signature")`
checks (`state_transition.py:1027`) and the v9 missing-signature policy
unchanged for the new shape.

### 2.4 Version gate / activation height

A new block version (**v16** — v15 is taken by the edge-registration
de-commit, `EDGE-REG-CONSENSUS-1`) registered in
`get_block_version_for_height` (`state_transition.py:958`) with an
operator-named activation height:

- Below activation: a tx carrying `payload.auth.scheme = "msig-v1"` is
  rejected at admission (`invalid_signature_scheme`), and a derived
  msig address spending as a normal single-sig tx is rejected as today
  (signature never verifies — the address has no key).
- At/above activation: `verify_transaction_signature` branches on
  whether `sender` is a derived msig address; if so it validates the
  envelope (§2.5). Single-sig accounts are completely untouched.
- History is safe: `get_block_version`/`state_transition_version`
  replay machinery (`state_transition.py:906–958`) replays old blocks
  under their recorded version — the standard gate mechanism, **not a
  chain reset**.

### 2.5 Envelope validation (apply-time)

At/above the gate, for a sender whose address derives as msig:

1. Recompute `derive(signers, threshold)` from the envelope's claimed
   `signers`+`threshold`; require equality with `sender` — a tx can never
   claim a signer set it didn't derive.
2. Require `1 <= threshold <= len(signers)` and
   `len(signatures) >= threshold`.
3. Verify each signature: `recover_address(tx_digest, sig)` ∈ `signers`,
   all distinct; reject duplicates (`len(set) == len(sigs)`).
4. Require the count of *valid distinct* signatures `>= threshold`.
5. Everything else (nonce, balance, fee) unchanged.

### 2.6 Clean refusal by old nodes — free

An old node seeing a v16 msig envelope treats `signature` as empty and
`payload.auth` as unknown payload → `verify_transaction_signature`
fails (`SignatureMalformed`/`SignatureMismatch` path). No special-case
compat code is needed — the refusal is the same path that rejects any
bad signature today. (For full safety the activation still pins the
block version, so old nodes also refuse the *block version* itself via
the existing version machinery rather than accepting a block containing
msig spends.)

### 2.7 Replay protection and nonce rules

- **Nonce**: the multisig account's own nonce, consumed once at apply —
  identical semantics to a normal account; no second nonce dimension.
- **Signature binding**: each collected signature signs the same
  canonical tx digest (which already embeds `chain_id`, EIP-155-style);
  a sig collected for tx A cannot be replayed onto tx B or another
  chain.
- **Envelope-level replay**: rejecting duplicate signer signatures in
  one envelope (§2.5.3) prevents padding the count with repeats.

### 2.8 Fee payer

The multisig account itself — it is a normal account with a balance;
fee deduction is unchanged (no fee delegation in v1).

### 2.9 CLI collection/assembly (`wallet/multisig.py`)

Replace the JSON-only stub with the real flow:

- `multisig create --signers … --threshold m --name <name>` — derives
  the address (same formula), stores `{address, signers, threshold}`.
- `multisig propose --wallet <name> --to <addr> --amount <x>` — builds
  the canonical unsigned tx + digest, writes a portable proposal file.
- `multisig sign --wallet <name> --tx <file> --signer <key>` — signs the
  digest with a real secp256k1 key via the existing wallet signing path;
  appends to the proposal's `signatures` (real sigs, not strings).
- `multisig submit --wallet <name> --tx <file>` — assembles the
  `payload.auth` envelope and POSTs `/rpc/transaction`.

### 2.10 Treasury migration

Migration is a **normal transfer** from the current single-key treasury
to the derived multisig address — never an address rewrite: allocations,
history, and the old address are untouched; the old treasury simply
holds a zero balance afterwards. (This is also the only correct
migration: a multisig address is a *new* account, not a flag on the old
one.)

## 3. Consensus-critical changes (coordinated fleet restart required)

1. `state_transition` verify path — branch on derived-msig senders and
   validate the envelope (§2.5). Apply-time code → new block version.
2. Admission — accept/validate the `payload.auth.scheme = "msig-v1"`
   envelope at/above the gate.
3. Gate registration — `get_block_version_for_height` gains the v16
   entry + operator-named activation height.
4. `signature_recovery`/`verify_signature` — multi-signature envelope
   decode path (new function; existing single-sig path untouched).

## 4. Golden vectors / gate additions

- New gate row in the gates table (v16, multisig accounts).
- Vectors: valid m-of-n spend lands; m−1 signatures refused; foreign
  signer refused; duplicate signer signature refused; nonce replay of
  the same envelope refused; pre-activation refusal; derivation
  determinism (same set/threshold → same address on two nodes);
  single-sig tx from a derived address refused.

## 5. What the rehearsal harness must prove

A `multisig` phase: create a 2-of-3 account, fund it, spend with two
signatures → balance moves; negative — single-sig refused, foreign
signer refused, replay refused; and a treasury-migration fixture
(single-key → msig transfer lands, old address untouched).

## 6. Effort estimate and order

| component | estimate | notes |
|---|---|---|
| Derivation + spec | ~1d | keccak via `eth_utils`/hashlib; canonical encoding + vectors |
| Wire format + `state_transition` verify path | ~2–3d | consensus-critical; envelope validation + replay safety |
| Gate registration + version plumbing | ~0.5d | mechanism already exists (`get_block_version_for_height`) |
| CLI collection/assembly | ~1–2d | `wallet/multisig.py` already has the JSON skeleton to replace |
| Harness scenario + canned vectors | ~1d | new phase + fixtures |
| Docs/operator runbook | ~0.5d | custody + migration procedure |

**Order**: this design doc → wire-format spec + vectors → consensus
verify path + gate → CLI → harness scenario → docs/runbook.

## 7. Ships without a hard fork

- The derivation spec and CLI collection UX (client-side only).
- **Funding** a derived address — receiving is a normal account credit.
  ⚠️ Caveat: funds sent **before** the v16 gate activates are locked
  until activation (the address has no single key); the CLI should warn.
- The *spend* path is the only consensus-gated piece — it ships as a
  versioned change with a coordinated fleet restart, **not** a chain
  reset (the `state_transition_version` machinery protects all recorded
  eras).

## 8. Decisions the operator owes

- **Threshold policy for the treasury** — e.g. 2-of-3 vs 3-of-5 for the
  treasury account; who is the tie-break.
- **Signer holders** — which people/devices hold the treasury signer
  keys, and the custody/backup arrangement per signer.
- **Activation timing relative to the soak** — whether v16 activates
  during the 3-day soak, right after it, or in a later window (a
  coordinated fleet restart is required either way; activating before
  soak-end puts a consensus change inside the rollback window).
