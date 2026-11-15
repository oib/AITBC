"""#1301 L2: proposer-signed abandon statement.

When a proposer misses attestation quorum and drops its candidate block, the
validators that already voted for it stay journal-locked to a hash nobody will
ever seal (#1268), blocking every fresh-hash retry until the 300 s valve plus
an unavailability certificate. The proposer can say so itself: it signs
``abandon(chain, height, hash, round, proposer)``. A voter whose journal holds
an attest vote for exactly that hash *from that proposer* may release it --
the only party able to seal the hash has signed that it will not. A later seal
of the same hash by that proposer is equivocation evidence, not a new fork
class.

Default OFF (``vote_journal_abandon_enabled``); every function here is inert
without the flag.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.consensus_signing import (
    DOMAIN_BLOCK_ABANDON,
    sign_consensus_message,
    sign_consensus_message_domain,
    verify_consensus_message,
    verify_consensus_message_domain,
)
from aitbc.crypto.signature_recovery import canonical_address

from ..metrics import metrics_registry

logger = get_logger(__name__)

KIND = "abandon"


def abandon_topic(chain_id: str) -> str:
    return f"consensus.abandon.{chain_id}"


def abandon_enabled() -> bool:
    from ..config import settings

    return bool(getattr(settings, "vote_journal_abandon_enabled", False)) and bool(
        getattr(settings, "vote_journal_enabled", False)
    )


def liveness_enabled() -> bool:
    """#1985: abandon re-announce / crash recovery / lock ordering. Needs the abandon path armed."""
    from ..config import settings

    return abandon_enabled() and bool(getattr(settings, "vote_journal_liveness_enabled", False))


def ledger_path(chain_id: str) -> Path:
    """Sidecar file next to the vote journal (same data dir, so tests that move it move this too)."""
    from . import vote_journal

    return vote_journal.DATA_DIR / "data" / chain_id / "abandon_ledger.json"


class AbandonLedger:
    """#1985: the abandons this proposer owes the mesh, kept until the height is decided.

    ``record`` is called when a proposal is dropped (or found orphaned at
    start), BEFORE the first publish, so a failed or lost first send is still
    owed. With a ``path`` the obligations are persisted (atomic write + fsync)
    and reloaded after a restart: the quorum-miss drop retracts the proposal's
    journal record, so without this a proposer restart between drop and
    height-decision forgot the abandon (the 7 hub restarts of the bc-2 halt).
    ``due`` yields entries not confirmed sent within ``every`` seconds and does
    NOT stamp them; the caller confirms each success with ``mark_sent`` so a
    failed send is retried on the next tick. Reloaded entries are due at once.
    ``forget`` is for a same-hash retry: a hash being retried must not keep
    being announced as dead.
    """

    def __init__(self, max_entries: int = 256, path: Path | None = None) -> None:
        self._max = max_entries
        self._path = path
        self._loaded = path is None
        # (height, hash) -> [round, proposer, last_confirmed_send_epoch]
        self._entries: dict[tuple[int, str], list[Any]] = {}

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._entries)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if self._path is None or not self._path.exists():
                return
            data = json.loads(self._path.read_text())
            for raw in data.get("entries", []):
                try:
                    rnd = raw.get("round")
                    self._entries[(int(raw["height"]), str(raw["hash"]))] = [
                        int(rnd) if rnd is not None else None,
                        str(raw["proposer"]),
                        0.0,
                    ]
                except (KeyError, TypeError, ValueError, AttributeError):
                    metrics_registry.increment("vote_journal_abandon_ledger_rows_skipped_total")
        except Exception as exc:  # noqa: BLE001 - the ledger is a re-announce aid; a bad file degrades to empty, loudly
            metrics_registry.increment("vote_journal_abandon_ledger_load_failed_total")
            self._entries = {}
            logger.error("Abandon ledger %s unreadable (%s); starting empty", self._path, exc)

    def _save(self) -> bool:
        if self._path is None:
            return True
        rows = [{"height": h, "hash": bh, "round": e[0], "proposer": e[1]} for (h, bh), e in sorted(self._entries.items())]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(self._path.name + ".tmp")
            with open(tmp, "w") as f:
                f.write(json.dumps({"version": 1, "entries": rows}))
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self._path)
        except Exception as exc:  # noqa: BLE001 - never block the proposer; the obligation stays in memory
            metrics_registry.increment("vote_journal_abandon_ledger_persist_failed_total")
            logger.warning("Abandon ledger not persisted (%s): %s", self._path, exc)
            return False
        return True

    def record(self, height: int, block_hash: str, round_: int | None, proposer: str, now: float) -> None:
        self._ensure_loaded()
        self._entries[(height, block_hash)] = [round_, proposer, now]
        while len(self._entries) > self._max:
            del self._entries[min(self._entries)]
        self._save()

    def forget(self, height: int, block_hash: str) -> None:
        self._ensure_loaded()
        if self._entries.pop((height, block_hash), None) is not None:
            self._save()

    def mark_sent(self, height: int, block_hash: str, now: float) -> None:
        """A re-announce went out: restart its pacing interval (in memory only -- a restart makes it due again)."""
        entry = self._entries.get((height, block_hash))
        if entry is not None:
            entry[2] = now

    def due(self, tip_height: int, every: float, now: float) -> list[tuple[int, str, int | None, str]]:
        """Entries above ``tip_height`` not confirmed sent for at least ``every`` seconds."""
        self._ensure_loaded()
        decided = [k for k in self._entries if k[0] <= tip_height]
        for key in decided:
            del self._entries[key]
        if decided:
            self._save()
        return [
            (height, block_hash, entry[0], entry[1])
            for (height, block_hash), entry in sorted(self._entries.items())
            if now - float(entry[2]) >= every
        ]


