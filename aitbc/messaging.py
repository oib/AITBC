"""On-chain forum messages: the ``aitbc_msg`` payload namespace (MSG-1).

A forum message is an ordinary signed ``MESSAGE`` transaction whose payload
carries a namespaced envelope::

    {"to": <signer>, "amount": 0,
     "aitbc_msg": {"v": 1, "kind": "post"|"reply", "topic": "<slug>",
                   "body": "<utf-8>", "agent_address": <signer>,
                   "parent": "<64-hex tx_hash>"   # replies only
                   }}

The top-level ``to``/``amount`` siblings exist because the transaction
signature covers the exact payload dict the submit route verifies (the
``TransactionRequest`` model injects them when absent — signing them up front
keeps the signed bytes identical to the verified bytes). They are *extra keys*
for everything in this module: readers must ignore them and everything else
outside ``aitbc_msg``.

This module is the single home of the wire contract — caps, kind names,
topic normalisation and the validity predicate — shared by the blockchain
node's derived read index (``aitbc_chain.messaging_index``), admission
checks, the CLI (``aitbc messaging``) and the generated MCP wrappers. The
index additionally enforces the predicate on already-sealed rows: a hostile
proposer can seal a malformed envelope but it simply never surfaces.

Permanence, stated once for every consumer of this module: message bodies are
public, replicated on every node, and cannot be edited or deleted — any later
moderation layer (MSG-2) can only be a read-side filter on each node.

Approved design: ``docs/design/msg1-onchain-messaging.md`` (MSG-1).
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

from .crypto.signature_recovery import canonical_address

#: Payload key carrying the forum envelope. Namespaced so ``payload.type``
#: type-promotion (rpc/utils.py ``_resolved_tx_type``) can never see it, and so
#: bridge-internal MESSAGE rows (no such key) never enter the forum index.
MSG_NAMESPACE = "aitbc_msg"

#: Envelope schema version. Readers ignore any other value.
MSG_VERSION = 1

#: v1 content kinds. ``announce`` was deliberately dropped in review —
#: nothing in the protocol marks a post as official.
POST_KINDS = frozenset({"post", "reply"})

#: v1 moderation kinds (MSG-2). ``lock``/``unlock`` take an optional
#: ``target`` (absent = whole topic); the rest require one.
MOD_ACTION_KINDS = frozenset({"hide", "unhide", "pin", "unpin", "lock", "unlock", "mod_grant", "mod_revoke"})

#: All non-content kinds: the moderation set plus ``vote``.
ACTION_KINDS = MOD_ACTION_KINDS | frozenset({"vote"})

#: v1 direct-message kinds (MSG-8). ``dm`` is the sealed ciphertext;
#: ``dm_key`` publishes the recipient's X25519 public key.
DM_KINDS = frozenset({"dm", "dm_key"})

#: Every recognised v1 kind.
MSG_KINDS = POST_KINDS | ACTION_KINDS | DM_KINDS

#: Legal ``vote`` values: +1 up, -1 down, 0 retract (MSG-2).
VOTE_VALUES = frozenset({-1, 0, 1})

#: Caps. The body cap is on UTF-8 *bytes*, not characters, and is effectively
#: raise-only: lowering it would invalidate already-sealed messages.
MAX_TOPIC_CHARS = 64
MAX_MESSAGE_BODY_BYTES = 4096

#: Canonical slug for the open broadcast topic. Reserved for canonical
#: spelling only — posting stays open to any fee-paying signer and nothing in
#: the index or API marks its posts as official.
BROADCAST_TOPIC = "broadcast"

#: Reserved slug for the DM kinds (MSG-8). ``topic == DM_TOPIC`` if and only
#: if ``kind in DM_KINDS`` — enforced both ways in the predicate, so a ``dm``
#: can never hide under a user topic and user content can never squat on the
#: reserved slug. The read index answers every carve-out from this one rule.
DM_TOPIC = "dm"

#: Context string bound into every DM plaintext (MSG-8 §3).
DM_CONTEXT = "aitbc-dm-v1"

#: ``ct`` cap: base64 characters on the wire (4096 base64 = 3072 raw bytes;
#: 48 B sealed-box overhead + ~100 B header leaves ≈ 2920 B of message).
MAX_DM_CT_B64_BYTES = 4096

#: Minimum length for the public search query.
MIN_SEARCH_CHARS = 3

_TX_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")

#: Canonical topic charset: lowercase alnum, starting and ending with an
#: alphanumeric, with ``.`` ``_`` ``-`` separators in between — *runs* of
#: separators are legal (``a..b``, ``a_-_b``); only ``--`` runs are collapsed
#: by ``normalize_topic`` into a single ``-`` and so never appear canonical.
_TOPIC_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")

#: C0 control characters except tab/LF/CR, plus DEL. Bodies are rendered as
#: text on public pages; terminal-escape bytes have no place in them.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_WS_RUN_RE = re.compile(r"\s+")


def normalize_topic(raw: Any) -> str | None:
    """Return the canonical slug for ``raw``, or ``None`` if it cannot be one.

    Normalisation is trim → lowercase → collapse each whitespace run to ``-``.
    The result must then be 1–64 chars of ``[a-z0-9._-]`` starting and ending
    with an alphanumeric. An input that cannot map to such a slug is rejected
    (not silently mangled) so the payload on the wire is always canonical.
    """
    if not isinstance(raw, str):
        return None
    slug = _WS_RUN_RE.sub("-", raw.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug or len(slug) > MAX_TOPIC_CHARS:
        return None
    if not _TOPIC_RE.fullmatch(slug):
        return None
    return slug


def extract_envelope(payload: Any) -> dict[str, Any] | None:
    """Return the ``aitbc_msg`` dict inside ``payload``, or ``None``.

    ``None`` covers both "not a forum message" (bridge-internal MESSAGE rows,
    opaque payloads) and a present-but-malformed namespace (a non-dict value
    under the key). Callers that must distinguish use :func:`claims_envelope`.
    """
    if isinstance(payload, dict):
        env = payload.get(MSG_NAMESPACE)
        if isinstance(env, dict):
            return env
    return None


def claims_envelope(payload: Any) -> bool:
    """Whether the payload *claims* to be a forum message at all.

    True whenever the namespaced key is present — even malformed — so
    admission can refuse a broken claim while leaving opaque MESSAGE
    transactions (bridge internals, other uses) untouched.
    """
    return isinstance(payload, dict) and MSG_NAMESPACE in payload


def _topic_error(topic: Any) -> str | None:
    if not isinstance(topic, str) or not topic:
        return "aitbc_msg.topic must be a non-empty string"
    if topic != normalize_topic(topic):
        return (
            "aitbc_msg.topic must be the canonical slug "
            f"(1–{MAX_TOPIC_CHARS} chars of a-z 0-9 . _ -, no leading/trailing separator)"
        )
    return None


def _body_error(body: Any) -> str | None:
    if not isinstance(body, str):
        return "aitbc_msg.body must be a string"
    try:
        body_bytes = len(body.encode("utf-8"))
    except UnicodeEncodeError:
        # Lone surrogates (JSON "a\ud800") decode into str but cannot
        # encode — the row is junk, never an exception.
        return "aitbc_msg.body is not valid UTF-8 text"
    if body_bytes == 0:
        return "aitbc_msg.body is empty"
    if body_bytes > MAX_MESSAGE_BODY_BYTES:
        return f"aitbc_msg.body is {body_bytes} bytes; maximum is {MAX_MESSAGE_BODY_BYTES}"
    if _CONTROL_RE.search(body):
        return "aitbc_msg.body contains control characters"
    return None


def _author_error(agent_address: Any, sender: Any) -> str | None:
    if not isinstance(agent_address, str):
        return "aitbc_msg.agent_address must equal the transaction signer"
    try:
        if canonical_address(agent_address) != canonical_address(sender):
            return "aitbc_msg.agent_address must equal the transaction signer"
    except Exception:
        return "aitbc_msg.agent_address must equal the transaction signer"
    return None


def _parent_error(kind: str, parent: Any) -> str | None:
    if kind == "reply":
        if not isinstance(parent, str) or not _TX_HASH_RE.fullmatch(parent):
            return "aitbc_msg.parent must be the parent message's 64-hex tx_hash"
    elif parent is not None:
        return "aitbc_msg.parent is only allowed on replies"
    return None


_TARGET_KINDS = frozenset({"vote", "hide", "unhide", "pin", "unpin"})


def _target_error(kind: str, target: Any) -> str | None:
    """``target`` is required for vote/hide/unhide/pin/unpin, optional on
    lock/unlock (absent = whole topic), ignored elsewhere."""
    if kind in _TARGET_KINDS:
        if not isinstance(target, str) or not _TX_HASH_RE.fullmatch(target):
            return "aitbc_msg.target must be the target message's 64-hex tx_hash"
    elif kind in {"lock", "unlock"} and target is not None:
        if not isinstance(target, str) or not _TX_HASH_RE.fullmatch(target):
            return "aitbc_msg.target must be the locked thread root's 64-hex tx_hash"
    return None


def _value_error(kind: str, value: Any) -> str | None:
    if kind != "vote":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value not in VOTE_VALUES:
        return "aitbc_msg.value must be one of -1, 0, +1 (integer)"
    return None


def _grantee_error(kind: str, grantee: Any) -> str | None:
    if kind not in {"mod_grant", "mod_revoke"}:
        return None
    if not isinstance(grantee, str):
        return "aitbc_msg.grantee must be the moderator address"
    try:
        canonical_address(grantee, strict=True)
    except Exception:
        return "aitbc_msg.grantee must be a 0x moderator address"
    return None


def _strict_b64(value: Any) -> bytes | None:
    """Decode strict base64 (standard alphabet, padding required) or ``None``."""
    if not isinstance(value, str):
        return None
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError):
        return None


def _dm_error(envelope: dict[str, Any]) -> str | None:
    """Field rules for the ``dm`` kind: ``to`` is a canonical recipient
    address; ``ct`` is strict base64 of at most ``MAX_DM_CT_B64_BYTES``
    characters (the sealed box, never decoded server-side)."""
    to = envelope.get("to")
    if not isinstance(to, str):
        return "aitbc_msg.to must be the recipient's 0x address"
    try:
        canonical_address(to, strict=True)
    except Exception:
        return "aitbc_msg.to must be the recipient's 0x address"
    ct = envelope.get("ct")
    if not isinstance(ct, str) or len(ct.encode("ascii", "ignore")) > MAX_DM_CT_B64_BYTES:
        return f"aitbc_msg.ct must be base64 text of at most {MAX_DM_CT_B64_BYTES} chars"
    if _strict_b64(ct) is None:
        return "aitbc_msg.ct must be strict base64 (standard alphabet, padding required)"
    return None


def _dm_key_error(envelope: dict[str, Any]) -> str | None:
    """``dm_key`` carries ``enc_pubkey``: strict base64 of a 32-byte X25519
    public key."""
    raw = _strict_b64(envelope.get("enc_pubkey"))
    if raw is None or len(raw) != 32:
        return "aitbc_msg.enc_pubkey must be strict base64 of a 32-byte X25519 public key"
    return None


def envelope_error(envelope: Any, *, sender: str) -> str | None:
    """The one validity predicate. ``None`` means valid; otherwise the reason.

    Enforced identically at admission, gossip ingest and index read — an
    envelope that fails here is junk no matter how it got sealed. Extra keys
    (in the envelope or beside ``aitbc_msg``) are ignored. Per-kind field
    rules apply after the shared ``v``/``kind`` checks (MSG-2).
    """
    if not isinstance(envelope, dict):
        return "aitbc_msg must be an object"
    version = envelope.get("v")
    # isinstance(int) but not bool: v=1.0 or v="1" or v=true are all unknown.
    if not isinstance(version, int) or isinstance(version, bool) or version != MSG_VERSION:
        return f"unsupported aitbc_msg.v (want {MSG_VERSION})"
    kind = envelope.get("kind")
    # isinstance first: `dict not in frozenset` raises TypeError (unhashable).
    if not isinstance(kind, str) or kind not in MSG_KINDS:
        return f"unsupported aitbc_msg.kind (want one of {sorted(MSG_KINDS)})"
    common = _topic_error(envelope.get("topic")) or _author_error(envelope.get("agent_address"), sender)
    if common is not None:
        return common
    # The `dm` slug is reserved in both directions (MSG-8): only the DM
    # kinds may carry it, and they may carry nothing else.
    if (envelope["topic"] == DM_TOPIC) != (kind in DM_KINDS):
        return f"aitbc_msg.topic '{DM_TOPIC}' is reserved for the dm kinds, and the dm kinds may use no other topic"
    if kind in POST_KINDS:
        return _body_error(envelope.get("body")) or _parent_error(kind, envelope.get("parent"))
    if kind == "dm":
        return _dm_error(envelope)
    if kind == "dm_key":
        return _dm_key_error(envelope)
    return (
        _target_error(kind, envelope.get("target"))
        or _value_error(kind, envelope.get("value"))
        or _grantee_error(kind, envelope.get("grantee"))
    )


def _attach_fields(
    envelope: dict[str, Any],
    *,
    kind: str,
    body: str | None,
    parent: str | None,
    target: str | None,
    value: int | None,
    grantee: str | None,
    to: str | None,
    ct: str | None,
    enc_pubkey: str | None,
) -> None:
    """Attach the per-kind payload fields; ``envelope_error`` validates."""
    if kind in POST_KINDS:
        envelope["body"] = body
        if parent is not None:
            envelope["parent"] = parent
    if kind in _TARGET_KINDS or kind in {"lock", "unlock"}:
        if target is not None:
            envelope["target"] = target
    if kind == "vote":
        envelope["value"] = value
    if kind in {"mod_grant", "mod_revoke"}:
        envelope["grantee"] = grantee
    if kind == "dm":
        envelope["to"] = to
        envelope["ct"] = ct
    if kind == "dm_key":
        envelope["enc_pubkey"] = enc_pubkey


def build_envelope(
    *,
    kind: str,
    topic: str,
    body: str | None = None,
    agent_address: str,
    parent: str | None = None,
    target: str | None = None,
    value: int | None = None,
    grantee: str | None = None,
    to: str | None = None,
    ct: str | None = None,
    enc_pubkey: str | None = None,
) -> dict[str, Any]:
    """Build a validated ``aitbc_msg`` envelope for signing.

    Normalises ``topic`` first; ``ValueError`` carries the same predicate
    message the node would reject with, so a locally-invalid envelope fails
    before it is ever signed. ``body`` is required on post/reply; ``target``,
    ``value`` and ``grantee`` apply to the MSG-2 action kinds.
    """
    canonical_topic = normalize_topic(topic)
    if canonical_topic is None:
        raise ValueError(
            f"topic '{topic}' has no canonical slug form (1–{MAX_TOPIC_CHARS} chars of a-z 0-9 . _ - after lowercasing)"
        )
    envelope: dict[str, Any] = {
        "v": MSG_VERSION,
        "kind": kind,
        "topic": canonical_topic,
        "agent_address": agent_address,
    }
    _attach_fields(
        envelope,
        kind=kind,
        body=body,
        parent=parent,
        target=target,
        value=value,
        grantee=grantee,
        to=to,
        ct=ct,
        enc_pubkey=enc_pubkey,
    )
    error = envelope_error(envelope, sender=agent_address)
    if error is not None:
        raise ValueError(error)
    return envelope
