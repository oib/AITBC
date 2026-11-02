"""aitbc.testing.endpoint_probe: the URL parsing behind the requires_redis / requires_postgres skips (#825)."""

import socket
from contextlib import closing

import pytest

from aitbc.testing.endpoint_probe import tcp_reachable, url_host_port, url_reachable


@pytest.mark.parametrize(
    ("url", "default_port", "expected"),
    [
        ("postgresql://localhost:5432/aitbc", 5432, ("localhost", 5432)),
        ("postgresql://u:pw@db.example:6543/aitbc?sslmode=require", 5432, ("db.example", 6543)),
        ("postgresql+psycopg2://postgres@127.0.0.1:54329/mempool", 5432, ("127.0.0.1", 54329)),
        ("postgresql://db.example/aitbc", 5432, ("db.example", 5432)),
        ("postgresql:///aitbc", 5432, ("localhost", 5432)),
        ("redis://localhost:6379/0", 6379, ("localhost", 6379)),
        ("redis://localhost", 6379, ("localhost", 6379)),
        ("rediss://:secret@cache.example:6380/2?timeout=3", 6379, ("cache.example", 6380)),
        ("redis://[::1]:6380/0", 6379, ("::1", 6380)),
    ],
)
def test_host_and_port_come_out_whatever_follows_them(url, default_port, expected):
    assert url_host_port(url, default_port) == expected


@pytest.mark.parametrize("url", ["", "localhost:5432", "not a url", "postgresql://localhost:abc/aitbc"])
def test_a_string_that_names_no_endpoint_gives_none(url):
    assert url_host_port(url, 5432) is None


@pytest.fixture
def listener():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        yield sock.getsockname()[1]


def test_tcp_reachable_sees_a_listener_and_not_a_closed_port(listener):
    assert tcp_reachable("127.0.0.1", listener)
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]
    assert not tcp_reachable("127.0.0.1", free_port, timeout=0.5)


def test_a_url_with_a_database_path_reaches_the_probe(listener):
    """The #825 regression: the /db suffix used to end up in the port and read as 'down'."""
    assert url_reachable(f"postgresql://postgres@127.0.0.1:{listener}/aitbc", 5432)
    assert url_reachable(f"redis://127.0.0.1:{listener}/0?timeout=2", 6379)


def test_a_url_nobody_listens_at_is_unreachable_and_garbage_is_too():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]
    assert not url_reachable(f"postgresql://127.0.0.1:{free_port}/aitbc", 5432, timeout=0.5)
    assert not url_reachable("localhost:5432", 5432)
