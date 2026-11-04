"""#1023 pin: install-nginx-node.sh must never leave a half-applied config.

Before the fix the script overwrote sites-available, then ran the sed
and `nginx -t` — any failure left the unsubstituted example (or a
slash-broken server_name) live. The fix renders to a temp file, tests
with `nginx -t -c`, and only then moves into place.

Pins drive the script against a scratch tree via its env overrides
(NGINX_SITES_*, NGINX_BIN, NGINX_RELOAD=0) — never real /etc paths.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/setup/install-nginx-node.sh"


def _scratch(tmp_path: Path, failing_nginx: bool, hub_url: str) -> dict:
    etc = tmp_path / "etc"
    (etc / "nginx/sites-available").mkdir(parents=True)
    (etc / "nginx/sites-enabled").mkdir(parents=True)
    (etc / "nginx/conf.d").mkdir(parents=True)
    site = etc / "nginx/sites-available/aitbc"
    site.write_text("server_name custom.local; # local edit must survive\n")

    stub = tmp_path / "nginx"
    stub.write_text("#!/usr/bin/env bash\nexit %d\n" % (1 if failing_nginx else 0))
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    env = dict(os.environ)
    env.update(
        {
            "NGINX_SITES_AVAILABLE": str(site),
            "NGINX_SITES_ENABLED": str(etc / "nginx/sites-enabled/aitbc"),
            "NGINX_OVERRIDE": str(etc / "nginx/conf.d/aitbc-hostname.conf"),
            "NGINX_BIN": str(stub),
            "NGINX_RELOAD": "0",
            "HUB_DISCOVERY_URL": hub_url,
        }
    )
    return {"site": site, "env": env}


def test_failed_render_test_leaves_previous_config(tmp_path):
    sc = _scratch(tmp_path, failing_nginx=True, hub_url="http://hub.aitbc.example:8102")
    res = subprocess.run(["bash", str(SCRIPT)], env=sc["env"], capture_output=True, text=True)
    assert res.returncode != 0
    # the pre-existing site with its local edit is untouched
    assert sc["site"].read_text() == "server_name custom.local; # local edit must survive\n"


def test_success_applies_substituted_config(tmp_path):
    sc = _scratch(tmp_path, failing_nginx=False, hub_url="http://hub.aitbc.example:8102")
    res = subprocess.run(["bash", str(SCRIPT)], env=sc["env"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    rendered = sc["site"].read_text()
    assert "server_name _;" not in rendered
    # scheme/port stripped from the URL — server_name is a bare host line
    server_line = next(l for l in rendered.splitlines() if "server_name" in l and ";" in l)
    assert "http" not in server_line
    assert "8102" not in server_line


def test_hostform_hub_url_also_works(tmp_path):
    sc = _scratch(tmp_path, failing_nginx=False, hub_url="hub.aitbc.invalid")
    res = subprocess.run(["bash", str(SCRIPT)], env=sc["env"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
