"""Shared service gating for the production suites (TEST-04).

These suites talk to a running agent coordinator on localhost:9001. Each of the five
modules carried its own copy of a `_service_available` helper and a plain
`pytest.mark.skipif`, so when the service was not running -- which is the normal case in
CI -- every test skipped and the run reported success. A suite that silently skips reads
as a suite that passes.

Two changes make that visible:

* The gate is defined once here, so a change to the host, port or timeout applies to all
  five modules rather than four of them.
* Setting ``AITBC_REQUIRE_PRODUCTION_SERVICES=1`` turns the skip into a failure. CI that
  is meant to exercise these paths sets it and finds out when the service did not come
  up, instead of going green on an empty run.

A skipped run also prints a summary line at the end, so the absence of coverage is stated
rather than inferred from the skip count.
"""

from __future__ import annotations

import os
import socket

import pytest

COORDINATOR_HOST = os.environ.get("AITBC_COORDINATOR_HOST", "localhost")
COORDINATOR_PORT = int(os.environ.get("AITBC_COORDINATOR_PORT", "9001"))

#: When set to "1", a missing service fails the run instead of skipping it.
REQUIRE_SERVICES_ENV = "AITBC_REQUIRE_PRODUCTION_SERVICES"


def service_available(host: str = COORDINATOR_HOST, port: int = COORDINATOR_PORT) -> bool:
    """Whether something is listening on the coordinator's address."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def services_required() -> bool:
    return os.environ.get(REQUIRE_SERVICES_ENV) == "1"


def coordinator_gate() -> pytest.MarkDecorator:
    """The mark every production module applies at import time.

    Returns a skip mark when the service is absent and skipping is allowed, and a failing
    mark when the caller has declared the service mandatory.
    """
    if service_available():
        return pytest.mark.usefixtures()  # no-op mark; the service is up

    if services_required():
        return pytest.mark.fail_missing_service

    return pytest.mark.skip(
        reason=(
            f"Agent coordinator not reachable at {COORDINATOR_HOST}:{COORDINATOR_PORT}. "
            f"These tests cover nothing in this run. Set {REQUIRE_SERVICES_ENV}=1 to make "
            "this a failure instead of a skip."
        )
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "fail_missing_service: production test whose backing service was required but absent",
    )


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Turn the mandatory-service marker into a real failure.

    Not a skip and not an xfail -- the point of the env var is that the run should go red
    when a service the caller declared mandatory is missing.
    """
    if item.get_closest_marker("fail_missing_service") is None:
        return

    pytest.fail(
        f"{REQUIRE_SERVICES_ENV}=1 but the agent coordinator is not reachable at {COORDINATOR_HOST}:{COORDINATOR_PORT}.",
        pytrace=False,
    )


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """State plainly that these suites covered nothing, when they did not."""
    if service_available() or services_required():
        return

    terminalreporter.write_sep(
        "-",
        f"production suites skipped: no agent coordinator at "
        f"{COORDINATOR_HOST}:{COORDINATOR_PORT} (set {REQUIRE_SERVICES_ENV}=1 to fail instead)",
        yellow=True,
    )
