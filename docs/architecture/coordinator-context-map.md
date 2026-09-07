# Coordinator API — bounded-context map

> **Purpose:** inventory only. This document maps what has accumulated in
> `coordinator-api` so the drag stays visible. It is **not** a refactor
> proposal — see the open register (G8/A-8): no fix should be attempted
> casually.

Snapshot: gitea `main` @ `7a3e664eb` (7 Sep 2026).

## Shape

- **36** top-level bounded-context directories under
  `apps/coordinator-api/src/coordinator_api/contexts/`
- **48** `include_router` calls in `coordinator_api/main.py`
- **107** router modules, **72** `APIRouter` declarations repo-wide
- Nearly everything mounts under the single `/v1` prefix; mounting is
  feature-flag gated in places (`zk_proofs`, `fhe`, `oracle`, `disputes`,
  `bounty`, `governance`, `ml_zk_proofs`, `staking`, `agent_security`,
  `trading`, `reputation`, `rewards`, `knowledge`).

## Context inventory

Routers = `*router*.py` / `routers/` modules; services = `services/` modules.

| Context | Routers | Services | What it holds |
|---|---|---|---|
| infrastructure | 13 | 10 | jobs, miners, explorer, inference, users, monitoring — the original core |
| developer_platform | 9 | 2 | developer registry, API keys, webhooks, analytics |
| agent_coordination | 7 | 11 | agent orchestration, swarm, messaging |
| marketplace | 7 | 11 | marketplace, GPU marketplace, offers, bonds |
| governance | 6 | 5 | governance, enhanced governance, disputes |
| zk_applications | 5 | 7 | ZK proof generation/verification, circuits, model registry |
| multimodal | 4 | 5 | multimodal job handling, RL |
| blockchain | 3 | 3 | chain-facing endpoints, sync status |
| bounty | 3 | 2 | bounty lifecycle |
| advanced_rl | 1 | 9 | RL pipelines (service-heavy, thin API) |
| wallet | 0 | 5 | wallet integration services (no own routers) |
| advanced_ai | 2 | 1 | advanced AI endpoints |
| agent_identity | 2 | 2 | agent identity/DID |
| analytics | 2 | 6 | market analytics, metrics |
| certification | 2 | 6 | certification/audit flows |
| community | 2 | 2 | community features |
| compliance | 2 | 2 | compliance checks/classification |
| confidential | 2 | 1 | confidential-compute surface |
| cross_chain | 2 | 6 | cross-chain transfers, bridges |
| developer | 2 | 2 | developer-facing endpoints |
| ecosystem | 2 | 2 | ecosystem/partner surface |
| edge_gpu | 2 | 2 | edge GPU coordination |
| enterprise_integration | 2 | 1 | enterprise connectors |
| gpu_multimodal | 2 | 1 | GPU multimodal jobs |
| ipfs | 2 | 3 | IPFS pinning/distribution |
| knowledge | 2 | 0 | knowledge base endpoints |
| payments | 2 | 6 | payments, escrow coordination |
| portfolio | 2 | 2 | portfolio tracking |
| reputation | 2 | 3 | reputation/trust scores |
| rewards | 2 | 2 | reward distribution |
| security | 2 | 6 | security policies, audit |
| settlement | 2 | 1 | settlement hooks, reconciliation |
| staking | 2 | 2 | staking, bonds |
| tee | 2 | 0 | TEE attestation surface |
| trading | 2 | 7 | trading coordination |
| agent_economics | 0 | 0 | models/logic only — no routers or services |
| preferences | 0 | 0 | models/logic only — no routers or services |

## Reading the map

- **The core is small; the rim is not.** `infrastructure` + `payments` +
  `marketplace` + `agent_coordination` carry the operational loop. The other
  ~32 contexts are feature surface accumulated into the one deployable.
- **Feature flags gate ~14 mounts.** A disabled flag removes routes at boot —
  meaning route inventory varies by deployment config, which is itself part of
  the drag (docs, tests, and clients can't assume a stable surface).
- **Two contexts are dead weight at the API layer**: `agent_economics` and
  `preferences` expose no routers or services — whatever they hold is imported
  from elsewhere or unused.
- **Duplication clusters**: `developer` vs `developer_platform`,
  `governance` + `governance_enhanced`, `advanced_ai` / `advanced_rl` /
  `gpu_multimodal` / `multimodal`, `agent_identity` vs `agent_coordination`.
  Each pair is a candidate-merge conversation — deliberately not actioned here.

## Why this exists

The coordinator was meant to coordinate. It now also carries jobs, payments,
reputation, marketplace, governance, ZK, TEE, staking, trading, bounties,
portfolios, knowledge, multimodal RL, compliance, developer platform, and
ecosystem endpoints — every bounded context that is neither consensus nor
execution landed here. Any future consolidation should be a decided
decomposition project with this map as the starting inventory, not a
drive-by refactor.
