"""Pytest plugin: disposable local PostgreSQL cluster (PG-TARGET-1 stream 3).

Load from any suite's conftest with ``pytest_plugins = ["aitbc.testing.pytest_pg"]``.
Skips cleanly when the host has no PostgreSQL server binaries — the marker
``requires_postgres`` on a test plus this fixture is all a suite needs.

The cluster binds only a unix socket inside a temp dir (``listen_addresses=''``)
and every DSN goes through ``assert_local_pg_url`` — a non-local URL raises, so
the fixture can never point a test at a real database.
"""

from __future__ import annotations

import pytest

from aitbc.testing.pg_cluster import LocalPostgresCluster, assert_local_pg_url, find_postgres_bin

from collections.abc import Callable, Iterator


@pytest.fixture(scope="session")
def postgres_cluster() -> Iterator[LocalPostgresCluster]:
    """Session-scoped throwaway cluster on a local unix socket under /var/tmp.

    ``pg_ctl`` runs the backend as the invoking user (or the ``postgres``
    system user under root). The dir and its socket never overlap the system
    cluster's.
    """
    if find_postgres_bin() is None:
        pytest.skip("requires_postgres: no initdb/pg_ctl/postgres binaries on this host")
    cluster = LocalPostgresCluster(base_dir="/var/tmp")
    cluster.start()
    yield cluster
    cluster.stop()


@pytest.fixture()
def pg_url(postgres_cluster: LocalPostgresCluster) -> Callable[..., str]:
    """Factory fixture: a fresh database per call, returned as a psycopg2 DSN.

    Usage::

        def test_x(pg_url):
            dsn = pg_url("trading_test")   # postgresql+psycopg2://…?host=/sock&port=…
            dsn_async = pg_url("trading_test", driver="postgresql+asyncpg")
    """

    counter = {"n": 0}

    def _make(name: str, *, driver: str = "postgresql+psycopg2") -> str:
        counter["n"] += 1
        dbname = f"{name}_{counter['n']}"
        postgres_cluster.create_database(dbname)
        url = postgres_cluster.dsn(dbname, driver=driver)
        assert_local_pg_url(url)
        return url

    return _make
