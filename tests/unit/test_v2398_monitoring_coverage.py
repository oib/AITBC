"""V23-98 — the health monitor watched five of the eleven services running on this host.

V23-96 added Pool Hub to ``scripts/monitoring/health_check.sh`` after a 404 on its
``/health`` survived because nothing ever probed it.  Pool Hub was not the exception.
Six more services were listening and answering ``/health`` 200 while ``SERVICE_ENDPOINTS``
watched five — monitoring 8002, blockchain-explorer 8100, gpu 8101, trading 8104,
governance 8105 and edge 8111.

Two of the seven entries it *did* have, ``aitbc-exchange`` and ``aitbc-agent-coordinator``,
are ``not-found`` in systemd here: this is a follower/shop node and those units were never
installed.  They were counted as errors, so the script exited 1 on every run whatever the
actual state — an exit code that never varies carries no information, which is a plausible
reason nobody ever scheduled it.

The behavioural tests below run the real script with stub ``systemctl`` and ``curl``
binaries ahead of it on ``PATH``, so they exercise the control flow rather than asserting
on its source text.
"""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTH_CHECK_SH = REPO_ROOT / "scripts" / "monitoring" / "health_check.sh"
PROMETHEUS_YML = REPO_ROOT / "scripts" / "monitoring" / "prometheus.yml"
SECURITY_HARDENING_SH = REPO_ROOT / "scripts" / "utils" / "security_hardening.sh"

# Every service in the map, and the file that decides which port it binds.  The point of
# carrying the source is that drift on either side fails: change the monitor and this
# disagrees, change the app's default and it disagrees too.
PORT_SOURCES: dict[str, tuple[int, str, str]] = {
    "aitbc-pool-hub": (8210, "apps/pool-hub/aitbc-pool-hub.service", r"--port\s+(\d+)"),
    "aitbc-monitoring": (8002, "scripts/monitoring/aitbc-monitoring.service", r"--port\s+(\d+)"),
    "aitbc-blockchain-explorer": (
        8100,
        "apps/blockchain-explorer/main.py",
        r"uvicorn\.run\(app, host=\"0\.0\.0\.0\", port=(\d+)",
    ),
    "aitbc-gpu": (8101, "apps/gpu/src/gpu_service/config.py", r"gpu_bind_port: int = (\d+)"),
    "aitbc-trading": (8104, "apps/trading/src/trading_service/config.py", r"bind_port: int = Field\(default=(\d+)\)"),
    "aitbc-governance": (8105, "apps/governance/src/governance_service/main.py", r'GOVERNANCE_BIND_PORT", "(\d+)"'),
    "aitbc-edge": (8111, "apps/edge/src/aitbc_edge/config.py", r"app_port: int = (\d+)"),
}

# Present before this finding and left alone; they are here so the map's size is asserted
# against a full list rather than a number nobody can check.
ALREADY_MONITORED = {
    "aitbc-blockchain-rpc": 8202,
    "aitbc-coordinator-api": 8203,
    "aitbc-marketplace": 8102,
    "aitbc-wallet": 8108,
    "aitbc-exchange": 8106,
    "aitbc-agent-coordinator": 8107,
}

# Added with the role filtering in V23-92, after this finding landed. Neither runs on a
# shop node, so neither has a live probe behind it; they are here so the size assertion
# below keeps checking against a full list.
ADDED_WITH_ROLE_FILTERING = {
    "aitbc-api-gateway": 8201,
    "aitbc-blockchain-event-bridge": 8205,
}


