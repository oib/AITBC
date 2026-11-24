"""AUDIT-EDGE-GPU-UNAUTH-READS (#2808): registry/marketplace GET routes
carried no auth dependency while every mutating route requires the shared
GPU_API_KEY. Pin: each data-bearing GET must depend on require_gpu_api_key.
Health/status routes stay public by design.
"""

import ast
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "src" / "gpu_service" / "main.py"

# (method, path) pairs that expose registry, pricing, miner or queue data.
_GATED_GETS = {
    ("/v1/gpu/discover",),
    ("/v1/gpu/{gpu_id}",),
    ("/v1/transactions",),
    ("/v1/miners/{miner_id}/gpus",),
    ("/v1/market/edge-gpu/profiles",),
    ("/v1/market/edge-gpu/metrics/{gpu_id}",),
}

_PUBLIC = {"/health", "/ready", "/live", "/v1/gpu/status"}


def _route_functions() -> dict[tuple[str, str], ast.FunctionDef]:
    tree = ast.parse(MAIN.read_text())
    routes: dict[tuple[str, str], ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            method = dec.func.attr
            if method not in {"get", "post", "put", "delete"}:
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant):
                continue
            path = dec.args[0].value
            if isinstance(path, str) and (path.startswith("/v1/") or path in _PUBLIC):
                routes.setdefault((method, path), node)
    return routes


def _depends_on_gpu_key(fn: ast.FunctionDef) -> bool:
    src = MAIN.read_text()
    for arg in (*fn.args.args, *fn.args.kwonlyargs):
        for node in (arg.annotation, arg.default if hasattr(arg, "default") else None):
            if node is None:
                continue
            seg = ast.get_source_segment(src, node) or ""
            if "require_gpu_api_key" in seg:
                return True
    # defaults live on fn.args, not on arg objects — scan them too
    for d in (*fn.args.defaults, *(d for d in fn.args.kw_defaults if d is not None)):
        seg = ast.get_source_segment(src, d) or ""
        if "require_gpu_api_key" in seg:
            return True
    return False


def test_data_bearing_gets_require_gpu_api_key():
    routes = _route_functions()
    missing = []
    for (path,) in _GATED_GETS:
        fn = routes.get(("get", path))
        assert fn is not None, f"route {path} not found"
        if not _depends_on_gpu_key(fn):
            missing.append(path)
    assert missing == [], f"GET routes missing require_gpu_api_key: {missing}"


def test_no_other_v1_get_is_unauthenticated():
    """Sweep: every /v1/* GET outside the public health set must gate."""
    routes = _route_functions()
    ungated = [
        path
        for (method, path), fn in routes.items()
        if method == "get" and path not in _PUBLIC and not _depends_on_gpu_key(fn)
    ]
    assert ungated == [], f"unauthenticated /v1 GET routes: {ungated}"
