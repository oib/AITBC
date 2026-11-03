"""UTILS-ENV-CONFIG-DOCSTRINGS-RUN-AS-COMMANDS-1 — docstring text must not
execute as command words when the library is sourced."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
ENV_CONFIG = REPO_ROOT / "scripts/utils/env_config.sh"


def _source(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    """Source the library under strict mode in a scratch AITBC_ROOT."""
    root = tmp_path / "aitbc"
    for d in ("config", "apps", "scripts", "logs", "backups"):
        (root / d).mkdir(parents=True)
    script = f"set -euo pipefail\nsource {ENV_CONFIG}\n{body}\n"
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={
            "AITBC_ROOT": str(root),
            "AITBC_NODE0_HOST": "127.0.0.1",
            "AITBC_NODE1_HOST": "127.0.0.2",
            "PATH": "/usr/bin:/bin",
        },
    )


def test_no_triple_quote_docstrings_left():
    assert '"""' not in ENV_CONFIG.read_text()


def test_source_under_set_e_no_command_not_found(tmp_path):
    result = _source(tmp_path, "true")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "command not found" not in (result.stdout + result.stderr).lower()


def test_functions_run_without_command_words(tmp_path):
    result = _source(
        tmp_path,
        "get_config_value MISSING_KEY fallback > /dev/null\nis_dry_run || true\nis_debug || true\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