def _service_endpoints() -> dict[str, str]:
    """The full catalogue, parsed out of the script.

    V23-92 split the map in two: ALL_SERVICE_ENDPOINTS is every service the platform has,
    and SERVICE_ENDPOINTS is what this node's role is supposed to run, filtered out of it
    at startup.  Which services exist and what port each binds is a property of the
    catalogue, so that is what the coverage and port checks read.
    """
    text = HEALTH_CHECK_SH.read_text(encoding="utf-8")
    block = re.search(r"declare -A ALL_SERVICE_ENDPOINTS=\((.*?)\n\)", text, re.S)
    assert block, "ALL_SERVICE_ENDPOINTS is not declared in health_check.sh"
    return dict(re.findall(r'\["([^"]+)"\]="([^"]+)"', block.group(1)))


def _role_endpoints(role: str) -> dict[str, str]:
    """The subset a node of this role probes -- its unit list, intersected with the catalogue."""
    text = HEALTH_CHECK_SH.read_text(encoding="utf-8")

    def array(name: str) -> list[str]:
        block = re.search(rf"^_{name}_SERVICES=\((.*?)\n\)", text, re.S | re.M)
        assert block, f"_{name}_SERVICES is no longer a bash array"
        return block.group(1).split()

    extra = {"hub": ["HUB"], "follower": ["FOLLOWER"], "shop": ["SHOP", "FOLLOWER"], "customer": []}[role]
    units = array("BASE") + [unit for group in extra for unit in array(group)]
    catalogue = _service_endpoints()
    return {unit: catalogue[unit] for unit in units if unit in catalogue}


def _port_of(url: str) -> int:
    port = re.search(r":(\d+)/", url)
    assert port, f"no port in {url}"
    return int(port.group(1))


# --- 1. everything that runs here is watched -------------------------------------------


@pytest.mark.parametrize("service", sorted(PORT_SOURCES))
def test_the_service_is_monitored(service: str) -> None:
    """Six of these seven were absent; all six answered /health 200 the whole time."""
    assert service in _service_endpoints(), f"{service} is missing from SERVICE_ENDPOINTS"


@pytest.mark.parametrize("service", sorted(PORT_SOURCES))
def test_the_monitored_port_is_the_port_the_service_binds(service: str) -> None:
    """V23-96 pinned pool-hub's port to its unit file; this generalises that to all of them."""
    expected, source, pattern = PORT_SOURCES[service]

    declared = re.search(pattern, (REPO_ROOT / source).read_text(encoding="utf-8"))
    assert declared, f"{source} no longer declares a port matching {pattern!r}"
    assert int(declared.group(1)) == expected, f"{source} now says {declared.group(1)}, not {expected}"

    assert _port_of(_service_endpoints()[service]) == expected


def test_the_map_holds_exactly_the_services_we_know_about() -> None:
    """A new entry has to be accounted for here, which is where the port check lives."""
    expected = set(PORT_SOURCES) | set(ALREADY_MONITORED) | set(ADDED_WITH_ROLE_FILTERING)

    assert set(_service_endpoints()) == expected


def test_every_monitored_url_probes_the_unversioned_health_path() -> None:
    """A health check is infrastructure, not versioned API surface (V23-96)."""
    for service, url in _service_endpoints().items():
        assert url.endswith("/health"), f"{service} is probed at {url}"
        assert "/v1/" not in url, f"{service} is probed at a versioned path: {url}"


# --- 2. absent is not down --------------------------------------------------------------


@pytest.fixture
def stub_host(tmp_path: Path) -> Path:
    """A fake systemctl/curl pair, so the script's control flow can be run in isolation.

    ``systemctl`` reports every unit not-found unless it is named in ``INSTALLED``; ``curl``
    fails for any URL whose port is named in ``DOWN_PORTS``.  Both are read from the
    environment, so one stub serves every case below.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()

    (stub_dir / "systemctl").write_text(
        textwrap.dedent(
            """\
            #!/bin/bash
            unit="${*: -1}"
            case "$1" in
              is-enabled)
                [[ " $INSTALLED " == *" $unit "* ]] && { echo enabled; exit 0; }
                echo not-found; exit 4 ;;
              is-active)
                [[ " $INACTIVE " == *" $unit "* ]] && exit 3
                exit 0 ;;
              is-failed) exit 1 ;;
              show) echo 0 ;;
              *) exit 0 ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    (stub_dir / "curl").write_text(
        textwrap.dedent(
            """\
            #!/bin/bash
            url="${*: -1}"
            for port in $DOWN_PORTS; do
              [[ "$url" == *":$port/"* ]] && exit 22
            done
            exit 0
            """
        ),
        encoding="utf-8",
    )
    for stub in stub_dir.iterdir():
        stub.chmod(0o755)
    return stub_dir


