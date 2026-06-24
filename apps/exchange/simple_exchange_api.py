#!/usr/bin/env python3
"""Deprecated entrypoint shim — delegates to simple_exchange.server.

Usage: python simple_exchange_api.py --port 8106
         python -m apps.exchange.simple_exchange.server --port 8106
"""

import sys
import warnings

warnings.warn(
    "simple_exchange_api.py is deprecated; use 'python -m apps.exchange.simple_exchange.server' instead.",
    DeprecationWarning,
    stacklevel=1,
)

if __name__ == "__main__":
    sys.path.insert(0, ".")
    from simple_exchange.server import main as _main

    _main()
