# Mining & Pool Hub

## 5. Mining & Pool Hub

### Miner Registration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Register Miner | Register GPU miner with network | [docs/mining/2_registration.md](../mining/2_registration.md) | ✅ | — |
| Miner Status | Get registration status, GPU availability, current jobs | [docs/mining/2_registration.md](../mining/2_registration.md) | ✅ | — |
| Update Registration | Update miner settings (price, max-concurrent) | [docs/mining/2_registration.md](../mining/2_registration.md) | ✅ | — |
| Deregister Miner | Remove miner from network | [docs/mining/2_registration.md](../mining/2_registration.md) | ✅ | — |

### Job Management

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Poll for Jobs | Poll coordinator for next job | [docs/mining/3_job-management.md](../mining/3_job-management.md) | ✅ | — |
| Submit Job Result | Submit job result to coordinator | [docs/mining/3_job-management.md](../mining/3_job-management.md) | ✅ | — |
| Report Job Failure | Report job failure | [docs/mining/3_job-management.md](../mining/3_job-management.md) | ✅ | — |
| List Jobs | List jobs for a miner | [docs/mining/3_job-management.md](../mining/3_job-management.md) | ✅ | — |

### Earnings

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Get Earnings | Get miner earnings | [docs/mining/4_earnings.md](../mining/4_earnings.md) | ✅ | — |
| Update Capabilities | Update miner capabilities | [docs/features/update-capabilities.md](./update-capabilities.md) | ✅ | — |

### Pool-Hub Miner & Match Surface

The pool-hub has no pool-CRUD entities (no `Pool` table; the v0.6.7-era
pool rows below were removed). Its real surface is miner registration,
job-to-miner matching, service configs, and SLA tracking
(`apps/pool-hub/src/poolhub/app/main.py` mounts the `match`, `health`,
`metrics`, `services`, `miners`, `ui`, `validation`, `sla`, `parameters`
routers).

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Miner Registration | Register a GPU miner with the pool-hub/coordinator (`POST /v1/miners/register`) | [docs/features/create-pool.md](./create-pool.md) | ✅ | — |
| Miner Detail & Status | Read registered detail and live status (`GET /v1/miners/status`, `miner_status`) | [docs/features/get-pool.md](./get-pool.md) | ✅ | — |
| List Miners & Match Entities | Miner roster (`GET /v1/admin/miners`), service configs (`GET /v1/services/`), match_requests/results | [docs/features/list-pools.md](./list-pools.md) | ✅ | — |
| Update Miner Capabilities | `PUT /v1/miners/{miner_id}/capabilities` on the coordinator; re-register / `PATCH /v1/services/{service_type}` on pool-hub | [docs/features/update-pool.md](./update-pool.md) | ✅ | — |
| Miner Deregistration | `DELETE /v1/miners/{miner_id}` on the coordinator; heartbeat expiry on pool-hub | [docs/features/delete-pool.md](./delete-pool.md) | ✅ | — |
| SLA Metrics & Reward Payouts | `GET /v1/sla/metrics`, `/v1/sla/violations`, capacity snapshots, `reward_payouts` audit table | [docs/features/pool-stats.md](./pool-stats.md) | ✅ | — |
| Match Request Submission | `POST /v1/match` — top-scored miners for a job | [docs/features/join-pool.md](./join-pool.md) | ✅ | — |
| Leaving the Miner Roster | Heartbeat expiry / coordinator deregistration | [docs/features/leave-pool.md](./leave-pool.md) | ✅ | — |
| Miner Roster | Fleet-wide miner list (coordinator admin, blockchain RPC) | [docs/features/pool-miners.md](./pool-miners.md) | ✅ | — |

Additional pool-hub routers not tied to a feature doc: `GET /v1/validation/compatible-services`, `POST /v1/validation/service/{service_id}`, `GET /v1/validation/hardware-profile` (`routers/validation.py`); `POST /v1/parameters/apply`, `GET /v1/parameters/list` (`routers/parameters.py`); service-config CRUD under `/v1/services` (`routers/services.py`).

### Mining RPC

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Start/Stop Mining | Start/stop mining via RPC | [docs/mining/7_api-miner.md](../mining/7_api-miner.md) | ✅ | — |
| Mining Status | Get mining status (aggregated from coordinator-api) | [docs/mining/6_monitoring.md](../mining/6_monitoring.md) | ✅ | v0.10.1 |
| List Miners | List active miners (from coordinator-api) | [docs/mining/6_monitoring.md](../mining/6_monitoring.md) | ✅ | v0.10.1 |

---
