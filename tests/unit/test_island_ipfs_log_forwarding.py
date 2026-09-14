"""The island IPFS wrapper forwards Kubo's output through the logging module.

It used to `print()` a string it assembled itself -- `[LEVEL] [component] message`,
the same shape `JournalFormatter` produces -- which read correctly in the journal
and reached no file at all. Everything a Kubo `ERROR` line said was therefore
outside `/var/log/aitbc`, and the level lived in the message text where nothing
could filter on it.

Routing it through a logger instead has to leave the journal line alone, or five
hosts' worth of `journalctl -u aitbc-island-ipfs` habits break for no gain. That is
what most of this file checks: the rendered console line, not the call arguments.

The one deliberate difference is `WARN` -> `WARNING`, asserted below rather than
left to be discovered: Kubo's level vocabulary is Go's, and Python's name is what
every other service on the fleet writes.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import tempfile
from pathlib import Path

import pytest

from aitbc.aitbc_logging import JournalFormatter

MODULE = Path(__file__).resolve().parents[2] / "apps/ipfs/island_ipfs_daemon.py"

# A real Kubo line, tab-separated, with a JSON attribute blob on the end.
KUBO_LINE = (
    '2026-09-14T19:00:00.123456789+02:00\tERROR\tbitswap/client\tclient/client.go:123\tfailed to fetch block\t{"cid": "Qm1"}'
)
KUBO_RENDERED = "[ERROR] [bitswap/client] client/client.go:123: failed to fetch block: cid='Qm1'"


@pytest.fixture(scope="module")
def daemon():
    """Import the wrapper with its log tree redirected and root logging restored.

    Importing it runs `configure_logging(..., to_file=True)` at module scope, which
    creates `<LOG_DIR>/island-ipfs` and replaces every handler on the root logger.
    Left alone that would mkdir into the real `/var/log/aitbc` -- as root, under a
    root `pytest` run -- and pull the root handlers out from under the rest of the
    suite. Redirect the one, put the other back.
    """
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as mp:
        mp.setenv("LOG_DIR", tmp)
        spec = importlib.util.spec_from_file_location("island_ipfs_daemon_under_test", MODULE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            yield module
        finally:
            for handler in root.handlers:
                if handler not in saved_handlers:
                    handler.close()
            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)
            sys.modules.pop(spec.name, None)


@pytest.fixture
def journal(daemon):
    """Capture what the console handler would print for each forwarded line."""
    lines: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(JournalFormatter().format(record))

    handler = _Capture()
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    # INFO is what configure_logging() leaves the root at, and the point of
    # pinning DEBUG on the component loggers is that it does not gate them.
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    try:
        yield lines
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


def test_kubo_line_renders_exactly_as_it_did(daemon, journal) -> None:
    """The regression anchor: this string is what the old print() produced."""
    daemon._forward_line(KUBO_LINE)
    assert journal == [KUBO_RENDERED]


def test_logfmt_line_renders_exactly_as_it_did(daemon, journal) -> None:
    daemon._forward_line('level=info source=core/corehttp msg="listening" addr=/ip4/0.0.0.0/tcp/8081')
    assert journal == ["[INFO] [core/corehttp] core/corehttp: listening: addr='/ip4/0.0.0.0/tcp/8081'"]


def test_unparseable_line_keeps_the_ipfs_component(daemon, journal) -> None:
    """Kubo's own startup banner matches neither format and must still come through."""
    daemon._forward_line("Daemon is ready\n")
    assert journal == ["[INFO] [ipfs] Daemon is ready"]


def test_blank_line_emits_nothing(daemon, journal) -> None:
    daemon._forward_line("   \n")
    assert journal == []


def test_warn_is_translated_to_pythons_name(daemon, journal) -> None:
    """The one accepted change to the journal text: Go's `warn`, Python's `WARNING`."""
    daemon._forward_line('level=warn source=core/commands msg="slow query"')
    assert journal == ["[WARNING] [core/commands] core/commands: slow query"]


@pytest.mark.parametrize(
    ("kubo_level", "expected"),
    [
        ("debug", logging.DEBUG),
        ("info", logging.INFO),
        ("warn", logging.WARNING),
        ("error", logging.ERROR),
        ("dpanic", logging.CRITICAL),
        ("panic", logging.CRITICAL),
        ("fatal", logging.CRITICAL),
    ],
)
def test_every_kubo_level_reaches_the_record(daemon, kubo_level: str, expected: int) -> None:
    """A level in the message text cannot be filtered on; one on the record can."""
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collect()
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    try:
        daemon._forward_line(f'level={kubo_level} source=core/commands msg="x"')
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)

    assert [r.levelno for r in records] == [expected]


def test_a_debug_line_is_not_swallowed_by_the_root_level(daemon, journal) -> None:
    """configure_logging() leaves the root at INFO; print() had no level at all.

    Gating happens on the logger the call is made on, and the record then goes to
    every ancestor's handlers regardless of their levels -- so pinning DEBUG on the
    component logger is what keeps this line, which the old code forwarded.
    """
    assert logging.getLogger().level == logging.INFO
    daemon._forward_line('level=debug source=core/commands msg="dialing peer"')
    assert journal == ["[DEBUG] [core/commands] core/commands: dialing peer"]


def test_a_percent_in_kubo_output_is_not_a_format_string(daemon, journal) -> None:
    """Kubo's text is not ours. `%s` in it must not raise inside getMessage()."""
    daemon._forward_line("Progress: 50% done, retry %s of %d")
    assert journal == ["[INFO] [ipfs] Progress: 50% done, retry %s of %d"]


def test_unknown_level_falls_back_to_info_rather_than_vanishing(daemon, journal) -> None:
    """Kubo could grow a level this map has not heard of; the line still has to arrive."""
    daemon._forward_line('level=trace source=core/commands msg="x"')
    assert journal == ["[INFO] [core/commands] core/commands: x"]
