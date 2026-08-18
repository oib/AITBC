"""V23-100: the production monitoring watched units and a host that do not exist.

``scripts/monitoring/production_monitoring.sh`` generates four scripts and puts three of
them on cron. Everything it generated was aimed at things that are not there:

* ``systemctl is-active aitbc-coordinator`` and ``blockchain-node``. Neither is a unit on
  any AITBC host -- they are ``aitbc-coordinator-api`` and ``aitbc-blockchain-node`` -- so
  the five-minute alert check raised two alerts on every run forever. Same two names
  V23-98 found in ``security_hardening.sh``.
* ``https://aitbc.bubuit.net/api/v1/health``. That name does not resolve from a node (this
  host is ``aitbc3.aitbc.bubuit.net``; the hub is ``hub.aitbc.bubuit.net``), and the
  ``/v1/`` prefix is not a health path anywhere -- it 404s on the coordinator and 401s
  through the gateway. So the 200 the alert check compares against was unreachable by
  construction, and the failure arrived as the string "000" rather than as an error,
  because every probe was written ``curl -s ... || echo "000"``.
* ``/opt/aitbc/monitoring``, which is inside the git checkout the services run from.

None of it had run here -- the directory does not exist -- and if it had, the generator
would have died at its first ``crontab -l`` on a host without a crontab, because the
subshell inherits ``set -e``.

These tests run the generator against a stubbed host and check the scripts it produces,
rather than reading the generator's source, because what matters is what ends up on cron.
"""

from __future__ import annotations

import http.server
import os
import re
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
GENERATOR = SCRIPTS / "monitoring" / "production_monitoring.sh"
QUICK_TEST = SCRIPTS / "testing" / "quick_test.py"
SCALABILITY = SCRIPTS / "testing" / "scalability_validation.py"

GENERATED = ["collect_metrics.sh", "check_alerts.sh", "dashboard.sh", "analyze_logs.sh"]

# The units these scripts are allowed to name, and the only ones that exist.
COORDINATOR_UNIT = "aitbc-coordinator-api"
BLOCKCHAIN_UNIT = "aitbc-blockchain-node"

# Names that were probed and are not AITBC hosts. `aitbc.bubuit.net` is the public web
# name; no node resolves it, and it is not where any service's health lives.
UNREACHABLE_HOSTS = ["aitbc.bubuit.net"]

# What a line has to be doing for a hostname on it to count as a probe. A server_name, a
# CORS origin, an alert email and a banner all mention the same name legitimately.
PROBE = re.compile(r"\bcurl\b|requests\.(get|post|request)|session\.(get|post|request)|wget\b")


# --- 1. the generator runs, and produces scripts that parse ------------------------------