def _run(stub_dir: Path, tmp_path: Path, mode: str, **env: str) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "LOG_DIR": str(tmp_path / "log"),
        "INSTALLED": "",
        "INACTIVE": "",
        "DOWN_PORTS": "",
        **env,
    }
    return subprocess.run(
        ["bash", str(HEALTH_CHECK_SH), mode],
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )


def test_a_unit_this_host_does_not_have_is_skipped_not_failed(stub_host: Path, tmp_path: Path) -> None:
    """The defect: exchange and agent-coordinator are not installed here, and were errors.

    Nothing is installed in this run, so *every* entry is absent — which must still be a
    pass, because a host that runs none of these services has nothing wrong with it.
    """
    result = _run(stub_host, tmp_path, "endpoints")

    assert result.returncode == 0, result.stdout
    assert "not installed on this host, skipping" in result.stdout
    assert "check(s) skipped" in result.stdout


def test_a_service_that_is_installed_and_down_still_fails(stub_host: Path, tmp_path: Path) -> None:
    """The skip must not become a way to pass by being absent everywhere."""
    # aitbc-pool-hub is shop-only; run in the shop role so the endpoint is actually probed.
    result = _run(
        stub_host,
        tmp_path,
        "endpoints",
        INSTALLED="aitbc-pool-hub",
        DOWN_PORTS="8210",
        BLOCKCHAIN_MODE="follower",
        MARKET_ROLE="shop",
        HARDWARE_PROFILE="gpu",
    )

    assert result.returncode == 1
    assert "aitbc-pool-hub endpoint is unhealthy" in result.stdout


def test_an_inactive_service_is_a_warning_not_an_error(stub_host: Path, tmp_path: Path) -> None:
    """check_service_status draws a three-way distinction — running, failed, inactive — and
    returns 0, 1, 2 for them.  Every call site was `|| TOTAL_ERRORS=...`, and `||` fires on
    any non-zero, so it collapsed back to two and the warning path was unreachable."""
    # aitbc-pool-hub is shop-only; run in the shop role so the service is actually checked.
    result = _run(
        stub_host,
        tmp_path,
        "services",
        INSTALLED="aitbc-pool-hub",
        INACTIVE="aitbc-pool-hub",
        BLOCKCHAIN_MODE="follower",
        MARKET_ROLE="shop",
        HARDWARE_PROFILE="gpu",
    )

    assert "aitbc-pool-hub is inactive" in result.stdout
    assert result.returncode == 0, "an inactive service was counted as an error"
    assert "warning(s)" in result.stdout


def test_a_healthy_host_passes(stub_host: Path, tmp_path: Path) -> None:
    """Since V23-92 a healthy host is role-specific: the run covers the endpoints its role
    is supposed to have, and the role is pinned here rather than read off this machine."""
    expected = _role_endpoints("shop")
    result = _run(
        stub_host,
        tmp_path,
        "endpoints",
        INSTALLED=" ".join(expected),
        BLOCKCHAIN_MODE="follower",
        MARKET_ROLE="shop",
        HARDWARE_PROFILE="gpu",
    )

    assert result.returncode == 0
    assert "All health checks passed" in result.stdout
    for service in expected:
        assert f"{service} endpoint is healthy" in result.stdout


# --- 3. one health check, not three -----------------------------------------------------


