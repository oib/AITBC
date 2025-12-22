# coordinator-api.md

Central API that orchestrates **jobs** from clients to **miners**, tracks lifecycle, validates results, and (later) settles AITokens.  
**Stage 1 (MVP):** no blockchain, no pool hub — just client ⇄ coordinator ⇄ miner.

## 1) Goals & Non-Goals

**Goals (MVP)**
- Accept computation jobs from clients.
- Match jobs to eligible miners.
- Track job state machine (QUEUED → RUNNING → COMPLETED/FAILED/CANCELED/EXPIRED).
- Stream results back to clients; store minimal metadata.
- Provide a clean, typed API (OpenAPI/Swagger).
- Simple auth (API keys) + idempotency + rate limits.
- Minimal persistence (SQLite/Postgres) with straightforward SQL (no migrations tooling).

**Non-Goals (MVP)**
- Token minting/settlement (stub hooks only).
- Miner marketplace, staking, slashing, reputation (placeholders).
- Pool hub coordination (future stage).

---

## 2) Tech Stack

- **Python 3.12**, **FastAPI**, **Uvicorn**
- **Pydantic** for schemas
- **SQL** via `sqlite3` or Postgres (user can switch later)
- **Redis (optional)** for queueing; MVP can start with in-DB FIFO
- **HTTP + WebSocket** (for miner heartbeats / job streaming)

> Debian 12 target. Run under **systemd** later.

---

## 3) Directory Layout (WindSurf Workspace)

```
coordinator-api/
├─ app/
│  ├─ main.py                  # FastAPI init, lifespan, routers
│  ├─ config.py                # env parsing
│  ├─ deps.py                  # auth, rate-limit deps
│  ├─ db.py                    # simple DB layer (sqlite/postgres)
│  ├─ matching.py              # job→miner selection
│  ├─ queue.py                 # enqueue/dequeue logic
│  ├─ settlement.py            # stubs for token accounting
│  ├─ models.py                # Pydantic request/response schemas
│  ├─ states.py                # state machine + transitions
│  ├─ routers/
│  │  ├─ client.py             # /v1/jobs (submit/status/result/cancel)
│  │  ├─ miner.py              # /v1/miners (register/heartbeat/poll/submit/fail)
│  │  └─ admin.py              # /v1/admin (stats)
│  └─ ws/
│     ├─ miner.py              # WS for miner heartbeats / job stream (optional)
│     └─ client.py             # WS for client result stream (optional)
├─ tests/
│  ├─ test_client_flow.http    # REST client flow (HTTP file)
│  └─ test_miner_flow.http     # REST miner flow
├─ .env.example
├─ pyproject.toml
└─ README.md
```

---

## 4) Environment (.env)

```
APP_ENV=dev
APP_HOST=127.0.0.1
APP_PORT=8011
DATABASE_URL=sqlite:///./coordinator.db
# or: DATABASE_URL=postgresql://user:pass@localhost:5432/aitbc

# Auth
CLIENT_API_KEYS=REDACTED_CLIENT_KEY,client_dev_key_2
MINER_API_KEYS=REDACTED_MINER_KEY,miner_dev_key_2
ADMIN_API_KEYS=REDACTED_ADMIN_KEY

# Security
HMAC_SECRET=change_me
ALLOW_ORIGINS=*

# Queue
JOB_TTL_SECONDS=900
HEARTBEAT_INTERVAL_SECONDS=10
HEARTBEAT_TIMEOUT_SECONDS=30
```

---

## 5) Core Data Model (conceptual)

**Job**
- `job_id` (uuid)
- `client_id` (from API key)
- `requested_at`, `expires_at`
- `payload` (opaque JSON / bytes ref)
- `constraints` (gpu, cuda, mem, model, max_price, region)
- `state` (QUEUED|RUNNING|COMPLETED|FAILED|CANCELED|EXPIRED)
- `assigned_miner_id` (nullable)
- `result_ref` (blob path / inline json)
- `error` (nullable)
- `cost_estimate` (optional)

**Miner**
- `miner_id` (from API key)
- `capabilities` (gpu, cuda, vram, models[], region)
- `heartbeat_at`
- `status` (ONLINE|OFFLINE|DRAINING)
- `concurrency` (int), `inflight` (int)

**WorkerSession**
- `session_id`, `miner_id`, `job_id`, `started_at`, `ended_at`, `exit_reason`

---

## 6) State Machine

```
QUEUED
  -> RUNNING (assigned to miner)
  -> CANCELED (client)
  -> EXPIRED (ttl)

RUNNING
  -> COMPLETED (miner submit_result)
  -> FAILED    (miner fail / timeout)
  -> CANCELED  (client)
```

