"""Tests for scripts/ops/key_residue_census.py.

Every key here is a throwaway test value; the suite's core assertion is that
key text never reaches the output, only derived addresses do.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("eth_keys")
from eth_keys import keys  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "key_residue_census.py"


def _load():
    spec = importlib.util.spec_from_file_location("key_residue_census", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["key_residue_census"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def census():
    return _load()


def _key(seed: int) -> tuple[str, str]:
    """(private hex without 0x, lowercase derived address) for a throwaway seed."""
    pk = keys.PrivateKey(bytes([seed]) * 32)
    return pk.to_hex().removeprefix("0x"), str(pk.public_key.to_checksum_address()).lower()


RETIRED_ADDR = "0x03DF9Ed3788E5BA3991e6788036f9D171f027716".lower()
LIVE_ADDR = "0x11741E1A83E85117712113A29954583B1f2A2B1F".lower()


def _run(census, argv, capsys):
    code = census.main(argv)
    return code, capsys.readouterr().out


class TestAddressHits:
    def test_retired_address_reports_var_and_address_never_value(self, census, tmp_path, capsys):
        env = tmp_path / "svc.env"
        env.write_text(
            f"BRIDGE_RELEASE=0x2b0F2399680E2f3BdbBBC06bDc8D9a6b301D2DDe\nSETTLEMENT={RETIRED_ADDR}\nOTHER={LIVE_ADDR}\n"
        )
        code, out = _run(census, [str(tmp_path), "--retired", RETIRED_ADDR], capsys)
        assert code == 1
        assert f"address={RETIRED_ADDR}" in out
        assert "var=SETTLEMENT" in out
        assert all(LIVE_ADDR not in line for line in out.splitlines() if "HIT" in line)
        # the env line's raw text is never echoed
        assert "SETTLEMENT=0x03df" not in out.lower()

    def test_clean_tree_exits_zero(self, census, tmp_path, capsys):
        (tmp_path / "svc.env").write_text(f"ADDR={LIVE_ADDR}\nNAME=x\n")
        code, out = _run(census, [str(tmp_path), "--retired", RETIRED_ADDR], capsys)
        assert code == 0
        assert "HIT-ADDR" not in out

    def test_mixed_case_and_no_0x_match(self, census, tmp_path, capsys):
        (tmp_path / "unit.service").write_text(f"Environment=WATCH={RETIRED_ADDR.removeprefix('0x').upper()}\n")
        code, out = _run(census, [str(tmp_path), "--retired", RETIRED_ADDR], capsys)
        # ADDRESS regex needs 0x; a bare-hex value without 0x is not an address hit
        assert code == 0


class TestKeyDerivation:
    def test_0x_literal_derives_and_reports_retired(self, census, tmp_path, capsys):
        priv, addr = _key(41)
        (tmp_path / "run.env").write_text(f"HUB1_VALIDATOR_KEY=0x{priv}\n")
        code, out = _run(census, [str(tmp_path), "--retired", addr], capsys)
        assert code == 1
        assert f"derived={addr}" in out
        assert "retired=yes" in out
        assert priv not in out and ("0x" + priv) not in out

    def test_bare_hex_private_key_var_derives(self, census, tmp_path, capsys):
        priv, addr = _key(42)
        (tmp_path / "svc.env").write_text(f"BRIDGE_PAYOUT_PRIVATE_KEY={priv}\n")
        code, out = _run(census, [str(tmp_path), "--retired", RETIRED_ADDR], capsys)
        assert code == 0  # decoy key derives a non-retired address
        assert f"derived={addr}" in out
        assert "retired=no" in out
        assert "var=BRIDGE_PAYOUT_PRIVATE_KEY" in out
        assert priv not in out

    def test_retired_key_exits_one(self, census, tmp_path, capsys):
        priv, addr = _key(43)
        (tmp_path / "svc.env").write_text(f"OLD_PRIVATE_KEY={priv}\n")
        code, out = _run(census, [str(tmp_path), "--retired", addr, "--retired", RETIRED_ADDR], capsys)
        assert code == 1
        assert "retired=yes" in out
        assert priv not in out


class TestTraversal:
    def test_symlink_outside_root_is_refused(self, census, tmp_path, capsys):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.env").write_text(f"DEAD={RETIRED_ADDR}\n")
        root = tmp_path / "root"
        root.mkdir()
        (root / "link.env").symlink_to(outside / "secret.env")
        (root / "clean.env").write_text("X=1\n")
        code, out = _run(census, [str(root), "--retired", RETIRED_ADDR], capsys)
        assert code == 0  # refused, so the retired address in the target is NOT a hit
        assert "REFUSED-SYMLINK" in out
        assert "HIT-ADDR" not in out

    def test_symlink_root_arg_outside_is_refused(self, census, tmp_path, capsys):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.env").write_text(f"DEAD={RETIRED_ADDR}\n")
        link = tmp_path / "link"
        link.symlink_to(outside)
        code, out = _run(census, [str(link), "--retired", RETIRED_ADDR], capsys)
        assert code == 0
        assert "REFUSED-SYMLINK" in out
        assert "HIT-ADDR" not in out

    def test_symlink_inside_root_is_followed(self, census, tmp_path, capsys):
        real = tmp_path / "real.env"
        real.write_text(f"DEAD={RETIRED_ADDR}\n")
        (tmp_path / "link.env").symlink_to(real)
        code, out = _run(census, [str(tmp_path), "--retired", RETIRED_ADDR], capsys)
        assert code == 1
        assert "HIT-ADDR" in out

    def test_binary_file_is_skipped(self, census, tmp_path, capsys):
        blob = RETIRED_ADDR.encode() + b"\x00\xff\x01" * 16
        (tmp_path / "blob.db").write_bytes(blob)
        code, out = _run(census, [str(tmp_path), "--retired", RETIRED_ADDR], capsys)
        assert code == 0
        assert "SKIP-BINARY" in out
        assert "HIT" not in out

    def test_file_modes_are_reported(self, census, tmp_path, capsys):
        env = tmp_path / "svc.env"
        env.write_text("X=1\n")
        env.chmod(0o600)
        _, out = _run(census, [str(tmp_path), "--retired", RETIRED_ADDR], capsys)
        assert "mode=0o600" in out


class TestCli:
    def test_no_retired_addresses_is_usage_error(self, census, tmp_path):
        with pytest.raises(SystemExit):
            census.main([str(tmp_path)])

    def test_bad_address_arg_is_usage_error(self, census, tmp_path):
        with pytest.raises(SystemExit):
            census.main([str(tmp_path), "--retired", "not-an-address"])

    def test_retired_file_loads_addresses(self, census, tmp_path, capsys):
        (tmp_path / "retired.txt").write_text(f"# comment\n{RETIRED_ADDR}\n")
        (tmp_path / "svc.env").write_text(f"OLD={RETIRED_ADDR}\n")
        code, out = _run(census, [str(tmp_path / "svc.env"), "--retired-file", str(tmp_path / "retired.txt")], capsys)
        assert code == 1
        assert f"address={RETIRED_ADDR}" in out

    def test_missing_root_is_an_error_not_a_clean_scan(self, census, tmp_path, capsys):
        code, out = _run(census, [str(tmp_path / "nope"), "--retired", RETIRED_ADDR], capsys)
        assert code == 2
        assert "ERROR" in out