def _domain_active(height: int) -> bool:
    """#1298: at/above ``consensus_domain_separation_height`` the abandon
    statement is signed under its own domain (hard cutover, like attestations);
    below it the legacy preimage stays authoritative."""
    from ..config import settings

    activation = getattr(settings, "consensus_domain_separation_height", None)
    return activation is not None and height >= activation


def _message(chain_id: str, height: int, block_hash: str, round_: int | None, proposer: str) -> dict[str, Any]:
    return {
        "kind": KIND,
        "chain_id": chain_id,
        "height": int(height),
        "hash": block_hash,
        "round": round_,
        "proposer": canonical_address(proposer),
    }


def build_abandon(
    chain_id: str, height: int, block_hash: str, round_: int | None, proposer: str, private_key: str
) -> dict[str, Any]:
    msg = _message(chain_id, height, block_hash, round_, proposer)
    if _domain_active(int(height)):
        return {**msg, "signature": sign_consensus_message_domain(msg, private_key, DOMAIN_BLOCK_ABANDON)}
    return {**msg, "signature": sign_consensus_message(msg, private_key)}


def verify_abandon(chain_id: str, payload: Any) -> dict[str, Any] | None:
    """The validated statement fields, or None for anything malformed or forged."""
    if not isinstance(payload, dict) or payload.get("kind") != KIND or payload.get("chain_id") != chain_id:
        return None
    try:
        height = int(payload["height"])
        block_hash = str(payload["hash"])
        proposer = str(payload["proposer"])
        round_ = payload.get("round")
        round_ = int(round_) if round_ is not None else None
        msg = _message(chain_id, height, block_hash, round_, proposer)
        if not block_hash:
            return None
        signature = str(payload.get("signature", ""))
        if _domain_active(height):
            ok = verify_consensus_message_domain(msg, signature, proposer, DOMAIN_BLOCK_ABANDON)
        else:
            ok = verify_consensus_message(msg, signature, proposer)
        if not ok:
            return None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return msg
