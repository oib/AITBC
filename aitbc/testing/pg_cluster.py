"""Disposable local PostgreSQL cluster for tests (PG-TARGET-1 stream 3).

Docker/podman are absent on the dev nodes, so the testcontainers fixture in
``tests/conftest_testcontainers.py`` can never run there. The PostgreSQL
server package *is* installed (``/usr/lib/postgresql/<ver>/bin``), so this
module spawns a throwaway cluster directly: ``initdb`` into a temp dir, a
``postgres`` backend bound to a unix socket in that dir with TCP listening
disabled (``listen_addresses=''``), torn down and deleted on exit. The real
``aitbc_*`` clusters are never touched — the fixture cannot reach them
because nothing listens on their socket or port from this cluster and every
DSN it hands out goes through :func:`assert_local_pg_url`, which refuses any
non-local target.

The cluster runs as the invoking user, or as the ``postgres`` system user
when tests run as root (``initdb`` refuses root). No systemd, no root-owned
resources, no changes to the running service.
"""

from __future__ import annotations

import os
import pwd
import shlex
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from aitbc.database.target import redacted_url

__all__ = [
    "LocalPostgresCluster",
    "PostgresUnavailableError",
    "assert_local_pg_url",
    "find_postgres_bin",
]


class PostgresUnavailableError(RuntimeError):
    """Raised when no usable initdb/pg_ctl/postgres binaries exist."""


_LOCAL_HOSTNAMES = {"", "localhost", "127.0.0.1", "::1"}


def find_postgres_bin() -> Path | None:
    """Locate a directory holding ``initdb``, ``pg_ctl``, ``postgres``, ``psql``.

    Checks ``PATH`` first, then Debian's versioned layout
    (``/usr/lib/postgresql/<ver>/bin``, newest first). Returns ``None`` when
    no complete set exists — callers should skip, not fail.
    """
    candidates: list[Path] = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            candidates.append(Path(entry))
    pg_root = Path("/usr/lib/postgresql")
    if pg_root.is_dir():
        for version_dir in sorted(pg_root.iterdir(), reverse=True):
            candidates.append(version_dir / "bin")
    for candidate in candidates:
        if all((candidate / name).is_file() for name in ("initdb", "pg_ctl", "postgres", "psql")):
            return candidate
    return None


def _hostname_is_local(host: str) -> bool:
    """A percent-encoded socket dir (``%2Fvar%2Ftmp…``) decodes to an absolute
    path, which is a unix socket — local. Loopback names/IPs are local."""
    decoded = unquote(host)
    return decoded.startswith("/") or decoded in _LOCAL_HOSTNAMES


