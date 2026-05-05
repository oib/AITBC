#!/bin/bash
# AITBC Faucet Setup Script
# Sets up a faucet mechanism from scratch for mainnet account funding
#
# DEPRECATED: This script is deprecated in favor of the Python-based setup system.
# Use: python -m aitbc.training_setup.cli setup (includes faucet setup)
# See: /opt/aitbc/docs/agent-training/ENVIRONMENT_SETUP.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AITBC_DIR="/opt/aitbc"
LOG_DIR="/var/log/aitbc/training-setup"
mkdir -p "$LOG_DIR"

# Configuration
FAUCET_PORT=8080
FAUCET_AMOUNT=1000  # AIT tokens per request
RATE_LIMIT_PER_HOUR=10  # Requests per IP per hour
FAUCET_WALLET="faucet"
FAUCET_PASSWORD="faucet-password"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    local level="$1"
    shift
    local message="$@
    local timestamp=$(date -Iseconds)
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_DIR/setup_faucet.log"
}

create_faucet_service() {
    log "INFO" "Creating faucet service..."
    
    # Create faucet service file
    cat > /etc/systemd/system/aitbc-faucet.service <<EOF
[Unit]
Description=AITBC Faucet Service
After=network.target aitbc-node.service

[Service]
Type=simple
User=root
WorkingDirectory=$AITBC_DIR
ExecStart=$AITBC_DIR/scripts/training/faucet_server.py --port $FAUCET_PORT --amount $FAUCET_AMOUNT --wallet $FAUCET_WALLET --password $FAUCET_PASSWORD
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    log "SUCCESS" "Faucet service file created"
}

