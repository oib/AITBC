"""Shared payloads and pure helpers for ``unavail``.

Extracted verbatim from ``unavail.py``: the node-local settings accessors,
the wire payload builders/verifiers, ``UnavailabilityCertificate``, the
per-response certificate check, the gossip-response signer matcher and the
carried-cert normaliser. ``unavail.py`` re-exports every name here so
``aitbc_chain.consensus.unavail.<name>`` keeps resolving exactly as it did
when the module was a single file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from aitbc.crypto.consensus_signing import sign_consensus_message, verify_consensus_message
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings

# Domain separation: an attestation signature must never verify as an
# unavailability statement (and vice versa). The tag is inside the signed
# payload, so it is covered by the signature.
UNAVAIL_TAG = "unavail-v1"
UC_VERSION = 1

QUERY_TYPE = "unavail_query"
RESPONSE_TYPE = "unavail_resp"


def justification_enabled() -> bool:
    """#1281 master switch — dormant default-off like Phase 1."""
    return bool(
        getattr(settings, "vote_journal_enabled", False) and getattr(settings, "vote_journal_justification_enabled", False)
    )


def nonblocking_persist_enabled() -> bool:
    """#1306: attest-listener leg 1 reads the sampler instead of waiting on it.
    Dormant default-off; only meaningful with the UC barrier armed."""
    return bool(getattr(settings, "unavail_nonblocking_persist_enabled", False)) and justification_enabled()


def _float(name: str, default: float) -> float:
    return float(getattr(settings, name, default))


def _int(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


def collect_seconds() -> float:
    return _float("unavail_collect_seconds", 15.0)


def cert_max_age_seconds() -> float:
    return _float("unavail_cert_max_age_seconds", 120.0)


def evidence_seconds() -> float:
    return _float("unavail_evidence_seconds", 90.0)


# #1964: height plausibility window for the observation index, relative to the
# node's local tip hint. The justification only ever concerns the next
# height(s), so evidence far outside [tip - BEHIND, tip + AHEAD] is noise (or a
# flood vector) and is not recorded. Unknown tip (None) records, as before.
OBS_HEIGHT_BEHIND = 8
OBS_HEIGHT_AHEAD = 64


def obs_height_plausible(height: int, tip_hint: int | None) -> bool:
    if tip_hint is None:
        return True
    return tip_hint - OBS_HEIGHT_BEHIND <= int(height) <= tip_hint + OBS_HEIGHT_AHEAD


def visibility_seconds() -> float:
    """Mesh-liveness window — deliberately much longer than T_evidence.

    "Peers answering" is a coarse reachability signal, not the quiet-window
    evidence: validator traffic is continuous in production, and the UC
    responders themselves refresh it. A partition still fails visibility
    once pre-partition actors age out of this window.
    """
    return _float("unavail_visibility_seconds", 300.0)


def sample_seconds() -> float:
    return _float("unavail_sample_seconds", 10.0)


def min_responses() -> int:
    """UC quorum-intersection threshold — ``MIN_ATTESTATIONS`` by ruling."""
    configured = _int("unavail_min_responses", 0)
    if configured > 0:
        return configured
    return max(1, _int("multi_validator_min_attestations", 2))


def collect_backoff_seconds() -> float:
    """Negative-result backoff after a failed UC probe (#1281 respin).

    Floored at ``2 * collect_seconds`` per the respin ruling — a failed
    collection must not be retried inside its own window, and gate retries
    every few seconds must not storm the query topic.
    """
    return max(_float("unavail_collect_backoff_seconds", 30.0), 2.0 * collect_seconds())


def query_topic(chain_id: str) -> str:
    return f"consensus.unavail_query.{chain_id}"


def response_topic(chain_id: str) -> str:
    return f"consensus.unavail_resp.{chain_id}"


def validator_addresses() -> set[str]:
    """Canonical validator set from settings (same parse as the gates)."""
    raw = getattr(settings, "validator_set", "")
    if not raw:
        return set()
    try:
        data = json.loads(raw)
        entries = data if isinstance(data, list) else data.get("validators", [])
        return {canonical_address(str(v.get("address", ""))) for v in entries if isinstance(v, dict) and v.get("address")}
    except Exception:  # noqa: BLE001 - a malformed set means no UC can verify anyway
        return set()


# ---------------------------------------------------------------------------
# Wire payloads
# ---------------------------------------------------------------------------


def unavail_response_message(chain_id: str, height: int, block_hash: str, epoch: int) -> dict[str, Any]:
    """The exact dict a responder signs (canonical-JSON + keccak + secp256k1)."""
    return {
        "tag": UNAVAIL_TAG,
        "chain_id": chain_id,
        "height": int(height),
        "hash": block_hash,
        "epoch": int(epoch),
    }


def build_unavail_response(
    chain_id: str, height: int, block_hash: str, epoch: int, signer: str, private_key: str
) -> dict[str, Any]:
    """One signed ``UNAVAIL_RESP`` payload."""
    return {
        "type": RESPONSE_TYPE,
        "chain_id": chain_id,
        "height": int(height),
        "hash": block_hash,
        "epoch": int(epoch),
        "signer": canonical_address(signer),
        "signature": sign_consensus_message(unavail_response_message(chain_id, height, block_hash, epoch), private_key),
    }


def verify_unavail_response(resp: dict[str, Any], validator_set: set[str]) -> str | None:
    """Canonical signer address when ``resp`` is a valid unavailability statement.

    Checks type, field binding is left to the caller (the cert verifier
    re-checks chain/height/hash/epoch), signature recovers to ``signer``,
    and ``signer`` is in ``validator_set``. Returns None on any failure.
    """
    if not isinstance(resp, dict) or resp.get("type") != RESPONSE_TYPE:
        return None
    signer = resp.get("signer")
    signature = resp.get("signature")
    if not signer or not signature:
        return None
    try:
        canon = canonical_address(str(signer))
    except (AttributeError, TypeError, ValueError):
        return None
    if canon not in validator_set:
        return None
    try:
        height = int(resp.get("height", 0))
        epoch = int(resp.get("epoch", 0))
    except (TypeError, ValueError):
        return None
    message = unavail_response_message(str(resp.get("chain_id", "")), height, str(resp.get("hash", "")), epoch)
    try:
        if not verify_consensus_message(message, str(signature), canon):
            return None
    except Exception:  # noqa: BLE001 - malformed signature is just an invalid response
        return None
    return canon


# ---------------------------------------------------------------------------
# UnavailabilityCertificate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnavailabilityCertificate:
    """Signed proof that a quorum-intersecting set of validators declared
    ``(chain_id, height, hash)`` unservable at ``epoch``."""

    chain_id: str
    height: int
    hash: str
    epoch: int
    responses: tuple[dict[str, str], ...]  # {"validator","signature"}
    index_verdict: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "version": UC_VERSION,
            "kind": "unavailability_cert",
            "chain_id": self.chain_id,
            "height": self.height,
            "hash": self.hash,
            "epoch": self.epoch,
            "responses": [dict(r) for r in self.responses],
        }
        if self.index_verdict:
            out["index_verdict"] = dict(self.index_verdict)
        return out

    @classmethod
    def from_dict(cls, raw: Any) -> UnavailabilityCertificate | None:
        if not isinstance(raw, dict) or raw.get("kind") != "unavailability_cert":
            return None
        # #1940 F6: version is enforced, not ignored — a foreign/newer cert
        # shape must fail closed rather than parse as v1. Absent version is
        # accepted as legacy v1 (hand-built/early certs carry none).
        if raw.get("version", UC_VERSION) != UC_VERSION:
            return None
        try:
            responses = tuple(
                {"validator": str(r.get("validator", "")), "signature": str(r.get("signature", ""))}
                for r in raw.get("responses", [])
                if isinstance(r, dict)
            )
            verdict = raw.get("index_verdict")
            return cls(
                chain_id=str(raw.get("chain_id", "")),
                height=int(raw.get("height", 0)),
                hash=str(raw.get("hash", "")),
                epoch=int(raw.get("epoch", 0)),
                responses=responses,
                index_verdict=verdict if isinstance(verdict, dict) else {},
            )
        except (TypeError, ValueError, OverflowError):
            return None  # OverflowError: json.loads accepts Infinity for height/epoch


