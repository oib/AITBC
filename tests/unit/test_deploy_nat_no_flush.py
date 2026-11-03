"""#885: deploy scripts must not flush the host's nat table.

On base, deploy-to-aitbc-container.sh and the remote block of
deploy-blockchain-and-explorer.sh ran ``iptables -t nat -F PREROUTING``
and ``-F POSTROUTING`` before adding their DNAT rules — wiping every
forwarding rule other deployments had installed — then snapshot the
resulting table into /etc/iptables/rules.v4 and installed
iptables-persistent, persisting a nat table the script never built.

The fix adds only this deployment's rules with the idempotent
-C-check/-A-add pattern in deploy-env.sh's setup_dnat, drops every flush,
and never creates /etc/iptables just to persist — when the host has no
persistence directory the rules are runtime-only and the script says so.
"""

import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "scripts" / "deployment" / "deploy"
ENV_SH = DEPLOY / "deploy-env.sh"
CONTAINER_SH = DEPLOY / "deploy-to-aitbc-container.sh"
EXPLORER_SH = DEPLOY / "deploy-blockchain-and-explorer.sh"


def test_no_nat_flush_anywhere():
    for script in (ENV_SH, CONTAINER_SH, EXPLORER_SH):
        src = script.read_text()
        assert not re.search(r"iptables\s+-t\s+nat\s+-F", src), f"{script.name} still flushes the nat table"


def test_additions_are_idempotent_checks():
    env_src = ENV_SH.read_text()
    body = env_src[env_src.index("setup_dnat()") : env_src.index("persist_dnat()")]
    assert re.search(r"iptables\s+-t\s+nat\s+-C\s+PREROUTING[^|]*\|\|[\s\\]*iptables\s+-t\s+nat\s+-A", body), (
        "setup_dnat does not guard PREROUTING additions with -C"
    )
    assert re.search(r"-C\s+POSTROUTING", body), "setup_dnat does not guard POSTROUTING additions with -C"

    explorer_src = EXPLORER_SH.read_text()
    assert re.search(r"-C\s+PREROUTING", explorer_src) and re.search(r"-C\s+POSTROUTING", explorer_src), (
        "remote DNAT block does not use the -C/-A idempotent pattern"
    )


def test_no_forced_persistence():
    for script in (CONTAINER_SH, EXPLORER_SH):
        src = script.read_text()
        assert "mkdir -p /etc/iptables" not in src, f"{script.name} creates /etc/iptables to persist a foreign table"
        assert "iptables-persistent" not in src, f"{script.name} installs iptables-persistent over foreign rules"
    # The remote block may persist only into a pre-existing /etc/iptables.
    src = EXPLORER_SH.read_text()
    for _m in re.finditer(r"[^\n]*iptables-save[^\n]*", src):
        assert "[ -d /etc/iptables ]" in src, "iptables-save is not gated on a pre-existing /etc/iptables"


def test_setup_dnat_idempotent_and_no_flush(tmp_path):
    """Drive deploy-env.sh's setup_dnat twice against a stub iptables."""
    rules = tmp_path / "rules"
    calls = tmp_path / "calls"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = """#!/bin/bash
echo "$*" >> "$IPT_CALLS"
op=""; rule=""
while [ $# -gt 0 ]; do
  case "$1" in
    -t) shift 2 ;;
    -C) op=C; shift ;;
    -A) op=A; shift ;;
    -F|-X) echo "FLUSH $*" >> "$IPT_CALLS"; echo "stub refusing flush" >&2; exit 99 ;;
    *) rule="${rule:+$rule }$1"; shift ;;
  esac
done
case "$op" in
  C) grep -Fxq "$rule" "$IPT_RULES" ;;
  A) echo "$rule" >> "$IPT_RULES" ;;
esac
"""
    (bindir / "iptables").write_text(stub)
    (bindir / "iptables").chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["IPT_RULES"] = str(rules)
    env["IPT_CALLS"] = str(calls)
    env["AITBC_DNAT_TARGET"] = "10.0.0.5"
    harness = f'source "{ENV_SH}"\nsetup_dnat 8202\nsetup_dnat 3000\n'
    r1 = subprocess.run(["bash", "-c", harness], env=env, capture_output=True, text=True, timeout=30)
    assert r1.returncode == 0, r1.stderr
    r2 = subprocess.run(["bash", "-c", harness], env=env, capture_output=True, text=True, timeout=30)
    assert r2.returncode == 0, r2.stderr

    call_lines = calls.read_text().splitlines()
    assert not any("FLUSH" in c for c in call_lines), "a nat flush was attempted"
    adds = [c for c in call_lines if c.startswith("-t nat -A")]
    checks = [c for c in call_lines if c.startswith("-t nat -C")]
    # Two runs x two ports x two chains = 4 adds total (second run all -C hits).
    assert len(adds) == 4, f"expected 4 rule additions across two runs, got {adds}"
    assert len(checks) == 8
    rule_lines = rules.read_text().splitlines()
    assert sum("--dport 8202 -j DNAT" in line for line in rule_lines) == 1
    assert sum("--dport 3000 -j MASQUERADE" in line for line in rule_lines) == 1
