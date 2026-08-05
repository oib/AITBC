# Key escrow: threshold secret sharing

`aitbc.crypto.key_recovery` splits a sensitive key into `shares_total` shares, any
`shares_required` of which reconstruct it. This note records why the implementation looks
the way it does, because the failure it replaces was silent.

## The defect (CORE-16)

`escrow_key` accepted and validated a `shares_required` threshold, and `KeyEscrow`
enforced `shares_total >= shares_required >= 1`, so the API presented an M-of-N scheme.
The split underneath was an XOR n-of-n.

Recovering with exactly `shares_required` shares of a larger total XOR'd a **subset** and
returned wrong key material with no error — `recover_key`'s only guard was
`len(shares) < shares_required`, which such a call satisfies. A 3-of-5 escrow of a known
32-byte key returned 32 bytes of unrelated data, and the caller would use it as a key.

## The implementation

Shamir Secret Sharing over GF(2^8), Rijndael polynomial `0x11B`:

- one random polynomial per secret byte, with the byte as the constant term
- coefficients from `secrets.token_bytes` — these are what stand between an attacker
  holding `k-1` shares and the key
- evaluated at `x = 1..n`; recovery is Lagrange interpolation at `x = 0`

## Why the threshold cannot be argued down

Shamir does not fail loudly on its own: interpolating from fewer than `k` points yields a
lower-degree polynomial and a plausible-looking wrong answer. Two properties close that:

1. **`k` and the x-coordinate travel inside each shard.** Recovery reads the threshold
   from the shares, so it holds regardless of what the caller passes. A caller-supplied
   `shares_required` may *tighten* the requirement, never loosen it.
2. **A 4-byte digest of the secret is carried in each share.** Corrupt, foreign or mixed
   share sets fail with an integrity error rather than returning bytes.

Shard layout: `[x][k][digest:4][one evaluation byte per secret byte]`.

## The generator

The exp/log tables use **3** as the generator. **2 is not a generator of this field** — it
has multiplicative order 51, not 255 — so tables built from it are not a bijection and
`mul`/`div` silently return wrong results. The first version of this fix made exactly that
mistake, which is the same class of defect as the bug being fixed: correct-looking
arithmetic returning wrong answers with no error.

`tests/unit/test_key_recovery_threshold.py` asserts the field laws directly (bijection,
identity, division inverts multiplication, commutativity) so the tables cannot regress
unnoticed.

## Operational notes

- Shares are key-adjacent material. Fewer than `k` reveal nothing about the key — that is
  the point of the scheme — but each should still be stored as a secret.
- `shares_total` is capped at 255: GF(2^8) has only 255 non-zero points, and `x = 0` is
  the secret itself.
- An HSM-backed custody implementation remains preferable for production. This provides
  the correct algorithm in software.
