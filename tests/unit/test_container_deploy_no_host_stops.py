"""#893: container deploys must not stop host units, must fail on errors,
and take domain/container from env.

On base the three entry points ran `systemctl stop` on the HOST's own
units before deploying into the container and never restarted them;
container-deploy.py ignored every failed step and printed success;
deploy-domain.sh called `python` and hardcoded the domain/container.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
D = REPO / "scripts" / "deployment" / "deploy"


def test_no_host_unit_stops_in_container_deploys():
    for name in ("deploy-domain.sh", "deploy-to-aitbc-container.sh", "container-deploy.py"):
        src = (D / name).read_text()
        assert not re.search(r"systemctl\s+(?:\"?sudo\"?\s*,?\s*)?\"?stop\"?", src), f"{name} still stops host units"


def test_run_command_failures_are_fatal():
    src = (D / "container-deploy.py").read_text()
    body = src[src.index("def deploy_to_container") :]
    bare = [
        line
        for line in body.splitlines()
        if "run_command(" in line and "if not run_command" not in line and "ok = run_command" not in line
    ]
    assert bare == [], f"unchecked run_command calls: {bare}"
    assert "returncode != 0" in body, "incus file push is still unchecked"


def test_no_hardcoded_domain_container_or_python():
    src = (D / "deploy-domain.sh").read_text()
    assert 'DOMAIN="aitbc.' not in src and 'CONTAINER="aitbc"' not in src
    assert " python " not in src and not re.search(r"^\s*python\s", src, re.M)
    src2 = (D / "container-deploy.py").read_text()
    assert '"aitbc"' not in src2 or 'os.environ.get("AITBC_CONTAINER")' in src2
