"""#891: deploy-explorer.sh's nginx insert is idempotent.

On base every run sed-inserted the /explorer/ locations again; run two
produced a duplicate-location config that fails nginx -t. Now a grep
guard skips the insert, the aliases derive from AITBC_EXPLORER_DIR, and
the backup is timestamped instead of overwritten.
"""

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deployment" / "deploy" / "deploy-explorer.sh"


def _run_nginx_step(tmp_path):
    """Drive just the nginx step against a scratch config via a stub ssh."""
    conf = tmp_path / "aitbc"
    if not conf.exists():
        conf.write_text("server {\n    listen 80;\n    # Health endpoint\n    location /health { return 200; }\n}\n")
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "ssh").write_text(
        '#!/bin/bash\nshift\ncmd="$1"\ncmd="${cmd//\\/etc\\/nginx\\/sites-available\\/aitbc/$AITBC_NGINX_CONFIG}"\nbash -c "$cmd"\n'
    )
    (bindir / "ssh").chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["AITBC_DEPLOY_SERVER"] = "stub@host.invalid"
    env["AITBC_NGINX_CONFIG"] = str(conf)
    env["AITBC_EXPLORER_DIR"] = str(tmp_path / "explorer")
    # Run only the nginx-update portion: everything before is build/scp; stub ssh runs locally.
    script = SCRIPT.read_text()
    step = script[script.index('ssh "$SERVER" "cp') : script.index('ssh "$SERVER" "nginx -t')]
    # NGINX_CONFIG is a script var, not exported — give the remote command
    # its value the way the real script would (the ssh stub just evals it).
    step = 'export NGINX_CONFIG="$AITBC_NGINX_CONFIG" EXPLORER_DIR="$AITBC_EXPLORER_DIR"\nprint_status() { true; }\n' + step
    return env, conf, subprocess.run(["bash", "-c", step], env=env, capture_output=True, text=True, timeout=30)


def test_second_run_does_not_duplicate_locations(tmp_path):
    env, conf, r1 = _run_nginx_step(tmp_path)
    assert r1.returncode == 0, r1.stderr
    after_one = conf.read_text()
    assert after_one.count("location /explorer/ {") == 1
    env2, conf2, r2 = _run_nginx_step(tmp_path)
    assert r2.returncode == 0, r2.stderr
    after_two = conf.read_text()
    assert after_two.count("location /explorer/ {") == 1, "second run inserted a duplicate location"


def test_alias_follows_explorer_dir_and_backup_is_timestamped(tmp_path):
    env, conf, _ = _run_nginx_step(tmp_path)
    text = conf.read_text()
    assert f"alias {tmp_path}/explorer/dist/" in text
    backups = list(tmp_path.glob("aitbc.backup*"))
    assert backups and any(b.name != "aitbc.backup" for b in backups), "backup should be timestamped"


def test_nginx_config_path_is_overridable():
    src = SCRIPT.read_text()
    assert "AITBC_NGINX_CONFIG:-" in src
