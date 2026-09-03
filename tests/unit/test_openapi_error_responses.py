"""V23-80: the published specs document the errors the handlers actually return.

Two halves. The first exercises the scanner against handlers written here, so a claim about
what it extracts is checked against a handler whose source is visible in the same file. The
second asserts against the committed `docs/api/*.json`, because the finding was about the
*published* specs and a scanner that works on toy input while the published files say nothing
would be the same bug with more code.

The scanner is deliberately a floor: it reads literals in a handler's own source and in its
route dependencies, and nothing else. `test_a_computed_status_code_is_not_guessed_at` pins
that -- an under-documented response is a gap, an invented one is a lie.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DOCS = REPO_ROOT / "docs" / "api"


def _load_module():
    """Import scripts/openapi_error_responses.py without putting scripts/ on sys.path."""
    path = REPO_ROOT / "scripts" / "openapi_error_responses.py"
    spec = importlib.util.spec_from_file_location("openapi_error_responses", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


oer = _load_module()


def codes(fn, dependencies=()):
    return oer.collect(fn, dependencies)


# --------------------------------------------------------------------------------------
# What the scanner reads out of a handler
# --------------------------------------------------------------------------------------


def test_http_exception_keyword_form():
    def handler():
        raise HTTPException(status_code=404, detail="Job not found")

    found = codes(handler)
    assert set(found) == {404}
    assert found[404].shapes == {("detail",)}
    assert found[404].description() == "Job not found"


def test_http_exception_positional_form():
    """`HTTPException(404, "...")` -- the code is the first argument, the message the second."""

    def handler():
        raise HTTPException(404, "Nope")

    found = codes(handler)
    assert set(found) == {404}
    assert found[404].description() == "Nope"


def test_status_constant_form():
    """169 call sites spell the code as `status.HTTP_404_NOT_FOUND`, not as an int.

    A scan matching only `ast.Constant` found none of them, which would have left
    coordinator-api, blockchain-node and wallet almost entirely undocumented while
    appearing to work on marketplace and agent-coordinator.
    """

    def handler():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already exists")

    assert set(codes(handler)) == {409}


def test_json_response_carries_its_own_body_shape():
    """`{"error": ...}` is not `{"detail": ...}`, and marketplace returns the former.

    V23-76 found seven "not found" paths in marketplace disagreeing about the status code.
    Documenting them all as `{"detail": ...}` because that is what FastAPI would have
    produced would relocate the disagreement into the body instead of recording it.
    """

    def handler():
        return JSONResponse(status_code=404, content={"error": "Offer not found"})

    found = codes(handler)
    assert found[404].shapes == {("error",)}
    assert found[404].description() == "Offer not found"
    assert found[404].schema() == {"type": "object", "properties": {"error": {"title": "Error"}}}


def test_detail_shape_refs_the_shared_component():
    def handler():
        raise HTTPException(status_code=500, detail="boom")

    assert codes(handler)[500].schema() == {"$ref": "#/components/schemas/ErrorResponse"}


def test_f_string_messages_keep_their_placeholder():
    def handler(node_id: str):
        return JSONResponse(status_code=404, content={"error": f"Edge node {node_id} not found"})

    assert codes(handler)[404].description() == "Edge node {node_id} not found"


def test_two_shapes_for_one_code_are_reported_as_both():
    """A handler answering 404 two ways is a defect; `anyOf` records it rather than picking."""

    def handler(flag: bool):
        if flag:
            raise HTTPException(status_code=404, detail="gone")
        return JSONResponse(status_code=404, content={"error": "gone"})

    schema = codes(handler)[404].schema()
    assert "anyOf" in schema
    assert len(schema["anyOf"]) == 2


def test_a_spread_body_documents_the_code_but_not_a_partial_schema():
    """`{**base, "error": ...}` -- the readable keys are a subset, and a subset is wrong."""

    def handler(base: dict):
        return JSONResponse(status_code=503, content={**base, "error": "down"})

    found = codes(handler)
    assert set(found) == {503}
    assert found[503].schema() is None
    assert found[503].description() == "down"


def test_success_codes_are_not_collected():
    def handler():
        return JSONResponse(status_code=201, content={"ok": True})

    assert codes(handler) == {}


def test_a_computed_status_code_is_not_guessed_at():
    """The scanner reads literals. A code chosen at runtime is left out, on purpose."""

    def handler(upstream_status: int):
        return JSONResponse(status_code=upstream_status, content={"error": "proxied"})

    assert codes(handler) == {}


def test_a_status_raised_inside_a_called_helper_is_not_found():
    """The documented floor, pinned so it is a known limit rather than a surprise."""

    def find_or_404(job_id: str):
        raise HTTPException(status_code=404, detail="Job not found")

    def handler(job_id: str):
        return find_or_404(job_id)

    assert codes(handler) == {}


def test_no_message_falls_back_to_the_reason_phrase():
    def handler():
        raise HTTPException(status_code=403)

    assert codes(handler)[403].description() == "Forbidden"


def test_many_messages_are_truncated_rather_than_dumped():
    def handler(n: int):
        if n == 1:
            raise HTTPException(status_code=400, detail="one")
        if n == 2:
            raise HTTPException(status_code=400, detail="two")
        if n == 3:
            raise HTTPException(status_code=400, detail="three")
        if n == 4:
            raise HTTPException(status_code=400, detail="four")
        raise HTTPException(status_code=400, detail="five")

    description = codes(handler)[400].description()
    # Source order, so the truncation is the last messages rather than whichever four
    # `ast.walk`'s breadth-first traversal happened to reach first.
    assert description == "one / two / three / four / …"


def test_unparseable_source_is_skipped_not_raised():
    """A builtin or a C-implemented callable has no source; that must not fail the run."""
    assert oer.collect(len) == {}


# --------------------------------------------------------------------------------------
# What `enrich` does to a spec
# --------------------------------------------------------------------------------------


def _app_with_dependency():
    def require_key(token: str = ""):
        if not token:
            raise HTTPException(status_code=401, detail="Missing API key")
        return token

    app = FastAPI()

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str, _: str = Depends(require_key)) -> dict:
        raise HTTPException(status_code=404, detail="Job not found")

    return app


def test_enrich_adds_the_codes_fastapi_could_not_see():
    app = _app_with_dependency()
    before = app.openapi()
    assert set(before["paths"]["/jobs/{job_id}"]["get"]["responses"]) == {"200", "422"}

    after = oer.enrich(app.openapi(), app)
    assert set(after["paths"]["/jobs/{job_id}"]["get"]["responses"]) == {"200", "401", "404", "422"}


def test_a_security_dependency_contributes_its_401():
    """The one code a client is most likely to need, and no handler body mentions it."""
    app = _app_with_dependency()
    spec = oer.enrich(app.openapi(), app)
    assert spec["paths"]["/jobs/{job_id}"]["get"]["responses"]["401"]["description"] == "Missing API key"


def test_enrich_never_overwrites_a_declared_response():
    app = FastAPI()

    @app.get("/thing", responses={404: {"description": "Hand-written and authoritative"}})
    def thing() -> dict:
        raise HTTPException(status_code=404, detail="scanner would say this")

    spec = oer.enrich(app.openapi(), app)
    assert spec["paths"]["/thing"]["get"]["responses"]["404"]["description"] == "Hand-written and authoritative"


def test_the_error_component_appears_only_when_referenced():
    app = FastAPI()

    @app.get("/plain")
    def plain() -> dict:
        return {}

    spec = oer.enrich(app.openapi(), app)
    assert "ErrorResponse" not in spec.get("components", {}).get("schemas", {})

    app2 = _app_with_dependency()
    spec2 = oer.enrich(app2.openapi(), app2)
    assert spec2["components"]["schemas"]["ErrorResponse"]["required"] == ["detail"]


def test_enriched_responses_carry_a_description():
    """OpenAPI requires it on every response object; a missing one makes the file invalid."""
    app = _app_with_dependency()
    spec = oer.enrich(app.openapi(), app)
    for item in spec["paths"].values():
        for operation in item.values():
            for code, response in operation["responses"].items():
                assert response.get("description"), f"{code} has no description"


# --------------------------------------------------------------------------------------
# The published specs -- the actual subject of the finding
# --------------------------------------------------------------------------------------

SPECS = sorted(API_DOCS.glob("*-openapi.json"))


def _operations(spec):
    methods = {"get", "post", "put", "patch", "delete", "head", "options"}
    for path, item in spec.get("paths", {}).items():
        for method, operation in item.items():
            if method.lower() in methods:
                yield path, method, operation


def test_five_specs_are_published():
    assert [p.name for p in SPECS] == [
        "agent-coordinator-openapi.json",
        "blockchain-node-openapi.json",
        "coordinator-api-openapi.json",
        "marketplace-openapi.json",
        "wallet-openapi.json",
    ]


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda p: p.stem)
def test_every_published_spec_documents_at_least_one_404(spec_path):
    """The finding, stated as an assertion. All five were at zero."""
    spec = json.loads(spec_path.read_text())
    with_404 = [f"{m.upper()} {p}" for p, m, op in _operations(spec) if "404" in op.get("responses", {})]
    assert with_404, f"{spec_path.name} documents no 404 on any operation"


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda p: p.stem)
def test_no_published_response_is_missing_its_description(spec_path):
    spec = json.loads(spec_path.read_text())
    for path, method, operation in _operations(spec):
        for code, response in operation.get("responses", {}).items():
            assert response.get("description"), f"{method.upper()} {path} -> {code}"


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda p: p.stem)
def test_every_referenced_error_schema_exists(spec_path):
    """A `$ref` to a component that was never added renders as a broken spec, not an error."""
    spec = json.loads(spec_path.read_text())
    schemas = spec.get("components", {}).get("schemas", {})
    text = spec_path.read_text()
    if f"#/components/schemas/{oer.ERROR_SCHEMA_NAME}" in text:
        assert oer.ERROR_SCHEMA_NAME in schemas


def test_the_marketplace_offer_routes_document_their_404():
    """The loose end V23-76 left.

    Seven marketplace routes answered 404 for a missing offer and the spec documented `200`
    and `422` for all eight -- so the documentation asserted they agreed, at the moment one
    of them genuinely did not. Fixing that route without fixing the spec left the
    documentation saying the same wrong thing about the other six.
    """
    spec = json.loads((API_DOCS / "marketplace-openapi.json").read_text())
    # Every 404 in the service, matching the `404` sites in main.py one for one.
    #
    # The last three were added by V23-81. This test previously recorded them as absent
    # "because they genuinely never answer 404: the first two re-raise to a 500 and the third
    # returns zeros for a service that is not there" -- which was true, and was the same
    # family of inconsistency V23-76 found rather than a documentation problem. Fixing the
    # behaviour is what moved them into this set; the spec still reports the routes as they
    # are, and this assertion is what stops the two drifting apart again.
    expected = {
        ("get", "/v1/marketplace/offers/{offer_id}"),
        ("get", "/v1/marketplace/offers/{offer_id}/history"),
        ("post", "/v1/marketplace/offers/{offer_id}/cancel"),
        ("post", "/v1/marketplace/dynamic-pricing"),
        ("get", "/v1/marketplace/offer/{plugin_id}"),
        ("delete", "/v1/marketplace/offer/{plugin_id}"),
        ("get", "/v1/marketplace/offer-by-id/{offer_id}"),
        ("get", "/v1/marketplace/edge/{node_id}/health"),
        ("post", "/v1/marketplace/offers/{offer_id}/book"),
        ("post", "/v1/marketplace/offer/{service_id}/rate"),
        ("get", "/v1/marketplace/offer/{service_id}/ratings"),
        ("get", "/v1/marketplace/ipfs/rental/{access_key}"),
    }
    found = {(m.lower(), p) for p, m, op in _operations(spec) if "404" in op.get("responses", {})}
    assert not sorted(expected - found), f"still undocumented: {sorted(expected - found)}"
    assert not sorted(found - expected), f"documented but not in the source: {sorted(found - expected)}"

    body = spec["paths"]["/v1/marketplace/offers/{offer_id}"]["get"]["responses"]["404"]
    assert body["description"] == "Offer not found"
    # The shape the route actually returns, not the one FastAPI would have produced.
    assert body["content"]["application/json"]["schema"]["properties"].keys() == {"error"}


def test_the_extractor_calls_the_enricher():
    """Cheap guard: the specs are only correct because generation runs this pass."""
    source = (REPO_ROOT / "scripts" / "extract_openapi_specs.py").read_text()
    tree = ast.parse(source)
    imported = any(isinstance(node, ast.ImportFrom) and node.module == "openapi_error_responses" for node in ast.walk(tree))
    called = any(isinstance(node, ast.Call) and getattr(node.func, "id", "") == "enrich" for node in ast.walk(tree))
    assert imported and called
