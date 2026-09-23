# Pricing, energy and exchange runbook

How the €0.25 AIT reference flows through shop energy profiles, the coordinator
DB, the exchange services and the public website — and which knobs an agent may
safely turn on live nodes.

## The value model

- **1 AIT ≈ 1 compute-hour** on the reference rig (RTX 4060 Ti 16GB, whole-node
  draw). Anchor is **EUR**: `AIT_REFERENCE_PRICE_EUR = Decimal("0.25")` in
  `aitbc/oracles/price_oracle.py`.
- USD and ETH prices are *derived* (`eth_usd`/`eth_eur` from the shared
  `PriceOracle`, Chainlink → CoinGecko with cache). AIT/USD and AIT/ETH move
  with ETH; AIT/EUR does not.
- Reference-consistent rate: **4.0 AIT/EUR**. Inverse on the exchange page:
  `1 ETH ≈ eth_eur / 0.25` AIT.
- Env overrides still win: `AIT_EUR_FIXED_PRICE` / `AIT_USD_FIXED_PRICE` /
  `AIT_USD_PRICE`. A shop node with `AIT_USD_PRICE=1.0` set diverges from the
  reference on purpose or by accident — check before assuming a bug.

## Two energy-pricing rails — check which is live

| rail | switched on by | state read from | contract |
|---|---|---|---|
| **native** | `NATIVE_ENERGY_PRICING=true` | `native_energy_profiles` / `native_energy_rates` tables in coordinator DB | none (DB only) |
| **evm** | default when unset | on-chain `IEnergyPricing` profiles | `registerEnergyProfile` is `onlyOwner` |

On the hub, `NATIVE_ENERGY_PRICING=true` is set in the coordinator environment,
so **live quotes read the DB, not the contract**. The Sepolia contract profiles
are stale/inert unless the flag is switched off. Quote JSON carries
`tbp_watts` (whole-card board power, *not* chip TDP — renamed in ecf8f2c2da).

## Shop pricing workflow

```bash
aitbc energy suggest --region de          # probe hw → watts, tariff, floor, suggested price
aitbc gpu update <id> --pricing <ait/h>   # set the market listing price
```

Rail selection is automatic: when `EVM_RPC_URL` +
`ENERGY_PRICING_CONTRACT_ADDRESS` are configured the CLI uses the EVM contract;
otherwise `energy floor`, `provider register`/`profile`/`rate` and
`suggest --register` talk to the coordinator's `/v1/market/native-energy/*`
endpoints (public GETs for reads, `X-Api-Key` miner auth for writes and the
rate read).

**Coordinator selection**: native pricing state lives on the hub coordinator
DB. Shop/follower nodes run a local coordinator replica that may be EVM-railed
or lack the native tables — every native CLI call therefore tries the
configured coordinator first, then falls back to the hub mount resolved by
`hub_coordinator_url()` (`HUB_COORDINATOR_URL`/`COORDINATOR_API_URL` env, else
`https://<hub>/c/v1` from discovery config). A local 404/500 on a native
endpoint means "not provisioned here", not failure.

**Miner credential**: the coordinator's `MinerDep` accepts a `role: "miner"`
JWT or an `X-Api-Key` present in `MINER_API_KEYS`/`miner_api_keys`. Wallet
login only mints `client`/`admin` roles, so in practice the working credential
is a miner API key. The CLI resolves it as `--api-key` > stored `miner`
credential (`aitbc auth login --credential-name miner`) > `api_key` from
config — which auto-loads the first `MINER_API_KEYS` entry from
`/etc/aitbc/aitbc-coordinator-api.env`. The operator fleet shares one miner
key, so node env files already satisfy hub auth; a stored *client* credential
is deliberately skipped (a client-role JWT can never pass miner auth and would
suppress the key).

`energy suggest` precedence: `--tbp-watts` > nvidia-smi `power.limit` > GPU
catalog. Tariff: `--eur-per-kwh` > `ENERGY_EUR_PER_KWH` > `--region`/
`SHOP_REGION` table. Rate: `--ait-per-eur` > published rate > 4.0 reference.

**Whole-node watts**: the floor formula multiplies `watts × gpu_count`, so
`register_watts` from `suggest` is *per-GPU-equivalent* (GPU TBP + platform
overhead split across GPUs). Don't register raw wall draw on multi-GPU nodes.

## Hub coordinator DB (live pricing state)

File: `/var/lib/aitbc/data/coordinator.db` (not `coordinator_api.db` — the
profiles table is *not* in the latter, and alembic does not manage it).

```sql
-- tables
native_energy_profiles(resource_id, provider, model_id, tbp_watts, eur_per_kwh_scaled, enabled, revision, ...)
native_energy_rates(ait_per_eur_scaled, version, updated_at, ...)
-- both *_scaled columns are fixed-point ×10^18:
--   €0.30/kWh = 300000000000000000,  4.0 AIT/EUR = 4000000000000000000
-- (gpu_count is a quote parameter, not a profile column)
```

