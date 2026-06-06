"""
AITBC Whisper Transcription Service
Minimal FastAPI service wrapping faster-whisper for the software marketplace.
Port: 8210
"""

import hashlib
import os
import tempfile
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

_model = None
_model_name = os.getenv("WHISPER_MODEL", "base")
_device = os.getenv("WHISPER_DEVICE", "cuda")
_compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "float16")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    from faster_whisper import WhisperModel
    print(f"Loading Whisper model '{_model_name}' on {_device} ({_compute_type})...")
    _model = WhisperModel(_model_name, device=_device, compute_type=_compute_type)
    print(f"Whisper model ready.")
    yield
    _model = None


app = FastAPI(title="AITBC Whisper Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": _model_name,
        "device": _device,
        "ready": _model is not None,
    }


@app.get("/models")
async def list_models():
    return {
        "models": [
            {"name": "tiny",   "params": "39M",   "vram_gb": 1},
            {"name": "base",   "params": "74M",   "vram_gb": 1},
            {"name": "small",  "params": "244M",  "vram_gb": 2},
            {"name": "medium", "params": "769M",  "vram_gb": 5},
            {"name": "large",  "params": "1550M", "vram_gb": 10},
            {"name": "turbo",  "params": "809M",  "vram_gb": 6},
        ],
        "loaded": _model_name,
    }


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    task: str = Form(default="transcribe"),
    beam_size: int = Form(default=5),
):
    """Transcribe audio file. Returns transcript, duration, language, and segments."""
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        t_start = time.time()
        segments, info = _model.transcribe(
            tmp_path,
            beam_size=beam_size,
            language=language,
            task=task,
        )
        segment_list = []
        full_text = []
        for seg in segments:
            segment_list.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            })
            full_text.append(seg.text.strip())

        elapsed = round(time.time() - t_start, 2)
        duration = round(info.duration, 2)
        transcript = " ".join(full_text)
        result_hash = hashlib.sha256(transcript.encode()).hexdigest()

        return JSONResponse({
            "text": transcript,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration_seconds": duration,
            "duration_minutes": round(duration / 60, 4),
            "segments": segment_list,
            "model": _model_name,
            "elapsed_seconds": elapsed,
            "real_time_factor": round(elapsed / duration, 3) if duration > 0 else 0,
            "result_hash": result_hash,
        })
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    port = int(os.getenv("WHISPER_PORT", "8110"))
    uvicorn.run(app, host="0.0.0.0", port=port)