def assert_local_pg_url(url: str) -> None:
    """Fail closed unless *url* targets a unix socket or loopback only.

    The disposable cluster must never be pointed at a real database, and no
    test DSN may dial out: any host that is not empty, a socket path,
    ``localhost``, ``127.0.0.1`` or ``::1`` — in the netloc or in a ``host=``
    query parameter (the psycopg2/asyncpg socket form) — raises ValueError.
    The message carries only :func:`redacted_url` output.
    """
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise ValueError("unparseable database URL — refusing a non-local target") from exc
    if parts.scheme and not parts.scheme.startswith("postgresql") and not parts.scheme.startswith("postgres"):
        raise ValueError(f"non-PostgreSQL database URL refused for the disposable cluster: {redacted_url(url)}")
    if parts.hostname and not _hostname_is_local(parts.hostname):
        raise ValueError(f"non-local database URL refused for the disposable cluster: {redacted_url(url)}")
    port = parts.port or dict(parse_qsl(parts.query)).get("port")
    if port is not None and int(port) == 5432:
        raise ValueError(
            f"default PostgreSQL port 5432 refused for the disposable cluster — that is the system port: {redacted_url(url)}"
        )
    for key, value in parse_qsl(parts.query):
        if key == "host" and not _hostname_is_local(value):
            raise ValueError(f"non-local database URL refused for the disposable cluster: {redacted_url(url)}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LocalPostgresCluster:
    """A throwaway cluster living entirely inside one temp directory.

    Socket-only (``listen_addresses=''``): nothing can reach it over TCP and
    it cannot be mistaken for the system cluster. ``start()`` runs ``initdb``
    and ``pg_ctl start``; ``stop()``/context-manager exit shuts the backend
    down and deletes the directory.
    """

    def __init__(self, bin_dir: Path | None = None, *, base_dir: str | Path | None = None) -> None:
        self.bin_dir = bin_dir or find_postgres_bin()
        if self.bin_dir is None:
            raise PostgresUnavailableError("no initdb/pg_ctl/postgres/psql binaries found")
        self.base_dir = base_dir or "/var/tmp"  # nosec B108 — test fixture scratch root per operator prompt
        self._dir: Path | None = None
        self.port: int | None = None

    # -- internals -------------------------------------------------------

    def _tool(self, name: str) -> str:
        return str(self.bin_dir / name)  # type: ignore[operator]

    def _run_as_cluster_user(self, argv: list[str]) -> list[str]:
        """initdb/postgres refuse to run as root: re-exec as ``postgres``.

        Returns argv prefixed with a privilege-drop wrapper when needed. The
        postgres system user always exists when the server package is
        installed (it owns the system cluster); ``nobody`` is the fallback.
        """
        if os.geteuid() != 0:
            return argv
        for user in ("postgres", "nobody"):
            try:
                pwd.getpwnam(user)
            except KeyError:
                continue
            runuser = shutil.which("runuser")
            if runuser:
                return [runuser, "-u", user, "--", *argv]
            su = shutil.which("su")
            if su:
                return [su, "-s", "/bin/sh", user, "-c", shlex.join(argv)]
        raise PostgresUnavailableError("running as root but neither postgres/nobody user nor runuser/su exists")

    def _exec(self, argv: list[str], **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(
            self._run_as_cluster_user(argv),
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            **kwargs,
        )

    # -- lifecycle -------------------------------------------------------

    def start(self) -> LocalPostgresCluster:
        if self._dir is not None:
            return self
        self._dir = Path(tempfile.mkdtemp(prefix="aitbc-pg-test-", dir=str(self.base_dir)))
        if os.geteuid() == 0:
            # The cluster user must own the dir for the socket, logs and data.
            uid = pwd.getpwnam("postgres").pw_uid if "postgres" in {p.pw_name for p in pwd.getpwall()} else 65534
            os.chown(self._dir, uid, -1)
        data = self._dir / "data"
        self.port = _free_port()
        self._exec(
            [
                self._tool("initdb"),
                "-D",
                str(data),
                "-A",
                "trust",
                "-U",
                "postgres",
                "-E",
                "UTF8",
                "--no-sync",
                "--no-instructions",
            ]
        )
        # Socket-only: no TCP listener at all, so there is no way to collide
        # with the system cluster's port or be reached off this dir.
        self._exec(
            [
                self._tool("pg_ctl"),
                "-D",
                str(data),
                "-w",
                "-t",
                "30",
                "-l",
                str(self._dir / "postgres.log"),
                "-o",
                f"-k {self._dir} -p {self.port} -c listen_addresses='' -c fsync=off",
                "start",
            ]
        )
        return self

    @property
    def socket_dir(self) -> Path:
        if self._dir is None:
            raise RuntimeError("cluster not started")
        return self._dir

    def dsn(self, database: str = "postgres", *, driver: str = "postgresql+psycopg2") -> str:
        """A local-socket DSN — the only form this fixture will ever emit.

        ``driver`` is a SQLAlchemy dialect+driver prefix (``postgresql+asyncpg``
        works too). Both psycopg2 and asyncpg read the ``host`` query param as
        a socket directory when it starts with ``/``.
        """
        if self.port is None:
            raise RuntimeError("cluster not started")
        url = f"{driver}://postgres@/{database}?host={self.socket_dir}&port={self.port}"
        self.assert_own_dsn(url)
        return url

    def assert_own_dsn(self, url: str) -> None:
        """Fail unless *url* is one this cluster emitted (same socket dir + port).

        A test that accidentally points at the system cluster or any other
        DSN raises here — belt on top of :func:`assert_local_pg_url`.
        """
        assert_local_pg_url(url)
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        if query.get("host") != str(self.socket_dir) or query.get("port") != str(self.port):
            raise ValueError(f"DSN does not match this disposable cluster: {redacted_url(url)}")

    def psql(self, sql: str, *, database: str = "postgres") -> str:
        """Run one statement via the same bin dir's psql; returns stdout."""
        if self.port is None:
            raise RuntimeError("cluster not started")
        result: subprocess.CompletedProcess[str] = self._exec(
            [
                self._tool("psql"),
                "-h",
                str(self.socket_dir),
                "-p",
                str(self.port),
                "-U",
                "postgres",
                "-d",
                database,
                "-v",
                "ON_ERROR_STOP=1",
                "-At",
                "-c",
                sql,
            ]
        )
        return result.stdout.strip()

    def create_database(self, name: str) -> str:
        """CREATE DATABASE on the throwaway cluster; returns its psycopg2 DSN."""
        if not name.replace("_", "").isalnum() or name.startswith("aitbc"):
            raise ValueError(f"refusing suspicious test database name: {name!r}")
        self.psql(f'CREATE DATABASE "{name}"')
        return self.dsn(name)

    def stop(self) -> None:
        if self._dir is None:
            return
        data = self._dir / "data"
        try:
            self._exec([self._tool("pg_ctl"), "-D", str(data), "stop", "-m", "fast", "-w"])
        except (subprocess.CalledProcessError, PostgresUnavailableError):
            pass  # already down — still remove the dir
        shutil.rmtree(self._dir, ignore_errors=True)
        self._dir = None
        self.port = None

    def __enter__(self) -> LocalPostgresCluster:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
