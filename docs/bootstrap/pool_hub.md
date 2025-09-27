# pool-hub.md — Client ↔ Miners Pool & Matchmaking Gateway (guide for Windsurf)

> **Role in AITBC**  
> The **Pool Hub** is the real-time directory of available miners and a low-latency **matchmaker** between **job requests** (coming from `coordinator-api`) and **worker capacity** (from `miner-node`).  
> It tracks miner capabilities, health, and price; computes a score; and returns the **best N candidates** for each job.

---

## 1) MVP Scope (Stage 3 of the boot plan)

- Accept **miner registrations** + **heartbeats** (capabilities, price, queues).
- Maintain an in-memory + persistent **miner registry** with fast lookups.
- Provide a **/match** API for `coordinator-api` to request top candidates.
- Simple **scoring** with pluggable strategy (latency, VRAM, price, trust).
- **No token minting/accounting** in MVP (stub hooks only).
- **No Docker**: Debian 12, `uvicorn` service, optional Nginx reverse proxy.

---

## 2) High-Level Architecture

```
client-web ──> coordinator-api ──> pool-hub ──> miner-node
                              ▲                 ▲
                              │                 │
                      wallet-daemon       heartbeat + capability updates
                       (later)            (WebSocket/HTTP)
```

### Responsibilities
- **Registry**: who’s online, what they can do, how much it costs.
- **Health**: heartbeats, timeouts, grace periods, auto-degrade/remove.
- **Matchmaking**: filter → score → return top K miner candidates.
- **Observability**: metrics for availability, match latency, rejection reasons.

---

## 3) Protocols & Endpoints (FastAPI)

> Base URL examples:
> - Public (optional): `https://pool-hub.example/api`
> - Internal (preferred): `http://127.0.0.1:8203` (behind Nginx)

### 3.1 Miner lifecycle (HTTP + WebSocket)

- `POST /v1/miners/register`
  - **Body**: `{ miner_id, api_key, addr, proto, gpu_vram, gpu_name, cpu_cores, ram_gb, price_token_per_ksec, max_parallel, tags[], capabilities[] }`
  - **Returns**: `{ status, lease_ttl_sec, next_heartbeat_sec }`
  - Notes: returns a **session_token** (short-lived) if `api_key` valid.

- `POST /v1/miners/update`
  - **Body**: `{ session_token, queue_len, busy, current_jobs[], price_token_per_ksec? }`

- `GET /v1/miners/lease/renew?session_token=...`
  - Renews online lease (fallback if WS drops).

- `WS /v1/miners/heartbeat`
  - **Auth**: `session_token` in query.
  - **Payload (periodic)**: `{ ts, queue_len, avg_latency_ms?, temp_c?, mem_free_gb? }`
  - Server may push **commands** (e.g., “update tags”, “set price cap”).

- `POST /v1/miners/logout`
  - Clean unregister (otherwise lease expiry removes).

### 3.2 Coordinator matchmaking (HTTP)

- `POST /v1/match`
  - **Body**:
    ```json
    {
      "job_id": "uuid",
      "requirements": {
        "task": "image_embedding",
        "min_vram_gb": 8,
        "min_ram_gb": 8,
        "accel": ["cuda"],
        "tags_any": ["eu-west","low-latency"],
        "capabilities_any": ["sentence-transformers/all-MiniLM-L6-v2"]
      },
      "hints": { "region": "eu", "max_price": 0.8, "deadline_ms": 5000 },
      "top_k": 3
    }
    ```
  - **Returns**:
    ```json
    {
      "job_id": "uuid",
      "candidates": [
        { "miner_id":"...", "addr":"...", "proto":"grpc", "score":0.87, "eta_ms": 320, "price":0.75 },
        { "miner_id":"...", "addr":"...", "proto":"grpc", "score":0.81, "eta_ms": 410, "price":0.65 }
      ],
      "explain": "cap=1.0 • price=0.8 • latency=0.9 • trust=0.7"
    }
    ```

- `POST /v1/feedback`
  - **Body**: `{ job_id, miner_id, outcome: "accepted"|"rejected"|"failed"|"completed", latency_ms?, fail_code?, tokens_spent? }`
  - Used to adjust **trust score** & calibration.

### 3.3 Observability

- `GET /v1/health` → `{ status:"ok", online_miners, avg_latency_ms }`
- `GET /v1/metrics` → Prometheus-style metrics (text)
- `GET /v1/miners` (admin-guarded) → paginated registry snapshot

---

## 4) Data Model (PostgreSQL minimal)

> Schema name: `poolhub`

**tables**
- `miners`  
  `miner_id PK, api_key_hash, created_at, last_seen_at, addr, proto, gpu_vram_gb, gpu_name, cpu_cores, ram_gb, max_parallel, base_price, tags jsonb, capabilities jsonb, trust_score float default 0.5, region text`
- `miner_status`  
  `miner_id FK, queue_len int, busy bool, avg_latency_ms int, temp_c int, mem_free_gb float, updated_at`
- `feedback`  
  `id PK, job_id, miner_id, outcome, latency_ms, fail_code, tokens_spent, created_at`
- `price_overrides` (optional)

**indexes**
- `idx_miners_region_caps_gte_vram` (GIN on jsonb + partials)
- `idx_status_updated_at`
- `idx_feedback_miner_time`

**in-memory caches**
- Hot registry (Redis or local LRU) for sub-millisecond match filter.

---

## 5) Matching & Scoring

**Filter**:
- Hard constraints: `min_vram_gb`, `min_ram_gb`, `accel`, `capabilities_any`, `region`, `max_price`, `queue_len < max_parallel`.