@pytest.fixture
def host(tmp_path: Path) -> dict[str, Path]:
    """A stubbed host: crontab, systemctl and curl that answer from the environment.

    ``crontab`` keeps its spool in a file under tmp_path, so running the generator here
    cannot schedule anything on the machine running the tests.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()

    (stub_dir / "crontab").write_text(
        textwrap.dedent(
            """\
            #!/bin/bash
            case "$1" in
              -l) [[ -s "$STUB_CRON" ]] || exit 1; cat "$STUB_CRON" ;;
              -)  buf=$(cat); printf '%s\\n' "$buf" > "$STUB_CRON" ;;
            esac
            """
        ),
        encoding="utf-8",
    )
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
                [[ " $INSTALLED " != *" $unit "* ]] && { echo inactive; exit 4; }
                [[ " $INACTIVE " == *" $unit "* ]] && { echo failed; exit 3; }
                echo active ;;
              *) exit 0 ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    # -w writes its value on failure too, which is what made the old `|| echo` fallbacks
    # produce "000000"; the stub reproduces that so the fix is actually being tested.
    (stub_dir / "curl").write_text(
        textwrap.dedent(
            """\
            #!/bin/bash
            code="${HTTP_CODE:-200}"
            for arg in "$@"; do
              case "$arg" in
                '%{http_code}') out="$code" ;;
                '%{time_total}') out="0.001234" ;;
              esac
            done
            printf '%s' "${out:-}"
            [[ "$code" == "000" ]] && exit 6
            exit 0
            """
        ),
        encoding="utf-8",
    )
    for stub in stub_dir.iterdir():
        stub.chmod(0o755)

    return {
        "bin": stub_dir,
        "cron": tmp_path / "crontab.txt",
        "mon": tmp_path / "mon",
        "env": tmp_path / "etc" / "monitoring.env",
    }


def _env(host: dict[str, Path], **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{host['bin']}:{os.environ['PATH']}",
        "STUB_CRON": str(host["cron"]),
        "AITBC_MONITORING_DIR": str(host["mon"]),
        "AITBC_MONITORING_ENV": str(host["env"]),
        "INSTALLED": f"{COORDINATOR_UNIT} {BLOCKCHAIN_UNIT} nginx",
        "INACTIVE": "",
        **extra,
    }


def _generate(host: dict[str, Path], **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(GENERATOR)],
        env=_env(host, **extra),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_generator_runs_on_a_host_with_no_crontab(host: dict[str, Path]) -> None:
    """It used to die here. `(crontab -l; echo ...) | crontab -` runs the subshell under the
    inherited `set -e`, and `crontab -l` exits 1 when the user has no crontab yet -- so on a
    fresh node the generator aborted at the first schedule, having written one script."""
    result = _generate(host)

    assert result.returncode == 0, result.stderr
    for name in GENERATED:
        assert (host["mon"] / name).exists(), f"{name} was not generated\n{result.stdout}\n{result.stderr}"


def test_every_generated_script_parses(host: dict[str, Path]) -> None:
    _generate(host)

    for name in GENERATED:
        check = subprocess.run(["bash", "-n", str(host["mon"] / name)], capture_output=True, text=True)
        assert check.returncode == 0, f"{name} does not parse: {check.stderr}"


def test_no_generated_script_uses_local_outside_a_function(host: dict[str, Path]) -> None:
    """`local total=...` sat at the top level of analyze_logs.sh, where bash refuses it with
    "can only be used in a function". `bash -n` does not catch it -- it is a runtime error --
    so the error rate section died every hour and the file said "Error Rate: %"."""
    _generate(host)

    for name in GENERATED:
        depth = 0
        offenders = []
        for lineno, line in enumerate((host["mon"] / name).read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if depth == 0 and re.match(r"^\s*local\b", line):
                offenders.append(f"{name}:{lineno}: {line.strip()}")
            depth += line.count("{") - line.count("}")
        assert depth == 0, f"{name}: brace tracking ended at depth {depth}, this check is no longer reliable"
        assert not offenders, "`local` outside a function:\n" + "\n".join(offenders)


def test_scheduling_twice_schedules_once(host: dict[str, Path]) -> None:
    """Three `(crontab -l; echo ...) | crontab -` calls appended unconditionally. Nothing
    says this script runs once, and a second run gave the node two copies of every job."""
    _generate(host)
    first = host["cron"].read_text(encoding="utf-8")
    _generate(host)

    assert host["cron"].read_text(encoding="utf-8") == first
    assert len([line for line in first.splitlines() if line.strip()]) == 3


def test_the_config_template_is_not_overwritten(host: dict[str, Path]) -> None:
    """Whatever the operator pointed the probes at has to survive a re-run."""
    _generate(host)
    host["env"].write_text("AITBC_API_HEALTH_URL=http://example.invalid/health\n", encoding="utf-8")
    _generate(host)

    assert "example.invalid" in host["env"].read_text(encoding="utf-8")


# --- 2. what the generated scripts point at ---------------------------------------------


def test_generated_scripts_name_units_that_exist(host: dict[str, Path]) -> None:
    _generate(host)

    for name in GENERATED:
        text = (host["mon"] / name).read_text(encoding="utf-8")
        assert not re.search(r'"aitbc-coordinator"|=aitbc-coordinator\b', text), f"{name} names a unit that does not exist"
        assert not re.search(r'"blockchain-node"|=blockchain-node\b', text), f"{name} names a unit that does not exist"

    preamble = (host["mon"] / "collect_metrics.sh").read_text(encoding="utf-8")
    assert COORDINATOR_UNIT in preamble
    assert BLOCKCHAIN_UNIT in preamble


def test_generated_scripts_do_not_write_into_the_git_checkout(host: dict[str, Path]) -> None:
    """/opt/aitbc/monitoring is inside the checkout the services run from, so four scripts
    and three growing logs landed there as untracked files."""
    _generate(host)

    for name in GENERATED:
        text = (host["mon"] / name).read_text(encoding="utf-8")
        assert "/opt/aitbc" not in text, f"{name} still writes into the checkout"
        assert 'MONITORING_DIR="${AITBC_MONITORING_DIR:-/var/lib/aitbc/monitoring}"' in text


def test_the_default_health_url_is_this_nodes_coordinator(host: dict[str, Path]) -> None:
    _generate(host)
    text = (host["mon"] / "check_alerts.sh").read_text(encoding="utf-8")

    assert 'API_HEALTH_URL="${AITBC_API_HEALTH_URL:-http://localhost:8203/health}"' in text

    code = [line for line in text.splitlines() if not line.strip().startswith("#")]
    assert not [line for line in code if "/v1/health" in line], "a versioned health path is still probed"


def test_an_absent_unit_is_skipped_not_alerted(host: dict[str, Path]) -> None:
    """Absent is not down: hub, follower and shop nodes run different sets of units, and an
    alarm that fires forever teaches the operator to ignore the channel (V23-98)."""
    _generate(host)
    result = subprocess.run(
        ["bash", str(host["mon"] / "check_alerts.sh")],
        env=_env(host, INSTALLED=BLOCKCHAIN_UNIT),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout
    assert "not installed on this host, skipping" in result.stdout
    assert "ALERT" not in result.stdout


def test_a_failed_unit_alerts(host: dict[str, Path]) -> None:
    _generate(host)
    result = subprocess.run(
        ["bash", str(host["mon"] / "check_alerts.sh")],
        env=_env(host, INACTIVE=COORDINATOR_UNIT),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 1, result.stdout
    assert f"Service {COORDINATOR_UNIT} is failed" in result.stdout


def test_an_unreachable_api_alerts_and_exits_nonzero(host: dict[str, Path]) -> None:
    """The old script exited 0 whatever it found, so the only trace of an alert was a line in
    a log file nobody reads. cron mails a non-zero run."""
    _generate(host)
    result = subprocess.run(
        ["bash", str(host["mon"] / "check_alerts.sh")],
        env=_env(host, HTTP_CODE="000"),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 1
    assert "API health check failed (HTTP 000 " in result.stdout, result.stdout


def test_a_failed_probe_records_one_status_not_two(host: dict[str, Path]) -> None:
    """`curl -w '%{http_code}' ... || echo "000"` prints twice on failure: -w writes its zero
    value and then the fallback adds another. The metrics row read api_status:000000."""
    _generate(host)
    subprocess.run(
        ["bash", str(host["mon"] / "collect_metrics.sh")],
        env=_env(host, HTTP_CODE="000"),
        capture_output=True,
        text=True,
        timeout=60,
    )

    row = (host["mon"] / "metrics.log").read_text(encoding="utf-8").strip()
    assert row.endswith("api_status:000"), row


def test_a_healthy_probe_is_recorded(host: dict[str, Path]) -> None:
    _generate(host)
    subprocess.run(
        ["bash", str(host["mon"] / "collect_metrics.sh")],
        env=_env(host),
        capture_output=True,
        text=True,
        timeout=60,
    )

    row = (host["mon"] / "metrics.log").read_text(encoding="utf-8").strip()
    assert "coordinator:active" in row, row
    assert row.endswith("api_status:200"), row


# --- 3. nothing under scripts/ probes a host that does not resolve -----------------------


def _probe_lines() -> list[tuple[Path, int, str]]:
    found = []
    for path in sorted(SCRIPTS.rglob("*")):
        if path.suffix not in {".sh", ".py"} or not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.strip().startswith("#") or not PROBE.search(line):
                continue
            found.append((path.relative_to(REPO_ROOT), lineno, line.strip()))
    return found


@pytest.mark.parametrize("host_name", UNREACHABLE_HOSTS)
def test_no_script_probes_a_host_no_node_resolves(host_name: str) -> None:
    """A server_name, a CORS origin, an alert address and a printed banner may all name the
    public site. A curl or a requests.get may not: from a node the lookup fails, and every
    one of these was written so the failure came back as a status code."""
    offenders = [f"{path}:{lineno}: {line}" for path, lineno, line in _probe_lines() if host_name in line]

    assert not offenders, f"probing {host_name}:\n" + "\n".join(offenders)


def test_the_load_generator_does_not_default_to_a_deployment() -> None:
    """Aiming load at a host is a decision. Its default was the unresolvable public name, so
    the one thing it could not do is what it said it did."""
    text = SCALABILITY.read_text(encoding="utf-8")

    assert 'DEFAULT_BASE_URL = os.environ.get("AITBC_BASE_URL", "http://localhost:8203/v1")' in text
    assert "def __init__(self, base_url=DEFAULT_BASE_URL):" in text


# --- 4. quick_test.py checks what it prints ---------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    """Answers each path with the code named in the server's `codes` map."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        self.send_response(self.server.codes.get(self.path, 404))  # type: ignore[attr-defined]
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def stub_api():
    """Start an HTTP server answering a given path -> status map; yield its base URL."""
    servers = []

    def start(codes: dict[str, int]) -> str:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.codes = codes  # type: ignore[attr-defined]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()


