#!/usr/bin/env python3
"""Private island IPFS daemon wrapper.

Runs a Kubo IPFS node that is member of a private swarm (using a swarm.key).
Only peers that share the same swarm key can connect, so the island's IPFS
storage is gated to paying members that received the key from the coordinator.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

# systemd runs this as a bare script with no PYTHONPATH, and `aitbc` is not
# installed into the venv, so the repo root has to go on the path before the
# imports below. Derived from __file__ rather than hardcoded, so a checkout
# somewhere other than the deployment path still works. The script's own
# directory is already sys.path[0] when this runs as a script, but not when it
# is loaded by path -- importlib.util.spec_from_file_location does not add it --
# so `kubo_log` gets an entry of its own rather than relying on that.
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))
sys.path.insert(0, str(_HERE.parent))

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from kubo_log import forward_line  # noqa: E402

configure_logging(level="INFO", service_name="island-ipfs", to_file=True)
logger = get_logger(__name__)


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
            forward_line(raw)
    finally:
        proc.wait()

    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
