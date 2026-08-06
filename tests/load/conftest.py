"""Keep pytest out of the Locust files.

tests/load holds Locust scenarios, not pytest tests. Two of them are named test_*.py, so
`pytest tests/` tries to import them; importing a Locust file pulls in gevent's monkey
patching mid-collection and the run dies with "greenlet is being finalized" rather than
anything that points at the cause.

The names are not changed here because .github/workflows/load-tests.yml and
scripts/performance/run_load_tests.sh pass these exact paths to `locust -f`.

Run them with, e.g.:
    locust -f tests/load/test_coordinator_api.py --host http://localhost:8203
"""

collect_ignore_glob = ["*.py"]
