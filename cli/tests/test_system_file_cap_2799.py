"""AUDIT-EDGE-CLI-SYSTEM-FILE-UNBOUNDED (#2799): ``system file`` read any
allowlisted path whole — multi-GB chain.db-adjacent stores under
/var/lib/aitbc OOM'd the CLI. Reads are now capped at 4 MiB with an
explicit truncation marker.
"""

from click.testing import CliRunner


def test_system_file_read_is_size_capped(monkeypatch, tmp_path):
    import aitbc_cli.commands.system as system_mod

    monkeypatch.setattr(system_mod, "_ALLOWED_READ_PREFIXES", (str(tmp_path) + "/",))
    monkeypatch.setattr(system_mod, "_FILE_READ_MAX_BYTES", 16)
    big = tmp_path / "big.log"
    big.write_bytes(b"x" * 100)
    result = CliRunner().invoke(system_mod.system, ["file", "--path", str(big)], obj={"output_format": "table"})
    assert result.exit_code == 0, result.output
    assert "truncated" in result.output


def test_system_file_read_small_file_unaffected(monkeypatch, tmp_path):
    import aitbc_cli.commands.system as system_mod

    monkeypatch.setattr(system_mod, "_ALLOWED_READ_PREFIXES", (str(tmp_path) + "/",))
    small = tmp_path / "small.env"
    small.write_text("AITBC_FOO=bar\n")
    result = CliRunner().invoke(system_mod.system, ["file", "--path", str(small)], obj={"output_format": "table"})
    assert result.exit_code == 0, result.output
    assert "AITBC_FOO=bar" in result.output
    assert "truncated" not in result.output
