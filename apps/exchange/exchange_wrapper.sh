#!/bin/bash
# AITBC Exchange Service Wrapper Script
# This script handles the systemd service startup properly

cd /opt/aitbc
exec /usr/bin/python3 -m apps.exchange.simple_exchange.server
