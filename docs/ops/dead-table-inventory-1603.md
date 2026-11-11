# Dead / write-only / dormant table inventory (#1603)

Status: **analysis + prepared cleanup — nothing here has been executed against
any live database.** Dropping tables is a live-DB mutation and requires explicit
operator approval; the SQL at the bottom is a draft for review, not a migration.

Method: static trace of every `__tablename__` model against runtime SQL usage
(selects, inserts, updates) across `apps/*/src`, `packages/`, `cli/`,
`mcp-server/`, `scripts/` — excluding the defining file, `*/versions/`,
alembic and tests. Cross-checked on `main` @ `4601c4d280` (2026-11-11).
Caveat: misses dynamic SQL, non-Python references, raw sqlite access, and
cross-service DB sharing — every "dead" verdict below is **flag-don't-drop**
until a live-DB census confirms zero rows interest.

## Verdicts

### WRITE-ONLY (written, never read)

| table | DB | writer | reader | note |
|---|---|---|---|---|
| `trade_settlements` | trading (`aitbc_trading`) | `trading_service.create_settlement` + expiry sweep (`services/trading_service.py` ~380-505), reachable via `POST /v1/transactions` `action=settlement` | **none in trading src** | orphan pair — see below |

The coordinator-api service has a **same-named, different-DB**
`trade_settlements` table (`contexts/trading/domain/trading.py`) that is read at
`contexts/trading/routers/trading.py:~695` (analytics window query) but has **no
writer** — `TradeSettlement(` is never instantiated in coordinator src. So:
trading writes rows nobody reads; coordinator reads a table nobody writes. The
two sides are not connected. Resolution is a **design decision** (wire the
coordinator analytics reader to the trading DB, or accept the coordinator table
as canonical and drop the trading-side write path) — flagged on #1603, not
changed here.

### DEAD candidates — zero runtime SQL references

Models + migrations exist; nothing instantiates, selects, inserts or updates
them. Each needs the same live-DB + alembic/env/ops-script confirmation before
drop.

**Trading / market domain mirrors** (both `apps/trading` and
`apps/coordinator-api` carry near-identical domain files):

- `trade_feedback` — domain/`__init__` re-exports only
- `trading_analytics` — the `TradingAnalytics` model is never instantiated;
  remaining hits are function names (`_get_trading_analytics`) and string
  labels (`"trading_analytics"` as a data-source name in analytics.py)
- `global_marketplace_offers`, `global_marketplace_transactions` —
  `apps/market/.../domain/global_market.py` + coordinator mirror; no service,
  router or query refs
- Same-file siblings with the identical pattern:
  `global_marketplace_configs`, `global_marketplace_analytics`,
  `global_marketplace_governance`, `marketplace_regions`,
  `marketplace_bid` (shared pkg — domain mirrors only)

**coordinator-api `models/confidential.py`** — the confidential-transaction
feature was never wired: `confidential_transactions`, `participant_keys`,
`confidential_access_logs`, `key_rotation_logs`, `audit_authorizations`.

**coordinator-api reputation domain** — `trust_score_calculations`,
`agent_economic_profiles`, `reputation_level_thresholds` (+ near-dead
`reputation_metrics`, `cross_chain_reputation_events`).

**coordinator-api portfolio domain** — `rebalance_history`, `portfolio_alert`,
`strategy_signal`, `portfolio_snapshot`, `trading_rule`, `market_condition`
(+ near-dead `agent_portfolio`, `portfolio_asset`, `portfolio_trade`,
`risk_metrics`).

**coordinator-api cross_chain domain** — the whole bridge model cluster is
unwired: `supported_token`, `bridge_transaction`, `bridge_dispute`,
`bridge_statistics`, `bridge_alert`, `bridge_configuration`,
`bridge_snapshot`, `validator_reward`.

**coordinator-api misc** — `certification_requirements`,
`certification_audits`, `analytics_reports`, `data_collection_jobs`,
`user_preferences`, `tenant_users`, `tenant_api_keys`, `tenant_audit_logs`,
`tenant_metrics` (multitenant scaffold — only a b8 upgrade test refs them),
`dao_member`, `dao_proposal`, `treasury_allocation`, `agent_solutions`,
`innovation_labs`, `community_posts`, federated-learning cluster
(`federated_learning_session`, `training_participant`, `training_round`,
`local_model_update`), `agent_memory_node`, `user_sessions`,
`pricing_summary_view`, `market_heatmap_view`.

