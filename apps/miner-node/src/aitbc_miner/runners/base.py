from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class RunnerResult:
    ok: bool
    output: Dict[str, Any]
    artifacts: Dict[str, Path] | None = None


class BaseRunner:
    async def run(self, job: Dict[str, Any], workspace: Path) -> RunnerResult:
        raise NotImplementedError
