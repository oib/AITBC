"""The IPFS wrappers forward Kubo's output through the logging module.

Both of them used to `print()` a string they assembled themselves -- `[LEVEL]
[component] message`, the same shape `JournalFormatter` produces -- which read
correctly in the journal and reached no file at all. Everything a Kubo `ERROR` line
said was therefore outside `/var/log/aitbc`, and the level lived in the message text
where nothing could filter on it.

Routing it through a logger instead has to leave the journal line alone, or five
hosts' worth of `journalctl -u aitbc-island-ipfs` habits break for no gain. That is
what most of this file checks: the rendered console line, not the call arguments.

The one deliberate difference is `WARN` -> `WARNING`, asserted below rather than
left to be discovered: Kubo's level vocabulary is Go's, and Python's name is what
every other service on the fleet writes.

The parsing lives in `apps/ipfs/kubo_log.py` because two wrappers use it -- the
public daemon and the private-island one. This file tests that module, plus the one
thing a shared module cannot enforce: that each wrapper actually calls it instead of
printing again.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
from pathlib import Path

import pytest

from aitbc.aitbc_logging import JournalFormatter

APPS_IPFS = Path(__file__).resolve().parents[2] / "apps/ipfs"
MODULE = APPS_IPFS / "kubo_log.py"
WRAPPERS = ("ipfs-daemon.py", "island_ipfs_daemon.py")

# A real Kubo line, tab-separated, with a JSON attribute blob on the end.
KUBO_LINE = (
    '2026-09-14T19:00:00.123456789+02:00\tERROR\tbitswap/client\tclient/client.go:123\tfailed to fetch block\t{"cid": "Qm1"}'
)
KUBO_RENDERED = "[ERROR] [bitswap/client] client/client.go:123: failed to fetch block: cid='Qm1'"


@pytest.fixture(scope="module")
def kubo():
    """Load the shared parsing module by path.

    `apps/ipfs` is not a package and is not on `pythonpath`; the wrappers reach it
    because a script's own directory is `sys.path[0]`. Nothing here needs the log
    tree redirected the way importing a wrapper would -- this module configures no
    logging of its own, it only emits records.
    """
    spec = importlib.util.spec_from_file_location("kubo_log_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


@pytest.fixture
def journal(kubo):
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


def test_kubo_line_renders_exactly_as_it_did(kubo, journal) -> None:
    """The regression anchor: this string is what the old print() produced."""
    kubo.forward_line(KUBO_LINE)
    assert journal == [KUBO_RENDERED]


def test_logfmt_line_renders_exactly_as_it_did(kubo, journal) -> None:
    kubo.forward_line('level=info source=core/corehttp msg="listening" addr=/ip4/0.0.0.0/tcp/8081')
    assert journal == ["[INFO] [core/corehttp] core/corehttp: listening: addr='/ip4/0.0.0.0/tcp/8081'"]


def test_unparseable_line_keeps_the_ipfs_component(kubo, journal) -> None:
    """Kubo's own startup banner matches neither format and must still come through."""
    kubo.forward_line("Daemon is ready\n")
    assert journal == ["[INFO] [ipfs] Daemon is ready"]


def test_blank_line_emits_nothing(kubo, journal) -> None:
    kubo.forward_line("   \n")
    assert journal == []


def test_warn_is_translated_to_pythons_name(kubo, journal) -> None:
    """The one accepted change to the journal text: Go's `warn`, Python's `WARNING`."""
    kubo.forward_line('level=warn source=core/commands msg="slow query"')
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
def test_every_kubo_level_reaches_the_record(kubo, kubo_level: str, expected: int) -> None:
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
        kubo.forward_line(f'level={kubo_level} source=core/commands msg="x"')
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)

    assert [r.levelno for r in records] == [expected]


def test_a_debug_line_is_not_swallowed_by_the_root_level(kubo, journal) -> None:
    """configure_logging() leaves the root at INFO; print() had no level at all.

    Gating happens on the logger the call is made on, and the record then goes to
    every ancestor's handlers regardless of their levels -- so pinning DEBUG on the
    component logger is what keeps this line, which the old code forwarded.
    """
    assert logging.getLogger().level == logging.INFO
    kubo.forward_line('level=debug source=core/commands msg="dialing peer"')
    assert journal == ["[DEBUG] [core/commands] core/commands: dialing peer"]


def test_a_percent_in_kubo_output_is_not_a_format_string(kubo, journal) -> None:
    """Kubo's text is not ours. `%s` in it must not raise inside getMessage()."""
    kubo.forward_line("Progress: 50% done, retry %s of %d")
    assert journal == ["[INFO] [ipfs] Progress: 50% done, retry %s of %d"]


def test_unknown_level_falls_back_to_info_rather_than_vanishing(kubo, journal) -> None:
    """Kubo could grow a level this map has not heard of; the line still has to arrive."""
    kubo.forward_line('level=trace source=core/commands msg="x"')
    assert journal == ["[INFO] [core/commands] core/commands: x"]


@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_the_wrapper_forwards_instead_of_printing(wrapper: str) -> None:
    """A shared module is no use to a wrapper that goes back to print().

    Both of these are bare scripts, not importable modules -- one of them is not even
    a legal module name -- so this reads the source rather than the imported object.
    """
    path = APPS_IPFS / wrapper
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "print" not in called, f"{wrapper} prints Kubo output again; it would reach no log file"
    assert "forward_line" in called, f"{wrapper} no longer forwards through kubo_log"
