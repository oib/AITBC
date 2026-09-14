"""Phase B2 tests for CLI-side agent-message signing.

Covers the client half of ``docs/agent-coordinator/agent-signed-envelopes.md``:

* ``utils/agent_signing.py`` — envelope fields, X-Agent-* read headers, the
  registration identity attestation, and the registry binding check;
* ``agent-task hire`` signing every envelope (plus ``--no-sign``), and
  ``status``/``result`` signing inbox polls;
* ``agent-msg send --wallet`` resolving to the wallet's bound agent and
  failing with guidance on unregistered/mismatched identities;
* ``agent-comm register --wallet`` posting the identity claim, and the
  send/receive path fixes to ``/api/v1/agent/messages/*``;
* ``agent inbox``/``agent subscribe`` signed headers (and the subscribe
  route fix).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

pytest.importorskip("eth_account", reason="envelope signing tests need eth-account")

from eth_account import Account  # noqa: E402

from aitbc.crypto.agent_envelope import (  # noqa: E402
    AGENT_MSG_DOMAIN,
    AGENT_MSG_SIGNATURE_VERSION,
    domain_digest,
    identity_claim,
    verify_agent_envelope,
    verify_identity_claim,
)
from aitbc.crypto.signature_recovery import canonical_address, recover_address  # noqa: E402

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)
OTHER_KEY = "0x" + "43" * 32
OTHER_ACCOUNT = Account.from_key(OTHER_KEY)


@pytest.fixture
def runner():
    return CliRunner()


def _mock_client(get_map=None, post_map=None):
    """AITBCHTTPClient double: get_map/post_map map path → response or callable."""
    client = MagicMock()

    def _get(path, params=None, headers=None):
        entry = (get_map or {}).get(path, {})
        return entry(params=params, headers=headers) if callable(entry) else entry

    def _post(path, json=None, headers=None):
        entry = (post_map or {}).get(path, {})
        return entry(json=json, headers=headers) if callable(entry) else entry

    client.get.side_effect = _get
    client.post.side_effect = _post
    return client


# --------------------------------------------------------------------------- #
# utils/agent_signing.py units
# --------------------------------------------------------------------------- #


class TestSignSendEnvelope:
    def test_envelope_fields_present_and_verifiable(self):
        from aitbc_cli.utils.agent_signing import sign_send_envelope

        body = {
            "sender": "agent-a",
            "recipient": "agent-b",
            "content": {"message": "hi"},
            "message_type": "direct",
            "encrypt": False,
            "ttl": 300,
        }
        signed = sign_send_envelope(body, ACCOUNT.address, PRIVATE_KEY)

        assert signed["signer"] == ACCOUNT.address
        assert signed["signature_version"] == AGENT_MSG_SIGNATURE_VERSION
        assert signed["timestamp"]
        assert signed["nonce"]
        # Model defaults are inside the signed bytes — the coordinator's
        # model_dump() reconstructs them even if the client omitted them.
        assert signed["message_id"] is None
        assert signed["priority"] == "normal"

        signature = signed.pop("signature")
        assert signature.startswith("0x")
        assert verify_agent_envelope(signed, signature, ACCOUNT.address) is True

    def test_tamper_and_wrong_key_fail(self):
        from aitbc_cli.utils.agent_signing import sign_send_envelope

        signed = sign_send_envelope({"sender": "a", "recipient": "b", "content": {}}, ACCOUNT.address, PRIVATE_KEY)
        signature = signed.pop("signature")
        assert verify_agent_envelope(dict(signed, sender="evil"), signature, ACCOUNT.address) is False
        assert verify_agent_envelope(signed, signature, OTHER_ACCOUNT.address) is False

    def test_original_body_not_mutated(self):
        from aitbc_cli.utils.agent_signing import sign_send_envelope

        body = {"sender": "a", "recipient": "b", "content": {}}
        sign_send_envelope(body, ACCOUNT.address, PRIVATE_KEY)
        assert "signature" not in body


class TestSignedRequestHeaders:
    def test_header_set_recovers_to_wallet(self):
        from aitbc_cli.utils.agent_signing import (
            AGENT_REQ_SIGNATURE_DOMAIN,
            request_signature_claim,
            signed_request_headers,
        )

        headers = signed_request_headers("agent-1", PRIVATE_KEY)
        assert headers["X-Agent-Id"] == "agent-1"
        assert headers["X-Agent-Signature"].startswith("0x")
        assert headers["X-Agent-Timestamp"]
        assert headers["X-Agent-Nonce"]

        claim = request_signature_claim("agent-1", headers["X-Agent-Timestamp"], headers["X-Agent-Nonce"])
        recovered = recover_address(domain_digest(claim, AGENT_REQ_SIGNATURE_DOMAIN), headers["X-Agent-Signature"])
        assert canonical_address(recovered) == canonical_address(ACCOUNT.address)

    def test_signature_bound_to_agent_id_and_domain(self):
        from aitbc_cli.utils.agent_signing import (
            AGENT_REQ_SIGNATURE_DOMAIN,
            request_signature_claim,
            signed_request_headers,
        )

        headers = signed_request_headers("agent-1", PRIVATE_KEY)
        claim = request_signature_claim("agent-1", headers["X-Agent-Timestamp"], headers["X-Agent-Nonce"])

        # A different agent_id does not recover the wallet.
        other = dict(claim, agent_id="agent-2")
        assert recover_address(domain_digest(other, AGENT_REQ_SIGNATURE_DOMAIN), headers["X-Agent-Signature"]) != (
            ACCOUNT.address
        )
        # Nor does the message-envelope domain (domain separation holds).
        assert recover_address(domain_digest(claim, AGENT_MSG_DOMAIN), headers["X-Agent-Signature"]) != ACCOUNT.address


class TestIdentityAttestation:
    def test_claim_format_verifies(self):
        from aitbc_cli.utils.agent_signing import identity_attestation_fields

        client = _mock_client(get_map={"/v1/agents/nonce": {"nonce": "n-123", "chain_id": "ait-mainnet"}})
        fields = identity_attestation_fields(client, "agent-1", ACCOUNT.address, "ait-mainnet", PRIVATE_KEY)

        assert fields["identity_address"] == ACCOUNT.address
        assert fields["identity_nonce"] == "n-123"
        assert fields["registered_at"]
        claim = identity_claim(
            agent_id="agent-1",
            identity_address=ACCOUNT.address,
            chain_id="ait-mainnet",
            nonce="n-123",
            registered_at=fields["registered_at"],
        )
        assert verify_identity_claim(claim, fields["identity_proof"], ACCOUNT.address) is True
        # The nonce request went out with the agent_id query param.
        assert client.get.call_args.kwargs["params"] == {"agent_id": "agent-1"}

    def test_missing_nonce_raises(self):
        from aitbc_cli.utils.agent_signing import identity_attestation_fields

        client = _mock_client(get_map={"/v1/agents/nonce": {"status": "error"}})
        with pytest.raises(ValueError, match="nonce"):
            identity_attestation_fields(client, "agent-1", ACCOUNT.address, "c", PRIVATE_KEY)


class TestLoadSigningWallet:
    def test_unconfigured_returns_none(self, monkeypatch):
        from aitbc_cli.utils.agent_signing import load_signing_wallet

        monkeypatch.delenv("AITBC_DEFAULT_WALLET", raising=False)
        assert load_signing_wallet(MagicMock(), wallet_name=None) is None

    def test_configured_loads_via_wallet_loader(self, monkeypatch):
        from aitbc_cli.utils import agent_signing

        monkeypatch.delenv("AITBC_DEFAULT_WALLET", raising=False)
        with patch.object(
            agent_signing, "load_wallet_for_payment", return_value=(ACCOUNT.address, PRIVATE_KEY, "w")
        ) as mock_load:
            assert agent_signing.load_signing_wallet(MagicMock(), wallet_name="w1") == (ACCOUNT.address, PRIVATE_KEY)
        assert mock_load.call_args.kwargs["wallet_name"] == "w1"


class TestRegistryBinding:
    def test_matching_binding_ok(self):
        from aitbc_cli.utils.agent_signing import check_registry_binding

        client = _mock_client(get_map={"/v1/agents/agent-1": {"agent": {"identity_address": ACCOUNT.address}}})
        assert check_registry_binding(client, "agent-1", ACCOUNT.address) is None

    def test_unregistered_agent_guidance(self):
        from aitbc_cli.utils.agent_signing import check_registry_binding

        client = _mock_client()
        client.get.side_effect = Exception("GET request failed: 404 Client Error")
        msg = check_registry_binding(client, "ghost", ACCOUNT.address)
        assert msg is not None and "not registered" in msg and "agent-comm register" in msg

    def test_mismatch_and_unbound_fail(self):
        from aitbc_cli.utils.agent_signing import check_registry_binding

        client = _mock_client(get_map={"/v1/agents/agent-1": {"agent": {"identity_address": OTHER_ACCOUNT.address}}})
        msg = check_registry_binding(client, "agent-1", ACCOUNT.address)
        assert msg is not None and "bound to identity" in msg

        client2 = _mock_client(get_map={"/v1/agents/agent-1": {"agent": {"identity_address": None}}})
        msg2 = check_registry_binding(client2, "agent-1", ACCOUNT.address)
        assert msg2 is not None and "no bound identity" in msg2

    def test_lookup_failure_is_not_fatal(self):
        from aitbc_cli.utils.agent_signing import check_registry_binding

        client = _mock_client()
        client.get.side_effect = Exception("connection refused")
        assert check_registry_binding(client, "agent-1", ACCOUNT.address) is None

    def test_find_agent_by_identity(self):
        from aitbc_cli.utils.agent_signing import find_agent_by_identity

        client = _mock_client(
            post_map={
                "/v1/agents/discover": {
                    "agents": [
                        {"agent_id": "other", "identity_address": OTHER_ACCOUNT.address},
                        {"agent_id": "mine", "identity_address": ACCOUNT.address.lower()},
                    ]
                }
            }
        )
        assert find_agent_by_identity(client, ACCOUNT.address) == "mine"
        assert find_agent_by_identity(_mock_client(), ACCOUNT.address) is None


# --------------------------------------------------------------------------- #
# agent-task: hire signs envelopes, status signs inbox polls
# --------------------------------------------------------------------------- #


def _hire_invoke(runner, client, extra_args):
    def fake_get(path, params=None, headers=None):
        if path.startswith("/v1/agents/"):
            return {"agent": {"metadata": {"wallet": "0xProvider"}, "identity_address": OTHER_ACCOUNT.address}}
        if path == "/v1/tasks/escrow-config":
            return {"settlement_wallet": "0xSettleNode"}
        return {"messages": []}

    def fake_post(path, json=None, headers=None):
        if path == "/v1/tasks/submit":
            return {"status": "success", "escrow_id": "esc-9", "task_id": json["task_data"]["task_id"]}
        return {"status": "success", "message_id": "m-1"}

    client.get.side_effect = fake_get
    client.post.side_effect = fake_post

    from aitbc_cli.commands.agent_task import agent_task

    with (
        patch("aitbc_cli.commands.agent_task.AITBCHTTPClient", return_value=client),
        patch(
            "aitbc_cli.commands.agent_task.get_config",
            return_value=MagicMock(agent_coordinator_url="http://coord.local", blockchain_rpc_url="http://rpc.local"),
        ),
        patch("aitbc_cli.commands.agent_task._resolve_payload_ref", return_value="QmCID"),
        patch(
            "aitbc_cli.commands.agent_task.load_wallet_for_payment",
            return_value=(ACCOUNT.address, PRIVATE_KEY, "w1"),
        ),
        patch("aitbc_cli.utils.escrow.create_signed_escrow_lock", return_value=({"type": "ESCROW_LOCK"}, "sig")),
        patch("aitbc_cli.commands.agent_task._get_blockchain_rpc_url", return_value="http://rpc.local"),
    ):
        return runner.invoke(
            agent_task,
            [
                "hire",
                "--to-agent",
                "aitbc-miner-1",
                "--service-type",
                "whisper",
                "--payload",
                "QmCID",
                "--max-price",
                "0.05",
                "--no-wait",
                "--coordinator-url",
                "http://coord.local",
                *extra_args,
            ],
            obj={"output_format": "json"},
        )


class TestAgentTaskSigning:
    def test_hire_signs_task_request_envelope(self, runner):
        client = _mock_client()
        result = _hire_invoke(runner, client, [])
        assert result.exit_code == 0, result.output

        send = next(c for c in client.post.call_args_list if c.args[0] == "/api/v1/agent/messages/send")
        msg = dict(send.kwargs["json"])
        signature = msg.pop("signature")
        assert msg["signer"] == ACCOUNT.address
        assert msg["signature_version"] == AGENT_MSG_SIGNATURE_VERSION
        assert msg["timestamp"] and msg["nonce"]
        assert verify_agent_envelope(msg, signature, ACCOUNT.address) is True

    def test_hire_no_sign_sends_unsigned(self, runner):
        client = _mock_client()
        result = _hire_invoke(runner, client, ["--no-sign"])
        assert result.exit_code == 0, result.output

        send = next(c for c in client.post.call_args_list if c.args[0] == "/api/v1/agent/messages/send")
        msg = send.kwargs["json"]
        for field in ("signature", "signer", "signature_version", "timestamp", "nonce"):
            assert field not in msg, f"{field} present despite --no-sign"

    def test_status_signs_inbox_poll_with_wallet(self, runner):
        client = _mock_client(get_map={"/api/v1/agent/messages/inbox": {"messages": []}})

        from aitbc_cli.commands.agent_task import agent_task

        with (
            patch("aitbc_cli.commands.agent_task.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent_task.get_config", return_value=MagicMock(agent_coordinator_url="http://c")),
            patch(
                "aitbc_cli.commands.agent_task.load_signing_wallet",
                return_value=(ACCOUNT.address, PRIVATE_KEY),
            ) as mock_load,
        ):
            result = runner.invoke(
                agent_task,
                ["status", "--task-id", "t-1", "--wallet", "w1", "--coordinator-url", "http://c"],
                obj={"output_format": "json"},
            )
        assert result.exit_code == 0, result.output
        assert mock_load.call_args.kwargs["wallet_name"] == "w1"

        inbox = next(c for c in client.get.call_args_list if c.args[0] == "/api/v1/agent/messages/inbox")
        headers = inbox.kwargs["headers"]
        assert headers["X-Agent-Id"]
        assert headers["X-Agent-Signature"].startswith("0x")

    def test_status_no_sign_sends_no_headers(self, runner):
        client = _mock_client(get_map={"/api/v1/agent/messages/inbox": {"messages": []}})

        from aitbc_cli.commands.agent_task import agent_task

        with (
            patch("aitbc_cli.commands.agent_task.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent_task.get_config", return_value=MagicMock(agent_coordinator_url="http://c")),
            patch("aitbc_cli.commands.agent_task.load_signing_wallet") as mock_load,
        ):
            result = runner.invoke(
                agent_task,
                ["status", "--task-id", "t-1", "--no-sign", "--coordinator-url", "http://c"],
                obj={"output_format": "json"},
            )
        assert result.exit_code == 0, result.output
        mock_load.assert_not_called()
        inbox = next(c for c in client.get.call_args_list if c.args[0] == "/api/v1/agent/messages/inbox")
        assert inbox.kwargs["headers"] is None


# --------------------------------------------------------------------------- #
# agent-msg: send resolves the wallet's bound agent; receive signs headers
# --------------------------------------------------------------------------- #


def _agent_msg_client(sender_address=ACCOUNT.address):
    return _mock_client(
        get_map={
            "/v1/agents/agent-a": {"agent": {"agent_id": "agent-a", "identity_address": sender_address}},
            "/api/v1/agent/messages/inbox": {"messages": [], "count": 0},
        },
        post_map={"/api/v1/agent/messages/send": {"status": "success", "message_id": "m-1"}},
    )


class TestAgentMsgSigning:
    def test_send_signs_when_wallet_bound(self, runner):
        client = _agent_msg_client()
        from aitbc_cli.commands.agent import messaging

        with (
            patch("aitbc_cli.commands.agent.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent.get_config", return_value=MagicMock(agent_coordinator_url="http://c")),
            patch("aitbc_cli.commands.agent.load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                messaging,
                ["send", "hello", "--from-agent", "agent-a", "--to-agent", "agent-b", "--wallet", "w1", "--no-encrypt"],
                obj={"output_format": "table"},
            )
        assert result.exit_code == 0, result.output
        msg = dict(client.post.call_args.kwargs["json"])
        signature = msg.pop("signature")
        assert msg["signer"] == ACCOUNT.address
        assert verify_agent_envelope(msg, signature, ACCOUNT.address) is True

    def test_send_resolves_agent_from_wallet_identity(self, runner):
        """No --from-agent: the registry is scanned for the wallet's binding."""
        client = _agent_msg_client()
        client.post.side_effect = lambda path, json=None, headers=None: (
            {"agents": [{"agent_id": "agent-a", "identity_address": ACCOUNT.address}]}
            if path == "/v1/agents/discover"
            else {"status": "success"}
        )
        from aitbc_cli.commands.agent import messaging

        with (
            patch("aitbc_cli.commands.agent.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent.get_config", return_value=MagicMock(agent_coordinator_url="http://c")),
            patch("aitbc_cli.commands.agent.load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                messaging,
                ["send", "hello", "--to-agent", "agent-b", "--wallet", "w1"],
                obj={"output_format": "table"},
            )
        assert result.exit_code == 0, result.output
        send_call = next(c for c in client.post.call_args_list if c.args[0] == "/api/v1/agent/messages/send")
        assert send_call.kwargs["json"]["sender"] == "agent-a"

    def test_send_unregistered_agent_fails_with_guidance(self, runner):
        client = _agent_msg_client()
        client.get.side_effect = Exception("GET request failed: 404 Client Error: Not Found")
        from aitbc_cli.commands.agent import messaging

        with (
            patch("aitbc_cli.commands.agent.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent.get_config", return_value=MagicMock(agent_coordinator_url="http://c")),
            patch("aitbc_cli.commands.agent.load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                messaging,
                ["send", "hello", "--from-agent", "ghost", "--to-agent", "agent-b", "--wallet", "w1"],
                obj={"output_format": "table"},
            )
        assert "not registered" in result.output
        assert "agent-comm register" in result.output
        # The message was never posted.
        assert not any(c.args[0] == "/api/v1/agent/messages/send" for c in client.post.call_args_list)

    def test_send_mismatched_identity_fails(self, runner):
        client = _agent_msg_client(sender_address=OTHER_ACCOUNT.address)
        from aitbc_cli.commands.agent import messaging

        with (
            patch("aitbc_cli.commands.agent.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent.get_config", return_value=MagicMock(agent_coordinator_url="http://c")),
            patch("aitbc_cli.commands.agent.load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                messaging,
                ["send", "hello", "--from-agent", "agent-a", "--to-agent", "agent-b", "--wallet", "w1"],
                obj={"output_format": "table"},
            )
        assert "bound to identity" in result.output
        assert not any(c.args[0] == "/api/v1/agent/messages/send" for c in client.post.call_args_list)

    def test_send_without_wallet_stays_unsigned(self, runner):
        client = _agent_msg_client()
        from aitbc_cli.commands.agent import messaging

        with (
            patch("aitbc_cli.commands.agent.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent.get_config", return_value=MagicMock(agent_coordinator_url="http://c")),
            patch("aitbc_cli.commands.agent.load_signing_wallet", return_value=None),
        ):
            result = runner.invoke(
                messaging,
                ["send", "hello", "--from-agent", "agent-a", "--to-agent", "agent-b"],
                obj={"output_format": "table"},
            )
        assert result.exit_code == 0, result.output
        msg = client.post.call_args.kwargs["json"]
        assert "signature" not in msg and "signer" not in msg

    def test_receive_signs_headers(self, runner):
        client = _agent_msg_client()
        from aitbc_cli.commands.agent import messaging

        with (
            patch("aitbc_cli.commands.agent.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent.get_config", return_value=MagicMock(agent_coordinator_url="http://c")),
            patch("aitbc_cli.commands.agent.load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                messaging,
                ["receive", "--from-agent", "agent-a", "--wallet", "w1"],
                obj={"output_format": "table"},
            )
        assert result.exit_code == 0, result.output
        headers = client.get.call_args.kwargs["headers"]
        assert headers["X-Agent-Id"] == "agent-a"
        assert headers["X-Agent-Signature"].startswith("0x")

    def test_receive_unsigned_by_default(self, runner):
        client = _agent_msg_client()
        from aitbc_cli.commands.agent import messaging

        with (
            patch("aitbc_cli.commands.agent.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent.get_config", return_value=MagicMock(agent_coordinator_url="http://c")),
            patch("aitbc_cli.commands.agent.load_signing_wallet", return_value=None),
        ):
            result = runner.invoke(messaging, ["receive", "--from-agent", "agent-a"], obj={"output_format": "table"})
        assert result.exit_code == 0, result.output
        assert client.get.call_args.kwargs["headers"] is None


# --------------------------------------------------------------------------- #
# agent-comm: register binds identity; send/receive hit real routes
# --------------------------------------------------------------------------- #


def _agent_comm_obj():
    return {
        "config": MagicMock(coordinator_api_url="http://coord.local", agent_coordinator_url=None, api_key=None),
        "output_format": "table",
    }


class TestAgentComm:
    def test_register_binds_wallet_identity(self, runner):
        client = _mock_client(
            get_map={"/v1/agents/nonce": {"nonce": "n-9", "chain_id": "ait-mainnet"}},
            post_map={"/v1/agents/register": {"status": "success"}},
        )
        from aitbc_cli.commands.agent_comm import agent_comm

        with (
            patch("aitbc_cli.commands.agent_comm.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent_comm.load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                agent_comm,
                [
                    "register",
                    "--agent-id",
                    "agent-1",
                    "--name",
                    "Agent One",
                    "--chain-id",
                    "ait-mainnet",
                    "--endpoint",
                    "http://node2:8107",
                    "--wallet",
                    "w1",
                ],
                obj=_agent_comm_obj(),
            )
        assert result.exit_code == 0, result.output
        payload = client.post.call_args.kwargs["json"]
        assert payload["identity_address"] == ACCOUNT.address
        assert payload["identity_nonce"] == "n-9"
        assert payload["metadata"]["wallet"] == ACCOUNT.address
        claim = identity_claim(
            agent_id="agent-1",
            identity_address=ACCOUNT.address,
            chain_id="ait-mainnet",
            nonce="n-9",
            registered_at=payload["registered_at"],
        )
        assert verify_identity_claim(claim, payload["identity_proof"], ACCOUNT.address) is True

    def test_register_without_wallet_posts_unsigned(self, runner):
        client = _mock_client(post_map={"/v1/agents/register": {"status": "success"}})
        from aitbc_cli.commands.agent_comm import agent_comm

        with (
            patch("aitbc_cli.commands.agent_comm.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent_comm.load_signing_wallet", return_value=None),
        ):
            result = runner.invoke(
                agent_comm,
                [
                    "register",
                    "--agent-id",
                    "agent-1",
                    "--name",
                    "Agent One",
                    "--chain-id",
                    "ait-mainnet",
                    "--endpoint",
                    "http://node2:8107",
                ],
                obj=_agent_comm_obj(),
            )
        assert result.exit_code == 0, result.output
        payload = client.post.call_args.kwargs["json"]
        assert "identity_proof" not in payload and "identity_address" not in payload

    def test_send_uses_messages_send_route(self, runner):
        client = _mock_client(
            get_map={"/v1/agents/agent-1": {"agent": {"identity_address": ACCOUNT.address}}},
            post_map={"/api/v1/agent/messages/send": {"status": "success", "message_id": "m-1"}},
        )
        from aitbc_cli.commands.agent_comm import agent_comm

        with (
            patch("aitbc_cli.commands.agent_comm.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent_comm.load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                agent_comm,
                [
                    "send",
                    "--sender-id",
                    "agent-1",
                    "--receiver-id",
                    "agent-2",
                    "--message-type",
                    "ping",
                    "--chain-id",
                    "ait-mainnet",
                    "--payload",
                    '{"job": "123"}',
                    "--wallet",
                    "w1",
                ],
                obj=_agent_comm_obj(),
            )
        assert result.exit_code == 0, result.output
        body = dict(client.post.call_args.kwargs["json"])
        assert client.post.call_args.args[0] == "/api/v1/agent/messages/send"
        assert body["content"] == {"job": "123", "chain_id": "ait-mainnet"}
        signature = body.pop("signature")
        assert verify_agent_envelope(body, signature, ACCOUNT.address) is True

    def test_receive_uses_inbox_route_with_headers(self, runner):
        client = _mock_client(get_map={"/api/v1/agent/messages/inbox": {"messages": []}})
        from aitbc_cli.commands.agent_comm import agent_comm

        with (
            patch("aitbc_cli.commands.agent_comm.AITBCHTTPClient", return_value=client),
            patch("aitbc_cli.commands.agent_comm.load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                agent_comm,
                ["receive", "--receiver-id", "agent-1", "--wallet", "w1"],
                obj=_agent_comm_obj(),
            )
        assert result.exit_code == 0, result.output
        call = client.get.call_args
        assert call.args[0] == "/api/v1/agent/messages/inbox"
        assert call.kwargs["params"]["agent_id"] == "agent-1"
        assert call.kwargs["headers"]["X-Agent-Id"] == "agent-1"


# --------------------------------------------------------------------------- #
# agent_sdk commands: inbox/subscribe signed headers + route fix
# --------------------------------------------------------------------------- #


class TestAgentSdkCommands:
    def _agent(self):
        from aitbc_cli.commands.agent_sdk import agent

        return agent

    def test_inbox_sends_signed_headers(self, runner):
        from aitbc_cli.commands import agent_sdk

        resp = MagicMock()
        resp.json.return_value = {"messages": []}
        resp.raise_for_status = MagicMock()
        with (
            patch("requests.get", return_value=resp) as mock_get,
            patch.object(agent_sdk, "load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                self._agent(),
                ["inbox", "--agent-id", "agent-1", "--wallet", "w1"],
                obj={"output_format": "json"},
            )
        assert result.exit_code == 0, result.output
        assert mock_get.call_args.args[0].endswith("/api/v1/agent/messages/inbox")
        headers = mock_get.call_args.kwargs["headers"]
        assert headers["X-Agent-Id"] == "agent-1"
        claim = {"agent_id": "agent-1", "nonce": headers["X-Agent-Nonce"], "timestamp": headers["X-Agent-Timestamp"]}
        recovered = recover_address(domain_digest(claim, "aitbc-agent-req-v1"), headers["X-Agent-Signature"])
        assert canonical_address(recovered) == canonical_address(ACCOUNT.address)

    def test_inbox_unsigned_without_wallet(self, runner):
        from aitbc_cli.commands import agent_sdk

        resp = MagicMock()
        resp.json.return_value = {"messages": []}
        resp.raise_for_status = MagicMock()
        with (
            patch("requests.get", return_value=resp) as mock_get,
            patch.object(agent_sdk, "load_signing_wallet", return_value=None),
        ):
            result = runner.invoke(self._agent(), ["inbox", "--agent-id", "agent-1"], obj={"output_format": "json"})
        assert result.exit_code == 0, result.output
        assert mock_get.call_args.kwargs["headers"] is None

    def test_subscribe_uses_messages_subscribe_route(self, runner):
        from aitbc_cli.commands import agent_sdk

        resp = MagicMock()
        resp.json.return_value = {"status": "subscribed"}
        resp.raise_for_status = MagicMock()
        with (
            patch("requests.post", return_value=resp) as mock_post,
            patch.object(agent_sdk, "load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
        ):
            result = runner.invoke(
                self._agent(),
                ["subscribe", "--agent-id", "agent-1", "--topic", "jobs", "--wallet", "w1"],
                obj={"output_format": "json"},
            )
        assert result.exit_code == 0, result.output
        # Latent bug fixed: /api/v1/agent/messages/subscribe, not /api/v1/agent/subscribe.
        assert mock_post.call_args.args[0].endswith("/api/v1/agent/messages/subscribe")
        assert mock_post.call_args.kwargs["headers"]["X-Agent-Id"] == "agent-1"


# --------------------------------------------------------------------------- #
# agent_login_token + WebSocket agent-JWT auth (Phase B1 login endpoint)
# --------------------------------------------------------------------------- #


class TestAgentLoginToken:
    def test_login_exchange_returns_jwt(self):
        from aitbc.crypto.agent_envelope import login_claim, verify_login_claim
        from aitbc_cli.utils.agent_signing import agent_login_token

        captured: dict[str, Any] = {}

        def _post(path, json=None, headers=None):
            if path.startswith("/api/v1/agent/auth/nonce"):
                assert "agent_id=agent-1" in path
                return {"nonce": "nonce-1", "chain_id": "ait-mainnet"}
            captured.update(json or {})
            return {"access_token": "jwt.token.here"}

        client = MagicMock()
        client.post.side_effect = _post
        token = agent_login_token(client, "agent-1", ACCOUNT.address, PRIVATE_KEY)
        assert token == "jwt.token.here"
        assert captured["agent_id"] == "agent-1"
        assert captured["nonce"] == "nonce-1"
        assert captured["wallet_address"] == ACCOUNT.address
        claim = login_claim("agent-1", ACCOUNT.address, "ait-mainnet", "nonce-1")
        assert verify_login_claim(claim, captured["signature"], ACCOUNT.address) is True

    def test_login_returns_none_without_endpoint(self):
        from aitbc_cli.utils.agent_signing import agent_login_token

        client = MagicMock()
        client.post.side_effect = Exception("404 Not Found")
        assert agent_login_token(client, "agent-1", ACCOUNT.address, PRIVATE_KEY) is None

    def test_login_returns_none_on_malformed_nonce(self):
        from aitbc_cli.utils.agent_signing import agent_login_token

        client = MagicMock()
        client.post.return_value = {"status": "success"}  # no nonce field
        assert agent_login_token(client, "agent-1", ACCOUNT.address, PRIVATE_KEY) is None


class TestWsAuthToken:
    def test_falls_back_without_wallet(self):
        from aitbc_cli.commands import agent

        with patch.object(agent, "load_signing_wallet", return_value=None):
            assert agent._ws_auth_token(MagicMock(), "http://x", "agent-1", None, None, "api-key") == "api-key"

    def test_falls_back_when_binding_fails(self):
        from aitbc_cli.commands import agent

        with (
            patch.object(agent, "load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
            patch.object(agent, "check_registry_binding", return_value="not bound"),
        ):
            assert agent._ws_auth_token(MagicMock(), "http://x", "agent-1", "w1", None, "api-key") == "api-key"

    def test_falls_back_when_login_endpoint_missing(self):
        from aitbc_cli.commands import agent

        with (
            patch.object(agent, "load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
            patch.object(agent, "check_registry_binding", return_value=None),
            patch.object(agent, "agent_login_token", return_value=None),
        ):
            assert agent._ws_auth_token(MagicMock(), "http://x", "agent-1", "w1", None, "api-key") == "api-key"

    def test_returns_agent_jwt_when_wallet_bound(self):
        from aitbc_cli.commands import agent

        with (
            patch.object(agent, "load_signing_wallet", return_value=(ACCOUNT.address, PRIVATE_KEY)),
            patch.object(agent, "check_registry_binding", return_value=None),
            patch.object(agent, "agent_login_token", return_value="agent.jwt"),
        ):
            assert agent._ws_auth_token(MagicMock(), "http://x", "agent-1", "w1", None, "api-key") == "agent.jwt"

    def test_ping_accepts_wallet_option(self, runner):
        from aitbc_cli.commands.agent import messaging

        result = runner.invoke(messaging, ["ping", "--help"])
        assert result.exit_code == 0
        assert "--wallet" in result.output
