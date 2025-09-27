from __future__ import annotations

from pathlib import Path


def ensure_workspace(root: Path, job_id: str) -> Path:
    path = root / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: dict) -> None:
    import json

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
