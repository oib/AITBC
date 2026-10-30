#!/usr/bin/env bash
# LANE: serial
# MODE: loop
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_acquire || exit 75
# TODO: play body (serial lane — nonce-sensitive)
ok ""