def test_the_stale_hyphenated_sibling_is_gone() -> None:
    """It listed 12 services of which one port was real: Coordinator on 8000, Wallet on
    8003, "Learning Service" on 8203 (which is Coordinator API), Agent Coordinator on 8012.
    Nothing called it. Two scripts disagreeing about every port is worse than one."""
    assert not (REPO_ROOT / "scripts" / "monitoring" / "health-check.sh").exists()


def test_security_hardening_does_not_generate_a_third_health_check() -> None:
    """It wrote its own checker into the git checkout and put it on a 5-minute cron. The
    two units it checked, "aitbc-coordinator" and "blockchain-node", do not exist under
    those names, so it would have failed its first check and exited 1 forever."""
    text = SECURITY_HARDENING_SH.read_text(encoding="utf-8")

    assert "scripts/health-check.sh" not in text, "it still writes a health checker into the git checkout"
    assert "aitbc.bubuit.net/api/v1/health" not in text, "it still probes a different host's API"
    assert "scripts/monitoring/health_check.sh" in text


def test_no_unit_name_that_systemd_does_not_have() -> None:
    """ "aitbc-coordinator" is not a unit; the real one is aitbc-coordinator-api. Besides the
    generated checker, it was also SERVICE_NAME, whose one use is the closing "Restart
    services: systemctl restart $SERVICE_NAME" line — the last instruction this script gave
    an operator, and it failed with "Unit aitbc-coordinator.service not found"."""
    text = SECURITY_HARDENING_SH.read_text(encoding="utf-8")

    assert not re.search(r'="aitbc-coordinator"', text)
    assert not re.search(r'="blockchain-node"', text)
    assert 'SERVICE_NAME="aitbc-coordinator-api"' in text


def test_the_scheduled_command_is_the_script_that_exists() -> None:
    """Whatever gets scheduled has to be a file in this repo, on a mode the script accepts."""
    text = SECURITY_HARDENING_SH.read_text(encoding="utf-8")

    scheduled = re.search(r"\*/5 \* \* \* \* \$health_check (\w+)", text)
    assert scheduled, "the cron line no longer runs $health_check with a mode"
    assert scheduled.group(1) in {"all", "services", "endpoints", "resources", "blockchain", "infrastructure"}
    assert HEALTH_CHECK_SH.exists()


# --- 4. prometheus ----------------------------------------------------------------------


def _jobs() -> dict[str, dict]:
    config = yaml.safe_load(PROMETHEUS_YML.read_text(encoding="utf-8"))
    return {job["job_name"]: job for job in config["scrape_configs"]}


@pytest.mark.parametrize("job,port", [("trading", 8104), ("governance", 8105)])
def test_the_service_is_scraped(job: str, port: int) -> None:
    """Of the six services the health map was missing, these two export /metrics."""
    jobs = _jobs()

    assert job in jobs, f"no scrape job for {job}"
    assert jobs[job]["static_configs"][0]["targets"] == [f"localhost:{port}"]
    assert jobs[job]["metrics_path"] == "/metrics"


def test_the_blockchain_job_targets_a_port_something_binds() -> None:
    """8006 until now, where nothing has ever listened — the same fictional port the stale
    hyphenated script claimed for this service. The RPC process exports the series."""
    assert _jobs()["blockchain-node"]["static_configs"][0]["targets"] == ["localhost:8202"]


def test_no_scrape_job_points_at_a_service_the_health_map_disagrees_about() -> None:
    """Both files name ports for the same services; they must not contradict each other."""
    monitored = {service.removeprefix("aitbc-"): _port_of(url) for service, url in _service_endpoints().items()}

    for name, job in _jobs().items():
        target = job["static_configs"][0]["targets"][0]
        if not target.startswith("localhost:") or name not in monitored:
            continue
        assert int(target.split(":")[1]) == monitored[name], (
            f"{name}: prometheus says {target}, health_check.sh says {monitored[name]}"
        )
