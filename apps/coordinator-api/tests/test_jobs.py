import pytest
from sqlmodel import Session, delete, text

from app.domain import Job, Miner
from app.models import JobCreate
from app.services.jobs import JobService
from app.storage.db import init_db, session_scope


@pytest.fixture(scope="module", autouse=True)
def _init_db(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("data") / "test.db"
    # override settings dynamically
    from app.config import settings

    settings.database_url = f"sqlite:///{db_file}"
    
    # Initialize database and create tables
    init_db()
    
    # Ensure payment_id column exists (handle schema migration)
    with session_scope() as sess:
        try:
            # Check if columns exist and add them if needed
            result = sess.exec(text("PRAGMA table_info(job)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'payment_id' not in columns:
                sess.exec(text("ALTER TABLE job ADD COLUMN payment_id TEXT"))
            if 'payment_status' not in columns:
                sess.exec(text("ALTER TABLE job ADD COLUMN payment_status TEXT"))
            sess.commit()
        except Exception as e:
            print(f"Schema migration error: {e}")
            sess.rollback()
    
    yield


@pytest.fixture()
def session():
    with session_scope() as sess:
        sess.exec(delete(Job))
        sess.exec(delete(Miner))
        sess.commit()
        yield sess


def test_create_and_fetch_job(session: Session):
    svc = JobService(session)
    job = svc.create_job("client1", JobCreate(payload={"task": "noop"}))
    fetched = svc.get_job(job.id, client_id="client1")
    assert fetched.id == job.id
    assert fetched.payload["task"] == "noop"


def test_acquire_next_job(session: Session):
    svc = JobService(session)
    job1 = svc.create_job("client1", JobCreate(payload={"n": 1}))
    job2 = svc.create_job("client1", JobCreate(payload={"n": 2}))

    miner = Miner(id="miner1", capabilities={}, concurrency=1)
    session.add(miner)
    session.commit()

    next_job = svc.acquire_next_job(miner)
    assert next_job is not None
    assert next_job.id == job1.id
    assert next_job.state == "RUNNING"

    next_job2 = svc.acquire_next_job(miner)
    assert next_job2 is not None
    assert next_job2.id == job2.id

    # No more jobs
    assert svc.acquire_next_job(miner) is None
