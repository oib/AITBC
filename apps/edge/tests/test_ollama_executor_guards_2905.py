"""AUDIT-EDGE pin: #2905 edge ollama executor must apply the miner-path guards.

request.model_name and the extracted prompt are buyer-controlled; Ollama
auto-pulls unknown models, so the executor must verify /api/tags before
/api/generate and cap the prompt length.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aitbc_edge.schemas.serve import ComputeRequest  # noqa: E402
from aitbc_edge.services import compute_worker as worker_mod  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    """Records calls; tags returns the given model list."""

    def __init__(self, models=None, tags_exc=None):
        self.models = models if models is not None else [{"name": "llama3.2:3b"}]
        self.tags_exc = tags_exc
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        if self.tags_exc is not None:
            raise self.tags_exc
        assert url.endswith("/api/tags")
        return _Resp({"models": self.models})

    async def post(self, url, json=None):
        self.posts.append((url, json))
        return _Resp({"response": "ok", "done": True})


def _req(model="llama3.2:3b", prompt="hi"):
    return ComputeRequest(request_id="r", gpu_id="g", model_name=model, input_data={"prompt": prompt})


@pytest.mark.asyncio
async def test_uninstalled_model_never_reaches_generate(monkeypatch):
    fake = _FakeClient(models=[{"name": "other:7b"}])
    monkeypatch.setattr(worker_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ValueError, match="not installed"):
        await worker_mod._execute_ollama(_req(model="llama3.2:3b"))
    assert fake.posts == [], "generate must not run for an auto-pull candidate"


@pytest.mark.asyncio
async def test_latest_alias_accepted(monkeypatch):
    fake = _FakeClient(models=[{"name": "llama3.2:latest"}])
    monkeypatch.setattr(worker_mod.httpx, "AsyncClient", lambda **kw: fake)
    out, _m = await worker_mod._execute_ollama(_req(model="llama3.2"))
    assert out["response"] == "ok"
    assert len(fake.posts) == 1


@pytest.mark.asyncio
async def test_oversize_prompt_rejected_before_http(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(worker_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(ValueError, match="cap"):
        await worker_mod._execute_ollama(_req(prompt="x" * (worker_mod._OLLAMA_MAX_PROMPT_CHARS + 1)))
    assert fake.posts == []


@pytest.mark.asyncio
async def test_tags_probe_failure_fails_closed(monkeypatch):
    fake = _FakeClient(tags_exc=RuntimeError("ollama down"))
    monkeypatch.setattr(worker_mod.httpx, "AsyncClient", lambda **kw: fake)
    with pytest.raises(RuntimeError):
        await worker_mod._execute_ollama(_req())
    assert fake.posts == []
