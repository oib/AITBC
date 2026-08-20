#!/usr/bin/env python3
"""Make `aitbc_cli` runnable with `python -m aitbc_cli`."""

from aitbc_cli.core.main import main

if __name__ == "__main__":
    raise SystemExit(main())