Reads: `GET .../native-energy/profile/{resource_id}` and
`GET .../native-energy/floor?resource_id&gpu_count&duration_seconds` are public
(no auth); `GET .../native-energy/rate` shares its path with the MINER POST so
it needs miner auth too. The floor endpoint returns `net_floor_units` +
`net_floor_ait` directly. On a coordinator without the native tables all three
return 404 (not 500) — let the CLI fall back to the hub rather than debugging
the local DB.

**Prefer the API** — write endpoints take the miner `X-Api-Key`
(`MinerDep`) and bump `revision`/`version` server-side (quote signatures embed
them):

```bash
# update watts/tariff on a profile (upsert)
curl -X POST http://127.0.0.1:8203/v1/market/native-energy/profile \
  -H "X-Api-Key: <miner-key>" -H "Content-Type: application/json" \
  -d '{"resource_id":"node2-rtx4060ti","tbp_watts":384,"eur_per_kwh":0.30}'

# republish the global AIT/EUR rate
curl -X POST http://127.0.0.1:8203/v1/market/native-energy/rate \
  -H "X-Api-Key: <miner-key>" -H "Content-Type: application/json" \
  -d '{"ait_per_eur":4.0}'
```

Direct SQL works too (backup first, bump `revision` yourself, and write scaled
values — `tbp_watts` is plain watts but `eur_per_kwh_scaled` is ×10^18):

```bash
cp /var/lib/aitbc/data/coordinator.db /tmp/coordinator.db.pre-<change>
sqlite3 /var/lib/aitbc/data/coordinator.db <<'SQL'
UPDATE native_energy_profiles
SET tbp_watts = 384, eur_per_kwh_scaled = 300000000000000000, revision = revision + 1
WHERE resource_id = 'node2-rtx4060ti';
SQL
```

Verify through
the coordinator's own oracle code, not just sqlite:

```bash
cd /opt/aitbc && PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/coordinator-api/src \
  venv/bin/python - <<'PY'
from sqlmodel import Session, create_engine
from coordinator_api.contexts.market.services.native_energy import NativeEnergyOracle
eng = create_engine("sqlite:////var/lib/aitbc/data/coordinator.db")
with Session(eng) as s:
    o = NativeEnergyOracle(s)
    rate = o.get_rate()
    units = o.get_energy_floor("node2-rtx4060ti", 1, 3600, 36_000_000)
    print("rate:", rate.ait_per_eur_scaled, "| floor/h:", units / 36_000_000, "AIT")
PY
```

`36_000_000` is `NATIVE_UNITS_PER_AIT` (atomic units per AIT, see
`aitbc/market/energy_pricing.py`); divide floor units by it for AIT.

Sanity: `floor_ait_h ≈ watts/1000 × eur_per_kwh × ait_per_eur`. At the €0.25
reference the floor in AIT equals the node's EUR electricity cost ÷ 0.25.

## Exchange services and the price surfaces

Two services publish prices — do not confuse them:

| port | unit | serves | `price.json`? |
|---|---|---|---|
| 8106 | `aitbc-exchange` | order book, `/exchange/price.json`, bridge tx endpoints | **yes — nginx routes the public `/exchange/price.json` here** |
| 8108 | `aitbc-wallet` | `/exchange/*` UI pages, `/v1/exchange/price`, `/v1/exchange/history`, `/v1/bridge/*` | yes internally (bridge price) |

Nginx splits `/exchange/`: `price.json` → 8106, everything else → 8108. The
exchange service needs `AIT_EUR_FIXED_PRICE` (in `/etc/aitbc/blockchain.env`,
"Exchange Configuration" section) or it cannot produce an AIT price; the
wallet resolves the €0.25 reference in code with no env required.

`PriceOracle` (shared) caches ETH prices 60s in memory + 1h on disk — it rides
out CoinGecko 429s; repeated `/v1/exchange/price` 503s mean the cache is empty,
not that the endpoint is down.

## Public website

`/opt/aitbc/website` is served as static files by nginx on the hub — edits are
live after `git pull`, no restart. `exchange.js` hard-codes `REF_EUR = 0.25`
and derives everything else from `/v1/exchange/history`; keep the literal in
sync with `AIT_REFERENCE_PRICE_EUR` if the reference ever moves.

## Common mistakes

- Editing `coordinator_api.db` — profiles live in `coordinator.db`.
- Forgetting `revision`/`version` bumps — silently invalidates quote matching.
- Reading `/exchange/price.json` to debug the wallet bridge — nginx sends it to
  8106; the wallet's price is under `/v1/exchange/*`.
- `AIT_USD_PRICE` left set on a shop — a flat USD anchor that overrides the
  compute reference.
- Forcing the EVM rail on a native fleet — the CLI now auto-selects native when
  EVM vars are unset; only set `EVM_RPC_URL`/`ENERGY_PRICING_CONTRACT_ADDRESS`
  on nodes that actually use the contract.