**Score formula (tunable)**:
```
score = w_cap*cap_fit
      + w_price*price_norm
      + w_latency*latency_norm
      + w_trust*trust_score
      + w_load*load_norm
```
- `cap_fit`: 1 if all required caps present, else <1 proportional to overlap.
- `price_norm`: cheaper = closer to 1 (normalized vs request cap).
- `latency_norm`: 1 for fastest observed in region, decays by percentile.
- `load_norm`: higher if queue_len small and max_parallel large.
- Default weights: `w_cap=0.40, w_price=0.20, w_latency=0.20, w_trust=0.15, w_load=0.05`.

Return top-K with **explain string** for debugging.

---

## 6) Security (MVP → later hardening)

- **Auth**:
  - Miners: static `api_key` → exchange for short **session_token**.
  - Coordinator: **shared secret** header (MVP), rotate via env.
- **Network**:
  - Bind to localhost; expose via Nginx with IP allowlist for coordinator.
  - Rate limits on `/match` and `/register`.
- **Later**:
  - mTLS between pool-hub ↔ miners.
  - Signed capability manifests.
  - Attestation (NVIDIA MIG/hash) optional.

---

## 7) Configuration

- `.env` (loaded by FastAPI):
  - `POOLHUB_BIND=127.0.0.1`
  - `POOLHUB_PORT=8203`
  - `DB_DSN=postgresql://poolhub:*****@127.0.0.1:5432/aitbc`
  - `REDIS_URL=redis://127.0.0.1:6379/4` (optional)
  - `COORDINATOR_SHARED_SECRET=...`
  - `SESSION_TTL_SEC=60`
  - `HEARTBEAT_GRACE_SEC=120`
  - `DEFAULT_WEIGHTS=cap:0.4,price:0.2,latency:0.2,trust:0.15,load:0.05`

---

## 8) Local Dev (Debian 12, no Docker)

```bash
# Python env
apt install -y python3-venv python3-pip
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn[standard] pydantic-settings psycopg[binary] orjson redis prometheus-client

# DB (psql one-liners, adjust to your policy)
psql -U postgres -c "CREATE USER poolhub WITH PASSWORD '***';"
psql -U postgres -c "CREATE DATABASE aitbc OWNER poolhub;"
psql -U postgres -d aitbc -c "CREATE SCHEMA poolhub AUTHORIZATION poolhub;"

# Run
uvicorn app.main:app --host 127.0.0.1 --port 8203 --workers 1 --proxy-headers
```

---

## 9) Systemd service (uvicorn)

`/etc/systemd/system/pool-hub.service`
```
[Unit]
Description=AITBC Pool Hub (FastAPI)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
User=games
Group=games
WorkingDirectory=/var/www/aitbc/pool-hub
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/var/www/aitbc/pool-hub/.env
ExecStart=/var/www/aitbc/pool-hub/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8203 --workers=1 --proxy-headers
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

---

## 10) Optional Nginx (host as reverse proxy)

```
server {
  listen 443 ssl http2;
  server_name pool-hub.example;
  # ssl_certificate ...; ssl_certificate_key ...;

  # Only allow coordinator’s IPs
  allow 10.0.3.32;
  allow 127.0.0.1;
  deny all;

  location / {
    proxy_pass http://127.0.0.1:8203;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
  }
}
```

---

## 11) FastAPI App Skeleton (files to create)

```
pool-hub/
  app/
    __init__.py
    main.py              # FastAPI init, routers include, metrics
    deps.py              # auth, db sessions, rate limits
    models.py            # SQLAlchemy/SQLModel tables (see schema)
    schemas.py           # Pydantic I/O models
    registry.py          # in-memory index + Redis bridge
    scoring.py           # score strategies
    routers/
      miners.py          # register/update/ws/logout
      match.py           # /match and /feedback
      admin.py           # /miners snapshot (guarded)
      health.py          # /health, /metrics
  .env.example
  README.md
```

---

## 12) Testing & Validation Checklist

1. Register 3 miners (mixed VRAM, price, region).  
2. Heartbeats arrive; stale miners drop after `HEARTBEAT_GRACE_SEC`.  
3. `/match` with constraints returns consistent top-K and explain string.  
4. Rate limits kick in (flood `/match` with 50 rps).  
5. Coordinator feedback adjusts trust score; observe score shifts.  
6. Systemd restarts on crash; Nginx denies non-coordinator IPs.  
7. Metrics expose `poolhub_miners_online`, `poolhub_match_latency_ms`.  

---

## 13) Roadmap (post-MVP)

- Weighted **multi-dispatch** (split jobs across K miners, merge).  
- **Price discovery**: spot vs reserved capacity.  
- **mTLS**, signed manifests, hardware attestation.  
- **AIToken hooks**: settle/pay via `wallet-daemon` + `blockchain-node`.  
- Global **region routing** + latency probes.

---

## 14) Dev Notes for Windsurf

- Start with **routers/miners.py** and **routers/match.py**.  
- Implement `registry.py` with a simple in-proc dict + RWLock; add Redis later.  
- Keep scoring in **scoring.py** with clear weight constants and unit tests.  
- Provide a tiny CLI seed to simulate miners for local testing.

---

### Open Questions

- Trust model inputs (what counts as failure vs transient)?  
- Minimal capability schema vs free-form tags?  
- Region awareness from IP vs miner-provided claim?

---

**Want me to generate the initial FastAPI file stubs for this layout now (yes/no)?**

