"""Tests for the 2026-09-15 CLI gap fixes.

Covers ``resource status``/``deallocate`` (GAP-04), ``ipfs unpin`` (GAP-05),
``wallet staking-info --address`` (GAP-06), ``system env-set`` (GAP-11),
coordinator ``/v1/services/{name}[ /test]`` + priced-job currency validation
(GAP-27/28), and ``messaging send --topic`` title resolution (GAP-30).
"""

import json
import re
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.ipfs import unpin
from aitbc_cli.commands.resource import deallocate, status
from aitbc_cli.commands.system import env_set
from aitbc_cli.commands.wallet.staking import staking_info


def extract_json_from_output(output):
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
    lines = clean.strip().split("\n")
    json_lines = []
    in_json = False
    brace_depth = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{"):
            in_json = True
        if in_json:
            json_lines.append(stripped)
            brace_depth += stripped.count("{")
            brace_depth -= stripped.count("}")
            if brace_depth == 0:
                break
    return json.loads("\n".join(json_lines))


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# GAP-04: resource status / deallocate
# ---------------------------------------------------------------------------


def test_resource_status_lists_allocations(runner):
    client = Mock()
    # The command reads through get_json (tolerates bare arrays), not get.
    client.get_json.return_value = [
        {
            "allocation_id": "alloc_1",
            "agent_id": "agent-1",
            "status": "allocated",
            "cpu_cores": 2.0,
            "memory_gb": 4.0,
            "gpu_count": 0.0,
            "allocated_at": "2026-09-15T10:00:00",
        }
    ]
    with patch("aitbc_cli.commands.resource._client", return_value=client):
        result = runner.invoke(status, ["--agent-id", "agent-1", "--status", "allocated"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    args, kwargs = client.get_json.call_args
    assert args[0] == "/v1/agent-performance/resources"
    assert kwargs["params"]["agent_id"] == "agent-1"
    assert kwargs["params"]["status"] == "allocated"


def test_resource_status_empty(runner):
    client = Mock()
    client.get_json.return_value = []
    with patch("aitbc_cli.commands.resource._client", return_value=client):
        result = runner.invoke(status, [], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output


def test_resource_deallocate_posts_release(runner):
    client = Mock()
    client.post.return_value = {"allocation_id": "alloc_1", "status": "released"}
    with patch("aitbc_cli.commands.resource._client", return_value=client):
        result = runner.invoke(deallocate, ["alloc_1", "--force"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    args, _ = client.post.call_args
    assert args[0] == "/v1/agent-performance/resources/alloc_1/deallocate"


def test_resource_deallocate_requires_confirmation(runner):
    client = Mock()
    with patch("aitbc_cli.commands.resource._client", return_value=client):
        result = runner.invoke(deallocate, ["alloc_1"], input="n\n", obj={"output_format": "json"})
    assert result.exit_code != 0
    client.post.assert_not_called()


# ---------------------------------------------------------------------------
# GAP-05: ipfs unpin
# ---------------------------------------------------------------------------


def test_ipfs_unpin_daemon_path(runner):
    with (
        patch("aitbc_cli.commands.ipfs._daemon_available", return_value=True),
        patch("aitbc_cli.commands.ipfs._ipfs_unpin_cid", return_value=True) as unpin_mock,
    ):
        result = runner.invoke(unpin, ["--cid", "QmTest123"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    unpin_mock.assert_called_once()
    data = extract_json_from_output(result.output)
    assert data["success"] is True
    assert data["data"]["pinned"] is False


def test_ipfs_unpin_filesystem_fallback(runner):
    items = [{"cid": "QmA", "pinned": True}, {"cid": "QmB", "pinned": True}]
    saved = []
    with (
        patch("aitbc_cli.commands.ipfs._daemon_available", return_value=False),
        patch("aitbc_cli.commands.ipfs._ensure_ipfs_dir"),
        patch("aitbc_cli.commands.ipfs._load_index", return_value=items),
        patch("aitbc_cli.commands.ipfs._save_index", side_effect=lambda x: saved.append(x)),
    ):
        result = runner.invoke(unpin, ["--cid", "QmA"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    assert saved[0][0]["pinned"] is False
    assert saved[0][1]["pinned"] is True


def test_ipfs_unpin_unknown_cid_errors(runner):
    with (
        patch("aitbc_cli.commands.ipfs._daemon_available", return_value=False),
        patch("aitbc_cli.commands.ipfs._ensure_ipfs_dir"),
        patch("aitbc_cli.commands.ipfs._load_index", return_value=[]),
    ):
        result = runner.invoke(unpin, ["--cid", "QmMissing"], obj={"output_format": "json"})
    assert result.exit_code != 0
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# GAP-06: wallet staking-info --address
# ---------------------------------------------------------------------------


def _staking_client():
    client = Mock()
    client.get.return_value = {
        "total_staked": 0,
        "active_stake_count": 0,
        "active_stakes": [],
    }
    return client


def test_staking_info_address_override_skips_wallet(runner, tmp_path):
    client = _staking_client()
    missing_wallet = tmp_path / "no-such-wallet.json"
    with (
        patch("aitbc_cli.commands.wallet.staking.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="ait-test"),
    ):
        result = runner.invoke(
            staking_info,
            ["--address", "0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d"],
            obj={
                "wallet_name": "doesnotexist",
                "wallet_path": missing_wallet,
                "wallet_sign_path": missing_wallet,
                "rpc_url": "http://localhost:8202",
                "output_format": "json",
            },
        )
    assert result.exit_code == 0, result.output
    args, _ = client.get.call_args
    assert "/rpc/staking/0xdb5247d03ca2e40f3995a583b2c097ab703efd4d" in args[0].lower()
    assert "doesnotexist" not in result.output or "(by address)" in result.output


def test_staking_info_address_override_validates(runner, tmp_path):
    client = _staking_client()
    with (
        patch("aitbc_cli.commands.wallet.staking.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="ait-test"),
    ):
        result = runner.invoke(
            staking_info,
            ["--address", "not-an-address"],
            obj={
                "wallet_name": "w",
                "wallet_path": tmp_path / "w.json",
                "wallet_sign_path": tmp_path / "w.json",
                "rpc_url": "http://localhost:8202",
                "output_format": "json",
            },
        )
    assert "Invalid sender address" in result.output
    client.get.assert_not_called()


def test_staking_info_default_requires_wallet(runner, tmp_path):
    missing_wallet = tmp_path / "gone.json"
    result = runner.invoke(
        staking_info,
        [],
        obj={
            "wallet_name": "gone",
            "wallet_path": missing_wallet,
            "wallet_sign_path": missing_wallet,
            "rpc_url": "http://localhost:8202",
            "output_format": "json",
        },
    )
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# GAP-11: system env-set
# ---------------------------------------------------------------------------


def test_env_set_upserts_and_appends(runner, tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("FOO=old\nBAR=keep\nexport OLD_EXPORT=x\n")
    result = runner.invoke(
        env_set,
        ["blockchain-node", "FOO=new", "BAZ=added", "--env-file", str(env_file), "--no-restart"],
        obj={},
    )
    assert result.exit_code == 0, result.output
    text = env_file.read_text()
    assert "FOO=new" in text
    assert "BAR=keep" in text
    assert "BAZ=added" in text
    assert "FOO=old" not in text
    # values are never echoed — only key names
    assert "added" not in result.output
    assert "BAZ" in result.output


def test_env_set_rejects_malformed_assignment(runner, tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("FOO=old\n")
    result = runner.invoke(
        env_set,
        ["blockchain-node", "NOEQUALS", "--env-file", str(env_file), "--no-restart"],
        obj={},
    )
    assert result.exit_code != 0
    assert "KEY=VALUE" in result.output
    assert env_file.read_text() == "FOO=old\n"


def test_env_set_rejects_bad_key_name(runner, tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("")
    result = runner.invoke(
        env_set,
        ["blockchain-node", "1BAD=x", "--env-file", str(env_file), "--no-restart"],
        obj={},
    )
    assert result.exit_code != 0
    assert "Invalid environment variable name" in result.output


def test_env_set_refuses_unit_without_env_file(runner):
    with patch("aitbc_cli.commands.system._unit_env_file", return_value=None):
        result = runner.invoke(env_set, ["nonexistent-svc", "FOO=1", "--no-restart"], obj={})
    assert result.exit_code != 0
    assert "No EnvironmentFile" in result.output or "--env-file" in result.output


# ---------------------------------------------------------------------------
# GAP-28: priced-job currency validation at submit (fail fast, no zombie job)
# ---------------------------------------------------------------------------


def test_job_create_rejects_invalid_currency_when_priced():
    from decimal import Decimal

    import pydantic
    from coordinator_api.schemas import JobCreate

    with pytest.raises(pydantic.ValidationError):
        JobCreate(payload={}, payment_amount=Decimal("1"), payment_currency="INVALID_CURRENCY")


def test_job_create_allows_invalid_currency_when_unpriced():
    from coordinator_api.schemas import JobCreate

    job = JobCreate(payload={}, payment_currency="INVALID_CURRENCY")
    assert job.payment_currency == "INVALID_CURRENCY"


def test_job_create_accepts_valid_currency_when_priced():
    from decimal import Decimal

    from coordinator_api.schemas import JobCreate

    job = JobCreate(payload={}, payment_amount=Decimal("1"), payment_currency="aitbc")
    assert job.payment_currency == "aitbc"


# ---------------------------------------------------------------------------
# GAP-27: coordinator /v1/services/{name} catalog lookup
# ---------------------------------------------------------------------------


def test_find_service_by_type_and_name(tmp_path, monkeypatch):
    # The services router imports aitbc.auth.api_key, whose module-level
    # APIKeyManager() takes a filelock under the key storage path — the default
    # /var/lib/aitbc only exists on deployed nodes. Redirect it so the import
    # works on dev hosts too. (If the module was already imported in this
    # session, the env is moot — the path was writable anyway.)
    monkeypatch.setenv("API_KEY_STORAGE_PATH", str(tmp_path / "api_keys.json"))
    from coordinator_api.contexts.infrastructure.routers.services import _find_service

    assert _find_service("whisper")["type"] == "whisper"
    assert _find_service("Whisper Speech Recognition")["type"] == "whisper"
    assert _find_service("LLM_INFERENCE")["type"] == "llm_inference"
    assert _find_service("no-such-service") is None


# ---------------------------------------------------------------------------
# GAP-30 (superseded by MSG-1): --topic is now the implicit slug itself —
# there is no topic_id lookup or create call; the slug is normalized
# client-side and an invalid one aborts before any network or wallet work.
# ---------------------------------------------------------------------------


def test_messaging_send_normalizes_topic_slug(runner):
    from aitbc_cli.commands.messaging import send

    with patch("aitbc_cli.commands.messaging._send_transaction_impl", return_value="ab" * 32) as send_tx, patch(
        "aitbc_cli.commands.messaging._wallet_address", return_value="0x" + "11" * 20
    ), patch("aitbc_cli.commands.messaging.resolve_wallet_password", return_value="pw"), patch(
        "aitbc_cli.commands.messaging._wait_for_seal"
    ):
        result = runner.invoke(
            send,
            ["--wallet", "w1", "--message", "hi", "--topic", "General  Chat", "--confirm"],
            obj={"output_format": "json"},
        )
    assert result.exit_code == 0, result.output
    assert "topic normalized to 'general-chat'" in result.output
    payload = send_tx.call_args.kwargs["payload"]
    assert payload["aitbc_msg"]["topic"] == "general-chat"


def test_messaging_send_invalid_topic_aborts(runner):
    from aitbc_cli.commands.messaging import send

    with patch("aitbc_cli.commands.messaging._send_transaction_impl") as send_tx:
        result = runner.invoke(
            send,
            ["--wallet", "w1", "--message", "hi", "--topic", "!!!"],
            obj={"output_format": "json"},
        )
    assert result.exit_code != 0
    assert "cannot become a slug" in result.output
    send_tx.assert_not_called()


def test_messaging_send_requires_wallet(runner):
    from aitbc_cli.commands.messaging import send

    result = runner.invoke(send, ["--message", "hi"], obj={"output_format": "json"})
    assert result.exit_code != 0
    assert "wallet" in result.output.lower()


# ---------------------------------------------------------------------------
# http_error_detail: FastAPI detail + coordinator error-envelope extraction
# ---------------------------------------------------------------------------


def _network_error_with_body(body):
    import requests

    from aitbc.exceptions import NetworkError

    resp = Mock()
    resp.json.return_value = body
    http_err = requests.HTTPError("422 Client Error", response=resp)
    err = NetworkError(f"POST request failed: {http_err}")
    err.__cause__ = http_err
    return err


def test_http_error_detail_fastapi_string():
    from aitbc_cli.utils.http_client import http_error_detail

    assert http_error_detail(_network_error_with_body({"detail": "lock period active"})) == "lock period active"


def test_http_error_detail_fastapi_list():
    from aitbc_cli.utils.http_client import http_error_detail

    body = {"detail": [{"loc": ["body", "payment_currency"], "msg": "must be one of", "type": "value_error"}]}
    assert http_error_detail(_network_error_with_body(body)) == "payment_currency: must be one of"


def test_http_error_detail_coordinator_envelope():
    from aitbc_cli.utils.http_client import http_error_detail

    body = {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "status": 422,
            "details": [
                {"field": "body", "message": "Value error, payment_currency must be one of: ['AITBC', 'ETH', 'USDT']"}
            ],
        }
    }
    assert (
        http_error_detail(_network_error_with_body(body))
        == "Value error, payment_currency must be one of: ['AITBC', 'ETH', 'USDT']"
    )


def test_http_error_detail_envelope_fallback_to_message():
    from aitbc_cli.utils.http_client import http_error_detail

    body = {"error": {"code": "NOT_FOUND", "message": "allocation not found", "status": 404}}
    assert http_error_detail(_network_error_with_body(body)) == "allocation not found"


def test_http_error_detail_no_response():
    from aitbc.exceptions import NetworkError

    from aitbc_cli.utils.http_client import http_error_detail

    assert http_error_detail(NetworkError("connection refused")) is None


# ---------------------------------------------------------------------------
# GAP-37: reputation — simulated fallback only when unreachable; HTTP
# responses (incl. 404/500) abort with the server's detail, never fake data
# ---------------------------------------------------------------------------


def _net_err_with_status(status: int):
    import requests

    from aitbc.exceptions import NetworkError

    resp = Mock()
    resp.status_code = status
    resp.json.return_value = {"error": {"message": "Reputation profile not found"}}
    http_err = requests.HTTPError(f"{status} err", response=resp)
    err = NetworkError(f"GET failed: {http_err}")
    err.__cause__ = http_err
    return err


def _net_err_unreachable():
    import requests

    from aitbc.exceptions import NetworkError

    err = NetworkError("GET failed: conn refused")
    err.__cause__ = requests.ConnectionError("conn refused")
    return err


def test_reputation_profile_404_aborts_not_simulates(runner):
    from aitbc_cli.commands.reputation import get_profile

    client = Mock()
    client.get.side_effect = _net_err_with_status(404)
    with patch("aitbc_cli.commands.reputation._coordinator_client", return_value=client):
        result = runner.invoke(get_profile, ["--agent-id", "ghost", "--format", "json"], obj={"output_format": "json"})
    assert result.exit_code != 0
    assert "Reputation profile not found" in result.output
    assert "trust_score" not in result.output


def test_reputation_profile_unreachable_simulates(runner):
    from aitbc_cli.commands.reputation import get_profile

    client = Mock()
    client.get.side_effect = _net_err_unreachable()
    with patch("aitbc_cli.commands.reputation._coordinator_client", return_value=client):
        result = runner.invoke(get_profile, ["--agent-id", "ghost", "--format", "json"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    assert '"trust_score"' in result.output


def test_reputation_profile_live_result(runner):
    from aitbc_cli.commands.reputation import get_profile

    client = Mock()
    client.get.return_value = {"agent_id": "a1", "trust_score": 800, "reputation_level": "excellent"}
    with patch("aitbc_cli.commands.reputation._coordinator_client", return_value=client):
        result = runner.invoke(get_profile, ["--agent-id", "a1", "--format", "json"], obj={"output_format": "json"})
    assert result.exit_code == 0
    assert '"excellent"' in result.output


def test_http_response_status_helper():
    from aitbc_cli.utils.http_client import http_response_status

    assert http_response_status(_net_err_with_status(404)) == 404
    assert http_response_status(_net_err_unreachable()) is None
