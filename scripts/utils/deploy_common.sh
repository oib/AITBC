#!/bin/bash

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        error "This script must be run as root (use sudo)"
    fi
}

require_command() {
    local cmd="$1"
    command -v "$cmd" >/dev/null 2>&1 || error "$cmd is not installed"
}

require_commands() {
    local missing=()
    local cmd

    for cmd in "$@"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        fi
    done

    if [ "${#missing[@]}" -gt 0 ]; then
        error "Missing required command(s): ${missing[*]}"
    fi
}

version_ge() {
    [ "$(printf '%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

require_min_version() {
    local actual="$1"
    local minimum="$2"
    local label="${3:-version}"

    if ! version_ge "$actual" "$minimum"; then
        error "${label} ${minimum}+ is required, found ${actual}"
    fi
}

# Detect if an NVIDIA GPU is present and accessible via nvidia-smi.
# Sets DETECTED_HARDWARE to "gpu" or "nogpu".
# Sets GPU_NAME and GPU_COUNT if a GPU is detected.
# Usage: detect_gpu; echo "$DETECTED_HARDWARE $GPU_NAME"
detect_gpu() {
    GPU_NAME=""
    GPU_COUNT=0
    DETECTED_HARDWARE="nogpu"
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader,nounits 2>/dev/null | head -1)
        GPU_COUNT="${GPU_COUNT:-1}"
        DETECTED_HARDWARE="gpu"
    fi
}
