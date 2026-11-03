"""#838: scripts/deployment must not copy env files between hosts or install unpinned packages.

provision_node.sh scp'd another node's key-bearing /etc/aitbc/blockchain.env
and pip-installed outside the lockfile; deploy-integrated-blockchain-node.sh
and setup.sh had the same bare-package fallback. Pinned so the shapes cannot
come back.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO / "scripts" / "deployment"


def _scripts():
    return {p.name: p.read_text() for p in DEPLOY_DIR.glob("*.sh")}


def test_no_script_copies_an_env_file_between_hosts():
    """No scp/rsync/cp of an /etc/aitbc env file from another host's path."""
    for name, text in _scripts().items():
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\b(scp|rsync)\b", line) and "/etc/aitbc" in line:
                raise AssertionError(f"{name}:{i} copies an env file between hosts: {line.strip()}")


def test_no_bare_pip_install_in_deployment_scripts():
    """Every pip install names a requirements file, an editable path, or pip itself."""
    allowed = re.compile(r"pip install( -q)? .*(-r\s|--upgrade|^-e|-e\s)")
    for name, text in _scripts().items():
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = re.search(r"pip install (.+)", stripped)
            if m and not allowed.search(stripped):
                raise AssertionError(f"{name}:{i} installs packages outside the lockfile: {stripped}")


def test_provision_node_is_gone():
    """The env-copying provisioner was deleted (#838), not patched around."""
    assert not (DEPLOY_DIR / "provision_node.sh").exists()
