"""#2947: edge commands must refuse cleanly on an expired stored credential.

Pre-fix ``_edge_auth_headers`` caught ``_OPS_ERRORS`` but not
``ExpiredAdminToken`` — a plain ``Exception`` subclass — so every
``aitbc edge`` command crashed with a raw traceback the moment the stored
admin JWT expired (the state the fleet was in after the 25 Nov re-credential
rotation, blocking S60/S66). The refusal must surface the re-login hint as a
clean CLIError, never a traceback and never a silently unauthenticated
request (bare 401).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

import aitbc_cli.auth as auth_mod
from aitbc_cli.commands import edge as edge_mod
from aitbc_cli.utils.error_handling import CLIError


@pytest.fixture
def runner():
    return CliRunner()


def _expired(self, *args, **kwargs):
    raise auth_mod.ExpiredAdminToken("The stored admin credential has expired. Run `aitbc auth login` to refresh it.")


def test_edge_status_expired_token_is_clean_refusal(runner):
    with patch.object(auth_mod.AuthManager, "get_admin_token", _expired):
        result = runner.invoke(edge_mod.edge, ["status"], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "aitbc auth login" in result.output
    # the failure is a CLIError (handled refusal), not the raw ExpiredAdminToken
    assert not isinstance(result.exception, auth_mod.ExpiredAdminToken)
    assert isinstance(result.exception, CLIError)


def test_edge_transfer_expired_token_is_clean_refusal(runner):
    """The crash was in shared client construction — every subcommand hit it,
    not just status."""
    with patch.object(auth_mod.AuthManager, "get_admin_token", _expired):
        result = runner.invoke(
            edge_mod.edge,
            ["transfer", "--to-address", "0x" + "ab" * 20, "--amount", "1.0"],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "aitbc auth login" in result.output
    assert not isinstance(result.exception, auth_mod.ExpiredAdminToken)


def test_expired_token_does_not_fall_back_to_unauthenticated(runner):
    """The refusal must not be swallowed into ``token = None`` — an
    unauthenticated request would surface as a bare 401 with no hint that
    re-login fixes it. ``CLIError`` is part of ``_OPS_ERRORS``, so a nested
    try would silently produce exactly that."""
    with patch.object(auth_mod.AuthManager, "get_admin_token", _expired):
        try:
            edge_mod._edge_auth_headers()
        except CLIError:
            return  # clean refusal — correct
        except auth_mod.ExpiredAdminToken:
            pytest.fail("raw ExpiredAdminToken escaped — traceback-class failure")
        pytest.fail("no refusal at all — the request would go out unauthenticated")
    pytest.fail("unreachable")


def test_missing_credential_still_unauthenticated_no_crash(runner):
    """No stored credential at all (get_admin_token returns None) keeps the
    old behavior: empty headers, server decides — no regression."""
    with patch.object(auth_mod.AuthManager, "get_admin_token", lambda self, *a, **k: None):
        assert edge_mod._edge_auth_headers() == {}
