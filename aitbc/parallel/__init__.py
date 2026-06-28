"""
Parallel processing utilities for AITBC.

Provides dependency graph analysis and a parallel executor for
parallel transaction validation in the blockchain node.
"""

from .dependency_graph import DependencyGraph
from .executor import ParallelExecutor

__all__ = ["DependencyGraph", "ParallelExecutor"]
