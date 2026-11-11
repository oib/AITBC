"""#1778: failover-gen.py carve-out blocks must not echo client
X-Forwarded-Proto — same defect class as #1694 ($scheme, not
$http_x_forwarded_proto)."""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_gen():
    spec = importlib.util.spec_from_file_location("failover_gen", REPO / "scripts/ops/failover-gen.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_carveout_blocks_use_connection_scheme():
    gen = _load_gen()
    for modifier, location in gen.CARVE_RPC + gen.CARVE_EXP:
        for line in gen._blk(modifier, location, "target"):
            assert "$http_x_forwarded_proto" not in line, f"client-echo proto header in {location}"
            if "X-Forwarded-Proto" in line:
                assert line.rstrip().endswith("$scheme;"), f"proto not from $scheme in {location}: {line}"


def test_generator_source_has_no_client_echo():
    src = (REPO / "scripts/ops/failover-gen.py").read_text()
    assert "$http_x_forwarded_proto" not in src
