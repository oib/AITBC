"""Minimal example agent for AITBC builders (v0.16.1 §B4)."""

from __future__ import annotations

import time


def run_agent(name: str = "hello-agent") -> dict[str, str]:
    """Run a trivial agent and return a greeting."""
    time.sleep(0.01)
    return {"agent": name, "status": "ok", "message": "Hello from AITBC!"}


if __name__ == "__main__":
    print(run_agent())
