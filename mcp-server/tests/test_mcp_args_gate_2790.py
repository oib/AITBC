"""AUDIT-EDGE pin: #2790 — args-position option smuggling + non-verb flags.

run_aitbc_cli renders args as shlex.quoted tokens but Click re-parses
option-shaped tokens as options regardless of position, and the gates
never scanned args for them — ``args=['--rpc-url=http://attacker']`` rode
the read allowlist into a credential-bearing SSRF. Non-verb flag names
(--force/--yes/--confirm/--overwrite/--no-encrypt) likewise bypassed the
exact-match destructive-verb check.
"""

import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_cli_helpers as helpers  # noqa: E402


def test_option_shaped_args_are_not_read_only() -> None:
    assert not helpers._is_aitbc_subcommand_read_only(["list"], "wallet", ["--rpc-url=http://attacker"])
    assert not helpers._is_aitbc_subcommand_read_only(["list"], "wallet", ["--force"])
    assert not helpers._is_aitbc_subcommand_read_only(["list"], "wallet", ["-f"])
    assert not helpers._is_aitbc_subcommand_read_only(["list"], "wallet", ["--opt=value"])


def test_positional_and_numeric_args_still_read_only() -> None:
    assert helpers._is_aitbc_subcommand_read_only(["list"], "wallet", None)
    assert helpers._is_aitbc_subcommand_read_only(["list"], "wallet", ["-5"])
    assert helpers._is_aitbc_subcommand_read_only(["list"], "wallet", ["0xabc123"])
    assert helpers._looks_like_option_token("-") is False
    assert helpers._looks_like_option_token("--") is False


def test_non_verb_flag_names_are_mutation_class() -> None:
    for key in ("force", "yes", "confirm", "overwrite", "no-encrypt"):
        assert helpers._option_key_suggests_mutation(key), key
    for key in ("mine", "limit", "format", "all", "recursive"):
        assert not helpers._option_key_suggests_mutation(key), key
