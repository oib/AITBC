#!/usr/bin/env bash
# LANE: parallel
# MODE: parallel
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75
# TODO: play body
ok ""
