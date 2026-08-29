#!/usr/bin/env bash
# install-system-deps.sh
# Check and (optionally) install the external system binaries AITBC callers need.
# Run on a Debian/Ubuntu node with the AITBC venv already configured.
#
# Usage:
#   /opt/aitbc/scripts/setup/install-system-deps.sh        # dry-run / check only
#   sudo /opt/aitbc/scripts/setup/install-system-deps.sh --install
#   sudo /opt/aitbc/scripts/setup/install-system-deps.sh --install --build --npm
set -euo pipefail

MODE=dry-run
INSTALL_BUILD=0
INSTALL_NPM=0

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Options:
  --install       Install missing apt packages.
  --build         Also install packages needed to build optional Python extras
                  (tenseal, fasttext, polyglot, pycuda, etc.).
  --npm           Run "npm install" in apps/zk-circuits if node_modules is stale.
  -h, --help      Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install) MODE=install; shift ;;
        --build) INSTALL_BUILD=1; shift ;;
        --npm) INSTALL_NPM=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

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

# Debian packages needed to compile optional Python extras (tenseal, fasttext,
# polyglot, pycuda, sqlcipher3-binary).
declare -a BUILD_PACKAGES=(
    build-essential
    cmake
    python3-dev
    pkg-config
    libssl-dev
    libffi-dev
    libicu-dev
)

check_binary() {
    local bin="$1"
    local pkg="$2"
    if command -v "$bin" >/dev/null 2>&1; then
        if [[ "$bin" == "node" ]]; then
            local version
            version="$(node --version 2>/dev/null || true)"
            if [[ -n "$version" && "${version#v}" < "24.14.0" ]]; then
                echo "  ⚠ $bin present but $version < 24.14.0; upgrade for apps/zk-circuits"
                return 1
            fi
        fi
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

check_build_deps() {
    local missing=()
    for pkg in "${BUILD_PACKAGES[@]}"; do
        if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
            missing+=("$pkg")
        fi
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
        echo "  ✓ Python build dependencies present"
        return 0
    fi
    echo "  ✗ Python build packages missing: ${missing[*]}"
    return 1
}

check_npm_modules() {
    local zk_dir="$1"
    if [[ ! -d "$zk_dir" ]]; then
        echo "  ⊘ $zk_dir not found, skipping Node check"
        return 0
    fi
    if [[ ! -f "$zk_dir/package.json" ]]; then
        echo "  ⊘ $zk_dir/package.json not found, skipping Node check"
        return 0
    fi
    if [[ -d "$zk_dir/node_modules" ]]; then
        echo "  ✓ node_modules present in $zk_dir"
        return 0
    fi
    echo "  ✗ node_modules missing in $zk_dir — run with --npm to install"
    return 1
}

main() {
    local missing_apt=()
    local missing_special=()
    local build_missing=0
    local npm_missing=0

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

    if [[ "$INSTALL_BUILD" -eq 1 ]]; then
        echo ""
        echo "Checking Python build dependencies..."
        if ! check_build_deps; then
            build_missing=1
            missing_apt+=("${BUILD_PACKAGES[@]}")
        fi
    fi

    local aitbc_dir
    aitbc_dir="$(cd "$(dirname "$0")/../.." && pwd)"

    if [[ "$INSTALL_NPM" -eq 1 || "$MODE" == "dry-run" ]]; then
        echo ""
        echo "Checking Node modules for ZK circuits..."
        if ! check_npm_modules "$aitbc_dir/apps/zk-circuits"; then
            npm_missing=1
        fi
    fi

    if [[ ${#missing_apt[@]} -eq 0 && ${#missing_special[@]} -eq 0 && $build_missing -eq 0 && $npm_missing -eq 0 ]]; then
        echo ""
        echo "All checked system dependencies are present."
        exit 0
    fi

    if [[ ${#missing_apt[@]} -gt 0 ]]; then
        echo ""
        echo "APT packages to install:"
        local apt_pkgs=()
        readarray -t apt_pkgs < <(printf '%s\n' "${missing_apt[@]}" | sort -u)
        printf '  %s\n' "${apt_pkgs[@]}"
    fi

    if [[ ${#missing_special[@]} -gt 0 ]]; then
        echo ""
        echo "Manual installs required:"
        printf '  %s\n' "${missing_special[@]}"
    fi

    if [[ "$MODE" == "dry-run" ]]; then
        echo ""
        echo "Dry run. Re-run with --install to install missing packages."
        exit 0
    fi

    if [[ ${#missing_apt[@]} -eq 0 ]]; then
        echo ""
        echo "No apt packages to install."
    else
        if [[ "$(id -u)" -ne 0 ]]; then
            echo "Error: --install must be run as root (or with sudo)." >&2
            exit 1
        fi

        echo ""
        echo "Installing missing apt packages..."
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        local apt_pkgs=()
        readarray -t apt_pkgs < <(printf '%s\n' "${missing_apt[@]}" | sort -u)
        apt-get install -y --no-install-recommends "${apt_pkgs[@]}"
    fi

    if [[ "$INSTALL_NPM" -eq 1 && $npm_missing -eq 1 ]]; then
        if ! command -v npm >/dev/null 2>&1; then
            echo "Error: npm is required to install ZK circuits but is not installed." >&2
            exit 1
        fi
        echo ""
        echo "Installing Node modules for ZK circuits..."
        (cd "$aitbc_dir/apps/zk-circuits" && npm install)
    fi

    echo ""
    echo "Done. Re-run the script to verify all dependencies are present."
}

main
