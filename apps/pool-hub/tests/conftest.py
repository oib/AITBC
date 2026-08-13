from __future__ import annotations

import os
import sys
from pathlib import Path
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


class FakeSession:
    """Minimal AsyncSession stand-in enforcing the reward_payouts unique constraint.

    Mirrors what Postgres does on (miner_id, chain_id, epoch_number) so the payout
    decision path can be exercised without a database.
    """

    def __init__(self, already_claimed: set[tuple[str, str, int]] | None = None) -> None:
        self.claimed: set[tuple[str, str, int]] = set(already_claimed or ())
        self.added: list[Any] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pending = self.added[-1]
        key = (pending.miner_id, pending.chain_id, pending.epoch_number)
        if key in self.claimed:
            raise IntegrityError("duplicate key", params=None, orig=Exception("uq_reward_payout_miner_chain_epoch"))
        self.claimed.add(key)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self.added:
            self.added.pop()


@pytest.fixture
def payout_session() -> FakeSession:
    """A fresh reward-payout session enforcing the uniqueness constraint."""
    return FakeSession()