---

## 7) Matching (MVP)

- Filter ONLINE miners by **capabilities** & **region**
- Prefer lowest `inflight` (simple load)
- Tiebreak by earliest `heartbeat_at` or random
- Lock job row → assign → return to miner

---

## 8) Auth & Rate Limits

- **API keys** via `X-Api-Key` header for `client`, `miner`, `admin`.
- Optional **HMAC** (`X-Signature`) over body with `HMAC_SECRET`.
- **Idempotency**: clients send `Idempotency-Key` on **POST /jobs**.
- **Rate limiting**: naive per-key window (e.g., 60 req / 60 s).

---

## 9) REST API

### Client

- `POST /v1/jobs`
  - Create job. Returns `job_id`.
- `GET /v1/jobs/{job_id}`
  - Job status & metadata.
- `GET /v1/jobs/{job_id}/result`
  - Result (200 when ready, 425 if not ready).
- `POST /v1/jobs/{job_id}/cancel`
  - Cancel if QUEUED or RUNNING (best effort).

### Miner

- `POST /v1/miners/register`
  - Upsert miner capabilities; set ONLINE.
- `POST /v1/miners/heartbeat`
  - Touch `heartbeat_at`, report `inflight`.
- `POST /v1/miners/poll`
  - Long-poll for next job → returns a job or 204.
- `POST /v1/miners/{job_id}/start`
  - Confirm start (optional if `poll` implies start).
- `POST /v1/miners/{job_id}/result`
  - Submit result; transitions to COMPLETED.
- `POST /v1/miners/{job_id}/fail`
  - Submit failure; transitions to FAILED.
- `POST /v1/miners/drain`
  - Graceful stop accepting new jobs.

### Admin

- `GET /v1/admin/stats`
  - Queue depth, miners online, success rates, avg latency.
- `GET /v1/admin/jobs?state=&limit=...`
- `GET /v1/admin/miners`

**Error Shape**
```json
{ "error": { "code": "STRING_CODE", "message": "human readable", "details": {} } }
```

Common codes: `UNAUTHORIZED_KEY`, `RATE_LIMITED`, `INVALID_PAYLOAD`, `NO_ELIGIBLE_MINER`, `JOB_NOT_FOUND`, `JOB_NOT_READY`, `CONFLICT_STATE`.

---

## 10) WebSockets (optional MVP+)

- `WS /v1/ws/miner?api_key=...`
  - Server → miner: `job.assigned`
  - Miner → server: `heartbeat`, `result`, `fail`
- `WS /v1/ws/client?job_id=...&api_key=...`
  - Server → client: `state.changed`, `result.ready`

Fallback remains HTTP long-polling.

---

## 11) Result Storage

- **Inline JSON** if ≤ 1 MB.
- For larger payloads: store to disk path (e.g., `/var/lib/coordinator/results/{job_id}`) and return `result_ref`.

---

## 12) Settlement Hooks (stub)

`settlement.py` exposes:
- `record_usage(job, miner)`  
- `quote_cost(job)`  
Later wired to **AIToken** mint/transfer when blockchain lands.

---

## 13) Minimal FastAPI Skeleton

```python
# app/main.py
from fastapi import FastAPI
from app.routers import client, miner, admin

def create_app():
    app = FastAPI(title="AITBC Coordinator API", version="0.1.0")
    app.include_router(client.router, prefix="/v1")
    app.include_router(miner.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1")
    return app

app = create_app()
```

```python
# app/models.py
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class Constraints(BaseModel):
    gpu: Optional[str] = None
    cuda: Optional[str] = None
    min_vram_gb: Optional[int] = None
    models: Optional[List[str]] = None
    region: Optional[str] = None
    max_price: Optional[float] = None

class JobCreate(BaseModel):
    payload: Dict[str, Any]
    constraints: Constraints = Constraints()
    ttl_seconds: int = 900

class JobView(BaseModel):
    job_id: str
    state: str
    assigned_miner_id: Optional[str] = None
    requested_at: str
    expires_at: str
    error: Optional[str] = None

class MinerRegister(BaseModel):
    capabilities: Dict[str, Any]
    concurrency: int = 1
    region: Optional[str] = None

class PollRequest(BaseModel):
    max_wait_seconds: int = 15

class AssignedJob(BaseModel):
    job_id: str
    payload: Dict[str, Any]
```

