# Money types and the signature boundary

**Status**: Accepted · **Decided**: v0.23 (V23-36, formalised V23-45) · **Scope**: `apps/blockchain-node`

Money in this repository is `Decimal`. Four fields are `float` and must stay `float`. This
document says which, why, what it costs, and what changing it would take.

---

## The rule, and the exemption

`CLAUDE.md` states it plainly: *all financial code uses `Decimal`, never `float`*. It is
enforced, not merely documented — `scripts/lint/no_float_money.py` runs in pre-commit and CI,
and its baseline is **0**. Reaching zero took six widenings of the checker and 210 conversions
across coordinator-api, blockchain-node, the CLI and the SDKs (V23-33 … V23-40).

Four fields are exempt:

| field | file |
|---|---|
| `AIJobRequest.payment` | `apps/blockchain-node/src/aitbc_chain/rpc/ai_services.py` |
| `AIJobResponse.payment` | `apps/blockchain-node/src/aitbc_chain/rpc/ai_services.py` |
| `MarketplaceListing.price` | `apps/blockchain-node/src/aitbc_chain/rpc/marketplace.py` |
| `MarketplaceCreateRequest.price` | `apps/blockchain-node/src/aitbc_chain/rpc/marketplace.py` |

Each carries a `# not-money:` marker at its declaration explaining itself. That marker is what
keeps the guard's baseline at zero without an entry in the ignore list.

---

## Why

These values go into `tx_data["payload"]`, and the payload is signed:

```python
tx_without_sig = {k: v for k, v in tx_data.items() if k != "signature"}
message = json.dumps(tx_without_sig, sort_keys=True, separators=(",", ":")).encode()
return verify_signature(keccak(message), signature, sender)
```

— `verify_transaction_signature`, `apps/blockchain-node/src/aitbc_chain/rpc/utils.py`

The signed message is the **canonical JSON bytes**. So the wire *spelling* of every value in
the payload is part of the protocol, fixed by every signature already issued and every
transaction hash already computed.

`Decimal` breaks that in two independent ways, both checked rather than assumed:

```
float payload    {"from":"0xa953…","nonce":0,"payload":{"payment":0.5,…}}     verifies
Decimal payload  TypeError: Object of type Decimal is not JSON serializable
string payload   {"from":"0xa953…","nonce":0,"payload":{"payment":"0.5",…}}   rejected
```

1. **`Decimal` is not JSON-serialisable at all.** Converting the field means adding an encoder.
2. **Any encoder must emit a string**, and `"0.5"` is not `0.5`. Different bytes, different
   keccak hash, different recovered address. A client that computed its signature *correctly*
   would be rejected, and transaction hashes already on chain would not re-derive.

That is a hard fork. It is not a lint fix, and the money guard is not the right instrument for
making it.

---

## The cost of the decision

This is a genuine design defect, and recording it as accepted does not make it a good design.

**Signature validity depends on float → str → float round-tripping.** Python's `repr` gives
shortest-round-trip formatting, so `0.1` encodes as `0.1` and parses back to the same double.
That is a *Python* guarantee, not a wire-format one. A client in another language that formats
the same double as `0.10000000000000001` produces a valid float, a different byte string, and
an invalid signature — with no diagnostic pointing at formatting.

**Arithmetic on these values is still binary floating point** wherever it happens outside the
`Decimal` boundary. The repo's position is that money arithmetic must be exact; on this side of
the boundary it is not.

The mitigations available today are: the chain settles in **integer compute-seconds**
(1 AIT = 3600), so the value that actually moves is an integer even when the payload field is a
float; and everything upstream of serialisation — CLI parsing, wallet balances, coordinator
accounting — is `Decimal`, so error cannot accumulate before the wire.

---

## What changing it would require

Not a type annotation. A protocol change, roughly:

1. **A transaction format version.** Signature verification would have to accept both the
   current encoding and the new one, keyed by an explicit version field, indefinitely — old
   transactions must keep verifying for the chain to remain auditable.
2. **A canonical encoding for exact decimals** that is not "whatever `json.dumps` does".
   Fixed-point integers in the smallest unit are the usual answer and would suit a chain that
   already settles in integer compute-seconds.
3. **Coordinated client updates.** Wallets, the CLI, `aitbc-sdk`, `aitbc-agent-sdk` and any
   third-party signer all produce the signed bytes independently. They must change together.
4. **A re-derivation story for history.** Every hash on chain was computed over the current
   encoding.

Steps 1 and 2 are the design work; step 3 is the coordination problem that makes this a fork
rather than a release.

---

## Enforcement

Prose decays; this one is executable.

`apps/blockchain-node/tests/test_signed_payload_money_is_float.py` signs a real transaction
with a deterministic secp256k1 key and asserts:

- a `float` payment verifies
- the **same signature** against the same amount spelled `"0.5"` does **not** verify, and the
  transaction hash moves with it
- `Decimal` raises `TypeError` at `json.dumps`, integral values included
- all four fields are still annotated `float`, with a failure message that names this document
- each still carries its `# not-money:` marker
- the canonicalisation is still `sort_keys=True, separators=(",", ":")` — every claim here
  assumes that exact encoding

Verified non-vacuous: converting `AIJobRequest.payment` to `Decimal`, deleting a marker, or
dropping `sort_keys` each fails the suite by name.

If a future change is genuinely intended, that test should be **deleted as part of the
protocol change**, not adjusted to pass.

---

## Related

- `docs/releases/v0.23/release.log` — V23-36 (the finding), V23-45 (this record)
- `scripts/lint/no_float_money.py` — the guard, and its `# not-money:` marker convention
- `aitbc/utils/units.py` — the AIT ↔ compute-second conversion the chain settles in
