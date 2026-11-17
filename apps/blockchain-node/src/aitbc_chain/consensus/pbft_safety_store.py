"""#2190: durable store for PBFT commit locks and view-change records.

These two records are durable-before-send safety state (#1940 F3-B, #2005
F3-C).  They used to live in ``consensus_state`` columns on chain.db and were
written by ``save_state`` from INSIDE the proposer's open write transaction —
a second writer on the same sqlite file, which self-deadlocks until the 60 s
busy_timeout expires.  They now live in their own file next to chain.db
(``pbft_safety.json``), written atomically (tmp + fsync + rename + dir fsync),
so a safety write never contends with the chain.db write lock.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from aitbc.constants import DATA_DIR

logger = logging.getLogger(__name__)

_VERSION = 1


class PbftSafetyStore:
    """Atomic JSON file holding ``commit_locks`` and ``view_change`` blobs."""

    def __init__(self, chain_id: str) -> None:
        self.path: Path = DATA_DIR / "data" / chain_id / "pbft_safety.json"
        self._lock = threading.Lock()

    def save(self, commit_locks_json: str, view_change_json: str) -> bool:
        """Persist both blobs; False (nothing changed) on any OS failure."""
        payload = json.dumps(
            {"v": _VERSION, "commit_locks": commit_locks_json, "view_change": view_change_json},
            sort_keys=True,
        )
        tmp = self.path.with_name(self.path.name + ".tmp")
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
                dir_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
                return True
            except OSError as exc:
                logger.error("pbft safety store write failed (%s): %s", self.path, exc)
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                return False

    def load(self) -> dict[str, Any] | None:
        """The stored blobs, ``None`` when the file does not exist.

        Raises ``ValueError`` on an unreadable/corrupt file so the caller can
        fail closed (a corrupt record may have held a floor or lock).
        """
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ValueError(f"pbft safety store unreadable: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("pbft safety store is not parseable JSON") from None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("commit_locks"), str)
            or not isinstance(data.get("view_change"), str)
        ):
            raise ValueError("pbft safety store has an unexpected shape")
        return data
