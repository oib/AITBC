#!/bin/bash
cd /opt/aitbc/apps/coordinator-api
export PATH=/opt/aitbc/apps/coordinator-api/.venv/bin
export PYTHONPATH=/opt/aitbc/apps/coordinator-api/src
export MINER_API_KEYS='["miner_test_abc123"]'
exec /opt/aitbc/apps/coordinator-api/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
