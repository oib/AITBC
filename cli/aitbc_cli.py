#!/opt/aitbc/venv/bin/python3
"""Deprecated shim — use `aitbc` (venv binary) directly."""

import os
import sys

os.execv("/opt/aitbc/venv/bin/aitbc", ["/opt/aitbc/venv/bin/aitbc"] + sys.argv[1:])
