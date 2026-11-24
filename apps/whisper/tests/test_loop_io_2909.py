"""AUDIT-EDGE pin: #2909 synchronous I/O must not run on the event loop."""

import ast
import importlib.util
from pathlib import Path

# Load under a unique module name — sibling apps ship their own main.py and
# a bare ``import main`` collides in sys.modules when suites run together.
_spec = importlib.util.spec_from_file_location("aitbc_whisper_main", Path(__file__).resolve().parents[1] / "main.py")
whisper_main = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(whisper_main)


def _fn_calls(fn_name: str) -> list[ast.Call]:
    src = Path(whisper_main.__file__).read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name)
    seg = ast.get_source_segment(src, fn)
    return [n for n in ast.walk(ast.parse(seg)) if isinstance(n, ast.Call)]


def _is_to_thread(call: ast.Call) -> bool:
    f = call.func
    return isinstance(f, ast.Attribute) and f.attr == "to_thread" and isinstance(f.value, ast.Name) and f.value.id == "asyncio"


def test_spool_upload_writes_off_loop() -> None:
    calls = [c for c in _fn_calls("_spool_upload") if _is_to_thread(c)]
    assert any(isinstance(c.args[0], ast.Attribute) and c.args[0].attr == "write" for c in calls), (
        "_spool_upload must offload tmp.write via asyncio.to_thread"
    )


def test_probe_duration_off_loop() -> None:
    calls = [c for c in _fn_calls("_transcribe_job") if _is_to_thread(c)]
    assert any(isinstance(c.args[0], ast.Name) and c.args[0].id == "_probe_duration" for c in calls), (
        "_transcribe_job must offload _probe_duration via asyncio.to_thread"
    )
