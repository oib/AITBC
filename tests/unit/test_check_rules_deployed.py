"""Pins for scripts/monitoring/check-rules-deployed.sh (#915).

The script derives its repo dir from its own location, so each test copies
the real script into a scratch dir alongside fixture ``*_rules.yml`` files
and points ``deployed-dir``/``prometheus.yml`` arguments at scratch dirs.
"""

import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "check-rules-deployed.sh"

RULES_A = "groups:\n  - name: aitbc\n    rules: []\n"
RULES_B = "groups:\n  - name: aitbc-hub\n    rules: []\n"


def make_env(tmp_path: Path, rule_files=("aitbc_rules.yml", "aitbc_hub_rules.yml")):
    """Scratch repo dir (script + rule files) and deployed dir."""
    repo = tmp_path / "repo"
    deployed = tmp_path / "deployed"
    repo.mkdir()
    deployed.mkdir()
    script = repo / "check-rules-deployed.sh"
    shutil.copy(REPO_SCRIPT, script)
    script.chmod(0o755)
    for name, body in zip(rule_files, (RULES_A, RULES_B), strict=False):
        (repo / name).write_text(body)
    return repo, deployed, script


def write_prometheus(deployed: Path, entries):
    lines = "".join(f"  - {e}\n" for e in entries)
    (deployed / "prometheus.yml").write_text(f"rule_files:\n{lines}scrape_configs: []\n")


def run(script: Path, *args, env=None):
    import os

    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", str(script), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=30,
        env=full_env,
    )


def test_deployed_but_unlisted_rule_file_fails(tmp_path):
    """The #915 bug: hub rules on disk in /etc/prometheus but absent from
    rule_files must fail the check."""
    repo, deployed, script = make_env(tmp_path)
    write_prometheus(deployed, ["aitbc_rules.yml"])
    for name in ("aitbc_rules.yml", "aitbc_hub_rules.yml"):
        (deployed / name).write_text((repo / name).read_text())

    res = run(script, deployed)
    assert res.returncode == 1
    assert "aitbc_hub_rules.yml" in res.stdout
    assert "not in rule_files" in res.stdout


def test_unlisted_repo_rule_without_deployed_copy_is_skipped(tmp_path):
    """Hosts that never deployed hub rules (nodes) must not false-positive."""
    repo, deployed, script = make_env(tmp_path)
    write_prometheus(deployed, ["aitbc_rules.yml"])
    (deployed / "aitbc_rules.yml").write_text(RULES_A)
    # aitbc_hub_rules.yml deliberately NOT copied to deployed dir.

    res = run(script, deployed)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "not deployed on this host" in res.stderr


def test_listed_file_missing_deployed_copy_fails(tmp_path):
    repo, deployed, script = make_env(tmp_path)
    write_prometheus(deployed, ["aitbc_rules.yml", "aitbc_hub_rules.yml"])
    (deployed / "aitbc_rules.yml").write_text(RULES_A)
    # aitbc_hub_rules.yml listed but not deployed.

    res = run(script, deployed)
    assert res.returncode == 1
    assert "aitbc_hub_rules.yml (missing)" in res.stdout


def test_listed_file_content_drift_fails(tmp_path):
    repo, deployed, script = make_env(tmp_path)
    write_prometheus(deployed, ["aitbc_rules.yml"])
    (deployed / "aitbc_rules.yml").write_text("groups: []\n")  # differs
    (deployed / "aitbc_hub_rules.yml").write_text(RULES_B)

    res = run(script, deployed)
    assert res.returncode == 1
    assert "aitbc_rules.yml" in res.stdout


def test_all_consistent_passes(tmp_path):
    repo, deployed, script = make_env(tmp_path)
    write_prometheus(deployed, ["aitbc_rules.yml", "aitbc_hub_rules.yml"])
    for name in ("aitbc_rules.yml", "aitbc_hub_rules.yml"):
        (deployed / name).write_text((repo / name).read_text())

    res = run(script, deployed)
    assert res.returncode == 0, res.stdout + res.stderr


class _RulesAPI(BaseHTTPRequestHandler):
    payload = {"status": "success", "data": {"groups": []}}

    def do_GET(self):
        if self.path == "/api/v1/rules":
            body = json.dumps(self.payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture()
def rules_api():
    server = HTTPServer(("127.0.0.1", 0), _RulesAPI)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=5)


def test_live_flags_listed_but_not_loaded(tmp_path, rules_api):
    repo, deployed, script = make_env(tmp_path)
    write_prometheus(deployed, ["aitbc_rules.yml", "aitbc_hub_rules.yml"])
    for name in ("aitbc_rules.yml", "aitbc_hub_rules.yml"):
        (deployed / name).write_text((repo / name).read_text())
    _RulesAPI.payload = {
        "status": "success",
        "data": {"groups": [{"name": "aitbc", "file": "/etc/prometheus/aitbc_rules.yml", "rules": []}]},
    }

    res = run(script, "--live", deployed, env={"PROMETHEUS_API": rules_api})
    assert res.returncode == 1
    assert "aitbc_hub_rules.yml (listed but not loaded)" in res.stdout


def test_live_passes_when_all_loaded(tmp_path, rules_api):
    repo, deployed, script = make_env(tmp_path)
    write_prometheus(deployed, ["aitbc_rules.yml", "aitbc_hub_rules.yml"])
    for name in ("aitbc_rules.yml", "aitbc_hub_rules.yml"):
        (deployed / name).write_text((repo / name).read_text())
    _RulesAPI.payload = {
        "status": "success",
        "data": {
            "groups": [
                {"name": "aitbc", "file": "/etc/prometheus/aitbc_rules.yml", "rules": []},
                {"name": "aitbc-hub", "file": "/etc/prometheus/aitbc_hub_rules.yml", "rules": []},
            ]
        },
    }

    res = run(script, "--live", deployed, env={"PROMETHEUS_API": rules_api})
    assert res.returncode == 0, res.stdout + res.stderr


def test_live_unreachable_exits_2(tmp_path):
    repo, deployed, script = make_env(tmp_path)
    write_prometheus(deployed, ["aitbc_rules.yml"])
    (deployed / "aitbc_rules.yml").write_text(RULES_A)

    res = run(
        script,
        "--live",
        deployed,
        env={"PROMETHEUS_API": "http://127.0.0.1:1"},
    )
    assert res.returncode == 2
    assert "cannot reach" in res.stderr
    assert "cannot reach" in res.stderr
