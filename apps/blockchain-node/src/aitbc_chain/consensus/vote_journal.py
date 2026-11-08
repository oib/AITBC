"""Durable per-height vote journal (#1268 Phase 1, item 1).

Safety invariant S1: a validator casts at most one vote -- an attestation
signature or its own block proposal -- per height until it has proof the
earlier vote can no longer join a quorum, or the height is decided locally.

With 3-of-4 quorums two conflicting seals at a height need at least two
validators that voted for both hashes. The pre-#1268 memory of those votes had
four gaps (see the #1268 design, comment 19769): the legacy lock lapses by wall
clock and dies on restart, round-lock entries are pruned after two windows, and
a validator's own proposal was never recorded at all. This journal closes the
last three:

* every vote is written to disk (temp file + fsync + rename) BEFORE the
  signature or proposal leaves the process -- a persistence failure refuses
  the vote rather than releasing it unrecorded;
* an entry is kept until the height is below the local tip -- pruned by height,
  never by timer;
* both kinds of vote land in the same index, keyed by (height, voter).

The journal is only a record. The decision logic (refuse, fetch-before-unlock,
the liveness valve) lives with the callers in ``remote_attestation`` and
``poa``; ``valve_open`` is the one shared time rule.

Residual, stated plainly: a wiped or corrupt journal file is amnesia. A load
failure is counted (``vote_journal_load_failed_total``) and the journal starts
empty -- fail-open for liveness -- so the operator-visible metric is the
detector, not a refusal.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR
from aitbc.crypto.signature_recovery import canonical_address

from ..metrics import metrics_registry

logger = get_logger(__name__)

# Hard bound on how many heights a journal keeps when no tip has ever been
# supplied (shadow mode / a node that never reads its own tip).
VOTE_JOURNAL_MAX_HEIGHTS = 4096

KIND_ATTEST = "attest"
KIND_PROPOSE = "propose"


class VoteJournalError(RuntimeError):
    """The vote could not be made durable -- the caller must not release it."""


@dataclass(frozen=True)
class VoteRecord:
    height: int
    voter: str
    block_hash: str
    kind: str
    round: int | None
    proposer: str
    at: float  # wall-clock epoch seconds, survives a restart

    def to_json(self) -> dict[str, Any]:
        return {
            "height": self.height,
            "voter": self.voter,
            "hash": self.block_hash,
            "kind": self.kind,
            "round": self.round,
            "proposer": self.proposer,
            "at": self.at,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> VoteRecord:
        rnd = raw.get("round")
        return cls(
            height=int(raw["height"]),
            voter=str(raw["voter"]),
            block_hash=str(raw["hash"]),
            kind=str(raw.get("kind", KIND_ATTEST)),
            round=int(rnd) if rnd is not None else None,
            proposer=str(raw.get("proposer", "")),
            at=float(raw["at"]),
        )


def valve_open(record: VoteRecord, unlock_seconds: float, now: float | None = None) -> bool:
    """True once ``record`` is old enough for the liveness valve to consider it.

    Necessary, not sufficient: the attester additionally requires that the
    voted block could not be fetched (fetch-before-unlock). ``unlock_seconds``
    <= 0 means the valve never opens.
    """
    if unlock_seconds <= 0:
        return False
    return ((time.time() if now is None else now) - record.at) >= unlock_seconds


class VoteJournal:
    """One chain's durable vote index."""

    def __init__(self, chain_id: str, path: Path | None = None) -> None:
        self._chain_id = chain_id
        self._path = path or (DATA_DIR / "data" / chain_id / "vote_journal.json")
        self._lock = threading.RLock()
        # height -> voter -> votes cast, oldest first
        self._votes: dict[int, dict[str, list[VoteRecord]]] = {}
        self._loaded = False

    # ── persistence ────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if not self._path.exists():
                return
            data = json.loads(self._path.read_text())
            if data.get("chain_id") != self._chain_id:
                return
            for raw in data.get("votes", []):
                try:
                    rec = VoteRecord.from_json(raw)
                except (KeyError, TypeError, ValueError):
                    continue
                self._votes.setdefault(rec.height, {}).setdefault(rec.voter, []).append(rec)
        except Exception as exc:  # noqa: BLE001 - a bad file must degrade to an empty journal, loudly
            metrics_registry.increment("vote_journal_load_failed_total")
            self._votes = {}
            logger.error("Vote journal for %s unreadable (%s) — starting empty", self._chain_id, exc)

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rows = [rec.to_json() for height in sorted(self._votes) for recs in self._votes[height].values() for rec in recs]
        payload = json.dumps({"version": 1, "chain_id": self._chain_id, "votes": rows})
        tmp = self._path.with_name(self._path.name + ".tmp")
        with open(tmp, "w") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self._path)

    # ── queries ────────────────────────────────────────────────────

    def votes_at(self, height: int, voter: str) -> list[VoteRecord]:
        with self._lock:
            self._ensure_loaded()
            return list(self._votes.get(height, {}).get(canonical_address(voter), ()))

    def conflicting(self, height: int, voter: str, block_hash: str) -> list[VoteRecord]:
        """Votes ``voter`` already cast at ``height`` for a hash other than ``block_hash``."""
        return [r for r in self.votes_at(height, voter) if r.block_hash != block_hash]

    def height_count(self) -> int:
        with self._lock:
            self._ensure_loaded()
            return len(self._votes)

    # ── mutation ───────────────────────────────────────────────────

    def record(
        self,
        height: int,
        voter: str,
        block_hash: str,
        kind: str,
        round_: int | None = None,
        proposer: str = "",
        now: float | None = None,
    ) -> bool:
        """Durably record a vote. Returns False for a repeat of an existing vote.

        Raises ``VoteJournalError`` when the write fails; the in-memory entry
        is rolled back so a failed vote leaves no trace.
        """
        canon = canonical_address(voter)
        with self._lock:
            self._ensure_loaded()
            existing = self._votes.setdefault(height, {}).setdefault(canon, [])
            if any(r.block_hash == block_hash for r in existing):
                return False
            rec = VoteRecord(
                height=height,
                voter=canon,
                block_hash=block_hash,
                kind=kind,
                round=round_,
                proposer=proposer,
                at=time.time() if now is None else now,
            )
            existing.append(rec)
            try:
                self._persist()
            except Exception as exc:  # noqa: BLE001 - any write failure must refuse the vote
                existing.remove(rec)
                if not existing:
                    del self._votes[height][canon]
                if not self._votes[height]:
                    del self._votes[height]
                metrics_registry.increment("vote_journal_persist_failed_total")
                raise VoteJournalError(f"vote journal write failed for height {height}: {exc}") from exc
            metrics_registry.increment(f"vote_journal_recorded_{kind}_total")
            return True

    def retract(self, height: int, voter: str, block_hash: str) -> bool:
        """Withdraw a vote that provably can never join a quorum.

        Only for a proposal this process rolled back before commit: the block
        can no longer be sealed by anyone, so the vote is void. Best-effort
        persistence -- a failure leaves the (conservative) entry on disk.
        """
        canon = canonical_address(voter)
        with self._lock:
            self._ensure_loaded()
            recs = self._votes.get(height, {}).get(canon)
            if not recs:
                return False
            kept = [r for r in recs if r.block_hash != block_hash]
            if len(kept) == len(recs):
                return False
            if kept:
                self._votes[height][canon] = kept
            else:
                del self._votes[height][canon]
                if not self._votes[height]:
                    del self._votes[height]
            try:
                self._persist()
            except Exception as exc:  # noqa: BLE001 - retraction is best-effort, the stale entry is the safe side
                logger.warning("Vote journal retract not persisted for %s height %s: %s", self._chain_id, height, exc)
            metrics_registry.increment("vote_journal_retracted_total")
            return True

    def prune_below(self, tip_height: int | None) -> int:
        """Drop heights strictly below the local tip (decided history).

        Never by clock. With no tip supplied only the hard height cap applies.
        Returns how many heights were dropped.
        """
        with self._lock:
            self._ensure_loaded()
            drop: list[int] = []
            if tip_height is not None:
                drop = [h for h in self._votes if h < tip_height]
            kept = [h for h in self._votes if h not in set(drop)]
            if len(kept) > VOTE_JOURNAL_MAX_HEIGHTS:
                drop += sorted(kept)[: len(kept) - VOTE_JOURNAL_MAX_HEIGHTS]
            if not drop:
                return 0
            for h in set(drop):
                self._votes.pop(h, None)
            try:
                self._persist()
            except Exception as exc:  # noqa: BLE001 - a missed prune only keeps extra (safe) entries
                logger.warning("Vote journal prune not persisted for %s: %s", self._chain_id, exc)
            return len(set(drop))


_JOURNALS: dict[str, VoteJournal] = {}
_JOURNALS_LOCK = threading.Lock()


def get_vote_journal(chain_id: str) -> VoteJournal:
    """The process-wide journal for ``chain_id`` (proposer and attester share it)."""
    with _JOURNALS_LOCK:
        journal = _JOURNALS.get(chain_id)
        if journal is None:
            journal = VoteJournal(chain_id)
            _JOURNALS[chain_id] = journal
        return journal


def reset_vote_journals() -> None:
    """Forget every cached journal instance (tests, and a deliberate reload)."""
    with _JOURNALS_LOCK:
        _JOURNALS.clear()


def vote_journal_enabled() -> bool:
    from ..config import settings

    return bool(getattr(settings, "vote_journal_enabled", False))
