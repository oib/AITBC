"""#886: print_success must be defined and every caller must source it.

Five deploy/ scripts ended with print_success and defined only
print_status/print_warning — `set -e` killed each with exit 127 after a
successful deploy. The function now lives in deploy-env.sh, which every
caller sources.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "scripts" / "deployment" / "deploy"


def test_deploy_env_defines_print_success():
    result = subprocess.run(
        ["bash", "-c", f'source "{DEPLOY}/deploy-env.sh" && print_success "done"'],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "done" in result.stdout


def test_every_print_success_caller_sources_deploy_env():
    callers = [p for p in DEPLOY.glob("*.sh") if "print_success " in p.read_text() or "print_success\n" in p.read_text()]
    callers = [p for p in DEPLOY.glob("*.sh") if "print_success" in p.read_text() and "deploy-env.sh" != p.name]
    assert callers, "no callers found — test is blind"
    for p in callers:
        src = p.read_text()
        assert 'source "$(dirname "$0")/deploy-env.sh"' in src, f"{p.name} calls print_success without sourcing deploy-env.sh"
