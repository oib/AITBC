"""Kubo output parsing shared by the two IPFS wrapper scripts in this directory.

`ipfs-daemon.py` and `island_ipfs_daemon.py` both run `ipfs daemon` as a child and
re-emit its output in AITBC's journal style. They each carried their own copy of the
parsing, which was tolerable while both merely `print()`ed the result. It stopped
being tolerable once the result had to reach the rotating log file too, because
three details below are each a silent bug when got wrong -- a dropped line or a
doubled prefix, never a crash -- and a second copy is a second place to get them
wrong.

Kubo's two line formats, for reference:

    2026-08-23T20:03:22.013+0200<TAB>WARN<TAB>dht/RtRefreshManager<TAB>rt.go:233<TAB>msg<TAB>{"k": "v"}
    time=... level=INFO source=core/corehttp msg="listening" addr=...   (logfmt)
"""

from __future__ import annotations

import json
import logging
import re

# 2026-08-23T20:03:22.013+0200  WARN  dht/RtRefreshManager  rtrefresh/rt_refresh_manager.go:233  failed  {"error": "..."}
KUBO_LOG_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:?\d{2})\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<component>\S+)\s+"
    r"(?P<caller>\S+)\s+"
    r"(?P<message>.*?)\s*"
    r"(?P<attrs>\{.*\})?\s*$"
)

LOGFMT_RE = re.compile(r'([\w-]+)=("(?:\\.|[^"\\])*"|[^\s]+)')

# Kubo's level vocabulary is Go's, not Python's: `warn` rather than `warning`, and
# three separate panic levels. Translating it is what lets the rotating JSON file
# record a real level per line instead of one baked into the message text.
KUBO_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "DPANIC": logging.CRITICAL,
    "PANIC": logging.CRITICAL,
    "FATAL": logging.CRITICAL,
}

_component_loggers: dict[str, logging.Logger] = {}


def _component_logger(component: str) -> logging.Logger:
    """Return a logger named after the Kubo subsystem that emitted the line.

    `JournalFormatter` renders `[levelname] [logger name] message`, which is the
    shape these wrappers used to assemble by hand, so naming the logger after the
    component leaves the journal line they produce as it was.

    The level is pinned on the logger instead of being left to the root, which
    `configure_logging` sets to INFO. Python gates on the logger the call is made
    on and then hands the record to every ancestor's handlers regardless of their
    levels -- without this, a Kubo debug line the old `print()` forwarded would be
    dropped.
    """
    component_logger = _component_loggers.get(component)
    if component_logger is None:
        component_logger = logging.getLogger(component)
        component_logger.setLevel(logging.DEBUG)
        _component_loggers[component] = component_logger
    return component_logger


def _component_from_source(source: str) -> str:
    """Derive a short component name from a go source path.

    Examples:
        github.com/libp2p/go-libp2p@v0.49.0/p2p/net/swarm/swarm_dial.go:614 -> swarm/swarm_dial
        provider/provider.go:1864 -> provider/provider
    """
    parts = source.split("/")
    if len(parts) > 1 and "@" in parts[1]:
        parts[1] = parts[1].split("@")[0]
    if len(parts) >= 2:
        comp = "/".join(parts[-2:])
    else:
        comp = source
    return re.sub(r"\.go:\d+$", "", comp)


def _parse_logfmt(line: str) -> dict[str, str] | None:
    pairs: dict[str, str] = {}
    for key, value in LOGFMT_RE.findall(line):
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        pairs[key] = value
    if not pairs or "level" not in pairs or "msg" not in pairs:
        return None
    return pairs


def parse_line(line: str) -> tuple[str, str, str] | None:
    """Split one line of Kubo output into (level, component, message).

    Returns None for a line with nothing on it. This used to return the assembled
    `[LEVEL] [component] message` string for `print()`; the three parts are kept
    apart now so the level can reach the log record rather than only its text.
    """
    line = line.rstrip()
    if not line:
        return None

    match = KUBO_LOG_RE.match(line)
    if match:
        level = match.group("level").upper()
        component = match.group("component")
        caller = match.group("caller")
        message = match.group("message").rstrip()
        attrs = match.group("attrs")

        if attrs:
            try:
                data = json.loads(attrs)
                extra = ", ".join(f"{k}={v!r}" for k, v in data.items())
                message = f"{message}: {extra}"
            except Exception:
                message = f"{message} {attrs}"

        if caller:
            message = f"{caller}: {message}"

        return level, component, message

    logfmt = _parse_logfmt(line)
    if logfmt:
        level = logfmt.pop("level", "INFO").upper()
        source = logfmt.pop("source", "")
        message = logfmt.pop("msg", "")
        logfmt.pop("time", None)
        component = _component_from_source(source) if source else "ipfs"
        extras = ", ".join(f"{k}={v!r}" for k, v in logfmt.items())
        if extras:
            message = f"{message}: {extras}"
        if source:
            message = f"{source}: {message}"
        return level, component, message

    # Startup banners and anything else Kubo writes in neither format.
    return "INFO", "ipfs", line


def forward_line(line: str) -> None:
    """Hand one line of Kubo output to the logging module."""
    parsed = parse_line(line)
    if parsed is None:
        return
    level, component, message = parsed
    # "%s" rather than the message itself as the format string: this is another
    # process's output, and a literal % in it would otherwise raise inside
    # LogRecord.getMessage() -- at which point the line is lost, not just mangled.
    _component_logger(component).log(KUBO_LEVELS.get(level, logging.INFO), "%s", message)
