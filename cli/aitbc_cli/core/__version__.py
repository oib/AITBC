"""AITBC CLI Version Information

Compatibility shim: the canonical literal lives in aitbc_cli/__init__.py;
this re-export keeps aitbc_cli.core.__version__ working for existing callers.
"""

from aitbc_cli import __version__  # noqa: F401
