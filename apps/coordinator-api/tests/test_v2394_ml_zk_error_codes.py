"""V23-94: a refused witness is the caller's fault, not a server error.

Correcting the circuits' range checks changed which answers are reachable. Before, the training
circuit accepted only ``learning_rate = 0`` and the modular one accepted anything at all, so
``generate_proof`` returning ``None`` was a path almost nothing took. After, it is the normal
answer for bad input — and the routers subscripted that ``None``:

    proof_result = await zk_service.generate_proof(...)
    return {"proof_id": proof_result["proof_id"],  # type: ignore[index]

``TypeError`` on a ``None`` subscript, caught by a bare ``except Exception``, answered
``500 Internal server error``. A caller submitting a learning rate the circuit is right to
refuse was told the coordinator was broken. mypy had said so at all eight subscripts; each
carried a ``type: ignore[index]``.

The request bodies were ``dict[str, Any]`` read with bare subscripts, so a missing key was a
500 rather than a 422. ``private_inputs`` was the worst of those: ``generate_proof`` defaults it
to ``None`` and does nothing with a falsy value, but the router demanded it.
"""

from __future__ import annotations

import pytest

from coordinator_api.contexts.zk_applications.routers import ml_zk_proofs
from coordinator_api.contexts.zk_applications.services.zk_proofs import snarkjs_available

GOOD_LR = 10000
PARAMS = ["10000000", "20000000", "30000000", "40000000"]
UNIT_GRADIENTS = [["1", "1", "1", "1"], ["1", "1", "1", "1"], ["1", "1", "1", "1"]]

pytestmark = pytest.mark.skipif(not snarkjs_available(), reason="snarkjs is not installed under apps/zk-circuits")


class TestARefusedWitnessIsTheCallersFault:
    def test_a_zero_learning_rate_is_a_400_not_a_500(self, client):
        """The circuit is right to refuse it. The API must not call that a server error."""
        response = client.post(
            "/v1/ml-zk/prove/training",
            json={"inputs": {"initial_parameters": PARAMS, "learning_rate": "0"}},
        )
        assert response.status_code == 400, f"got {response.status_code}: {response.text}"

        detail = response.json()["detail"]
        assert "circuit refused" in detail, detail
        assert "/v1/ml-zk/circuits" in detail, "the caller has to be told where the ranges are"

    def test_a_learning_rate_of_exactly_one_is_a_400(self, client):
        response = client.post(
            "/v1/ml-zk/prove/training",
            json={"inputs": {"initial_parameters": PARAMS, "learning_rate": "1000000"}},
        )
        assert response.status_code == 400, f"got {response.status_code}: {response.text}"

    def test_modular_without_gradients_is_a_400(self, client):
        """Gradients became a real input; omitting them is unprovable, not broken."""
        response = client.post(
            "/v1/ml-zk/prove/modular",
            json={"inputs": {"initial_parameters": PARAMS, "learning_rate": str(GOOD_LR)}},
        )
        assert response.status_code == 400, f"got {response.status_code}: {response.text}"

    def test_a_circuit_with_no_key_is_a_503_not_a_400(self, client, monkeypatch):
        """The two reasons generate_proof answers None are not the same answer.

        No usable proving key on this node is a server-side condition; inputs that do not
        satisfy the circuit are the caller's. Both used to be a 500, which distinguished
        neither.
        """
        monkeypatch.setattr(ml_zk_proofs.zk_service, "available_circuits", {})

        response = client.post(
            "/v1/ml-zk/prove/training",
            json={"inputs": {"initial_parameters": PARAMS, "learning_rate": str(GOOD_LR)}},
        )
        assert response.status_code == 503, f"got {response.status_code}: {response.text}"


class TestAMissingFieldIsNotAServerError:
    def test_omitting_private_inputs_still_proves(self, client):
        """The service defaults it to None and ignores a falsy value; the router demanded it."""
        response = client.post(
            "/v1/ml-zk/prove/modular",
            json={
                "inputs": {
                    "initial_parameters": PARAMS,
                    "learning_rate": str(GOOD_LR),
                    "gradients": UNIT_GRADIENTS,
                }
            },
        )
        assert response.status_code == 200, f"got {response.status_code}: {response.text}"
        assert response.json()["public_signals"][4] == "1"

    def test_omitting_inputs_is_a_422(self, client):
        response = client.post("/v1/ml-zk/prove/training", json={})
        assert response.status_code == 422, f"got {response.status_code}: {response.text}"

    def test_verify_without_a_proof_is_a_422(self, client):
        response = client.post("/v1/ml-zk/verify/training", json={"public_signals": ["1"]})
        assert response.status_code == 422, f"got {response.status_code}: {response.text}"

    def test_the_published_schema_names_the_body_fields(self, client):
        """The bodies were `dict[str, Any]`, so the spec documented no fields at all."""
        schema = client.get("/openapi.json").json()
        body = schema["paths"]["/v1/ml-zk/prove/training"]["post"]["requestBody"]
        ref = body["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]

        properties = schema["components"]["schemas"][ref]["properties"]
        assert "inputs" in properties
        assert "private_inputs" in properties
        assert schema["components"]["schemas"][ref]["required"] == ["inputs"]
