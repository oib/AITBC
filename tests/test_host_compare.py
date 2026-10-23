"""Fixture tests for scripts/ops/host-compare.py (B4, note 1493).

Feeds the parser canned probe captures — no ssh, no systemd. Covers the
three real-world shapes observed on the fleet: ``list-unit-files``'s
three-column output, ``list-units``'s leading ``●`` on not-found units,
and ``EnvironmentFiles`` carrying ``(ignore_errors=…)`` annotations.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "host_compare",
    Path(__file__).resolve().parents[1] / "scripts" / "ops" / "host-compare.py",
)
hc = importlib.util.module_from_spec(_spec)
sys.modules["host_compare"] = hc
_spec.loader.exec_module(hc)


CAP_A = """\
@@HOST
hub.example
1000
boot_epoch 900
@@UNITS_FILES
aitbc-blockchain-node.service           enabled enabled
aitbc-coordinator-api.service           enabled enabled
aitbc-market.service                    enabled enabled
@@UNITS_ACTIVE
aitbc-blockchain-node.service loaded active running
aitbc-coordinator-api.service loaded active running
● aitbc-market.service not-found inactive dead
@@UNITENV
UNIT aitbc-blockchain-node.service
/etc/aitbc/aitbc-blockchain-node.env (ignore_errors=no)
/etc/aitbc/blockchain-secrets.env (ignore_errors=yes)
UNIT aitbc-coordinator-api.service
/etc/aitbc/aitbc-coordinator-api.env (ignore_errors=no)
@@ENVKEYS
FILE aitbc-blockchain-node.env
CHAIN_ID
VALIDATOR_SET
PROPOSER_ID
FILE aitbc-coordinator-api.env
DATABASE_URL
JWT_SECRET
@@CHAIN
DB /var/lib/aitbc/data/bc-2/chain.db
2396|0x3282edc274e5b2b8|2026-10-23 09:05:53.819341
SIZE 8392704
@@STORES
/var/lib/aitbc/data/coordinator.db 4194304
/var/lib/aitbc/data/keystore.db 32768
@@MEM
/sys/fs/cgroup/memory.current = 2510118912
/sys/fs/cgroup/memory.max = 4096000000
MemTotal:        4000000 kB
"""

CAP_B = """\
@@HOST
hub1.example
1010
boot_epoch 800
@@UNITS_FILES
aitbc-blockchain-node.service           enabled enabled
aitbc-blockchain-rpc.service            enabled enabled
@@UNITS_ACTIVE
aitbc-blockchain-node.service loaded active running
aitbc-blockchain-rpc.service loaded active running
@@UNITENV
UNIT aitbc-blockchain-node.service
/etc/aitbc/aitbc-blockchain-node.env (ignore_errors=no)
@@ENVKEYS
FILE aitbc-blockchain-node.env
CHAIN_ID
VALIDATOR_SET
FILE aitbc-blockchain-rpc.env
RPC_BIND_PORT
@@CHAIN
DB /var/lib/aitbc/data/bc-2/chain.db
2396|0x3282edc274e5b2b8|2026-10-23 09:05:53.819341
SIZE 8392704
@@STORES
/var/lib/aitbc/data/keystore.db 32768
@@MEM
/sys/fs/cgroup/memory.current = 2493431808
/sys/fs/cgroup/memory.max = max
MemTotal:        3909180 kB
"""


def _parse(a: str = CAP_A, b: str = CAP_B):
    ha = hc.parse(a, "hub")
    hb = hc.parse(b, "hub1")
    return ha, hb, hc.compare(ha, hb)


def test_sections_parse():
    ha, hb, _ = _parse()
    assert ha.sections["HOST"][0] == "hub.example"
    assert len(ha.sections["UNITS_FILES"]) == 3
    assert len(hb.sections["ENVKEYS"]) >= 2


def test_bullet_unit_stripped():
    ha, _, out = _parse()
    states = hc.active_states(ha.sections["UNITS_ACTIVE"])
    assert "aitbc-market.service" in states  # the ● prefix must not eat the name
    assert states["aitbc-market.service"] == "inactive/dead"
    assert not any(k == "●" for k in states)


def test_enabled_state_diffs():
    _, _, out = _parse()
    joined = "\n".join(out)
    assert "aitbc-coordinator-api.service" in joined
    assert "hub=enabled" in joined and "hub1=-" in joined


def test_envkey_names_only_diff():
    _, _, out = _parse()
    joined = "\n".join(out)
    # PROPOSER_ID exists only in A's node env; RPC file absent on A.
    assert "only-hub=['PROPOSER_ID']" in joined
    assert "aitbc-blockchain-rpc.env: absent on hub" in joined
    # Never a value: the fixture has no '=' values and the report must not invent any.
    assert "DATABASE_URL=" not in joined


def test_chain_match():
    _, _, out = _parse()
    joined = "\n".join(out)
    assert "h=2396" in joined and "MATCH" in joined


def test_chain_delta_reported():
    b_lagged = CAP_B.replace("2396|", "2390|").replace("0x3282edc274e5b2b8", "0xdeadbeef00000000")
    ha = hc.parse(CAP_A, "hub")
    hb = hc.parse(b_lagged, "hub1")
    joined = "\n".join(hc.compare(ha, hb))
    assert "delta=+6" in joined and "0xdeadbeef" in joined


def test_store_missing_side_shows_dash():
    _, _, out = _parse()
    joined = "\n".join(out)
    assert "coordinator.db: hub=4MB hub1=-" in joined
    assert "keystore.db: hub=32KB hub1=32KB" in joined


def test_unitenv_ignores_annotations():
    ha, _, _ = _parse()
    m = hc.unitenv_map(ha.sections["UNITENV"])
    assert m["aitbc-blockchain-node.service"] == [
        "/etc/aitbc/aitbc-blockchain-node.env",
        "/etc/aitbc/blockchain-secrets.env",
    ]


def test_main_offline_files(tmp_path):
    fa, fb = tmp_path / "a.txt", tmp_path / "b.txt"
    fa.write_text(CAP_A)
    fb.write_text(CAP_B)
    assert hc.main(["--a-file", str(fa), "--a-name", "hub", "--b-file", str(fb), "--b-name", "hub1"]) == 0
