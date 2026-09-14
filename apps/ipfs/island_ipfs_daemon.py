#!/usr/bin/env python3
"""Private island IPFS daemon wrapper.

Runs a Kubo IPFS node that is member of a private swarm (using a swarm.key).
Only peers that share the same swarm key can connect, so the island's IPFS
storage is gated to paying members that received the key from the coordinator.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

# systemd runs this as a bare script with no PYTHONPATH, and `aitbc` is not
# installed into the venv, so the repo root has to go on the path before the
# import below. Derived from __file__ rather than hardcoded, so a checkout
# somewhere other than the deployment path still works.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402

configure_logging(level="INFO", service_name="island-ipfs", to_file=True)
logger = get_logger(__name__)


# Kubo log parsing. The two regexes below are shared with apps/ipfs/ipfs-daemon.py;
# what that script does with them is not -- it still prints, while this one hands
# the parts to the logging module so the rotating file gets them too.
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
    shape this wrapper used to assemble by hand, so naming the logger after the
    component leaves the journal line it produces as it was.

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


def _parse_line(line: str) -> tuple[str, str, str] | None:
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

    return "INFO", "ipfs", line


def _forward_line(line: str) -> None:
    """Hand one line of Kubo output to the logging module."""
    parsed = _parse_line(line)
    if parsed is None:
        return
    level, component, message = parsed
    # "%s" rather than the message itself as the format string: this is another
    # process's output, and a literal % in it would otherwise raise inside
    # LogRecord.getMessage() -- at which point the line is lost, not just mangled.
    _component_logger(component).log(KUBO_LEVELS.get(level, logging.INFO), "%s", message)


def _ipfs_bin() -> str:
    return os.environ.get("IPFS_BIN", "/usr/local/bin/ipfs")


def _run(cmd: list[str], env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    return subprocess.run(cmd, env=proc_env, check=check, capture_output=True, text=True)


def _repo_path(island_id: str) -> Path:
    data_dir = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc/data"))
    return data_dir / "ipfs-island" / island_id


def _init_repo(repo: Path) -> None:
    if (repo / "config").exists():
        return
    repo.mkdir(parents=True, exist_ok=True)
    _run([_ipfs_bin(), "init"], env={"IPFS_PATH": str(repo)})


def _parse_multiaddrs(raw: str) -> list[str]:
    """Split a comma- or whitespace-separated multiaddr list."""
    return [part for part in re.split(r"[,\s]+", raw.strip()) if part]


def _set_island_config(
    repo: Path,
    api_port: int,
    gateway_port: int,
    swarm_port: int,
    announce: list[str] | None = None,
) -> None:
    """Apply island-specific config directly to the Kubo config file.

    We edit the JSON config directly because `ipfs config --json` can fail
    or silently drop keys when the nested object does not exist.
    """
    config_file = repo / "config"
    if not config_file.exists():
        raise RuntimeError(f"Kubo config not found at {config_file}; repo may not be initialised")

    with config_file.open("r+") as f:
        config: dict[str, Any] = json.load(f)
        config.setdefault("Addresses", {})
        config["Addresses"]["API"] = f"/ip4/127.0.0.1/tcp/{api_port}"
        config["Addresses"]["Gateway"] = f"/ip4/127.0.0.1/tcp/{gateway_port}"
        config["Addresses"]["Swarm"] = [
            f"/ip4/0.0.0.0/tcp/{swarm_port}",
            f"/ip4/0.0.0.0/udp/{swarm_port}/quic-v1",
            f"/ip4/0.0.0.0/udp/{swarm_port}/quic-v1/webtransport",
        ]
        # A node behind a NAT or a container proxy only ever sees its private
        # address, so left empty it advertises something no outside peer can
        # dial. Set ISLAND_IPFS_ANNOUNCE to the address peers actually reach.
        config["Addresses"]["Announce"] = list(announce or [])
        config["AutoConf"] = {"Enabled": False}
        config["Gateway"] = config.get("Gateway", {})
        config["Gateway"]["PublicGateways"] = {}
        f.seek(0)
        json.dump(config, f, indent=2)
        f.truncate()


def _generate_swarm_key() -> str:
    import secrets

    return f"/key/swarm/psk/1.0.0/\n/base16/\n{secrets.token_hex(32)}\n"


def _write_swarm_key(repo: Path, key: str | None, allow_generate: bool = False) -> None:
    key_file = repo / "swarm.key"
    if key is not None:
        key_file.write_text(key)
        key_file.chmod(0o600)
    elif not key_file.exists():
        if allow_generate:
            key_file.write_text(_generate_swarm_key())
            key_file.chmod(0o600)
        else:
            raise RuntimeError(
                f"Missing swarm key for island IPFS repo {repo}. Set ISLAND_SWARM_KEY or place swarm.key in the repo."
            )


def _add_bootstrap(repo: Path, multiaddrs: list[str]) -> None:
    ipfs = _ipfs_bin()
    env = {"IPFS_PATH": str(repo)}
    _run([ipfs, "bootstrap", "rm", "all"], env=env, check=False)
    for multiaddr in multiaddrs:
        _run([ipfs, "bootstrap", "add", multiaddr], env=env, check=False)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    parser = argparse.ArgumentParser(description="Run a private island IPFS daemon")
    parser.add_argument("--island-id", default=os.environ.get("ISLAND_ID", ""), help="Island identifier")
    parser.add_argument("--repo", default=os.environ.get("ISLAND_IPFS_REPO", ""), help="IPFS repository path")
    parser.add_argument("--api-port", type=int, default=int(os.environ.get("ISLAND_IPFS_API_PORT", "5002")))
    parser.add_argument("--gateway-port", type=int, default=int(os.environ.get("ISLAND_IPFS_GATEWAY_PORT", "8081")))
    parser.add_argument("--swarm-port", type=int, default=int(os.environ.get("ISLAND_IPFS_SWARM_PORT", "4002")))
    parser.add_argument(
        "--bootstrap",
        default=os.environ.get("ISLAND_IPFS_BOOTSTRAP", ""),
        help="Hub multiaddr(s) to bootstrap, comma-separated",
    )
    parser.add_argument(
        "--announce",
        default=os.environ.get("ISLAND_IPFS_ANNOUNCE", ""),
        help="Multiaddr(s) peers should dial to reach this node, comma-separated",
    )
    parser.add_argument("--swarm-key", default=os.environ.get("ISLAND_SWARM_KEY", ""), help="Swarm key contents")
    parser.add_argument(
        "--hub", action="store_true", default=os.environ.get("ISLAND_IPFS_HUB", "").lower() in ("1", "true", "yes")
    )
    args = parser.parse_args(argv)

    if not args.island_id:
        logger.error("--island-id or ISLAND_ID is required")
        return 1

    repo = Path(args.repo) if args.repo else _repo_path(args.island_id)
    _init_repo(repo)
    _write_swarm_key(repo, args.swarm_key or None, allow_generate=args.hub)
    _set_island_config(repo, args.api_port, args.gateway_port, args.swarm_port, _parse_multiaddrs(args.announce))
    bootstrap = _parse_multiaddrs(args.bootstrap)
    if bootstrap:
        _add_bootstrap(repo, bootstrap)

    cmd = [_ipfs_bin(), "daemon", "--enable-gc"]
    env = os.environ.copy()
    env["IPFS_PATH"] = str(repo)
    env["IPFS_FORCE_PNET"] = "1"

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
    )

    def _forward(signum: int, _frame: object) -> None:
        try:
            proc.send_signal(signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT, _forward)

    try:
        for raw in proc.stdout or []:
            _forward_line(raw)
    finally:
        proc.wait()

    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
