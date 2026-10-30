#!/usr/bin/env bash
# LANE: once
# MODE: loop
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75
# TODO: play body
ok ""
