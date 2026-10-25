"""Disposable PostgreSQL cluster fixture tests (PG-TARGET-1 stream 3).

The fail-closed URL guard is tested unconditionally; the cluster tests are
marked ``requires_postgres`` and skip on hosts without server binaries.
"""

from __future__ import annotations

import pytest

from aitbc.testing.pg_cluster import assert_local_pg_url

pytest_plugins = ["aitbc.testing.pytest_pg"]


class TestLocalUrlGuard:
    """The fixture must refuse any non-local target — fail closed."""

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql://u:p@db.internal.example:5432/aitbc",
            "postgresql+asyncpg://u:p@10.0.0.5:5432/aitbc",
            "postgresql+psycopg2:///d?host=remote.example.com&port=5432",
            "postgresql://postgres@localhost:5432/db",
            "postgresql://postgres@127.0.0.1:5432/db",
            "postgresql://postgres@[::1]:5432/db",
            "postgresql+psycopg2://u:p@192.168.1.10/x",
            "mysql://u:p@localhost/db",
        ],
    )
    def test_refuses_non_local(self, url: str) -> None:
        with pytest.raises(ValueError, match="refus"):
            assert_local_pg_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql+psycopg2:///postgres?host=/var/tmp/sock&port=55432",
            "postgresql+asyncpg://postgres@/db?host=/tmp/s",
            "postgresql://%2Fvar%2Ftmp%2Fsock/db",
        ],
    )
    def test_accepts_local(self, url: str) -> None:
        assert_local_pg_url(url)


@pytest.mark.requires_postgres
class TestThrowawayCluster:
    def test_real_insert_and_read(self, postgres_cluster) -> None:
        """Prove the cluster runs real operations, not SELECT 1 theatre."""
        psycopg2 = pytest.importorskip("psycopg2")
        postgres_cluster.create_database("pgfix_probe")
        conn = psycopg2.connect(postgres_cluster.dsn("pgfix_probe", driver="postgresql"))
        try:
            with conn, conn.cursor() as cur:
                cur.execute("CREATE TABLE probe (id serial primary key, val text)")
                cur.execute("INSERT INTO probe (val) VALUES (%s)", ("stream3",))
                cur.execute("SELECT val FROM probe")
                assert cur.fetchone() == ("stream3",)
        finally:
            conn.close()

    def test_second_database_isolated(self, postgres_cluster) -> None:
        psycopg2 = pytest.importorskip("psycopg2")
        postgres_cluster.create_database("pgfix_a")
        postgres_cluster.create_database("pgfix_b")
        conn = psycopg2.connect(postgres_cluster.dsn("pgfix_b", driver="postgresql"))
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                assert cur.fetchone() == ("pgfix_b",)
        finally:
            conn.close()


def test_port_5432_refused():
    import pytest
    from aitbc.testing.pg_cluster import assert_local_pg_url

    with pytest.raises(ValueError):
        assert_local_pg_url("postgresql://postgres@127.0.0.1:5432/x")
    with pytest.raises(ValueError):
        assert_local_pg_url("postgresql://postgres@/x?host=/tmp&port=5432")


def test_assert_own_dsn(postgres_cluster):
    import pytest

    dsn = postgres_cluster.dsn("x")
    postgres_cluster.assert_own_dsn(dsn)
    with pytest.raises(ValueError):
        postgres_cluster.assert_own_dsn("postgresql://postgres@/x?host=/tmp&port=1")
    with pytest.raises(ValueError):
        postgres_cluster.assert_own_dsn(dsn.replace(f"port={postgres_cluster.port}", "port=59999"))


def test_assert_local_pg_url_refuses_implicit_5432():
    """NITS-B-1: a DSN without an explicit port implies 5432 — refused."""
    import pytest

    from aitbc.testing.pg_cluster import assert_local_pg_url

    with pytest.raises(ValueError, match="5432"):
        assert_local_pg_url("postgresql://u@localhost/db")
    assert_local_pg_url("postgresql://u@localhost:55433/db")
