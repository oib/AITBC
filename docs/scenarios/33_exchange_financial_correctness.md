# Exchange Financial Correctness

**Level**: Intermediate
**Prerequisites**: [Scenario 32 Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-19
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Exchange Financial Correctness

---

## See Also

- **Previous Scenario**: [Scenario 32 Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md)
- **Next Scenario**: [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
- **Release Notes**: [v0.10.3 Change Log](../releases/v0.10.3/change.log)
- **Feature Documentation**: [Exchange Architecture](../apps/exchange/exchange.md)

---

## Scenario Overview

This scenario verifies the exchange service's financial correctness on a live hub node. It covers the **B1** (order matching race condition), **B2** (Float → Decimal/TEXT migration), **B3** (database connection leak), and **B4** (predictable session tokens) fixes from v0.10.3.

> **v0.10.3 backport note**: The B1–B4 fixes were originally applied to `apps/exchange/exchange_api.py` (FastAPI + SQLAlchemy), but the running service is `apps/exchange/simple_exchange/server.py` (stdlib `http.server` + raw `sqlite3`). A backport was applied on 2026-07-05 to bring B1, B2, and B3 to the running `simple_exchange` implementation. B4 (session token predictability) does not apply — `simple_exchange` uses static API-key auth, not session tokens.

### Use Case

A hub operator needs to verify that customer-node trades on the exchange are financially correct: no float rounding drift, no double-matching under concurrency, no connection leaks, and no guessable auth tokens.

### What You'll Learn

- How to verify the running exchange uses TEXT (Decimal) columns, not REAL (float)
- How to test for float rounding drift (B2) in the live service
- How to test for order-matching race conditions (B1) under concurrent requests
- How to check for connection cleanup (B3) on exceptions
- How to verify the B4 fix applies to `exchange_api.py` (and why it doesn't apply to `simple_exchange`)

---

## Prerequisites

### Knowledge Required

- Understanding of floating-point vs fixed-point arithmetic for monetary values
- Familiarity with concurrent HTTP requests and race conditions
- Basic SQL and SQLite knowledge

### Tools Required

- `curl` (HTTP requests)
- `python3` (concurrent test scripts)
- `sqlite3` (database inspection)
- `journalctl` (log inspection)

### Setup Required

- A running AITBC hub node with `aitbc-exchange.service` active
- Access to `/opt/aitbc/apps/exchange/` source tree

---

## Step-by-Step Workflow

### Step 1: Identify Which Exchange Implementation Is Running

```bash
# Check the systemd unit's ExecStart
systemctl show aitbc-exchange -p ExecStart --value

# Check which port the exchange listens on
ss -ltnp | grep -E '8106|8205'
```

**Expected output (current default deployment):**

```
{ path=/opt/aitbc/venv/bin/python ; argv[]=/opt/aitbc/venv/bin/python -m apps.exchange.simple_exchange.server --port 8106 ... }
LISTEN 0  5  127.0.0.1:8106  0.0.0.0:*  users:(("python",pid=...,fd=3))
```

**Interpretation:**

- If `ExecStart` contains `simple_exchange.server` → the **simple_exchange** implementation is live. B1/B2/B3 backport fixes are active.
- If `ExecStart` contains `exchange_api.py` → the **FastAPI** implementation is live. B1–B4 fixes are active.

### Step 2: Verify B2 — Schema Uses TEXT (Decimal) Columns

```bash
# Check the source schema (post-backport)
grep -E "amount|price|total|filled|remaining" /opt/aitbc/apps/exchange/simple_exchange/db.py | grep -c "TEXT"
```

**Expected output (post-backport):**

```
9  (amount, price, total in trades + amount, price, total, filled, remaining in orders + price in both marketplace tables)
```

**Verify the live database after restart:**

```bash
# Find the exchange database
DB_PATH=$(find /opt/aitbc /var/lib/aitbc -name "exchange.db" 2>/dev/null | head -1)
sqlite3 "$DB_PATH" "PRAGMA table_info(orders);" | grep -E "amount|price|total|filled|remaining"
```

**Expected output (post-backport, after service restart triggers init_db migration):**

```
4|amount|TEXT|1||0
5|price|TEXT|1||0
6|total|TEXT|1||0
7|filled|TEXT|0|'0'|0
8|remaining|TEXT|1||0
```

> If columns still show `REAL`, restart the exchange service to trigger the automatic migration:
>
> ```bash
> systemctl restart aitbc-exchange
> ```

### Step 3: Test for Float Rounding Drift (B2)

```bash
# Place an order that would expose float imprecision (0.1 * 0.3)
curl -s -X POST http://localhost:8106/api/orders \
  -H "Content-Type: application/json" \
  -d '{"order_type":"BUY","amount":0.1,"price":0.3,"user_address":"0xtest33"}'

# Query the stored order back and verify exact decimal
curl -s http://localhost:8106/api/orders/orderbook | python3 -c "
import sys, json
from decimal import Decimal
book = json.load(sys.stdin)
for order in book.get('buys', []):
    amount = Decimal(str(order['amount']))
    price = Decimal(str(order['price']))
    stored_total = Decimal(str(order['total']))
    computed_total = amount * price
    print(f'amount={order[\"amount\"]} price={order[\"price\"]} stored_total={order[\"total\"]}')
    print(f'computed={computed_total} stored={stored_total}')
    if stored_total == computed_total:
        print('PASS: B2 — exact Decimal arithmetic, no float drift')
    else:
        print(f'FAIL: B2 — float drift detected: {stored_total} != {computed_total}')
    break
"
```

**Expected output (post-backport):**

```
amount=0.1 price=0.3 stored_total=0.03
computed=0.03 stored=0.03
PASS: B2 — exact Decimal arithmetic, no float drift
```

> **Before the backport**: `total` would be `0.030000000000000002` (float imprecision).

### Step 4: Test for Order-Matching Race Condition (B1)

```bash
# Place a SELL order that two concurrent BUY orders will try to match
curl -s -X POST http://localhost:8106/api/orders \
  -H "Content-Type: application/json" \
  -d '{"order_type":"SELL","amount":10,"price":1.0,"user_address":"0xseller33"}'

# Fire two concurrent BUY orders for the same 10 units
python3 -c "
import concurrent.futures, requests, json

def buy(units):
    r = requests.post('http://localhost:8106/api/orders',
        json={'order_type':'BUY','amount':units,'price':1.0,'user_address':'0xbuyer33'})
    return r.status_code, r.json()

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(buy, 10) for _ in range(2)]
    results = [f.result() for f in futures]

for i, (code, body) in enumerate(results):
    filled = body.get('filled', 'n/a')
    print(f'BUY #{i}: HTTP {code} filled={filled}')

# Check the SELL order's final state
book = requests.get('http://localhost:8106/api/orders/orderbook').json()
from decimal import Decimal
for s in book.get('sells', []):
    if s.get('user_address') == '0xseller33':
        filled = Decimal(str(s['filled']))
        print(f'SELL order: filled={s[\"filled\"]} remaining={s[\"remaining\"]} status={s[\"status\"]}')
        if filled > 10:
            print('FAIL: B1 — SELL order over-filled (double-matching race condition)')
        else:
            print('PASS: B1 — no over-fill (BEGIN IMMEDIATE transaction prevents double-matching)')
        break
"
```

**Expected output (post-backport):**

```
BUY #0: HTTP 200 filled=10
BUY #1: HTTP 200 filled=0
SELL order: filled=10 remaining=0 status=filled
PASS: B1 — no over-fill (BEGIN IMMEDIATE transaction prevents double-matching)
```

> **How it works**: The `BEGIN IMMEDIATE` transaction in `handle_place_order` acquires the SQLite write lock before reading open orders. The second BUY order waits for the first to commit, then finds the SELL order already filled.

### Step 5: Verify B3 — Connection Cleanup

```bash
# Check that all DB access methods use try/finally
grep -c "finally:" /opt/aitbc/apps/exchange/simple_exchange/handlers/exchange.py
grep -c "finally:" /opt/aitbc/apps/exchange/simple_exchange/handlers/marketplace.py
```

**Expected output (post-backport):**

```
5  (get_recent_trades, get_orderbook, handle_place_order, match_orders, _match_orders_in_txn wrapper)
8  (all marketplace handler methods)
```

**Verify no connection leaks under load:**

```bash
# Check open file descriptors before and after 100 requests
ls /proc/$(pgrep -f simple_exchange.server)/fd | wc -l
for i in $(seq 1 100); do
  curl -s http://localhost:8106/api/orders/orderbook > /dev/null
done
ls /proc/$(pgrep -f simple_exchange.server)/fd | wc -l
```

**Expected output:** The FD count should not increase significantly (connections are closed via `try/finally`).

### Step 6: Verify B4 — Session Token Predictability (exchange_api.py only)

```bash
# B4 only applies to exchange_api.py (FastAPI), not simple_exchange
# Verify the fix exists in the FastAPI code:
grep "secrets.token_urlsafe" /opt/aitbc/apps/exchange/exchange_api.py
```

**Expected output:**

```
token = secrets.token_urlsafe(32)
```

**Verify simple_exchange uses API-key auth (B4 N/A):**

```bash
grep "_require_api_key\|EXCHANGE_API_KEY" /opt/aitbc/apps/exchange/simple_exchange/handlers/base.py
```

**Expected output:**

```
def _require_api_key(self) -> bool:
    expected = os.getenv("EXCHANGE_API_KEY")
    ...
```

**Interpretation:** `simple_exchange` uses a static API key (`X-Api-Key` header), not session tokens. B4 doesn't apply. Ensure `EXCHANGE_API_KEY` is set in production:

```bash
grep EXCHANGE_API_KEY /etc/aitbc/aitbc-exchange.env 2>/dev/null || echo "WARNING: EXCHANGE_API_KEY not set — auth is DISABLED"
```

---

## Code Examples

### B2 Fix: TEXT Columns + Decimal Arithmetic (simple_exchange backport)

```python
# apps/exchange/simple_exchange/db.py — schema uses TEXT, not REAL
cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        ...
        amount TEXT NOT NULL,       -- was REAL, now Decimal-as-string
        price TEXT NOT NULL,        -- was REAL
        total TEXT NOT NULL,        -- was REAL
        filled TEXT DEFAULT '0',    -- was REAL DEFAULT 0
        remaining TEXT NOT NULL,    -- was REAL
        ...
    )
""")

# Automatic migration of existing REAL columns via table rebuild
def _migrate_real_to_text(conn, cursor, table_name, schema_sql, monetary_columns):
    cols = _get_column_types(cursor, table_name)
    if not any(cols.get(col) == "REAL" for col in monetary_columns):
        return False
    # Rename, create new, copy with CAST, drop old
    ...
```

```python
# apps/exchange/simple_exchange/handlers/exchange.py — Decimal arithmetic
from decimal import Decimal

def _to_decimal(value) -> Decimal:
    return Decimal(str(value))  # str() avoids float precision trap

amount_dec = _to_decimal(data.get("amount"))
price_dec = _to_decimal(data.get("price"))
total_dec = amount_dec * price_dec  # exact: 0.1 * 0.3 = 0.03
```

### B1 Fix: Single Transaction with BEGIN IMMEDIATE (simple_exchange backport)

```python
# apps/exchange/simple_exchange/handlers/exchange.py
conn = sqlite3.connect(get_db_path(), timeout=30)
try:
    conn.execute("BEGIN IMMEDIATE")  # acquire write lock before reading
    cursor = conn.cursor()
    # Insert the new order
    cursor.execute("INSERT INTO orders ...")
    # Match within the same transaction (holds the write lock)
    self._match_orders_in_txn(cursor, order)
    conn.commit()
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
```

### B3 Fix: try/finally for Connection Cleanup (simple_exchange backport)

```python
# Before (B3 bug): connection not closed on exception
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute(...)  # if this raises, conn leaks
conn.close()

# After (B3 fix): try/finally guarantees cleanup
conn = sqlite3.connect(get_db_path())
try:
    cursor = conn.cursor()
    cursor.execute(...)
finally:
    conn.close()
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Verify the running exchange uses TEXT (Decimal) columns, not REAL (float)
- Confirm that `0.1 * 0.3 = 0.03` exactly (no float drift)
- Verify concurrent orders don't double-match (BEGIN IMMEDIATE transaction)
- Confirm database connections are closed via try/finally
- Understand why B4 (session tokens) applies to `exchange_api.py` but not `simple_exchange`

---

## Validation

```bash
# 1. Confirm which service is running
systemctl show aitbc-exchange -p ExecStart --value | grep -o 'simple_exchange\|exchange_api'

# 2. Confirm schema uses TEXT (post-backport, after restart)
DB_PATH=$(find /opt/aitbc /var/lib/aitbc -name "exchange.db" 2>/dev/null | head -1)
sqlite3 "$DB_PATH" "PRAGMA table_info(orders);" | grep "amount" | grep -c "TEXT"
# Expected: 1 (amount column is TEXT)

# 3. Confirm Decimal arithmetic in source
grep -c "Decimal" /opt/aitbc/apps/exchange/simple_exchange/handlers/exchange.py
# Expected: 10+ (Decimal used throughout)

# 4. Confirm BEGIN IMMEDIATE in source
grep -c "BEGIN IMMEDIATE" /opt/aitbc/apps/exchange/simple_exchange/handlers/exchange.py
# Expected: 2 (handle_place_order + match_orders)

# 5. Confirm try/finally in source
grep -c "finally:" /opt/aitbc/apps/exchange/simple_exchange/handlers/exchange.py
# Expected: 5+

# 6. Run the test suite
cd /opt/aitbc && ./venv/bin/python -m pytest apps/exchange/tests/test_simple_exchange_b1_b2_b3.py -q -o addopts=""
# Expected: 14 passed
```

---

## Megaplan Status

This scenario has been refreshed to reflect the current codebase megaplan (hub `hub.aitbc` ↔ shop `aitbc3`).

- All examples use the current coordinator API path `/v1/jobs` and the authenticated coordinator (`Authorization: Bearer <JWT>`).
- The Agent SDK `ComputeConsumer` supports `auth_token` and `coordinator_url` in `create(...)`.
- The live two-node AI job flow has been validated end-to-end on the deployed hub and shop nodes.
- The megaplan test suite is green: **0 failures**, **9 skipped** live-deployment verification tests under `tests/verification/` (gated by `AITBC_ALLOW_PRODUCTION_WRITE_TESTS=1`), and **4 expected xfails** for removed BlockSearch/TransactionSearch model tests.


## Related Resources

- [v0.10.3 Change Log](../releases/v0.10.3/change.log) (includes backport section)
- [v0.10.3 AGENTS.md](../releases/v0.10.3/AGENTS.md) (includes backport details)
- [Next Scenario: Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)

---

*Last updated: 2026-08-20*
*Version: 1.2*
