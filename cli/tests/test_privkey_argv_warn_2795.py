"""AUDIT-EDGE-CLI-PRIVKEY-ARGV (#2795): ``--private-key`` values are visible
in ``ps`` and shell history; auth login and bond now warn like the bridge
key resolver (#2544), and ``--private-key-file`` warns on loose modes and
refuses empty files.
"""

import pytest


def test_private_key_argv_warns(capsys):
    from aitbc_cli.commands.auth import _resolve_private_key

    key = "ab" * 32
    assert _resolve_private_key(None, key, None, None) == key
    captured = capsys.readouterr()
    assert "process list" in captured.out + captured.err


def test_private_key_file_loose_mode_warns(tmp_path, capsys):
    from aitbc_cli.commands.auth import _resolve_private_key

    key_file = tmp_path / "key"
    key_file.write_text("cd" * 32)
    key_file.chmod(0o644)
    assert _resolve_private_key(None, None, str(key_file), None) == "cd" * 32
    captured = capsys.readouterr()
    assert "group/other-accessible" in captured.out + captured.err


def test_private_key_file_empty_refused(tmp_path):
    from aitbc_cli.commands.auth import _resolve_private_key

    key_file = tmp_path / "key"
    key_file.write_text("   \n")
    with pytest.raises(ValueError, match="empty"):
        _resolve_private_key(None, None, str(key_file), None)
