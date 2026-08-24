"""V23-99: health gates that probe a path the service does not serve, or that cannot fail.

Two independent defects combined to make most of the repo's health checking decorative.

The first is path drift. Eight scripts and a dozen runbooks gated on
``http://localhost:8203/v1/health``. coordinator-api serves ``/health``, ``/health/live``
and ``/health/ready``; it has never served ``/v1/health``. The same drift reached
``deploy-to-server.sh``, where the generated nginx config proxied ``/health`` to
``127.0.0.1:8203/v1/health``, and ``chaos_test_network.py``, which asked for ``/v1/health``
and then tested ``"ok" in stdout`` -- so it reported every pod down on a healthy cluster.

The second is that ``curl -s`` exits 0 on a 404: the connection succeeded, and curl does not
care what the server said. Only ``-f`` turns an HTTP error into a non-zero exit. So
``curl -s "$URL" && echo OK`` prints OK against a 404, and
``curl -s "$URL" >/dev/null 2>&1 || exit 1`` passes against one. Combined with the first
defect, a readiness gate on ``/v1/health`` waited for a service that was already up, got a
404, and called it ready -- ``diagnose-services.sh`` printed ``{"detail":"Not Found"}  OK``.

Underneath both sat three port maps that disagreed: ``aitbc/constants.py`` had marketplace on
8081 and exchange on 8001 (nothing has ever bound either), ``lib/services.sh`` had marketplace
on 8107 (agent-coordinator) and trading on 8201 (api-gateway), and only
``scripts/monitoring/health_check.sh`` -- rebuilt in V23-98 -- was right.

These guards pin the three invariants that make a health gate mean something:
a path the service declares, a port the service actually binds, and ``-f``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTH_CHECK_SH = REPO_ROOT / "scripts" / "monitoring" / "health_check.sh"
SERVICES_SH = REPO_ROOT / "scripts" / "service-management" / "lib" / "services.sh"
CONSTANTS_PY = REPO_ROOT / "aitbc" / "constants.py"
SCRIPTS_DIR = REPO_ROOT / "scripts"
DOCS_DIR = REPO_ROOT / "docs"

# Ports whose service is committed to this repo as an OpenAPI spec. The spec is the route
# table: check-openapi-drift.sh regenerates it from the live app on every commit, so a path
# that is not in here is a path the app does not answer.
SPEC_BACKED_PORTS: dict[int, str] = {
    8102: "marketplace",
    8107: "agent-coordinator",
    8108: "wallet",
    8202: "blockchain-node",
    8203: "coordinator-api",
}

# Services with no committed spec. Their liveness paths were read off the running services on
# this host -- every entry below answered 200, and every path omitted answered 404. They are
# not uniform: gpu, trading and governance serve the /ready and /live pair, edge serves /ready
# but not /live, and monitoring, blockchain-explorer and pool-hub serve /health alone. That is
# why this has to be a table and not a rule.
NON_SPEC_HEALTH_PATHS: dict[int, set[str]] = {
    8002: {"/health"},  # aitbc-monitoring
    8100: {"/health"},  # aitbc-blockchain-explorer
    8101: {"/health", "/ready", "/live"},  # aitbc-gpu
    8104: {"/health", "/ready", "/live"},  # aitbc-trading
    8105: {"/health", "/ready", "/live"},  # aitbc-governance
    8111: {"/health", "/ready"},  # aitbc-edge
    8210: {"/health"},  # aitbc-pool-hub (V23-96)
    # Neither of these runs on a shop node, so they come from the source rather than a probe.
    8205: {"/health"},  # blockchain_event_bridge/main.py:46
    # aitbc-exchange is not running here, so this one comes from the source: the request
    # dispatcher in apps/exchange/simple_exchange/handlers/__init__.py routes both spellings
    # to health_check(), so 8106/api/health is correct and must not be "fixed" to /health.
    8106: {"/health", "/api/health"},
}

# Health URLs on ports nothing in this repo binds. They belong to a service layout that does
# not exist here -- the same family as the health-check.sh deleted in V23-98 -- and fixing
# them means deciding what those services are, not editing a path. Frozen so the set cannot
# grow while that decision is outstanding; 9090 and 9093 are Prometheus and Alertmanager,
# whose real liveness path is /-/healthy.
UNDECLARED_PORT_HEALTH_URLS: set[tuple[int, str]] = {
    (8000, "/health"),
    (8000, "/v1/health"),
    (8001, "/api/health"),
    (8001, "/health"),
    (8003, "/api/health"),
    (8003, "/health"),
    (8004, "/api/health"),
    (8004, "/health"),
    (8005, "/health"),
    (8006, "/health"),
    (8007, "/health"),
    (8008, "/health"),
    (8010, "/health"),
    (8012, "/api/health"),
    (8012, "/health"),
    (8013, "/api/health"),
    (8013, "/health"),
    (8015, "/health"),
    (8015, "/v1/health"),
    (8017, "/health"),
    (8080, "/health"),
    (8083, "/health"),
    (9090, "/-/healthy"),
    (9093, "/-/healthy"),
}

# Matches a literal liveness-probe URL against the loopback host, capturing port and path.
#
# The final segment must be the probe itself -- health, healthy, healthz, live, ready. That is
# what makes a URL a health gate. It deliberately excludes routes that merely live under a
# "health" namespace, such as coordinator-api's /v1/agent/health/report: those are reporting
# APIs whose payload matters, not gates whose exit status does, and whether that particular
# family exists at all is a separate question from this finding.
HEALTH_URL_RE = re.compile(
    r"(?:localhost|127\.0\.0\.1):(\d+)"
    r"((?:/[A-Za-z0-9_.-]+)*?/(?:health|healthy|healthz|live|ready))"
    r"(?![A-Za-z0-9/_-])"
)


def _text_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in {".sh", ".py", ".md"})


def _health_urls(root: Path) -> list[tuple[int, str, str]]:
    """Every literal loopback health URL under root, as (port, path, "file:line")."""
    found: list[tuple[int, str, str]] = []
    for path in _text_files(root):
        for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            for port, url_path in HEALTH_URL_RE.findall(line):
                found.append((int(port), url_path, f"{path.relative_to(REPO_ROOT)}:{lineno}"))
    return found


def _spec_paths(service: str) -> set[str]:
    spec = REPO_ROOT / "docs" / "api" / f"{service}-openapi.json"
    return set(json.loads(spec.read_text())["paths"])


def _shell_map(text: str, name: str) -> dict[str, int]:
    """Parse a `declare -A NAME=( [key]=value ... )` block into a dict."""
    block = re.search(rf"declare -A {name}=\((.*?)\n\)", text, re.DOTALL)
    assert block, f"{name} is no longer a `declare -A` block"
    return {k: int(v) for k, v in re.findall(r"\[([a-z-]+)\]=(\d+)", block.group(1))}


def _endpoint_map() -> dict[str, tuple[int, str]]:
    """health_check.sh ALL_SERVICE_ENDPOINTS, as service -> (port, path).

    The catalogue, not the probe list: V23-92 made health_check.sh filter it down to the
    units this node's role is supposed to run. What ports exist in the platform is a
    property of the catalogue, so that is what this reads.
    """
    text = HEALTH_CHECK_SH.read_text()
    block = re.search(r"declare -A ALL_SERVICE_ENDPOINTS=\((.*?)\n\)", text, re.DOTALL)
    assert block, "ALL_SERVICE_ENDPOINTS is no longer a `declare -A` block"
    entries = re.findall(r'\["([a-z-]+)"\]="http://localhost:(\d+)(/[a-z/]*)"', block.group(1))
    assert entries, "SERVICE_ENDPOINTS parsed empty"
    return {svc: (int(port), path) for svc, port, path in entries}


DECLARED_PORTS = {port for port, _ in _endpoint_map().values()}


API_GATEWAY_PORT = 8201


def _gateway_paths() -> set[str]:
    """api-gateway's own /health, plus the proxied /v1/<service>/health it forwards.

    Read off the SERVICES table in the app rather than written down, because the whole
    point of the V23-99 doc fix was that the prefixes had been guessed: the examples said
    /gpu/health on port 8203, where the truth is /v1/gpu/health on 8201.
    """
    main = (REPO_ROOT / "apps" / "api-gateway" / "src" / "api_gateway" / "main.py").read_text()
    prefixes = re.findall(r'"prefix":\s*"(/v1/[a-z-]+)"', main)
    assert prefixes, "api-gateway's SERVICES table no longer declares prefixes"
    return {"/health"} | {f"{p}/health" for p in prefixes}


def _expected_paths(port: int) -> set[str]:
    if port == API_GATEWAY_PORT:
        return _gateway_paths()
    if port in SPEC_BACKED_PORTS:
        return _spec_paths(SPEC_BACKED_PORTS[port])
    return NON_SPEC_HEALTH_PATHS[port]


class TestHealthPathsExist:
    """A health URL on a port this repo binds must name a path that service serves."""

    def test_every_declared_port_is_covered_by_a_route_table(self):
        """Each port in the health map has either a committed spec or an explicit path set."""
        uncovered = sorted(DECLARED_PORTS - set(SPEC_BACKED_PORTS) - set(NON_SPEC_HEALTH_PATHS) - {API_GATEWAY_PORT})
        assert not uncovered, (
            f"health_check.sh watches ports with no route table in this test: {uncovered}. "
            "Add the port to SPEC_BACKED_PORTS or NON_SPEC_HEALTH_PATHS."
        )

    @pytest.mark.parametrize("root", [SCRIPTS_DIR, DOCS_DIR], ids=["scripts", "docs"])
    def test_no_health_url_uses_a_path_its_service_does_not_serve(self, root: Path):
        bad = []
        for port, url_path, where in _health_urls(root):
            if port not in DECLARED_PORTS:
                continue
            # docs/releases/ is an append-only history of what shipped; it records the old
            # paths on purpose and must not be rewritten.
            if "docs/releases/" in where:
                continue
            if url_path not in _expected_paths(port):
                bad.append(f"{where}: :{port}{url_path}")
        assert not bad, "health URLs naming a path the service on that port does not serve:\n  " + "\n  ".join(bad)

    def test_v1_health_is_gone_from_declared_ports(self):
        """The specific 404 that started this: nothing declares /v1/health."""
        for service in SPEC_BACKED_PORTS.values():
            assert "/v1/health" not in _spec_paths(service), f"{service} now declares /v1/health"
        offenders = [
            where
            for port, url_path, where in _health_urls(REPO_ROOT / "scripts") + _health_urls(DOCS_DIR)
            if port in DECLARED_PORTS and url_path == "/v1/health" and "docs/releases/" not in where
        ]
        assert not offenders, f"/v1/health is back on a declared port: {offenders}"


class TestHealthGatesCanFail:
    """curl -s exits 0 on a 404, so a gate without -f proves only that the port is open."""

    # Health probes that legitimately have no -f: prose examples for a human to paste, and
    # the two Prometheus checks, which run against ports this repo does not bind.
    DASH_F_EXEMPT = {
        "scripts/gpu/README.md",  # documentation example, not a gate
        "scripts/README.md",  # documentation example, not a gate
    }

    def test_every_declared_port_health_curl_uses_dash_f(self):
        curl_re = re.compile(r"curl\b[^|;&\n]*")
        bad = []
        for path in _text_files(SCRIPTS_DIR):
            rel = str(path.relative_to(REPO_ROOT))
            if rel in self.DASH_F_EXEMPT:
                continue
            for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                for call in curl_re.findall(line):
                    hits = HEALTH_URL_RE.findall(call)
                    if not hits and "AITBC_SERVICE_PORTS" in call and "health" in call:
                        hits = [("0", "/health")]  # map lookup: port is resolved at runtime
                    if not any(int(p) in DECLARED_PORTS or p == "0" for p, _ in hits):
                        continue
                    # -f may be bundled: -fsS, -sf, --fail.
                    if not re.search(r"(?<![a-zA-Z-])-[a-zA-Z]*f|--fail", call):
                        bad.append(f"{rel}:{lineno}: {call.strip()}")
        assert not bad, (
            "health probes on a port this repo binds that cannot fail -- curl -s exits 0 on a "
            "404, so these report success against any listening socket:\n  " + "\n  ".join(bad)
        )


class TestPortMapsAgree:
    """Three files write the port map down. They disagreed; two of them were wrong."""

    def test_services_sh_agrees_with_the_health_map(self):
        shell = _shell_map(SERVICES_SH.read_text(), "AITBC_SERVICE_PORTS")
        health = {svc: port for svc, (port, _) in _endpoint_map().items()}
        disagreements = {svc: (port, health[svc]) for svc, port in shell.items() if svc in health and health[svc] != port}
        assert not disagreements, (
            f"lib/services.sh and health_check.sh disagree (service: services.sh, health_check.sh): {disagreements}"
        )

    def test_services_sh_ports_are_ports_something_binds(self):
        shell = _shell_map(SERVICES_SH.read_text(), "AITBC_SERVICE_PORTS")
        stray = {svc: port for svc, port in shell.items() if port not in DECLARED_PORTS}
        assert not stray, f"lib/services.sh points at ports no service declares: {stray}"

    def test_no_two_services_share_a_port_in_services_sh(self):
        shell = _shell_map(SERVICES_SH.read_text(), "AITBC_SERVICE_PORTS")
        assert len(set(shell.values())) == len(shell), f"two services in lib/services.sh claim the same port: {shell}"

    def test_constants_agree_with_the_health_map(self):
        from aitbc.constants import (
            AGENT_COORDINATOR_PORT,
            BLOCKCHAIN_RPC_PORT,
            COORDINATOR_API_PORT,
            EXCHANGE_PORT,
            MARKETPLACE_PORT,
            WALLET_PORT,
        )

        health = {svc: port for svc, (port, _) in _endpoint_map().items()}
        assert MARKETPLACE_PORT == health["aitbc-marketplace"]
        assert EXCHANGE_PORT == health["aitbc-exchange"]
        assert COORDINATOR_API_PORT == health["aitbc-coordinator-api"]
        assert BLOCKCHAIN_RPC_PORT == health["aitbc-blockchain-rpc"]
        assert WALLET_PORT == health["aitbc-wallet"]
        assert AGENT_COORDINATOR_PORT == health["aitbc-agent-coordinator"]

    def test_constants_ports_are_the_ports_the_units_start(self):
        """The numbers in constants.py must be the ones the systemd units pass to uvicorn."""
        from aitbc.constants import EXCHANGE_PORT, MARKETPLACE_PORT

        exchange_unit = (REPO_ROOT / "apps" / "exchange" / "aitbc-exchange.service").read_text()
        assert f"--port {EXCHANGE_PORT}" in exchange_unit, (
            f"constants.EXCHANGE_PORT={EXCHANGE_PORT} is not what aitbc-exchange.service starts"
        )
        marketplace_unit = (REPO_ROOT / "apps" / "marketplace" / "aitbc-marketplace.service").read_text()
        assert str(MARKETPLACE_PORT) in marketplace_unit, (
            f"constants.MARKETPLACE_PORT={MARKETPLACE_PORT} is not what aitbc-marketplace.service starts"
        )


class TestUndeclaredPortInventory:
    """The health URLs left alone, pinned so the backlog cannot quietly grow."""

    def test_the_undeclared_set_is_exactly_what_was_triaged(self):
        found = {(port, url_path) for port, url_path, _ in _health_urls(SCRIPTS_DIR) if port not in DECLARED_PORTS}
        new = sorted(found - UNDECLARED_PORT_HEALTH_URLS)
        assert not new, (
            "new health URLs on ports nothing in this repo binds: "
            f"{new}. Point them at a real service, or triage them into "
            "UNDECLARED_PORT_HEALTH_URLS with a reason."
        )

    def test_fixed_urls_are_not_still_listed_as_unfixed(self):
        found = {(port, url_path) for port, url_path, _ in _health_urls(SCRIPTS_DIR) if port not in DECLARED_PORTS}
        gone = sorted(UNDECLARED_PORT_HEALTH_URLS - found)
        assert not gone, f"these were fixed or removed; drop them from the inventory: {gone}"


class TestSpecificRegressions:
    """The individual gates this finding repaired, pinned by the shape that was wrong."""

    def test_deploy_nginx_does_not_proxy_health_to_a_404(self):
        text = (REPO_ROOT / "scripts" / "deployment" / "deploy" / "deploy-to-server.sh").read_text()
        assert "proxy_pass http://127.0.0.1:8203/v1/health" not in text, (
            "the generated nginx config proxies the public /health to a path coordinator-api 404s"
        )

    def test_chaos_test_asks_for_a_path_that_answers_ok(self):
        """It greps stdout for "ok"; a 404 body has none, so every pod read as down."""
        text = (REPO_ROOT / "scripts" / "testing" / "chaos_test_network.py").read_text()
        assert "/v1/health" not in text
        assert "coordinator:8203/health" in text

    def test_ledger_wait_loops_do_not_gate_on_a_404(self):
        """Both wait_for_blockchain_node loops retry 30 times, then exit 1."""
        for name in ("backup_ledger.sh", "restore_ledger.sh"):
            text = (REPO_ROOT / "scripts" / "maintenance" / name).read_text()
            probe = re.search(r"curl [^\n]*localhost:8080[^\n]*health[^\n]*", text)
            assert probe, f"{name} no longer has the blockchain-node readiness probe"
            assert "/v1/health" not in probe.group(0), f"{name} still waits on /v1/health"
            assert "-fsS" in probe.group(0) or "-sf" in probe.group(0), (
                f"{name}'s readiness probe cannot fail: {probe.group(0)}"
            )

    def test_rotate_jwt_secret_verifies_the_service_it_names(self):
        """The marketplace gate probed 8104, which is trading, and passed while marketplace was down."""
        text = (REPO_ROOT / "scripts" / "ops" / "rotate_jwt_secret.sh").read_text()
        marketplace = re.search(r'"aitbc-marketplace"\)(.*?);;', text, re.DOTALL)
        assert marketplace, "the aitbc-marketplace case is gone from rotate_jwt_secret.sh"
        assert "8102" in marketplace.group(1), "the marketplace gate does not probe marketplace"
        assert "8104" not in marketplace.group(1), "the marketplace gate still probes trading"

    def test_monitoring_blackbox_targets_are_reachable_paths(self):
        text = (REPO_ROOT / "scripts" / "monitoring" / "monitoring-setup.md").read_text()
        assert "/v1/health" not in text, "the blackbox exporter still targets /v1/health"
        assert "blockchain-node:8080" not in text, "blockchain-node is on 8202, not 8080"