**blockchain-node** — `apps/blockchain-node/src/aitbc_chain/contracts/
persistent_spending_tracker.py` defines `spending_records`,
`spending_limits`, `guardian_authorizations` and is the **only file that
references the module** — the tracker was never imported into the chain apply
path, so all three tables are dead-on-arrival (verify no raw-SQL access before
flagging, per the original audit note — none found in `src/`).

### DORMANT — live code behind default-off flags (keep)

pool-hub `sla_metrics`, `sla_violations`, `reward_payouts` — referenced by
`sla_collector.py`, `miner_repository.py`, the blockchain client and CLI
dashboard; inactive by configuration, not dead.

### KEEP — verified live

`trade_negotiations` — real CRUD on both trading and coordinator sides.

## Recommended cleanup path (spec-gated, NOT executed)

1. **Operator/live-DB census first**: row counts + last-write timestamps per
   flagged table on each service DB (`aitbc_coordinator`, `aitbc_trading`,
   `aitbc_market`, chain DB). A table with recent writes is not dead.
2. **Dead candidates**: remove model classes + their alembic revisions *in the
   same change* once census confirms zero interest — dropping a table while a
   model still maps it breaks `alembic upgrade head` at service start
   (coordinator-api runs it in `ExecStartPre`).
3. **`trade_settlements` pair**: Director design decision required — wire the
   coordinator analytics reader to the trading DB, or drop the trading-side
   write path. Until decided, leave both tables alone.
4. **`trading.trade_settlements` write path** stays live meanwhile — it is the
   settlement audit trail even if nothing reads it yet.

## Prepared cleanup draft — DO NOT EXECUTE

For review only. This is **not** an alembic revision and must not be committed
under `*/versions/` — coordinator-api's `ExecStartPre` runs `alembic upgrade
head`, so a drop migration in the chain executes on the next deploy. Convert to
a proper revision only after the census + operator approval.

```sql
-- coordinator DB (aitbc_coordinator) — dead-candidate cluster
-- DROP TABLE IF EXISTS confidential_transactions, participant_keys,
--   confidential_access_logs, key_rotation_logs, audit_authorizations,
--   trust_score_calculations, agent_economic_profiles,
--   reputation_level_thresholds, rebalance_history, portfolio_alert,
--   strategy_signal, portfolio_snapshot, trading_rule, market_condition,
--   supported_token, bridge_transaction, bridge_dispute,
--   bridge_statistics, bridge_alert, bridge_configuration,
--   bridge_snapshot, validator_reward, certification_requirements,
--   certification_audits, analytics_reports, data_collection_jobs,
--   user_preferences, tenant_users, tenant_api_keys, tenant_audit_logs,
--   tenant_metrics, dao_member, dao_proposal, treasury_allocation,
--   agent_solutions, innovation_labs, community_posts,
--   federated_learning_session, training_participant, training_round,
--   local_model_update, agent_memory_node, user_sessions,
--   pricing_summary_view, market_heatmap_view,
--   trade_feedback, trading_analytics,
--   global_marketplace_offers, global_marketplace_transactions,
--   global_marketplace_configs, global_marketplace_analytics,
--   global_marketplace_governance, marketplace_regions, marketplace_bid;

-- trading DB (aitbc_trading) — dead-candidate mirrors
-- DROP TABLE IF EXISTS trade_feedback, trading_analytics,
--   global_marketplace_offers, global_marketplace_transactions,
--   global_marketplace_configs, global_marketplace_analytics,
--   global_marketplace_governance, marketplace_regions, marketplace_bid;
-- trade_settlements: HOLD pending the orphan-pair design decision.

-- market DB (aitbc_market) — global_marketplace_* mirror
-- DROP TABLE IF EXISTS global_marketplace_offers,
--   global_marketplace_transactions, global_marketplace_configs,
--   global_marketplace_analytics, global_marketplace_governance,
--   marketplace_regions, marketplace_bid;

-- chain DB — persistent_spending_tracker module (dead-on-arrival)
-- DROP TABLE IF EXISTS spending_records, spending_limits,
--   guardian_authorizations;
```

Census queries to run before any drop:

```sql
SELECT relname, n_live_tup, last_vacuum, last_autovacuum
FROM pg_stat_user_tables
WHERE relname IN ('trade_settlements','trade_feedback','trading_analytics',
  'global_marketplace_offers','spending_records','guardian_authorizations' /* ...full list... */);
```