def cert_message(cert: UnavailabilityCertificate) -> dict[str, Any]:
    """Reconstruct the per-response signed payload for verification."""
    return unavail_response_message(cert.chain_id, cert.height, cert.hash, cert.epoch)


def _verify_cert_response(resp: dict[str, str], message: dict[str, Any], vset: set[str], seen: set[str]) -> str | None:
    """One certificate response: distinct in-set signer + valid signature."""
    signer = str(resp.get("validator", ""))
    signature = str(resp.get("signature", ""))
    try:
        canon = canonical_address(signer)
    except (AttributeError, TypeError, ValueError):
        return "bad_signer"
    if canon in seen:
        return "duplicate_signer"
    seen.add(canon)
    if canon not in vset:
        return "signer_not_validator"
    try:
        ok = verify_consensus_message(message, signature, canon)
    except Exception:  # noqa: BLE001 - a bad signature invalidates the cert
        return "bad_signature"
    if not ok:
        return "bad_signature"
    return None


def _matching_response_signer(
    resp: Any, chain_id: str, height: int, block_hash: str, epoch: int, vset: set[str]
) -> str | None:
    """Canonical signer when ``resp`` answers THIS query, else None."""
    if not isinstance(resp, dict):
        return None
    try:
        resp_height = int(resp.get("height", 0))
        resp_epoch = int(resp.get("epoch", 0))
    except (TypeError, ValueError):
        return None
    if resp.get("chain_id") != chain_id or resp_height != int(height):
        return None
    if resp.get("hash") != block_hash or resp_epoch != epoch:
        return None
    return verify_unavail_response(resp, vset)


# ---------------------------------------------------------------------------
# Combined predicate — the single release rule both gates share
# ---------------------------------------------------------------------------


def _carried_certs(
    request_cert: dict[str, Any] | UnavailabilityCertificate | None,
) -> dict[str, UnavailabilityCertificate]:
    """Normalise a carried justification into ``{block_hash: cert}``.

    Accepts a single cert (dict or dataclass) or the full unlock bundle
    whose ``certs`` list holds one cert per voted hash.
    """
    carried: dict[str, UnavailabilityCertificate] = {}
    if request_cert is None:
        return carried
    if isinstance(request_cert, dict) and isinstance(request_cert.get("certs"), list):
        items: list[Any] = list(request_cert["certs"])
    else:
        items = [request_cert]
    for item in items:
        cand = item if isinstance(item, UnavailabilityCertificate) else UnavailabilityCertificate.from_dict(item)
        if cand is not None:
            carried[cand.hash] = cand
    return carried
