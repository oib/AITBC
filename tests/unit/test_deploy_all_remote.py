"""#887: deploy-all-remote.sh stages the real deploy/ paths with
deploy-env.sh beside them and fails fast (set -euo pipefail).

On base the two scp lines pointed at a directory that no longer exists,
deploy-env.sh never travelled with them (each remote script sources it at
line 8), and with no `set -e` the run printed "Deployment complete!"
after the missing-file failures.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deployment" / "deploy" / "deploy-all-remote.sh"
DEPLOY = SCRIPT.parent


def test_staged_paths_exist_and_include_deploy_env():
    src = SCRIPT.read_text()
    assert "set -euo pipefail" in src
    for name in ("deploy-blockchain-remote.sh", "deploy-explorer-remote.sh", "deploy-env.sh", "deploy-in-container.sh"):
        assert name in src, f"{name} not staged"
        assert (DEPLOY / name).is_file()
    assert "scripts/deployment/deploy-blockchain-remote.sh" not in src, "stale parent-dir path still referenced"


def test_scp_invocation_lists_every_staged_file(tmp_path):
    """Drive the copy step with stubbed scp/ssh/rsync and assert the files
    actually pushed — all scratch, nothing remote touched."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "calls.log"
    for name in ("scp", "ssh", "rsync", "sleep"):
        stub = bindir / name
        stub.write_text(f'#!/bin/bash\necho "{name} $@" >> "{log}"\nexit 0\n')
        stub.chmod(0o755)
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "AITBC_SSH_TARGET": "stub@host.invalid",
        "AITBC_PUBLIC_HOST": "stub.invalid",
    }
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    calls = log.read_text() if log.exists() else ""
    scp_calls = [line for line in calls.splitlines() if line.startswith("scp ")]
    assert scp_calls, f"no scp call logged: {result.stdout + result.stderr}"
    for name in ("deploy-blockchain-remote.sh", "deploy-explorer-remote.sh", "deploy-env.sh", "deploy-in-container.sh"):
        assert any(name in line for line in scp_calls), f"{name} missing from scp staging"
    # every staged local path must be a real file under deploy/
    for line in scp_calls:
        for token in line.split()[1:]:
            if token.endswith(".sh") and ":" not in token:
                assert Path(token).is_file(), f"scp stages a non-existent path: {token}"
