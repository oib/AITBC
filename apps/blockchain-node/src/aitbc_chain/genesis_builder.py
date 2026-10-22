"""Deterministic genesis-document builder (RESET-GENESIS-BUILDER-1).

One pure entry point — :func:`build_genesis_doc` — produces the genesis.json
payload *and* the claims it carries, so the builder, ``verify-genesis-root.py``
and the loader's ``_verify_genesis_claims`` all recompute the same values from
the same code. Claims are computed, never accepted as input.

Loader contract this module satisfies
(``consensus/poa.py:_ensure_genesis_block`` / ``_verify_genesis_claims``):

- ``state_root`` = ``"0x" + StateManager().get_root().hex()`` after
  ``update_account(address, balance, nonce)`` for every allocation (trie key:
  EIP-55-normalized address bytes; value: ``"{balance}:{nonce}"``).
- ``genesis_hash`` = ``compute_block_hash(chain_id, 0, "0x00", timestamp, [],
  "genesis", state_root=…, bridge_state_root=empty-trie-root)``.
- ``timestamp`` must satisfy ``datetime.fromisoformat(s).isoformat() == s``:
  the loader re-hashes the *parsed* datetime while ``verify-genesis-root.py``
  re-hashes the *raw string*, so only the ``+00:00`` offset form satisfies both.
- Allocation addresses must be unique after lowercase-normalization, and are
  required here in EIP-55 checksummed form (``canonical_address(a) == a``).
- ``bridge_validators`` rows are *not* covered by ``genesis_hash`` (the block
  preimage has no validator term), so the document carries
  ``bridge_validators_digest`` — a sha256 over the canonical sorted rows —
  which the loader and the checker both verify before any row is inserted.
  That commits the *set* to the document (a file carrying different rows fails
  its digest), which is the check available at genesis time; binding rows into
  block 0 itself would need a preimage change and is out of scope.

Modes: scratch (the only implemented write path — output must live under an
explicit data dir and never under a live prefix) and live (designed only — see
``check_live_conditions``; this build always refuses the final live write).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from aitbc.crypto.signature_recovery import canonical_address

_CHAIN_ID_RE = re.compile(r"[A-Za-z0-9._-]+")
_HEX_RE = re.compile(r"(?:0x)?[0-9a-fA-F]+")

#: Prefixes a scratch build must never write under. The shared TOOL-GUARD
#: module owns the general form of this list; the builder keeps its own copy so
#: it stands alone until that module lands.
FORBIDDEN_WRITE_PREFIXES = ("/var/lib/aitbc", "/etc/aitbc", "/root")

#: Chain ids a scratch build refuses outright — the live fleet's id lives here
#: until the shared guard module owns the canonical list. The pre-reset id
#: stays: its data dirs still exist as custody archives a build must not touch.
LIVE_CHAIN_IDS = ("ait-hub.aitbc.bubuit.net", "bc-2")


class GenesisBuildError(ValueError):
    """A genesis document input failed validation — the build is refused."""


def _require_checksum_address(address: Any, *, field: str) -> str:
    """Return the EIP-55 form of ``address`` or refuse.

    Inputs must already be checksummed: silently normalizing a malformed or
    lower-case list would hide exactly the data-entry errors a genesis wants
    surfaced. Non-``0x``+40-hex input is refused outright.
    """
    text = str(address or "").strip()
    try:
        canonical = canonical_address(text, strict=True)
    except ValueError as exc:
        raise GenesisBuildError(f"{field}: not an EVM address (0x + 40 hex): {text!r}") from exc
    if canonical != text:
        raise GenesisBuildError(f"{field}: address is not EIP-55 checksummed: {text!r}")
    return canonical


def _require_int(value: Any, *, field: str, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise GenesisBuildError(f"{field}: not an integer: {value!r}") from exc
    if parsed < minimum:
        raise GenesisBuildError(f"{field}: {parsed} below minimum {minimum}")
    return parsed


def _require_timestamp(timestamp: Any) -> str:
    """Return an ISO-8601 string that round-trips ``fromisoformat``.

    ``+00:00`` renders identically after parsing; ``Z`` and space-separated
    forms do not, and can satisfy only one of the loader/checker hash paths —
    refused here instead of diverging there.
    """
    ts = str(timestamp or "").strip()
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError as exc:
        raise GenesisBuildError(f"timestamp is not ISO-8601: {ts!r}") from exc
    if parsed.isoformat() != ts:
        raise GenesisBuildError(f"timestamp does not round-trip fromisoformat (emit +00:00 form, not {ts!r})")
    return ts


def _normalize_pubkey(public_key: Any, *, field: str) -> str:
    """Return ``0x``-lowercase hex for a secp256k1 pubkey; refuse anything else.

    The doubled ``0x0x…`` prefix seen in legacy ``bridge_validators`` rows is
    refused, not repaired — a doubled prefix in the input list is a data-entry
    error that must surface to the operator.
    """
    key = str(public_key or "").strip()
    lowered = key.lower()
    if lowered.startswith("0x0x"):
        raise GenesisBuildError(f"{field}: doubled 0x prefix in public key: {key!r}")
    body = lowered[2:] if lowered.startswith("0x") else lowered
    if not body or not _HEX_RE.fullmatch(body) or len(body) % 2:
        raise GenesisBuildError(f"{field}: public key is not hex bytes: {key!r}")
    return "0x" + body


def canonical_bridge_validators(
    rows: list[dict[str, Any]], *, chain_id: str, require_checksum: bool = True
) -> list[dict[str, Any]]:
    """Normalize bridge-validator rows to the canonical digestable form.

    Field-for-field what the loader inserts and what the register route writes:
    lowercase address (the route lowercases before insert), ``0x``-lowercase
    pubkey, int epoch (default 0), the document's chain id. Sorted by
    (chain_id, address, epoch) so the digest is order-independent.

    ``require_checksum`` distinguishes the two callers: the builder applies it
    to operator-supplied input lists (a malformed spelling must surface as a
    data-entry error), while digest verification passes ``False`` — the rows in
    an emitted document are already in lowercase canonical form and the digest
    commits the normalized set, not the spelling.
    """
    canonical = []
    for i, row in enumerate(rows or []):
        if not isinstance(row, dict):
            raise GenesisBuildError(f"bridge_validators[{i}]: not an object")
        raw_address = row.get("address")
        if require_checksum:
            address = _require_checksum_address(raw_address, field=f"bridge_validators[{i}].address").lower()
        else:
            try:
                address = canonical_address(str(raw_address or "").strip()).lower()
            except ValueError as exc:
                raise GenesisBuildError(
                    f"bridge_validators[{i}].address: not an EVM address (0x + 40 hex): {raw_address!r}"
                ) from exc
        canonical.append(
            {
                "chain_id": chain_id,
                "address": address,
                "public_key": _normalize_pubkey(row.get("public_key"), field=f"bridge_validators[{i}].public_key"),
                "epoch": _require_int(row.get("epoch", 0), field=f"bridge_validators[{i}].epoch"),
            }
        )
    return sorted(canonical, key=lambda r: (r["chain_id"], r["address"], r["epoch"]))


def bridge_validators_digest(rows: list[dict[str, Any]], *, chain_id: str, require_checksum: bool = False) -> str:
    """sha256 over the canonical JSON of the sorted validator rows.

    Lenient on address spelling by default (``require_checksum=False``): the
    digest commits the normalized lowercase set, so a document whose rows are
    already emitted canonical rows verifies. ``build_genesis_doc`` computes the
    digest with ``require_checksum=True`` because it digests operator input.
    """
    canonical = canonical_bridge_validators(rows, chain_id=chain_id, require_checksum=require_checksum)
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return "0x" + hashlib.sha256(blob.encode()).hexdigest()


def allocations_state_root(allocations: list[dict[str, Any]]) -> str:
    """The ``state_root`` the loader recomputes from the allocation set."""
    from .state.merkle_patricia_trie import StateManager

    state = StateManager()
    for alloc in allocations:
        state.update_account(str(alloc["address"]), int(alloc["balance"]), int(alloc.get("nonce", 0)))
    return "0x" + state.get_root().hex()


def empty_bridge_root() -> str:
    """The bridge-event trie root every genesis block carries."""
    from .state.merkle_patricia_trie import MerklePatriciaTrie

    return "0x" + MerklePatriciaTrie().get_root().hex()


def genesis_block_hash(chain_id: str, timestamp: str, state_root: str) -> str:
    """The ``genesis_hash`` the loader recomputes over the file's fields."""
    from .consensus.block_hash import compute_block_hash

    return compute_block_hash(
        chain_id,
        0,
        "0x00",
        timestamp,
        [],
        "genesis",
        state_root=state_root,
        bridge_state_root=empty_bridge_root(),
    )


