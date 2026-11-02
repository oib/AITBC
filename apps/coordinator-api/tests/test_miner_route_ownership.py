"""Route-ownership tests for the miner-scoped coordinator endpoints (Refs #804).

fail_job and complete_job already refuse a caller whose ``sub`` differs from the
path ``miner_id``; the four sibling routes below must apply the same guard:
list_miner_jobs, get_miner_earnings, update_miner_capabilities and
deregister_miner. Until per-miner credentials exist the shared miner key is the
trust boundary — these checks stop mistakes between key holders.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth.dependencies import require_miner

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.miner import Miner
from coordinator_api.contexts.infrastructure.services.miners import MinerService
from coordinator_api.main import app
from coordinator_api.schemas import MinerRegister
from coordinator_api.storage import get_session


EVIL = {"sub": "miner-evil", "role": "miner"}
VICTIM = "miner-victim"
SECRET_PROMPT = "CUSTOMER-SECRET-PROMPT"


@pytest.fixture
def caller_client(db_session):
    """TestClient factory: caller identity is swapped per test, in-memory DB."""

    def _make(caller: dict[str, str]) -> TestClient:
        def override_session():
            yield db_session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[require_miner] = lambda: caller
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_miner, None)


def _seed_victim(db_session: Session) -> Job:
    MinerService(db_session).register(
        VICTIM,
        MinerRegister(capabilities={"gpu": "probe"}, wallet_address="0x" + "11" * 20),
    )
    job = Job(
        id="job-own1",
        client_id="client-1",
        state="RUNNING",
        payload={"type": "inference", "prompt": SECRET_PROMPT},
        assigned_miner_id=VICTIM,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.mark.unit
class TestMinerRouteOwnership:
    def test_list_miner_jobs_refuses_other_miner(self, caller_client, db_session):
        _seed_victim(db_session)
        client = caller_client(EVIL)
        resp = client.post(f"/v1/miners/{VICTIM}/jobs")
        assert resp.status_code == 403
        assert SECRET_PROMPT not in resp.text

    def test_get_miner_earnings_refuses_other_miner(self, caller_client, db_session):
        _seed_victim(db_session)
        client = caller_client(EVIL)
        resp = client.post(f"/v1/miners/{VICTIM}/earnings")
        assert resp.status_code == 403

    def test_update_miner_capabilities_refuses_other_miner(self, caller_client, db_session):
        _seed_victim(db_session)
        client = caller_client(EVIL)
        resp = client.put(
            f"/v1/miners/{VICTIM}/capabilities",
            json={"capabilities": {"gpu": "evil"}, "concurrency": 1},
        )
        assert resp.status_code == 403

    def test_deregister_miner_refuses_other_miner(self, caller_client, db_session):
        _seed_victim(db_session)
        client = caller_client(EVIL)
        resp = client.delete(f"/v1/miners/{VICTIM}")
        assert resp.status_code == 403
        db_session.expire_all()
        miner = db_session.get(Miner, VICTIM)
        assert miner is not None
        assert miner.status == "ONLINE"
        assert miner.session_token is not None

    def test_own_miner_can_list_jobs_and_earnings(self, caller_client, db_session):
        _seed_victim(db_session)
        client = caller_client({"sub": VICTIM, "role": "miner"})
        resp = client.post(f"/v1/miners/{VICTIM}/jobs")
        assert resp.status_code == 200
        resp = client.post(f"/v1/miners/{VICTIM}/earnings")
        assert resp.status_code == 200

    def test_earnings_error_does_not_leak_exception_text(self, caller_client, db_session, monkeypatch):
        """The except branch must answer a fixed message, not str(e) (Refs #804)."""
        _seed_victim(db_session)

        def _boom(*args, **kwargs):
            raise RuntimeError("secret-internal-error-detail")

        monkeypatch.setattr(
            "coordinator_api.contexts.infrastructure.services.jobs.JobService.list_jobs",
            _boom,
        )
        client = caller_client({"sub": VICTIM, "role": "miner"})
        resp = client.post(f"/v1/miners/{VICTIM}/earnings")
        assert resp.status_code == 200
        assert "secret-internal-error-detail" not in resp.text
