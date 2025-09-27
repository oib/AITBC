from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseRunner, RunnerResult


class CLIRunner(BaseRunner):
    async def run(self, job: Dict[str, Any], workspace: Path) -> RunnerResult:
        runner_cfg = job.get("runner", {})
        command: List[str] = runner_cfg.get("command", [])
        if not command:
            return RunnerResult(
                ok=False,
                output={
                    "error_code": "INVALID_COMMAND",
                    "error_message": "runner.command is required for CLI jobs",
                    "metrics": {},
                },
            )

        stdout_path = workspace / "stdout.log"
        stderr_path = workspace / "stderr.log"

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await process.communicate()
        stdout_path.write_bytes(stdout_bytes)
        stderr_path.write_bytes(stderr_bytes)

        if process.returncode == 0:
            return RunnerResult(
                ok=True,
                output={
                    "exit_code": 0,
                    "stdout": stdout_path.name,
                    "stderr": stderr_path.name,
                },
                artifacts={
                    "stdout": stdout_path,
                    "stderr": stderr_path,
                },
            )

        return RunnerResult(
            ok=False,
            output={
                "error_code": "PROCESS_FAILED",
                "error_message": f"command exited with code {process.returncode}",
                "metrics": {
                    "exit_code": process.returncode,
                    "stderr": stderr_path.name,
                },
            },
        )
