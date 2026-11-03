"""#881: deploy-agent-protocols.sh is removed.

The script could never run: it pip-installed ``sqlite3`` — a package that
does not exist on PyPI — so ``set -e`` aborted it on the very first step.
The units it copied (``deployment/agent-protocols/aitbc-agent-registry.
service`` and ``aitbc-agent-coordinator.service``) do not exist anywhere
in the repo either; the real agent-coordinator unit lives at
``apps/agent-coordinator/aitbc-agent-coordinator.service`` and is
installed by setup.sh. Nothing referenced the script — it is deleted,
not repaired.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deployment" / "deploy-agent-protocols.sh"


def test_script_is_gone():
    assert not SCRIPT.exists(), (
        "deploy-agent-protocols.sh still exists; it pip-installs the "
        "non-existent 'sqlite3' package and references unit files that "
        "were never in the repo — delete it"
    )


def test_nothing_references_the_script():
    import subprocess

    out = subprocess.run(
        ["git", "-C", str(REPO), "grep", "-n", "deploy-agent-protocols"],
        capture_output=True,
        text=True,
    ).stdout
    # The only allowed mention is this test's own name for the file.
    lines = [line for line in out.splitlines() if "test_deploy_agent_protocols_removed" not in line]
    assert not lines, f"stale references to deploy-agent-protocols.sh: {lines}"
