"""Tests for ``aitbc bridge proof`` / ``sign-proof`` ``-o/--output`` (CLI-PROOF-OUT-1).

Regression: the ``--output`` option used to bind to a parameter named
``output``, shadowing the ``output()`` formatter — after writing the proof
file the success call raised ``'str' object is not callable`` (or
``'NoneType' object is not callable`` on sign-proof with no ``-o``). These
tests pin the success path end to end through click's CliRunner.
"""

import json
from unittest import mock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.bridge as bridge_mod
from aitbc_cli.commands.bridge import get_proof, sign_proof


@pytest.fixture
def runner():
    return CliRunner()


_PROOF = {
    "transfer_id": "0xabc123",
    "block_height": 51044,
    "lock_event": "lock:0xabc123:3600000:ait-dest:0xbeef",
    "merkle_proof": ["deadbeef"],
}


def _fake_client(doc):
    client = mock.Mock()
    client.__aenter__ = mock.AsyncMock(return_value=client)
    client.__aexit__ = mock.AsyncMock(return_value=None)
    client.get_proof = mock.AsyncMock(return_value={"proof": doc})
    return client


class TestProofOutput:
    def test_proof_writes_file_and_prints_success(self, runner, tmp_path):
        out = tmp_path / "proof.json"
        client = _fake_client(_PROOF)
        with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
            result = runner.invoke(
                get_proof,
                obj={"output_format": "table"},
                args=["--transfer-id", "0xabc123", "-o", str(out)],
            )
        assert result.exit_code == 0, result.output
        written = json.loads(out.read_text())
        assert written == _PROOF
        # sorted-JSON contract
        assert list(written) == sorted(written)
        assert "Bridge Proof" in result.output
        assert "0xabc123" in result.output

    def test_proof_output_flag_unchanged(self, runner):
        # --output/-o must still parse (flag names unchanged)
        assert any("--output" in p.opts or "-o" in p.opts for p in get_proof.params)


class TestSignProofOutput:
    def test_sign_proof_writes_and_prints_success(self, runner, tmp_path):
        src = tmp_path / "unsigned.json"
        src.write_text(json.dumps(_PROOF))
        out = tmp_path / "signed.json"
        result = runner.invoke(
            sign_proof,
            obj={"output_format": "table"},
            args=[
                "--proof-file",
                str(src),
                "--private-key",
                "0x" + "11" * 32,
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        signed = json.loads(out.read_text())
        assert signed["proposer_signature"]
        assert len(signed["validator_signatures"]) == 1
        assert "Signed Bridge Proof" in result.output

    def test_sign_proof_default_outfile_also_exits_clean(self, runner, tmp_path):
        # Without -o the param is None — the crash was unconditional here.
        src = tmp_path / "unsigned.json"
        src.write_text(json.dumps(_PROOF))
        result = runner.invoke(
            sign_proof,
            obj={"output_format": "table"},
            args=["--proof-file", str(src), "--private-key", "0x" + "11" * 32],
        )
        assert result.exit_code == 0, result.output
        signed = json.loads(src.read_text())
        assert signed["proposer_signature"]
