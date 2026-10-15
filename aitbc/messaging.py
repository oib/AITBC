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

import re
from typing import Any

from .crypto.signature_recovery import canonical_address

#: Payload key carrying the forum envelope. Namespaced so ``payload.type``
#: type-promotion (rpc/utils.py ``_resolved_tx_type``) can never see it, and so
#: bridge-internal MESSAGE rows (no such key) never enter the forum index.
MSG_NAMESPACE = "aitbc_msg"

#: Envelope schema version. Readers ignore any other value.
MSG_VERSION = 1

#: v1 kinds. ``announce`` was deliberately dropped in review — nothing in the
#: protocol marks a post as official.
MSG_KINDS = frozenset({"post", "reply"})

#: Caps. The body cap is on UTF-8 *bytes*, not characters, and is effectively
#: raise-only: lowering it would invalidate already-sealed messages.
MAX_TOPIC_CHARS = 64
MAX_MESSAGE_BODY_BYTES = 4096

#: Canonical slug for the open broadcast topic. Reserved for canonical
#: spelling only — posting stays open to any fee-paying signer and nothing in
#: the index or API marks its posts as official.
BROADCAST_TOPIC = "broadcast"

#: Minimum length for the public search query.
MIN_SEARCH_CHARS = 3

_TX_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")

#: Canonical topic charset: lowercase alnum with single ``.`` ``_`` ``-``
#: separators between runs of alnum. No leading/trailing separator.
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


def envelope_error(envelope: Any, *, sender: str) -> str | None:
    """The one validity predicate. ``None`` means valid; otherwise the reason.

    Enforced identically at admission, gossip ingest and index read — an
    envelope that fails here is junk no matter how it got sealed. Extra keys
    (in the envelope or beside ``aitbc_msg``) are ignored.
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
    return (
        _topic_error(envelope.get("topic"))
        or _body_error(envelope.get("body"))
        or _author_error(envelope.get("agent_address"), sender)
        or _parent_error(kind, envelope.get("parent"))
    )


def build_envelope(
    *,
    kind: str,
    topic: str,
    body: str,
    agent_address: str,
    parent: str | None = None,
) -> dict[str, Any]:
    """Build a validated ``aitbc_msg`` envelope for signing.

    Normalises ``topic`` first; ``ValueError`` carries the same predicate
    message the node would reject with, so a locally-invalid envelope fails
    before it is ever signed.
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
        "body": body,
        "agent_address": agent_address,
    }
    if parent is not None:
        envelope["parent"] = parent
    error = envelope_error(envelope, sender=agent_address)
    if error is not None:
        raise ValueError(error)
    return envelope
