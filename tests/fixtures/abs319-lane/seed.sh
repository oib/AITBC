#!/usr/bin/env bash
# ABS-319 Test-Prep fixture — lane as a first-class tracker field.
#
# Seeds an ISOLATED, throwaway tracker state (never touches work/tickets) with the
# minimum records QAS needs to exercise AC1–AC5 of ABS-319 with zero setup:
#   - one ticket created WITH  --lane fastlane   (explicit fastlane)
#   - one ticket created WITHOUT --lane          (default -> normal)
#
# Usage:
#   eval "$(tests/fixtures/abs319-lane/seed.sh)"   # exports FIX_DIR, FL_ID, NL_ID
#   # ...then run the mock adapter with MOCK_TRACKER_TICKETS_DIR="$FIX_DIR"
# or just:
#   tests/fixtures/abs319-lane/seed.sh             # prints the seeded ids + dir
#
# The script is idempotent: it wipes and re-seeds FIX_DIR on every run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ADAPTER="${MOCK_TRACKER:-$REPO_ROOT/scripts/mock-tracker.sh}"

FIX_DIR="${ABS319_FIX_DIR:-${TMPDIR:-/tmp}/abs319-lane-fixture}"
rm -rf "$FIX_DIR"; mkdir -p "$FIX_DIR"
export MOCK_TRACKER_TICKETS_DIR="$FIX_DIR"

FL_ID="$("$ADAPTER" create --type ticket --prefix DEMO \
  --title "ABS-319 fastlane fixture" --lane fastlane | grep -oE 'DEMO-[0-9]+' | head -1)"
NL_ID="$("$ADAPTER" create --type ticket --prefix DEMO \
  --title "ABS-319 normal fixture (default lane)"        | grep -oE 'DEMO-[0-9]+' | head -1)"

# Emit as eval-able exports so callers can `eval "$(seed.sh)"`.
printf 'export FIX_DIR=%q\n'  "$FIX_DIR"
printf 'export MOCK_TRACKER_TICKETS_DIR=%q\n' "$FIX_DIR"
printf 'export FL_ID=%q\n'    "$FL_ID"
printf 'export NL_ID=%q\n'    "$NL_ID"
