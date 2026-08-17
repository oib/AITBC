"""V23-91: a proof made by the service must verify against the key it loaded.

The earlier checks only asked whether files existed and whether their headers agreed.
That let a stub verification key, a renamed zero-contribution zkey, and a
``wtns.calculate`` call that never produced a witness all sit in the loaded path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coordinator_api.contexts.zk_applications.services import zk_proofs as zk_module
from coordinator_api.contexts.zk_applications.services.zk_proofs import (
    RECEIPT_CIRCUIT,
    ZKProofService,
    _node_env,
    snarkjs_available,
)


def test_node_env_puts_snarkjs_on_the_require_path():
    env = _node_env()
    assert "snarkjs" in env["NODE_PATH"] or str(zk_module.SNARKJS_NODE_PATH) in env["NODE_PATH"]


def test_generic_script_uses_fullprove_not_a_buffer_witness(monkeypatch, tmp_path):
    """``wtns.calculate`` was handed Buffers and returned undefined (V23-91)."""
    captured: dict[str, str] = {}

    class _FakeProc:
        returncode = 1
        stdout = b""
        stderr = b"captured"

        async def communicate(self) -> tuple[bytes, bytes]:
            return self.stdout, self.stderr

    async def fake_exec(*_args, **_kwargs):
        captured["script"] = Path(_args[1]).read_text()
        return _FakeProc()

    monkeypatch.setattr(zk_module.asyncio, "create_subprocess_exec", fake_exec)

    service = ZKProofService()
    wasm = tmp_path / "c.wasm"
    zkey = tmp_path / "c.zkey"
    vkey = tmp_path / "vkey.json"
    wasm.write_bytes(b"")
    zkey.write_bytes(b"")
    vkey.write_text("{}")

    with pytest.raises(Exception, match="Proof generation failed"):
        import asyncio

        asyncio.run(service._generate_proof_generic({"x": 1}, None, wasm, zkey, vkey))

    assert "fullProve" in captured["script"]
    assert "wtns.calculate" not in captured["script"]
    assert "process.exit(0)" in captured["script"]


@pytest.mark.skipif(not snarkjs_available(), reason="snarkjs is not installed under apps/zk-circuits")
async def test_a_real_proof_verifies_against_the_exported_key(monkeypatch):
    """ml_inference is the smallest circuit whose key is both contributed and real."""
    monkeypatch.setattr(zk_module, "ENABLE_ZK_VERIFICATION", True)
    service = ZKProofService()
    assert "ml_inference_verification" in service.available_circuits
    assert RECEIPT_CIRCUIT in service.available_circuits

    proof = await service.generate_proof(
        "ml_inference_verification",
        {"x": "2", "w": "3", "b": "4", "expected": "10"},
    )
    assert proof is not None, "proving returned None — snarkjs failed inside generate_proof"
    assert proof["public_signals"] == ["1"]

    result = await service.verify_proof(
        proof["proof"],
        proof["public_signals"],
        circuit_name="ml_inference_verification",
    )
    assert result["verified"] is True


@pytest.mark.skipif(not snarkjs_available(), reason="snarkjs is not installed under apps/zk-circuits")
async def test_modular_ml_components_round_trips_after_re_contribution(monkeypatch):
    """The _0001 key that was a renamed _0000 has been re-generated and now proves (V23-91)."""
    monkeypatch.setattr(zk_module, "ENABLE_ZK_VERIFICATION", True)
    service = ZKProofService()
    assert "modular_ml_components" in service.available_circuits

    # These inputs used to be `{"initial_parameters": ["1", "0", "-1", "-2"], "learning_rate": "0"}`.
    # Every one of those values is now refused, and rightly: a zero learning rate was the only
    # value the old circuit accepted, and negative parameters were field elements near the
    # modulus (V23-94). Values are scaled by 1e6, so 10000 is a learning rate of 0.01.
    proof = await service.generate_proof(
        "modular_ml_components",
        {
            "initial_parameters": ["10000000", "20000000", "30000000", "40000000"],
            "learning_rate": "10000",
            "gradients": [["1", "1", "1", "1"], ["1", "1", "1", "1"], ["1", "1", "1", "1"]],
        },
    )
    assert proof is not None
    assert proof["public_signals"][4] == "1"  # training_complete

    result = await service.verify_proof(
        proof["proof"],
        proof["public_signals"],
        circuit_name="modular_ml_components",
    )
    assert result["verified"] is True
