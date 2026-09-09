"""Tests for the aitbc auth command group."""

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aitbc_cli.auth import AuthManager, ExpiredAdminToken
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class TestAuthCommands:
    """Test auth command group."""

    def test_auth_group_exists(self):
        from aitbc_cli.commands.auth import auth

        assert auth is not None
        assert auth.name == "auth"
        assert "login" in auth.commands
        assert "status" in auth.commands
        assert "logout" in auth.commands

    @patch("aitbc_cli.commands.auth.AITBCHTTPClient")
    @patch("aitbc_cli.commands.auth.Account")
    @patch("aitbc_cli.commands.auth.AuthManager")
    @patch("aitbc_cli.commands.auth.get_config")
    def test_auth_login_stores_token(
        self,
        mock_get_config,
        mock_auth_manager,
        mock_account,
        mock_http_class,
        runner,
        mock_config,
    ):
        mock_get_config.return_value = mock_config

        mock_client = mock_http_class.return_value
        mock_client.post.side_effect = [
            {"wallet_address": "0xcustomeraddress", "nonce": "nonce123", "expires_at": 1234567890},
            {"user_id": "user-1", "session_token": "jwt-token-xyz"},
        ]

        mock_account.from_key.return_value = MagicMock(
            address="0xCustomerAddress",
            sign_message=MagicMock(return_value=MagicMock(signature=MagicMock(hex=MagicMock(return_value="deadbeef")))),
        )

        mock_manager = MagicMock()
        mock_manager.store_credential.return_value = True
        mock_manager.backend_name = "file"
        mock_auth_manager.return_value = mock_manager

        from aitbc_cli.commands.auth import auth

        result = runner.invoke(
            auth,
            ["login", "--private-key", "0x" + "11" * 32, "--environment", "test"],
        )

        assert result.exit_code == 0, result.output
        assert mock_client.post.call_count == 2
        nonce_call, login_call = mock_client.post.call_args_list
        assert nonce_call.kwargs["json"] == {"wallet_address": "0xcustomeraddress"}
        assert login_call.kwargs["json"]["nonce"] == "nonce123"
        assert login_call.kwargs["json"]["signature"] == "0xdeadbeef"

        mock_manager.store_credential.assert_called_once_with("client", "jwt-token-xyz", environment="test")

    @patch("aitbc_cli.commands.auth.get_config")
    def test_auth_login_missing_credential_source(self, mock_get_config, runner, mock_config):
        mock_get_config.return_value = mock_config

        from aitbc_cli.commands.auth import auth

        result = runner.invoke(auth, ["login"])
        assert result.exit_code != 0
        assert "Provide --wallet, --private-key, or --private-key-file" in result.output

    @patch("aitbc_cli.commands.auth.AuthManager")
    def test_auth_status(self, mock_auth_manager, runner):
        mock_manager = MagicMock()
        mock_manager.list_credentials.return_value = {"client@default": "******"}
        mock_auth_manager.return_value = mock_manager

        from aitbc_cli.commands.auth import auth

        result = runner.invoke(auth, ["status"])
        assert result.exit_code == 0
        assert "client@default" in result.output

    @patch.object(AuthManager, "get_credential")
    def test_get_admin_token_falls_back_to_client(self, mock_get_credential, tmp_path):
        """An admin client should prefer the admin slot but accept a client JWT."""
        store = tmp_path / "creds.json"
        store.write_text("{}")
        mgr = AuthManager(store_path=store)

        # No admin token: fall back to client token.
        mock_get_credential.side_effect = [None, "client-jwt"]
        assert mgr.get_admin_token() == "client-jwt"

        # Admin token present: use it directly.
        mock_get_credential.side_effect = ["admin-jwt", None]
        assert mgr.get_admin_token() == "admin-jwt"

    def test_get_admin_token_raises_on_expired_jwt(self, tmp_path):
        """An expired JWT is surfaced before it reaches the server."""

        def _b64(v: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(v).encode()).decode().rstrip("=")

        expired_token = f"{_b64({'alg': 'none'})}.{_b64({'exp': 1})}."

        store = tmp_path / "creds.json"
        store.write_text("{}")
        mgr = AuthManager(store_path=store)

        with patch.object(mgr, "get_credential", return_value=expired_token):
            with pytest.raises(ExpiredAdminToken):
                mgr.get_admin_token()

    @patch("aitbc_cli.commands.auth.AuthManager")
    def test_auth_logout(self, mock_auth_manager, runner):
        mock_manager = MagicMock()
        mock_manager.delete_credential.return_value = True
        mock_auth_manager.return_value = mock_manager

        from aitbc_cli.commands.auth import auth

        result = runner.invoke(auth, ["logout"])
        assert result.exit_code == 0
        mock_manager.delete_credential.assert_called_once_with("client", environment="default")
