from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict

from ..base import BaseRunner, RunnerResult


class PythonNoopRunner(BaseRunner):
    async def run(self, job: Dict[str, Any], workspace: Path) -> RunnerResult:
        await asyncio.sleep(0)
        payload = job.get("payload", {})
        return RunnerResult(
            ok=True,
            output={
                "echo": payload,
                "message": "python noop runner executed",
            },
        )
