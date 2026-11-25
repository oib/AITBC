"""REPO-SPLIT-DECOUPLE-1 — update.sh treats ops checkout helpers as optional.

The product repo must not invoke the in-repo OPS script paths that the
carve-out deletes. These pins source update.sh (never run its main()) in a
scratch tree and exercise the two integration functions both ways:

* without a mock ``aitbc-ops`` checkout they warn and skip cleanly;
* with executable mock helpers under ``$AITBC_OPS_ROOT/scripts/...`` they call
  the helpers and still finish green.

No real /etc, /var, systemd, deployment script, or ops script is touched.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "deployment" / "update.sh"


def _write_exe(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)


def _sandbox(tmp_path: Path, *, with_ops: bool) -> tuple[dict[str, str], Path]:
    root = tmp_path / "product"
    ops = tmp_path / "ops-checkout"
    etc = tmp_path / "etc-aitbc"
    bin_dir = tmp_path / "bin"
    calls = tmp_path / "calls"
    for d in (root, etc, bin_dir):
        d.mkdir(parents=True, exist_ok=True)
    (etc / "website.env").write_text("WEBSITE_DOMAIN=hub.example.net\n")

    # deploy_prometheus_rules only considers hosts where systemd knows a
    # prometheus.service. The stub answers that one query and nothing else.
    _write_exe(
        bin_dir / "systemctl",
        '#!/bin/sh\nif [ "$1" = cat ] && [ "$2" = prometheus.service ]; then exit 0; fi\nexit 1\n',
    )

    if with_ops:
        _write_exe(
            ops / "scripts" / "ops" / "render-website.sh",
            "#!/bin/sh\n"
            'printf "render root=%s env=%s node=%s\\n" "$AITBC_ROOT" "$WEBSITE_ENV_FILE" "$NODE_ENV_FILE" >> "$CALLS_FILE"\n',
        )
        _write_exe(
            ops / "scripts" / "monitoring" / "deploy-rules.sh",
            '#!/bin/sh\nprintf "deploy-rules cwd=%s\\n" "$PWD" >> "$CALLS_FILE"\n',
        )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "AITBC_ROOT": str(root),
            "AITBC_OPS_ROOT": str(ops),
            "AITBC_ETC_DIR": str(etc),
            "AITBC_NODE_ENV_FILE": str(etc / "node.env"),
            "AITBC_BLOCKCHAIN_ENV_FILE": str(etc / "blockchain.env"),
            "CALLS_FILE": str(calls),
        }
    )
    return env, calls


def _run_functions(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    script = f'source "{UPDATE_SH}"; render_website_files; deploy_prometheus_rules\n'
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=20, check=False)


def test_update_skips_optional_ops_helpers_cleanly_without_ops_checkout(tmp_path: Path) -> None:
    env, calls = _sandbox(tmp_path, with_ops=False)
    result = _run_functions(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not calls.exists()
    assert "skipping optional website render" in result.stderr
    assert "skipping optional Prometheus rules sync" in result.stderr
    assert str(REPO_ROOT / "scripts" / "ops") not in result.stderr


def test_update_prefers_executable_helpers_from_ops_checkout(tmp_path: Path) -> None:
    env, calls = _sandbox(tmp_path, with_ops=True)
    result = _run_functions(env)

    assert result.returncode == 0, result.stdout + result.stderr
    text = calls.read_text()
    assert "render root=" in text
    assert "deploy-rules" in text
    assert "Website branding rendered" in result.stdout
    assert "Prometheus rules synced" in result.stdout
    assert str(tmp_path / "product") in text
    assert str(tmp_path / "etc-aitbc" / "website.env") in text


def test_update_has_no_in_repo_ops_invocation_paths() -> None:
    text = UPDATE_SH.read_text()
    assert "$AITBC_ROOT/scripts/ops/render-website.sh" not in text
    assert "$AITBC_ROOT/scripts/monitoring/deploy-rules.sh" not in text
    assert "$AITBC_OPS_ROOT/scripts/ops/render-website.sh" in text
    assert "$AITBC_OPS_ROOT/scripts/monitoring/deploy-rules.sh" in text
