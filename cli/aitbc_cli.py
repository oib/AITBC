#!/opt/aitbc/venv/bin/python3
"""Shim — delegates to the real AITBC CLI entrypoint."""

import os
import sys

os.execv("/opt/aitbc/venv/bin/aitbc", ["/opt/aitbc/venv/bin/aitbc"] + sys.argv[1:])
