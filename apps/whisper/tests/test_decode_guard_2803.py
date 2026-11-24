"""AUDIT-EDGE pins for the whisper decode path.

#2803: faster-whisper's decode_audio opens media with a bare av.open — no
protocol/format whitelist — so nested resource references in a whitelisted
container became blind SSRF/local-file reads. The service must decode
through pyav_open_options() itself and hand the model PCM, never the path.

#2806: a container that opens but reports no duration (ffprobe absent or
equally silent) used to decode unbounded inside an unkillable thread,
wedging the single-slot service. Unknown duration now fails closed (415).
"""

import ast
import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as whisper_main  # noqa: E402


def test_decode_uses_media_guard_options() -> None:
    """_decode_audio_guarded must open via pyav_open_options(), not bare av.open."""
    src = Path(whisper_main.__file__).read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_decode_audio_guarded")
    seg = ast.get_source_segment(src, fn)
    assert "pyav_open_options()" in seg
    # and the model must never receive the filesystem path again
    sync_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_transcribe_sync")
    sync_seg = ast.get_source_segment(src, sync_fn)
    assert "_decode_audio_guarded" in sync_seg


def test_model_receives_decoded_audio_not_path(monkeypatch, tmp_path) -> None:
    sentinel = object()
    seen: dict = {}

    class _M:
        def transcribe(self, audio, **kw):
            seen["audio"] = audio
            return iter(()), SimpleNamespace(language="en", language_probability=1.0, duration=1.0)

    monkeypatch.setattr(whisper_main, "_decode_audio_guarded", lambda p: sentinel)
    monkeypatch.setattr(whisper_main, "_model", _M())
    f = tmp_path / "a.wav"
    f.write_bytes(b"RIFF")
    whisper_main._transcribe_sync(str(f), None, "transcribe", 5)
    assert seen["audio"] is sentinel