create_faucet_server() {
    log "INFO" "Creating faucet server script..."
    
    mkdir -p "$AITBC_DIR/scripts/training"
    
    cat > "$AITBC_DIR/scripts/training/faucet_server.py" <<'PYEOF'
#!/usr/bin/env python3
"""
AITBC Faucet Server
Simple HTTP API for funding accounts on mainnet
"""

import argparse
import json
import subprocess
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
import threading

class RateLimiter:
    def __init__(self, max_requests_per_hour=10):
        self.requests = {}
        self.max_requests = max_requests_per_hour
        self.lock = threading.Lock()
    
    def is_allowed(self, ip):
        with self.lock:
            now = datetime.now()
            # Clean old requests
            self.requests = {
                k: [t for t in v if now - t < timedelta(hours=1)]
                for k, v in self.requests.items()
            }
            
            if ip not in self.requests:
                self.requests[ip] = []
            
            if len(self.requests[ip]) >= self.max_requests:
                return False
            
            self.requests[ip].append(now)
            return True

class FaucetHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, faucet_config=None, **kwargs):
        self.config = faucet_config
        self.rate_limiter = RateLimiter()
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
            return
        
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>AITBC Faucet</h1><p>POST to /fund with address parameter</p></body></html>")
            return
        
        self.send_response(404)
        self.end_headers()
    
    def do_POST(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/fund":
            client_ip = self.client_address[0]
            
            if not self.rate_limiter.is_allowed(client_ip):
                self.send_response(429)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Rate limit exceeded"}).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                address = data.get('address')
                if not address:
                    raise ValueError("Address required")
                
                # Fund the address
                result = self.fund_address(address)
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def fund_address(self, address):
        cmd = [
            "./aitbc-cli", "wallet", "send",
            self.config['wallet'], address,
            str(self.config['amount']),
            self.config['password']
        ]
        
        result = subprocess.run(
            cmd,
            cwd=self.config['aitbc_dir'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            raise Exception(f"Funding failed: {result.stderr}")
        
        return {
            "status": "success",
            "address": address,
            "amount": self.config['amount'],
            "transaction_id": result.stdout.strip(),
            "timestamp": datetime.now().isoformat()
        }
    
    def log_message(self, format, *args):
        pass  # Suppress default logging

def main():
    parser = argparse.ArgumentParser(description='AITBC Faucet Server')
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    parser.add_argument('--amount', type=int, default=1000, help='Amount to fund per request')
    parser.add_argument('--wallet', type=str, default='faucet', help='Faucet wallet name')
    parser.add_argument('--password', type=str, default='', help='Faucet wallet password')
    parser.add_argument('--aitbc-dir', type=str, default='/opt/aitbc', help='AITBC directory')
    
    args = parser.parse_args()
    
    config = {
        'port': args.port,
        'amount': args.amount,
        'wallet': args.wallet,
        'password': args.password,
        'aitbc_dir': args.aitbc_dir
    }
    
    def handler(*args_handler, **kwargs_handler):
        return FaucetHandler(*args_handler, faucet_config=config, **kwargs_handler)
    
    server = HTTPServer(('0.0.0.0', config['port']), handler)
    print(f"Faucet server running on port {config['port']}")
    print(f"Funding amount: {config['amount']} AIT per request")
    print(f"Rate limit: 10 requests per hour per IP")
    server.serve_forever()

if __name__ == '__main__':
    main()
PYEOF
    
    chmod +x "$AITBC_DIR/scripts/training/faucet_server.py"
    
    log "SUCCESS" "Faucet server script created"
}

setup_faucet_funding() {
    log "INFO" "Setting up faucet funding source..."
    
    cd "$AITBC_DIR"
    
    # Create faucet wallet if it doesn't exist
    if ! ./aitbc-cli wallet list | grep -q "$FAUCET_WALLET"; then
        log "INFO" "Creating faucet wallet..."
        ./aitbc-cli wallet create "$FAUCET_WALLET" "$FAUCET_PASSWORD"
    fi
    
    # Fund faucet from genesis
    log "INFO" "Funding faucet wallet from genesis..."
    ./aitbc-cli wallet send genesis "$FAUCET_WALLET" 100000 "" || log "WARN" "Faucet funding may have failed"
    
    # Verify faucet balance
    local balance
    balance=$(./aitbc-cli wallet balance "$FAUCET_WALLET" 2>&1 || echo "0")
    log "INFO" "Faucet wallet balance: $balance"
    
    log "SUCCESS" "Faucet funding source setup completed"
}

start_faucet_service() {
    log "INFO" "Starting faucet service..."
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable and start service
    systemctl enable aitbc-faucet
    systemctl start aitbc-faucet
    
    # Wait for service to start
    sleep 3
    
    # Check service status
    if systemctl is-active --quiet aitbc-faucet; then
        log "SUCCESS" "Faucet service started successfully"
    else
        log "WARN" "Faucet service may not have started correctly"
        systemctl status aitbc-faucet || true
    fi
}

test_faucet_api() {
    log "INFO" "Testing faucet API..."
    
    # Test health endpoint
    local health_result
    health_result=$(curl -s http://localhost:$FAUCET_PORT/health 2>&1 || echo "failed")
    
    if [[ "$health_result" == *"healthy"* ]]; then
        log "SUCCESS" "Faucet API health check passed"
    else
        log "WARN" "Faucet API health check failed"
    fi
}

main() {
    log "INFO" "Starting faucet setup from scratch..."
    
    create_faucet_server
    create_faucet_service
    setup_faucet_funding
    start_faucet_service
    test_faucet_api
    
    log "SUCCESS" "Faucet setup completed"
    echo ""
    echo -e "${GREEN}=== Faucet Setup Summary ===${NC}"
    echo "Faucet service: aitbc-faucet"
    echo "API endpoint: http://localhost:$FAUCET_PORT"
    echo "Funding amount: $FAUCET_AMOUNT AIT per request"
    echo "Rate limit: $RATE_LIMIT_PER_HOUR requests per hour per IP"
    echo ""
    echo "API Usage:"
    echo "  POST http://localhost:$FAUCET_PORT/fund"
    echo "  Content-Type: application/json"
    echo '  {"address": "ait1..."}'
    echo ""
    echo "Service management:"
    echo "  Start: systemctl start aitbc-faucet"
    echo "  Stop: systemctl stop aitbc-faucet"
    echo "  Status: systemctl status aitbc-faucet"
    echo "  Logs: journalctl -u aitbc-faucet -f"
}

main "$@"
