#!/bin/bash
# AITBC User Detection Script
# Returns the appropriate user to run AITBC services

if id "aitbc" >/dev/null 2>&1; then
    echo "aitbc"
elif id "oib" >/dev/null 2>&1; then
    echo "oib"
else
    echo "root"
fi
