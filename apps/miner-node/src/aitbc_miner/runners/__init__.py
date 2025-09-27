from __future__ import annotations

from typing import Dict

from .base import BaseRunner
from .cli.simple import CLIRunner
from .python.noop import PythonNoopRunner


_RUNNERS: Dict[str, BaseRunner] = {
    "cli": CLIRunner(),
    "python": PythonNoopRunner(),
    "noop": PythonNoopRunner(),
}


def get_runner(kind: str) -> BaseRunner:
    return _RUNNERS.get(kind, _RUNNERS["noop"])
