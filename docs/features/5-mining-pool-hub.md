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

### Pool Management

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Pool | Create a new mining pool | [docs/features/create-pool.md](./create-pool.md) | ✅ | v0.6.7 |
| Get Pool | Get pool information | [docs/features/get-pool.md](./get-pool.md) | ✅ | v0.6.7 |
| List Pools | List all pools with pagination | [docs/features/list-pools.md](./list-pools.md) | ✅ | v0.6.7 |
| Update Pool | Update pool settings | [docs/features/update-pool.md](./update-pool.md) | ✅ | v0.6.7 |
| Delete Pool | Delete a pool (must have no miners) | [docs/features/delete-pool.md](./delete-pool.md) | ✅ | v0.6.7 |
| Pool Stats | Get pool statistics | [docs/features/pool-stats.md](./pool-stats.md) | ✅ | v0.6.7 |
| Join Pool | Join a miner to a pool | [docs/features/join-pool.md](./join-pool.md) | ✅ | v0.6.7 |
| Leave Pool | Remove a miner from a pool | [docs/features/leave-pool.md](./leave-pool.md) | ✅ | v0.6.7 |
| Pool Miners | Get miners in a pool | [docs/features/pool-miners.md](./pool-miners.md) | ✅ | v0.6.7 |

### Mining RPC

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Start/Stop Mining | Start/stop mining via RPC | [docs/mining/7_api-miner.md](../mining/7_api-miner.md) | ✅ | — |
| Mining Status | Get mining status (aggregated from coordinator-api) | [docs/mining/6_monitoring.md](../mining/6_monitoring.md) | ✅ | v0.10.1 |
| List Miners | List active miners (from coordinator-api) | [docs/mining/6_monitoring.md](../mining/6_monitoring.md) | ✅ | v0.10.1 |

---
