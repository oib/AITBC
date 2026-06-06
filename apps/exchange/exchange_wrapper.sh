#!/bin/bash
# AITBC Exchange Service Wrapper Script
# This script handles the systemd service startup properly

cd /opt/aitbc/apps/exchange
exec /usr/bin/python3 simple_exchange_api.py