```python
# app/routers/client.py
from fastapi import APIRouter, Depends, HTTPException
from app.models import JobCreate, JobView
from app.deps import require_client_key

router = APIRouter(tags=["client"])

@router.post("/jobs", response_model=JobView)
def submit_job(req: JobCreate, client_id: str = Depends(require_client_key)):
    # enqueue + return JobView
    ...

@router.get("/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str, client_id: str = Depends(require_client_key)):
    ...
```

```python
# app/routers/miner.py
from fastapi import APIRouter, Depends
from app.models import MinerRegister, PollRequest, AssignedJob
from app.deps import require_miner_key

router = APIRouter(tags=["miner"])

@router.post("/miners/register")
def register(req: MinerRegister, miner_id: str = Depends(require_miner_key)):
    ...

@router.post("/miners/poll", response_model=AssignedJob, status_code=200)
def poll(req: PollRequest, miner_id: str = Depends(require_miner_key)):
    # try dequeue, else 204
    ...
```

Run:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8011 --reload
```

OpenAPI: `http://127.0.0.1:8011/docs`

---

## 14) Matching & Queue Pseudocode

```python
def match_next_job(miner):
    eligible = db.jobs.filter(
        state="QUEUED",
        constraints.satisfied_by(miner.capabilities)
    ).order_by("requested_at").first()
    if not eligible:
        return None
    db.txn(lambda:
        db.jobs.assign(eligible.job_id, miner.id) and
        db.states.transition(eligible.job_id, "RUNNING")
    )
    return eligible
```

---

## 15) CURL Examples

**Client creates a job**
```bash
curl -sX POST http://127.0.0.1:8011/v1/jobs \
  -H 'X-Api-Key: REDACTED_CLIENT_KEY' \
  -H 'Idempotency-Key: 7d4a...' \
  -H 'Content-Type: application/json' \
  -d '{
        "payload": {"task":"sum","a":2,"b":3},
        "constraints": {"gpu": null, "region": "eu-central"}
      }'
```

**Miner registers + polls**
```bash
curl -sX POST http://127.0.0.1:8011/v1/miners/register \
  -H 'X-Api-Key: REDACTED_MINER_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"capabilities":{"gpu":"RTX4060Ti","cuda":"12.3","vram_gb":16},"concurrency":2,"region":"eu-central"}'

curl -i -sX POST http://127.0.0.1:8011/v1/miners/poll \
  -H 'X-Api-Key: REDACTED_MINER_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"max_wait_seconds":10}'
```

**Miner submits result**
```bash
curl -sX POST http://127.0.0.1:8011/v1/miners/<JOB_ID>/result \
  -H 'X-Api-Key: REDACTED_MINER_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"result":{"sum":5},"metrics":{"latency_ms":42}}'
```

**Client fetches result**
```bash
curl -s http://127.0.0.1:8011/v1/jobs/<JOB_ID>/result \
  -H 'X-Api-Key: REDACTED_CLIENT_KEY'
```

---

## 16) Timeouts & Health

- **Job TTL**: auto-expire QUEUED after `JOB_TTL_SECONDS`.
- **Heartbeat**: miners post every `HEARTBEAT_INTERVAL_SECONDS`.
- **Miner OFFLINE** if no heartbeat for `HEARTBEAT_TIMEOUT_SECONDS`.
- **Requeue**: RUNNING jobs from OFFLINE miners → back to QUEUED.

---

## 17) Security Notes

- Validate `payload` size & type; enforce max 1 MB inline.
- Optional **HMAC** signature for tamper detection.
- Sanitize/validate miner-reported capabilities.
- Log every state transition (append-only).

---

## 18) Admin Metrics (MVP)

- Queue depth, running count
- Miner online/offline, inflight
- P50/P95 job latency
- Success/fail/cancel rates (windowed)

---

## 19) Future Stages

- **Blockchain layer**: mint on verified compute; tie to `record_usage`.
- **Pool hub**: multi-coordinator balancing; marketplace.
- **Reputation**: miner scoring, penalty, slashing.
- **Bidding**: price discovery; client max price.

---

## 20) Checklist (WindSurf)

1. Create repo structure from section **3**.  
2. Implement `.env` & `config.py` keys from **4**.  
3. Add `models.py`, `states.py`, `deps.py` (auth, rate limit).  
4. Implement DB tables for Job, Miner, WorkerSession.  
5. Implement `queue.py` and `matching.py`.  
6. Wire **client** and **miner** routers (MVP endpoints).  
7. Add admin stats (basic counts).  
8. Add OpenAPI tags, descriptions.  
9. Add curl `.http` test files.  
10. Systemd unit + Nginx proxy (later).

