"""#2988 CLI-S90-TRANSCRIBE-URL-1: transcribe/reencode submits need an input.

The S90 paid leg found the gap: ``ai submit --type transcribe`` had no
enforced input flag — ``--input`` existed but ``--url`` (the natural name)
was rejected, and a submit without either would lock escrow for a job no
worker can execute.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.ai import ai
from aitbc_cli.commands.ai.submit import _require_media_input
from aitbc_cli.utils.error_handling import CLIError


def test_transcribe_without_input_aborts():
    with pytest.raises(CLIError, match="--input/--url is required"):
        _require_media_input(None, "transcribe", None)


def test_reencode_without_input_aborts():
    with pytest.raises(CLIError, match="--input/--url is required"):
        _require_media_input(None, "reencode", "")


def test_transcribe_with_input_passes():
    _require_media_input(None, "transcribe", "https://example.com/a.mp3")
    _require_media_input(None, "transcribe", "/tmp/a.mp3")


def test_non_media_type_without_input_passes():
    _require_media_input(None, "inference", None)


def test_submit_command_enforces_media_input():
    """Call-site pin: the guard must run inside ``submit`` itself, not just exist."""
    result = CliRunner().invoke(ai, ["submit", "--type", "transcribe"])
    assert "--input/--url is required for --type transcribe" in result.output


def test_url_flag_alias_is_accepted():
    """``--url`` must parse as the input flag, not die as an unknown option."""
    result = CliRunner().invoke(
        ai,
        ["submit", "--type", "transcribe", "--url", "https://example.com/a.mp3"],
    )
    assert "No such option" not in result.output
