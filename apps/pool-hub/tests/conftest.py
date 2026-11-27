from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError

# Load .env file
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

# Ensure pool-hub src is on the path
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Set a default shared secret for test environments if not provided
os.environ.setdefault("POOLHUB_COORDINATOR_SHARED_SECRET", "test-secret")

from poolhub.models import Miner, RewardPayout, RewardShare  # noqa: E402


class _ScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


def _entity(stmt: Any) -> Any:
    try:
        return stmt.column_descriptions[0].get("entity")
    except Exception:  # noqa: BLE001 - non-SELECT statements have no column descriptions; treat as unknown entity
        return None


def _param(params: dict[str, Any], name: str) -> Any:
    """First bound value for ``name`` — SQLAlchemy suffixes repeats (``miner_id_1``)."""
    for key, value in params.items():
        if key == name or key.startswith(f"{name}_"):
            return value
    return None


class FakeSession:
    """Minimal AsyncSession stand-in enforcing the reward_payouts unique constraint.

    Mirrors what Postgres does on (miner_id, chain_id, epoch_number) so the payout
    decision path can be exercised without a database. ``execute`` dispatches on
    the selected entity:

    - ``Miner`` — the wallet lookup (#1401): every miner resolves to
      ``default_wallet`` unless ``miner_wallets[miner_id]`` overrides it
      (None = no wallet registered).
    - ``RewardShare`` — the verified-share ledger read/write (#3058).
    - ``RewardPayout`` — claim lookups and the reconciliation sweep select.
    """

    default_wallet = "0x000000000000000000000000000000000000dEaD"

    def __init__(
        self,
        already_claimed: set[tuple[str, str, int]] | None = None,
        miner_wallets: dict[str, str | None] | None = None,
    ) -> None:
        self.claimed: set[tuple[str, str, int]] = set(already_claimed or ())
        self.added: list[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.miner_wallets = miner_wallets or {}
        self.shares: list[RewardShare] = []
        self.payouts: list[RewardPayout] = []
        self._flush_idx = 0

    # -- execute ---------------------------------------------------------

    async def execute(self, stmt: Any) -> _ScalarResult:
        entity = _entity(stmt)
        params = stmt.compile().params

        if entity is Miner:
            miner_id = _param(params, "miner_id")
            if miner_id is None:
                return _ScalarResult([])
            wallet = self.miner_wallets.get(miner_id, self.default_wallet)
            row = SimpleNamespace(wallet_address=wallet) if wallet is not None or miner_id in self.miner_wallets else None
            return _ScalarResult([row] if row is not None else [])

        if entity is RewardShare:
            rows = [s for s in self.shares if self._share_matches(s, params)]
            return _ScalarResult(rows)

        if entity is RewardPayout:
            return self._payout_result(params)

        return _ScalarResult([])

    @staticmethod
    def _share_matches(share: RewardShare, params: dict[str, Any]) -> bool:
        for key in ("miner_id", "chain_id", "epoch_number", "source", "verified"):
            value = _param(params, key)
            if value is not None and getattr(share, key) != value:
                return False
        return True

    def _payout_result(self, params: dict[str, Any]) -> _ScalarResult:
        # Reconciliation sweep: select by chain + status IN (...) + created_at < cutoff.
        # ``in_`` binds one expanding param holding the whole list.
        status_params: set[Any] = set()
        for key, value in params.items():
            if key.startswith("status"):
                if isinstance(value, (list, tuple, set)):
                    status_params.update(value)
                else:
                    status_params.add(value)
        if status_params:
            chain_id = _param(params, "chain_id")
            cutoff = next((v for k, v in params.items() if k.startswith("created_at")), None)
            rows = []
            for p in self.payouts:
                if p.chain_id != chain_id or p.status not in status_params:
                    continue
                if cutoff is not None and not (p.created_at < cutoff):
                    continue
                rows.append(p)
            return _ScalarResult(rows)
        # Single-row lookups (claim reuse, has_been_paid).
        miner_id = _param(params, "miner_id")
        epoch = _param(params, "epoch_number")
        chain_id = _param(params, "chain_id")
        rows = [
            p
            for p in self.payouts
            if p.miner_id == miner_id and p.epoch_number == epoch and (chain_id is None or p.chain_id == chain_id)
        ]
        return _ScalarResult(rows)

    # -- write side ------------------------------------------------------

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        while self._flush_idx < len(self.added):
            obj = self.added[self._flush_idx]
            if isinstance(obj, RewardPayout):
                key = (obj.miner_id, obj.chain_id, obj.epoch_number)
                if key in self.claimed:
                    raise IntegrityError("duplicate key", params=None, orig=Exception("uq_reward_payout_miner_chain_epoch"))
                self.claimed.add(key)
                self.payouts.append(obj)
            elif isinstance(obj, RewardShare):
                key = (obj.miner_id, obj.chain_id, obj.epoch_number, obj.source)
                if any((s.miner_id, s.chain_id, s.epoch_number, s.source) == key for s in self.shares):
                    raise IntegrityError(
                        "duplicate key", params=None, orig=Exception("uq_reward_share_miner_chain_epoch_source")
                    )
                self.shares.append(obj)
            self._flush_idx += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
        # Drop rows added but not yet flushed; flushed rows stay (a real
        # rollback would undo them too, but tests only exercise the claim
        # path where rollback precedes any successful flush).
        self.added = self.added[: self._flush_idx]


@pytest.fixture
def payout_session() -> FakeSession:
    """A fresh reward-payout session enforcing the uniqueness constraint."""
    return FakeSession()
