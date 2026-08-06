# AITBC Test Status

> **This file no longer records pass/fail counts.**
>
> It previously claimed **"100% COMPLETED (v0.3.0 - April 2, 2026)"** and listed the JWT,
> monitoring, type-safety and advanced-features production suites as "PASSED 100%". Those
> suites are gated on `skipif(not _service_available())` against a live service on
> `localhost:9001`, so in any normal run they are skipped, not passed — and the version it
> referenced was many releases behind. A hand-maintained summary drifts the moment someone
> forgets to update it, and a stale one is worse than none, because it gets read as
> evidence (TEST-02).

## Getting the actual status

Run the suites:

```bash
# Cross-cutting suites
./venv/bin/python -m pytest tests/unit -q
./venv/bin/python -m pytest tests/integration -q
./venv/bin/python -m pytest tests/cli -q

# Per-app suites (own package, own src on PYTHONPATH)
cd apps/<service> && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

Coverage:

```bash
./venv/bin/python -m pytest tests/unit --cov=aitbc --cov-report=term-missing
```

## Reading the result honestly

- **Skipped is not passed.** Several suites skip when a dependency is absent — a live
  coordinator on `localhost:9001`, `POOLHUB_TEST_POSTGRES_DSN`, a Redis instance. A run
  reporting "0 failed" may have executed very little.
- **Check the skip count**, not just the failure count. `-rs` lists skip reasons.
- **Compare against a clean checkout** before attributing a failure to your change; some
  failures predate it.

## Known environment-gated suites

| Suite | Requires |
|---|---|
| `tests/production/*` | Agent coordinator on `localhost:9001` |
| `apps/pool-hub` DB tests | `POOLHUB_TEST_POSTGRES_DSN` |
| `tests/cli/test_simulate_integration.py`, `test_workflow.py` | coordinator-api on `127.0.0.1:18000` |
