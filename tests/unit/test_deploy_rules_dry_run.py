"""Pins for scripts/monitoring/deploy-rules.sh --dry-run (#1498).

The script copies rule files into the deployed dir and reloads prometheus;
--dry-run must print the plan and change nothing. Like
test_check_rules_deployed.py, each test copies the real script into a scratch
repo dir with fixture ``*_rules.yml`` files and points ``deployed-dir`` at a
scratch dir.
"""

import shutil
import subprocess
from pathlib import Path

REPO_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "deploy-rules.sh"

RULES_A = "groups:\n  - name: aitbc\n    rules: []\n"
RULES_B = "groups:\n  - name: aitbc-hub\n    rules: []\n"


def make_env(tmp_path: Path):
    repo = tmp_path / "repo"
    deployed = tmp_path / "deployed"
    repo.mkdir()
    deployed.mkdir()
    script = repo / "deploy-rules.sh"
    shutil.copy(REPO_SCRIPT, script)
    script.chmod(0o755)
    (repo / "aitbc_rules.yml").write_text(RULES_A)
    (repo / "aitbc_hub_rules.yml").write_text(RULES_B)
    (deployed / "prometheus.yml").write_text("rule_files:\n  - aitbc_rules.yml\n  - aitbc_hub_rules.yml\nscrape_configs: []\n")
    return repo, deployed, script


def run(script: Path, *args):
    return subprocess.run(
        ["bash", str(script), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_dry_run_reports_but_writes_nothing(tmp_path):
    repo, deployed, script = make_env(tmp_path)
    stale = "groups: []\n"  # deployed copy differs from the repo copy
    (deployed / "aitbc_rules.yml").write_text(stale)
    (deployed / "aitbc_hub_rules.yml").write_text(RULES_B)  # already in sync

    res = run(script, "--dry-run", "--no-reload", deployed)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "aitbc_rules.yml (would deploy)" in res.stdout
    assert "aitbc_hub_rules.yml (unchanged)" in res.stdout
    assert "would reload prometheus" not in res.stdout  # --no-reload suppresses it
    # Nothing was written.
    assert (deployed / "aitbc_rules.yml").read_text() == stale


def test_dry_run_announces_the_reload_it_skips(tmp_path):
    _repo, deployed, script = make_env(tmp_path)

    res = run(script, "--dry-run", deployed)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "would deploy" in res.stdout
    assert "dry-run: would reload prometheus" in res.stdout
    # systemctl was never reached: the deployed files are still absent.
    assert not (deployed / "aitbc_rules.yml").exists()
    assert not (deployed / "aitbc_hub_rules.yml").exists()
