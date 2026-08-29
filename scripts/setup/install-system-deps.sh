#!/usr/bin/env bash
# install-system-deps.sh
# Check and (optionally) install the external system binaries AITBC callers need.
# Run on a Debian/Ubuntu node with the AITBC venv already configured.
#
# Usage:
#   /opt/aitbc/scripts/setup/install-system-deps.sh        # dry-run / check only
#   sudo /opt/aitbc/scripts/setup/install-system-deps.sh --install
set -euo pipefail

MODE=dry-run
if [[ "${1:-}" == "--install" ]]; then
    MODE=install
elif [[ -n "${1:-}" ]]; then
    echo "Unknown option: $1" >&2
    echo "Usage: $0 [--install]" >&2
    exit 1
fi

# Map callers to the Debian package that provides the binary.
# Entries with a "#special" prefix are not in default Debian repos and are
# documented instead of apt-installed.
declare -Ar BINARY_PACKAGE=(
    [ssh]=openssh-client
    [ffmpeg]=ffmpeg
    [promtool]=prometheus
    [node]=nodejs
    [npm]=npm
    [redis-server]=redis-server
    [ollama]="#special ollama: install from https://ollama.com/download/linux"
    [ipfs]="#special kubo: install from https://github.com/ipfs/kubo/releases or https://docs.ipfs.tech/install"
    [nvidia-smi]="#special nvidia-utils-XXX: install the nvidia-utils package matching your NVIDIA driver"
)

check_binary() {
    local bin="$1"
    local pkg="$2"
    if command -v "$bin" >/dev/null 2>&1; then
        echo "  ✓ $bin present"
        return 0
    fi
    if [[ "$pkg" == "#special"* ]]; then
        echo "  ✗ $bin missing — ${pkg#"#special "}"
        return 1
    fi
    echo "  ✗ $bin missing — package: $pkg"
    return 1
}

main() {
    local missing_apt=()
    local missing_special=()

    echo "Checking AITBC system dependencies..."

    for bin in "${!BINARY_PACKAGE[@]}"; do
        pkg="${BINARY_PACKAGE[$bin]}"
        if ! check_binary "$bin" "$pkg"; then
            if [[ "$pkg" == "#special"* ]]; then
                missing_special+=("$bin: ${pkg#"#special "}")
            else
                missing_apt+=("$pkg")
            fi
        fi
    done

    if [[ ${#missing_apt[@]} -eq 0 && ${#missing_special[@]} -eq 0 ]]; then
        echo ""
        echo "All checked system dependencies are present."
        exit 0
    fi

    if [[ ${#missing_apt[@]} -gt 0 ]]; then
        echo ""
        echo "APT packages to install:"
        printf '  %s\n' "${missing_apt[@]}"
    fi

    if [[ ${#missing_special[@]} -gt 0 ]]; then
        echo ""
        echo "Manual installs required:"
        printf '  %s\n' "${missing_special[@]}"
    fi

    if [[ "$MODE" == "dry-run" ]]; then
        echo ""
        echo "Dry run. Re-run with --install to apt-get install missing packages."
        exit 0
    fi

    if [[ "${#missing_apt[@]}" -eq 0 ]]; then
        echo ""
        echo "No apt packages to install."
        exit 0
    fi

    if [[ "$(id -u)" -ne 0 ]]; then
        echo "Error: --install must be run as root (or with sudo)." >&2
        exit 1
    fi

    echo ""
    echo "Installing missing apt packages..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends "${missing_apt[@]}"

    echo ""
    echo "Done. Re-run the script to verify all binaries are present."
}

main
