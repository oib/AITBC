#!/bin/bash
# Wrapper script for GPU miner to ensure proper logging
exec /home/oib/windsurf/aitbc/.venv/bin/python -u /home/oib/windsurf/aitbc/scripts/gpu/gpu_miner_host.py 2>&1
