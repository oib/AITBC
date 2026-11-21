"""#2392: AITBC_WALLET_PASSWORD_FILE may pass the MCP ``env`` allow-list.

Its value is a *path to* a root-provisioned password file — never the
password itself — so it is the same exposure class as the ``--password-file``
option the generated tools already expose. The path is pinned under
``/etc/aitbc/``; every other secret-shaped name stays refused.
"""

import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server


def test_password_file_env_allowed_under_etc_aitbc():
    assert mcp_server._validate_cli_env({"AITBC_WALLET_PASSWORD_FILE": "/etc/aitbc/wallets/r5.pw"}) is None


def test_password_file_env_rejected_outside_secret_root():
    for bad in (
        "/var/tmp/r5.pw",
        "/etc/shadow",
        "/root/.aitbc/r5.pw",
        "/etc/aitbc/../shadow",
        "/etc/aitbc",  # the root itself is a directory, not a file
    ):
        assert mcp_server._validate_cli_env({"AITBC_WALLET_PASSWORD_FILE": bad}) is not None, bad


def test_password_file_env_rejects_non_string_value():
    assert mcp_server._validate_cli_env({"AITBC_WALLET_PASSWORD_FILE": 42}) is not None  # type: ignore[dict-item]


def test_secret_value_names_still_refused():
    for name in (
        "AITBC_WALLET_PASSWORD",
        "AITBC_WALLET_PASSWORD_R5",
        "AITBC_NODE_PRIVATE_KEY",
        "AITBC_API_TOKEN",
    ):
        assert mcp_server._validate_cli_env({name: "/var/tmp/x"}) is not None, name


def test_scratch_env_still_works_alongside():
    assert (
        mcp_server._validate_cli_env(
            {
                "AITBC_WALLET_DIR": "/var/tmp/wallets",
                "AITBC_WALLET_PASSWORD_FILE": "/etc/aitbc/wallets/r5.pw",
            }
        )
        is None
    )