def _normalize_allocations(allocations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Checksummed, deduplicated allocation rows plus their base-unit total."""
    if not allocations:
        raise GenesisBuildError("allocations must be a non-empty list")
    norm: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    for i, alloc in enumerate(allocations):
        if not isinstance(alloc, dict):
            raise GenesisBuildError(f"allocations[{i}]: not an object")
        address = _require_checksum_address(alloc.get("address"), field=f"allocations[{i}].address")
        if address.lower() in seen:
            raise GenesisBuildError(f"allocations[{i}]: duplicated address {address}")
        seen.add(address.lower())
        norm.append(
            {
                "address": address,
                "balance": _require_int(alloc.get("balance"), field=f"allocations[{i}].balance", minimum=0),
                "nonce": _require_int(alloc.get("nonce", 0), field=f"allocations[{i}].nonce"),
            }
        )
        total += norm[-1]["balance"]
    return norm, total


def _normalize_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    """Parameter map with str|int|None values (``None`` is a deliberate clear)."""
    norm: dict[str, Any] = {}
    for name, value in (parameters or {}).items():
        key = str(name).strip()
        if not key:
            raise GenesisBuildError("parameters: empty parameter name")
        if isinstance(value, bool) or (value is not None and not isinstance(value, (str, int))):
            raise GenesisBuildError(f"parameters[{key!r}]: value must be str, int or null")
        norm[key] = value
    return norm


def build_genesis_doc(
    *,
    chain_id: str,
    allocations: list[dict[str, Any]],
    parameters: dict[str, Any] | None = None,
    bridge_validators: list[dict[str, Any]] | None = None,
    timestamp: str | None = None,
    expected_total: int | None = None,
) -> dict[str, Any]:
    """Build a loader-valid genesis document or refuse with ``GenesisBuildError``.

    ``allocations`` rows are ``{address, balance, nonce?}`` in base units.
    ``parameters`` values must be ``str`` | ``int`` | ``None`` (``None`` is a
    deliberate clear, stored as ``""``). ``bridge_validators`` rows are
    ``{address, public_key, epoch?}`` and are stamped with ``chain_id`` in the
    emitted document. ``expected_total`` is the manifest's expected supply in
    base units; when given, the allocation sum must match it exactly.
    """
    cid = str(chain_id or "").strip()
    if not cid or not _CHAIN_ID_RE.fullmatch(cid):
        raise GenesisBuildError(f"chain_id must be non-empty [A-Za-z0-9._-]: {chain_id!r}")
    if cid in LIVE_CHAIN_IDS:
        raise GenesisBuildError(f"refusing to build a genesis for live chain id {cid!r}")

    norm_allocs, total = _normalize_allocations(allocations)
    if expected_total is not None and total != int(expected_total):
        raise GenesisBuildError(f"allocation total {total} does not match the manifest's expected_total {int(expected_total)}")

    ts = datetime.now(UTC).isoformat() if timestamp is None else _require_timestamp(timestamp)
    doc: dict[str, Any] = {
        "chain_id": cid,
        "timestamp": ts,
        "allocations": norm_allocs,
        "parameters": _normalize_parameters(parameters),
    }

    if bridge_validators:
        doc["bridge_validators"] = canonical_bridge_validators(bridge_validators, chain_id=cid)
        doc["bridge_validators_digest"] = bridge_validators_digest(bridge_validators, chain_id=cid, require_checksum=True)

    doc["state_root"] = allocations_state_root(norm_allocs)
    doc["genesis_hash"] = genesis_block_hash(cid, ts, doc["state_root"])
    return doc


def verify_bridge_validators_claim(doc: dict[str, Any], *, chain_id: str) -> None:
    """Check a document's ``bridge_validators`` rows against its claimed digest.

    Called by the loader before the rows are written and by
    ``verify-genesis-root.py`` — a document carrying rows but no digest, or a
    digest that does not recompute over the canonical rows, is refused. A
    document with neither key is a legacy file and is skipped (still loads).
    """
    rows = doc.get("bridge_validators")
    claimed = doc.get("bridge_validators_digest")
    if not rows and claimed:
        raise GenesisBuildError("genesis document claims a bridge_validators_digest but carries no rows")
    if rows:
        if not claimed:
            raise GenesisBuildError("genesis document carries bridge_validators but no bridge_validators_digest")
        computed = bridge_validators_digest(rows, chain_id=chain_id)
        if computed.lower() != str(claimed).lower():
            raise GenesisBuildError(
                f"bridge_validators_digest mismatch: claimed {str(claimed)[:18]}… recomputes to {computed[:18]}…"
            )


def check_live_conditions(
    *,
    doc: dict[str, Any],
    manifest: dict[str, Any] | None,
    target_dir_exists: bool,
    operator_line: str | None,
) -> list[str]:
    """Evaluate the live-mode preconditions; return the unmet ones.

    Live mode — the reset-day write onto a production data dir — is *designed*
    but deliberately not enabled in this build: every call is refused at the
    write step. These checks are the gate it will live behind, listed here so
    the refusal paths can be tested now:

    - a manifest is supplied and its ``chain_id`` equals the document's;
    - the target has no existing blocks or genesis for that chain id
      (``target_dir_exists`` is the caller's verdict on that);
    - the chain id is not in use on the host (covered by the previous check
      plus the caller's no-running-service condition);
    - the operator's named line is recorded verbatim in the output.
    """
    unmet: list[str] = []
    if not manifest:
        unmet.append("no manifest supplied")
    elif str(manifest.get("chain_id") or "") != str(doc.get("chain_id") or ""):
        unmet.append("manifest chain_id does not match the document's")
    if target_dir_exists:
        unmet.append("target already holds blocks or a genesis for this chain id")
    if not operator_line or not str(operator_line).strip():
        unmet.append("no operator line supplied for the output record")
    return unmet
