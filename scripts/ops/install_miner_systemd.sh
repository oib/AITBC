#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="aitbc-miner"
APP_DIR="/opt/aitbc/apps/miner-node"
VENV_DIR="$APP_DIR/.venv"
LOG_DIR="/var/log/aitbc"
SYSTEMD_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root" >&2
  exit 1
fi

install -d "$APP_DIR" "$LOG_DIR"
install -d "/etc/aitbc"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt" || true

deactivate

install -m 644 "$(pwd)/configs/systemd/${SERVICE_NAME}.service" "$SYSTEMD_PATH"

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

echo "${SERVICE_NAME} systemd unit installed and started."