def _quick_test(base_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(QUICK_TEST), base_url], capture_output=True, text=True, timeout=60)


def test_quick_test_passes_against_a_node_answering_correctly(stub_api) -> None:
    base = stub_api({"/health": 200, "/v1/client/jobs": 401})

    result = _quick_test(base)

    assert result.returncode == 0, result.stdout
    assert "❌" not in result.stdout


def test_quick_test_fails_when_the_health_path_is_not_there(stub_api) -> None:
    """The whole point. It printed a green tick for the 404 and exited 0, which is how a
    probe aimed at a path that does not exist survived in the repo."""
    base = stub_api({"/v1/client/jobs": 401})

    result = _quick_test(base)

    assert result.returncode == 1
    assert "404 in" in result.stdout
    assert "(expected 200)" in result.stdout


def test_quick_test_fails_when_the_authenticated_route_is_open(stub_api) -> None:
    """200 without a valid key is not a pass -- the key it sends is deliberately junk."""
    base = stub_api({"/health": 200, "/v1/client/jobs": 200})

    result = _quick_test(base)

    assert result.returncode == 1
    assert "(expected 401/403)" in result.stdout


def test_quick_test_fails_when_nothing_answers() -> None:
    """A name that does not resolve was reported as a successful probe."""
    result = _quick_test("http://aitbc.invalid")

    assert result.returncode == 1
    assert "❌" in result.stdout


def test_quick_test_declares_no_test_prefixed_function() -> None:
    """It is not a pytest module and scripts/ is not in testpaths, but the file is named
    quick_test.py and defined `def test_endpoint(url, headers=None)` -- collected by
    anything pointed at scripts/, that errors on a missing `url` fixture."""
    text = QUICK_TEST.read_text(encoding="utf-8")

    assert not re.search(r"^def test_", text, re.M)
