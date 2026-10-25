"""MCP-ECHO-1: secret-bearing argument values are masked in every echoed command.

All values are obviously fake. The mask runs in ``_json`` on the echoed copy
only; the argv handed to ``subprocess`` must stay byte-identical.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_mask as mask  # noqa: E402
import aitbc_mcp_server as mcp_server  # noqa: E402

mcp_server._HOSTS_CONFIG = {
    "roles": {"hub": "hub", "customer": "node0", "shop": "node2"},
    "default_host": "hub",
    "ssh_user": "",
}

import aitbc_mcp_cli_tools_generated_http as generated_http  # noqa: E402
import aitbc_mcp_cli_tools_generated_system as generated_system  # noqa: E402

FAKE = "fake-secret-value-123"
FAKE_HEX = "0x" + "fa" * 32
MARKER = mask.MARKER
TX_HASH = "0x" + "ab" * 32
ADDRESS = "0x" + "12" * 20


def _recorder(host: str, command: str, timeout: int = 60) -> dict[str, object]:
    return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}


@pytest.fixture(autouse=True)
def _offline_run_remote():
    with mock.patch.object(mcp_server, "_run_remote", _recorder):
        yield


def _load_isolated_server():
    spec = importlib.util.spec_from_file_location("aitbc_mcp_server_echo_isolated", MCP_SERVER_DIR / "aitbc_mcp_server.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


# --- pattern coverage --------------------------------------------------------

SECRET_COMMANDS = [
    pytest.param(f"aitbc wallet send {ADDRESS} 1.0 --api-key={FAKE}", "--api-key=" + MARKER, id="option-equals"),
    pytest.param(f"aitbc wallet unlock --password {FAKE}", "--password " + MARKER, id="option-space"),
    pytest.param(f"aitbc exchange register --secret-key={FAKE}", "--secret-key=" + MARKER, id="secret-key"),
    pytest.param(f"aitbc market download --access-secret={FAKE}", "--access-secret=" + MARKER, id="access-secret"),
    pytest.param(f"aitbc wallet restore --mnemonic {FAKE}", "--mnemonic " + MARKER, id="mnemonic"),
    pytest.param(f"aitbc http call x --token={FAKE}", "--token=" + MARKER, id="token"),
    pytest.param(f"aitbc wallet import --private-key {FAKE_HEX}", "--private-key " + MARKER, id="hex-after-key-option"),
    pytest.param(f"aitbc http call x --idempotency-key={FAKE}", "--idempotency-key=" + MARKER, id="token-like-option"),
    pytest.param(f"aitbc system env-set aitbc-market FAKE_API_KEY={FAKE}", "FAKE_API_KEY=" + MARKER, id="env-set-positional"),
    pytest.param(
        f"cd /var/tmp/sc && HOME=/var/tmp/sc FAKE_TOKEN={FAKE} aitbc wallet list", "FAKE_TOKEN=" + MARKER, id="env-prefix"
    ),
    pytest.param(
        f"aitbc http call x --header='Authorization: Bearer {FAKE}'", "Authorization: " + MARKER, id="authorization-header"
    ),
    pytest.param(f"aitbc http call x --header 'X-API-Key: {FAKE}'", "X-API-Key: " + MARKER, id="x-api-key-header"),
    pytest.param(
        f"aitbc http call x --url=http://fake-user:{FAKE}@127.0.0.1:1/base", "fake-user:" + MARKER + "@", id="url-userinfo"
    ),
    pytest.param(f"aitbc http call market 'v1/demo?token={FAKE}'", "?token=" + MARKER, id="query-token"),
    pytest.param(f"aitbc http call market 'v1/demo?a=1&api_key={FAKE}'", "&api_key=" + MARKER, id="query-api-key"),
    pytest.param(f"aitbc http call market v1/demo --params=api_key={FAKE}", "--params=api_key=" + MARKER, id="params-pair"),
    pytest.param(
        f'aitbc http call coordinator-api v1/jobs --body=\'{{"api_key": "{FAKE}", "name": "fake-job"}}\'',
        '"api_key": "' + MARKER + '"',
        id="json-body",
    ),
]


@pytest.mark.parametrize(("command", "expected"), SECRET_COMMANDS)
def test_secret_shapes_masked_in_string_echo(command: str, expected: str) -> None:
    masked = mask.mask_command(command)
    assert isinstance(masked, str)
    assert FAKE not in masked and FAKE_HEX not in masked
    assert expected in masked


def test_json_body_keeps_non_secret_keys() -> None:
    masked = mask.mask_command(f'aitbc http call x --body=\'{{"api_key": "{FAKE}", "name": "fake-job"}}\'')
    assert '"name": "fake-job"' in masked


MUST_NOT_MASK = [
    pytest.param(f"aitbc explorer tx {TX_HASH}", id="bare-64-hex-tx-hash"),
    pytest.param(f"aitbc blockchain block --hash={TX_HASH}", id="block-hash"),
    pytest.param(f"aitbc explorer tx --tx-hash={TX_HASH}", id="tx-hash-option"),
    pytest.param(f"aitbc wallet send --to={ADDRESS} --from={ADDRESS} --address={ADDRESS} 1.0", id="addresses"),
    pytest.param("aitbc ipfs download --cid=bafyfakecid0000000000000000000000000000000000000", id="cid"),
    pytest.param("aitbc wallet balance --wallet=fake-wallet --name=fake-name --wallet-name fake-w", id="names"),
    pytest.param("aitbc market download --access-key=AKFAKE0000", id="access-key-public-half"),
    pytest.param(f"aitbc node info --public-key=0x{'0f' * 33}", id="public-key"),
    pytest.param("aitbc ai status --job-id=job-fake-1 --chain-id=ait-fake", id="ids"),
    pytest.param("aitbc wallet unlock --password-stdin fake-wallet", id="password-stdin-flag"),
    pytest.param("aitbc auth login --private-key-file=/var/tmp/fake.key", id="key-file-path"),
    pytest.param("AITBC_WALLET_DIR=/var/lib/aitbc/wallets aitbc wallet list", id="server-env-path"),
    pytest.param("aitbc http call market v1/demo --url=http://127.0.0.1:8000/base?limit=5", id="plain-url"),
    pytest.param("aitbc --output=json blockchain height", id="ordinary-read"),
]


@pytest.mark.parametrize("command", MUST_NOT_MASK)
def test_must_not_mask_values_unchanged(command: str) -> None:
    assert mask.mask_command(command) == command


def test_list_form_stays_list_and_caller_unchanged() -> None:
    argv = ["aitbc", "wallet", "unlock", "--token", FAKE, "--wallet", "fake-wallet", f"--api-key={FAKE}"]
    original = list(argv)
    masked = mask.mask_command(argv)
    assert masked == ["aitbc", "wallet", "unlock", "--token", MARKER, "--wallet", "fake-wallet", f"--api-key={MARKER}"]
    assert argv == original


def test_unbalanced_quotes_fall_back_to_regex() -> None:
    masked = mask.mask_command(f"aitbc wallet unlock --password={FAKE} 'unterminated")
    assert FAKE not in masked
    assert "--password=" + MARKER in masked


def test_mask_envelope_copies_and_masks_text_keys() -> None:
    envelope = {
        "command": f"aitbc wallet unlock --password {FAKE}",
        "details": [f"disallowed shell metacharacter in token: --api-key={FAKE};"],
        "error": f"refused --token={FAKE}",
        "stdout": "untouched",
        "nested": [{"argv": ["aitbc", "--secret", FAKE]}],
    }
    snapshot = json.dumps(envelope, sort_keys=True)
    masked = mask.mask_envelope(envelope)
    assert FAKE not in json.dumps(masked)
    assert masked["stdout"] == "untouched"
    assert json.dumps(envelope, sort_keys=True) == snapshot


# --- envelopes, through the real builders and _json --------------------------


def test_dry_run_echo_masked() -> None:
    out = mcp_server._json(mcp_server._build_dry_run("dry", f"aitbc wallet unlock --password {FAKE}", host="hub"))
    assert FAKE not in out and MARKER in out


def test_confirm_echo_masked() -> None:
    guard = mcp_server._require_confirm(False, False, f"aitbc wallet send --api-key={FAKE}", host="hub")
    assert guard is not None
    out = mcp_server._json(guard)
    assert FAKE not in out and "Confirmation required" in out


def test_result_and_timeout_echo_masked() -> None:
    command = f"aitbc wallet unlock --password {FAKE}"
    result = mcp_server._result_status({"host": "hub", "command": command, "returncode": 0, "stdout": "{}", "stderr": ""})
    assert FAKE not in mcp_server._json(result)
    timeout = mcp_server._timeout_result({"host": "hub"}, command, 5, subprocess.TimeoutExpired(command, 5))
    assert FAKE not in mcp_server._json(timeout)
    # Internal dicts keep the real command; only the serialized copy is masked.
    assert result["command"] == command


def test_run_aitbc_command_dry_run_masked() -> None:
    out = mcp_server.run_aitbc_command(role="hub", command=f"wallet unlock --password {FAKE}")
    assert FAKE not in out and "--password " + MARKER in out


def test_run_aitbc_command_refusal_text_masked() -> None:
    out = json.loads(mcp_server.run_aitbc_command(role="hub", command=f"wallet unlock --password={FAKE};"))
    assert out["error"] == "invalid command"
    assert FAKE not in json.dumps(out)


def test_run_aitbc_cli_dry_run_masked() -> None:
    out = mcp_server.run_aitbc_cli(group="wallet", subcommand="send", args=[ADDRESS, "1.0"], options={"api-key": FAKE})
    assert FAKE not in out and ADDRESS in out


def test_call_aitbc_http_dry_run_masked() -> None:
    out = mcp_server.call_aitbc_http(
        service="coordinator-api", path="v1/jobs", method="POST", body={"api_key": FAKE, "name": "fake-job"}, dry_run=True
    )
    assert FAKE not in out and "fake-job" in out


def test_generated_http_call_dry_run_masked() -> None:
    out = generated_http.aitbc_http_call(
        service="market",
        path=f"v1/demo?token={FAKE}",
        method="POST",
        params=f"api_key={FAKE}",
        url=f"http://fake-user:{FAKE}@127.0.0.1:1/base",
        idempotency_key=FAKE,
        role="hub",
    )
    assert FAKE not in out
    assert "v1/demo" in out and "127.0.0.1:1/base" in out


def test_generated_env_set_dry_run_masked() -> None:
    out = generated_system.aitbc_system_env_set(service="aitbc-market", assignments=[f"FAKE_API_KEY={FAKE}"], role="hub")
    assert FAKE not in out and "FAKE_API_KEY=" + MARKER in out


def test_ordinary_read_echo_unchanged() -> None:
    command = f"/opt/aitbc/venv/bin/aitbc --output=json explorer tx {TX_HASH} --address={ADDRESS}"
    out = json.loads(mcp_server._json(mcp_server._build_dry_run("dry", command)))
    assert out["command"] == command


# --- executed argv is byte-identical ------------------------------------------


def test_local_executed_argv_byte_identical() -> None:
    server = _load_isolated_server()
    command = f"HOME=/var/tmp/sc aitbc wallet unlock --password {FAKE} --api-key={FAKE}"
    run = mock.Mock(return_value=_completed(stdout="{}"))
    with mock.patch.object(server, "_is_local_host", return_value=True), mock.patch.object(server.subprocess, "run", run):
        out = server._json(server._run_remote("localhost", command))
    assert run.call_args[0][0] == shlex.split(command)[1:]
    assert run.call_args.kwargs["env"]["HOME"] == "/var/tmp/sc"
    assert FAKE not in out


def test_ssh_executed_command_byte_identical() -> None:
    server = _load_isolated_server()
    command = f"aitbc wallet unlock --password {FAKE}"
    run = mock.Mock(return_value=_completed(stdout="{}"))
    with mock.patch.object(server, "_is_local_host", return_value=False), mock.patch.object(server.subprocess, "run", run):
        out = server._json(server._run_remote("hub.aitbc", command))
    assert run.call_args[0][0][-1] == command
    assert FAKE not in out


# --- coverage: no envelope can skip the mask ----------------------------------

_SOURCES = sorted(p for p in MCP_SERVER_DIR.glob("*.py") if p.name != "aitbc_mcp_mask.py")
# json.dumps calls that encode an option value or stdout, never an envelope.
_OPTION_VALUE_DUMPS = {("aitbc_mcp_server.py", "_run_http"), ("aitbc_mcp_server.py", "_http_dry_run_command")}


def _json_dumps_calls(tree: ast.AST):
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "dumps"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "json"
                ):
                    yield fn.name, node


def _is_mask_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "mask_envelope"


def test_every_envelope_serialisation_goes_through_the_mask() -> None:
    unmasked = []
    for path in _SOURCES:
        for fn_name, call in _json_dumps_calls(ast.parse(path.read_text())):
            if _is_mask_call(call.args[0]) or (path.name, fn_name) in _OPTION_VALUE_DUMPS:
                continue
            if isinstance(call.args[0], ast.Name) and fn_name == "list_market_offers" and call.args[0].id == "offers":
                continue  # stdout payload re-encoded inside an envelope that is masked on return
            unmasked.append(f"{path.name}:{call.lineno} in {fn_name}")
    assert unmasked == [], f"json.dumps of a possible envelope without mask_envelope: {unmasked}"


def test_only_the_server_defines_json_and_command_builders_import_it() -> None:
    for path in _SOURCES:
        tree = ast.parse(path.read_text())
        defines = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_json"]
        if path.name == "aitbc_mcp_server.py":
            assert defines == ["_json"]
            continue
        assert defines == [], f"{path.name} defines its own _json"
        has_command_key = any(
            isinstance(n, ast.Dict) and any(isinstance(k, ast.Constant) and k.value in mask.ECHO_KEYS for k in n.keys)
            for n in ast.walk(tree)
        )
        if has_command_key:
            imported = {
                alias.name
                for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.module == "aitbc_mcp_server"
                for alias in n.names
            }
            assert "_json" in imported, f"{path.name} builds a command envelope without the server's _json"


def test_json_serialiser_calls_the_mask() -> None:
    tree = ast.parse((MCP_SERVER_DIR / "aitbc_mcp_server.py").read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_json")
    assert any(_is_mask_call(n) for n in ast.walk(fn))


def test_bypassing_the_mask_leaks_mutation_check() -> None:
    with mock.patch.object(mcp_server, "mask_envelope", lambda result: result):
        leaked = mcp_server.run_aitbc_command(role="hub", command=f"wallet unlock --password {FAKE}")
    assert FAKE in leaked
    assert FAKE not in mcp_server.run_aitbc_command(role="hub", command=f"wallet unlock --password {FAKE}")
