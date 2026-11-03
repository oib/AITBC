"""#920: dashboard.sh reads the live system, not an in-process demo.

On base the consensus line came from a fresh MultiValidatorPoA object
with two invented validators, service lines were hardcoded strings, and
the port list watched a port the RPC does not use. Now it queries the
local RPC, the env file, and systemctl.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / "scripts" / "monitoring" / "dashboard.sh").read_text()


def test_no_fabricated_consensus_or_static_service_lines():
    assert "MultiValidatorPoA" not in SRC
    assert "0xvalidator" not in SRC
    assert "LIMITED" not in SRC  # the hardcoded yellow lines are gone


def test_live_queries_present():
    assert "curl -sf --max-time 5" in SRC and "/rpc/head" in SRC
    assert "systemctl is-active" in SRC
    assert "aitbc-blockchain-rpc" in SRC


def test_ports_come_from_the_env_file():
    assert "rpc_bind_port" in SRC.lower()
    assert '"8006" "30303" "9090"' not in SRC
